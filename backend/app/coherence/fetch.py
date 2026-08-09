"""Fetch ~100 papers per candidate domain from OpenAlex, then compute
coherence features. Every call is a `filter=` list endpoint (1 credit
each), and results are cached under data/coherence/{slug}/, so runs
after the first are free.

Budget: 8 domains × 1 filter call each = 8 credits (~0.008% of the free
daily quota of 100,000). Zero spend.

Usage:
    python -m backend.app.coherence.fetch --all      # fetch + features
    python -m backend.app.coherence.fetch --features # features only from cache

The list of candidate domains and the filter for each lives in
`DOMAINS` below and is the honest input to the study — changing it
changes the results, so it's committed with a comment about why each
was chosen.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from backend.app.coherence import features as F
from backend.app.config import get_settings

REPO = Path(__file__).resolve().parents[3]
CACHE = REPO / "data" / "coherence"
OA_BASE = "https://api.openalex.org"


# --------------------------------------------------------------------------
# The candidate domains. Selection is the honest input to the study.
#
# Each is defined by an OpenAlex `filter=` string. All use `filter=`
# rather than `search=` for the 10× credit discount. Papers are ranked
# by citation count and capped at 100 to keep the graphs comparable in
# size — one credit per fetch either way.
#
# The set is chosen for RANGE, not statistical representativeness:
#   - two we already have ground truth for (our own domain, present
#     twice — cached and freshly-fetched — as a sanity check)
#   - fields reputed to be contested (empirical software engineering,
#     nutrition science's "diet-and-mortality" strand)
#   - fields reputed to be consolidated (protein structure prediction,
#     transformer architectures, formal methods for concurrency)
#   - interdisciplinary sweeps (fairness-in-ML)
#
# All filter strings restrict to peer-reviewed or preprint articles,
# publication years since 2015, and use `primary_topic.id` where a
# well-defined topic exists. See docs/findings/domain-coherence-
# predictor.md for the reasoning per domain.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainSpec:
    slug: str
    name: str
    filt: str
    per_page: int = 100
    reputation: str = ""  # "contested" / "consolidated" / "unknown"
    note: str = ""


DOMAINS: list[DomainSpec] = [
    DomainSpec(
        slug="llm-calibration",
        name="LLM calibration / hallucination / uncertainty",
        filt=("title_and_abstract.search:(\"language model\" OR \"LLM\" OR "
              "\"large language model\") AND (calibration OR hallucination "
              "OR \"uncertainty quantification\" OR abstention),"
              "type:article|preprint,publication_year:>2018"),
        reputation="measured",
        note=("The ONE ground-truth domain: measured 0 confirmed "
              "contradictions on 113 papers, some structural-hole "
              "leads."),
    ),
    DomainSpec(
        slug="protein-structure-prediction",
        name="Protein structure prediction (post-AlphaFold)",
        filt=("title_and_abstract.search:(\"protein structure\" OR "
              "\"AlphaFold\" OR \"protein folding\"),"
              "type:article|preprint,publication_year:>2020"),
        reputation="consolidated",
        note=("AlphaFold consolidated the field around one dominant "
              "approach; expect low contestedness."),
    ),
    DomainSpec(
        slug="empirical-software-engineering",
        name="Empirical software engineering (bug prediction)",
        filt=("title_and_abstract.search:(\"defect prediction\" OR "
              "\"bug prediction\" OR \"fault prediction\") AND (empirical "
              "OR replication OR reproducibility),"
              "type:article|preprint,publication_year:>2015"),
        reputation="contested",
        note=("Persistent methodological arguments about metrics, "
              "datasets, external validity; classic disputed field."),
    ),
    DomainSpec(
        slug="ml-fairness",
        name="Fairness in machine learning",
        filt=("title_and_abstract.search:(\"algorithmic fairness\" OR "
              "\"machine learning fairness\" OR \"fair classification\"),"
              "type:article|preprint,publication_year:>2018"),
        reputation="contested",
        note=("Definitions of fairness proven mutually incompatible; "
              "should score as contested."),
    ),
    DomainSpec(
        slug="diet-and-mortality",
        name="Diet composition and all-cause mortality",
        filt=("title_and_abstract.search:(\"all-cause mortality\") AND "
              "(diet OR \"dietary pattern\" OR nutrition),"
              "type:article|preprint,publication_year:>2015"),
        reputation="contested",
        note=("Notorious for meta-analyses reaching opposite "
              "conclusions on the same food group."),
    ),
    DomainSpec(
        slug="formal-methods-concurrency",
        name="Formal verification of concurrent systems",
        filt=("title_and_abstract.search:(\"model checking\" OR "
              "\"linearizability\" OR \"weak memory\") AND "
              "(concurrent OR concurrency),"
              "type:article|preprint,publication_year:>2015"),
        reputation="consolidated",
        note=("Small, tight community; established theoretical "
              "foundations; expect low contestedness, low churn."),
    ),
    DomainSpec(
        slug="transformer-attention",
        name="Transformer attention mechanisms",
        filt=("title_and_abstract.search:(\"self-attention\" OR "
              "\"transformer attention\" OR \"attention mechanism\") "
              "AND (\"language model\" OR sequence),"
              "type:article|preprint,publication_year:>2018"),
        reputation="consolidated",
        note=("Vaswani et al. established the canon; most work extends "
              "rather than argues."),
    ),
    DomainSpec(
        slug="microplastics-health",
        name="Microplastics and human health",
        filt=("title_and_abstract.search:(microplastic OR nanoplastic) AND "
              "(human OR health OR exposure OR toxic),"
              "type:article|preprint,publication_year:>2018"),
        reputation="contested",
        note=("Rapidly emerging field, methodological arguments about "
              "detection and dose-response; expect moderate-high "
              "contestedness."),
    ),
    DomainSpec(
        slug="deep-rl-continuous-control",
        name="Deep RL for continuous control",
        filt=("title_and_abstract.search:(\"deep reinforcement learning\" "
              "OR \"deep RL\") AND (\"continuous control\" OR robotic OR "
              "locomotion OR MuJoCo),"
              "type:article|preprint,publication_year:>2016"),
        reputation="contested",
        note=("Well-known irreproducibility crisis for RL benchmarks; "
              "expect contestedness."),
    ),
]


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------

def _api_key() -> str:
    key = get_settings().openalex_api_key
    if not key:
        sys.exit(
            "OPENALEX_API_KEY is required. Get one free at "
            "https://openalex.org/settings/api and put it in .env.\n"
            "Free quota: 100,000 credits/day. This tool needs 8."
        )
    return key.get_secret_value()


def fetch_domain(spec: DomainSpec, *, force: bool = False) -> dict[str, Any]:
    """Fetch a domain's records and cache them.

    Returns the on-disk payload (either freshly fetched or cached).
    Uses `filter=` (1 credit) and captures OpenAlex's rate-limit
    headers so the ledger stays honest."""
    out_dir = CACHE / spec.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "openalex.json"

    if raw_path.exists() and not force:
        return json.loads(raw_path.read_text())

    params = {
        "filter": spec.filt,
        "per-page": spec.per_page,
        "sort": "cited_by_count:desc",
        "select": (
            "id,doi,display_name,publication_year,type,"
            "primary_location,referenced_works,cited_by_count"
        ),
        "api_key": _api_key(),
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.get(f"{OA_BASE}/works", params=params)
        r.raise_for_status()
        payload = r.json()
        credit_headers = {
            "credits_used": r.headers.get("X-RateLimit-Credits-Used"),
            "limit": r.headers.get("X-RateLimit-Limit"),
            "remaining": r.headers.get("X-RateLimit-Remaining"),
        }

    out = {
        "spec": {
            "slug": spec.slug,
            "name": spec.name,
            "filter": spec.filt,
            "per_page": spec.per_page,
            "reputation": spec.reputation,
            "note": spec.note,
        },
        "credit_headers": credit_headers,
        "meta": payload.get("meta", {}),
        "results": payload.get("results", []),
    }
    raw_path.write_text(json.dumps(out, indent=2))
    return out


def features_for(spec: DomainSpec) -> dict[str, Any]:
    """Load the cached fetch and compute the feature vector + verdict."""
    payload = fetch_domain(spec)
    records = payload.get("results", [])
    feats = F.features(records)
    return {
        "slug": spec.slug,
        "name": spec.name,
        "reputation": spec.reputation,
        "note": spec.note,
        "n_matching_in_openalex": payload.get("meta", {}).get("count"),
        "features": feats,
        "verdict": F.verdict(feats),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--all", action="store_true",
                   help="fetch missing domains, then compute features")
    p.add_argument("--fetch", action="store_true",
                   help="fetch only; don't compute features")
    p.add_argument("--force", action="store_true",
                   help="re-fetch even if cached")
    p.add_argument("--out", type=Path, default=CACHE / "features.json",
                   help="where to write the feature table")
    args = p.parse_args()

    if args.all or args.fetch:
        for spec in DOMAINS:
            print(f"→ {spec.slug:35}", end=" ")
            payload = fetch_domain(spec, force=args.force)
            n = len(payload.get("results", []))
            credits = payload.get("credit_headers", {}).get("credits_used")
            print(f"cached: {n} papers  (this fetch: {credits} credits)")

    if args.all or not args.fetch:
        rows = [features_for(s) for s in DOMAINS]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\nfeatures written → {args.out.relative_to(REPO)}\n")

        _print_table(rows)
    return 0


def _print_table(rows: list[dict]) -> None:
    """Compact human-readable print of the feature table."""
    cols = [
        ("slug", 32),
        ("N", 4),
        ("intra", 6),
        ("recip", 6),
        ("mod", 6),
        ("rev", 5),
        ("churn", 6),
        ("HHI", 6),
        ("spread", 7),
        ("ct-scr", 6),
        ("mt-scr", 6),
        ("reputation", 14),
    ]
    header = "  ".join(name.ljust(w) for name, w in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        f = r["features"]
        v = r["verdict"]
        vals = [
            r["slug"][:32],
            str(f["n_papers"]),
            f'{f["intracorpus_reference_rate"]:.3f}',
            f'{f["citation_reciprocity"]:.3f}',
            f'{f["citation_modularity"]:.3f}',
            f'{f["review_ratio"]:.2f}',
            f'{f["temporal_churn"]:.3f}',
            f'{f["venue_concentration"]:.3f}',
            f'{f["term_vector_spread"]:.3f}',
            f'{v["contested_score"]:.3f}',
            f'{v["method_transfer_score"]:.3f}',
            r["reputation"],
        ]
        print("  ".join(str(v).ljust(w) for (_, w), v in zip(cols, vals)))


if __name__ == "__main__":
    raise SystemExit(main())
