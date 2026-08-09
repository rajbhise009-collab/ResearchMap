"""Live pre-flight predictor for the "Build a library" button.

Given a plain-English query, hit OpenAlex free `filter=` list endpoint
for the top ~50 citation-weighted papers, run the features + verdict
from `.features`, and hand back BOTH a plain-language summary (safe to
show any consumer) and the raw feature vector (dev-mode only).

Aggressive on-disk caching: repeated queries for the same term don't
re-hit OpenAlex at all. First call ~10 credits (~0.01% of free daily
quota); subsequent calls free.

Zero cost. No LLM, no embedding, no extraction.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from backend.app.coherence import features as F
from backend.app.config import get_settings

REPO = Path(__file__).resolve().parents[3]
CACHE_DIR = REPO / "data" / "coherence" / "queries"
OA_BASE = "https://api.openalex.org"

# Preflight is deliberately smaller than the offline study — a public
# visitor's live query shouldn't burn 10+ credits per keystroke of retry.
DEFAULT_PER_PAGE = 50
DEFAULT_MIN_YEAR = 2018


def _slugify(q: str) -> str:
    """Stable cache key from a raw query. Case-fold and collapse
    whitespace so trivial variants share a cache entry, and hash-suffix
    the result so we never conflict on similar terms."""
    normal = re.sub(r"\s+", " ", q.strip().lower())
    hashsuf = hashlib.sha256(normal.encode()).hexdigest()[:10]
    safe = re.sub(r"[^a-z0-9]+", "-", normal)[:60].strip("-")
    return f"{safe}--{hashsuf}"


def _build_filter(query: str, min_year: int) -> str:
    """OpenAlex filter for the top papers matching `query`. We use
    `title_and_abstract.search:"…"` inside a `filter=` so we get the
    1-credit tier rather than the 10-credit `search=` tier. Escape any
    quote characters in the user query."""
    safe = query.replace('"', "").strip()
    return (
        f'title_and_abstract.search:"{safe}",'
        f'type:article|preprint,'
        f'publication_year:>{min_year}'
    )


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------

@dataclass
class PreflightResult:
    query: str
    slug: str
    n_openalex_matches: int
    n_sampled: int
    features: dict[str, Any]
    verdict: dict[str, Any]
    consumer_summary: dict[str, Any]
    dev_details: dict[str, Any] = field(default_factory=dict)


def _cache_path(slug: str) -> Path:
    return CACHE_DIR / f"{slug}.json"


def _try_relative(p: Path) -> Path:
    """Show cache path relative to the repo when possible; absolute
    otherwise. Tests point CACHE_DIR at a tempdir outside the repo, so
    `.relative_to` would raise."""
    try:
        return p.relative_to(REPO)
    except ValueError:
        return p


def _fetch(query: str, *, per_page: int, min_year: int) -> dict:
    settings = get_settings()
    api_key = settings.openalex_api_key
    if not api_key:
        raise RuntimeError(
            "OPENALEX_API_KEY not configured. The pre-flight needs it "
            "to fetch metadata (free under 100k credits/day)."
        )
    params = {
        "filter": _build_filter(query, min_year),
        "per-page": per_page,
        "sort": "cited_by_count:desc",
        "select": ("id,doi,display_name,publication_year,type,"
                   "primary_location,referenced_works,cited_by_count"),
        "api_key": api_key.get_secret_value(),
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{OA_BASE}/works", params=params)
        r.raise_for_status()
        payload = r.json()
        credit_headers = {
            "credits_used": r.headers.get("X-RateLimit-Credits-Used"),
            "remaining": r.headers.get("X-RateLimit-Remaining"),
        }
    return {
        "query": query,
        "credit_headers": credit_headers,
        "meta": payload.get("meta", {}),
        "results": payload.get("results", []),
    }


# --------------------------------------------------------------------------
# Cost projection using the corrected pricing from the scaling finding
# --------------------------------------------------------------------------

def _estimate_build_cost(n_openalex_matches: int) -> dict[str, Any]:
    """Cost + time to build a new library on this subject, using our
    scaling-study-corrected pricing.

    Sizing rule: we'd build to N ≈ min(matches, 200) — enough for the
    reasoning engine to have signal (per the fulltext-vs-abstract
    finding: at 2.19 own-work limitations/paper, ~200 papers gives
    ~440 items, adequate for cross-paper recurrence). Larger than 200
    starts to hit diminishing returns per the scaling study.
    """
    target_n = min(max(50, n_openalex_matches), 200) if n_openalex_matches else 100
    # Same coefficients as scaling_tool.project_cost, kept local so this
    # module can be sourced by the API without importing the whole tool.
    ft_ratio = 0.55  # measured on our own corpus; assumed portable
    n_ft = round(target_n * ft_ratio)
    n_ab = target_n - n_ft
    extraction = round(n_ft * 0.0336 + n_ab * 0.0109, 2)
    # A rough estimate: pair candidates scale ~ N^1.77 on our corpus,
    # so at N=200 → ~700 pairs → ~$1.40.
    est_pairs = int(round(256 * (target_n / 113) ** 1.77))
    contra = round(est_pairs * 0.00199, 2)
    total = round(extraction + contra + 0.15, 2)
    return {
        "target_papers": target_n,
        "est_extraction_usd": extraction,
        "est_pair_classification_usd": contra,
        "est_total_usd": total,
        "est_hours": _hours_for(target_n),
    }


def _hours_for(n: int) -> str:
    """Rough wall-clock estimate — batch extraction is the slow path."""
    # Batch API ~200 papers/hour for full-text; ingestion + snowball ~1h.
    if n <= 100: return "2-3 hours"
    if n <= 200: return "3-5 hours"
    return "5-8 hours"


# --------------------------------------------------------------------------
# Plain-language render
# --------------------------------------------------------------------------

def _consumer_summary(query: str, records: list[dict], n_openalex: int | None,
                      feats: dict, verd: dict, cost: dict) -> dict[str, Any]:
    """Plain-language description consistent with the translation
    layer. No numeric internals other than paper counts and dollars —
    the reader isn't expected to interpret "contested_score = 0.68"."""
    n = len(records)
    n_match = n_openalex

    if n == 0:
        return {
            "headline": f"OpenAlex has almost no work indexed on “{query}”",
            "coverage_line": (
                "We looked for papers on this in OpenAlex — the world's "
                "largest open academic index — and found essentially "
                "nothing to build on. This may be a very new area, an "
                "obscure spelling, or a phrase that doesn't map to how "
                "researchers write about it."
            ),
            "diagnostic_line": (
                "Not enough literature to say anything about whether the "
                "reasoning engine would find signal here."
            ),
            "diagnostic_confidence": "n/a",
            "estimate_headline": (
                "Not enough material in the world to build a useful "
                "library on this yet."
            ),
        }

    coverage = _coverage_language(n, n_match)
    diagnostic, diag_conf = _diagnostic_language(verd)
    est_head = (
        f"Building a library on this would cost roughly "
        f"${cost['est_total_usd']:.0f} in AI-model spend and take about "
        f"{cost['est_hours']}, working from ~{cost['target_papers']} papers."
    )

    return {
        "headline": f"About “{query}” in the academic literature",
        "coverage_line": coverage,
        "diagnostic_line": diagnostic,
        "diagnostic_confidence": diag_conf,
        "estimate_headline": est_head,
    }


def _openalex_estimate(records: list[dict]) -> int | None:
    """Prefer the OpenAlex meta.count if present in cache; otherwise
    fall back to the number of records fetched as a floor."""
    # Meta count is threaded through cached_or_fetch's payload; this
    # function accepts records for compatibility, and the caller sends
    # the meta count separately.
    return None


def _coverage_language(n_sampled: int, n_matches: int | None) -> str:
    if n_matches is None:
        return (
            f"We looked at the top {n_sampled} most-cited papers on this "
            "subject in OpenAlex."
        )
    if n_matches < 20:
        return (
            f"OpenAlex indexes about {n_matches} papers on this subject "
            "in total — very sparse."
        )
    if n_matches < 100:
        return (
            f"OpenAlex indexes about {n_matches} papers on this subject. "
            "That's a small but real body of work."
        )
    if n_matches < 500:
        return (
            f"OpenAlex indexes about {n_matches} papers on this subject. "
            "We looked at the top " f"{n_sampled} of them by citation count."
        )
    return (
        f"OpenAlex indexes {n_matches:,} papers on this subject. "
        f"We looked at the top {n_sampled} of them by citation count "
        "for this pre-flight check."
    )


def _diagnostic_language(verd: dict) -> tuple[str, str]:
    """Turn the two composite scores into a plain-English band. Always
    ends by naming the hypothesis-not-guarantee caveat — the diagnostic
    IS the finding, and the finding says it hasn't been validated."""
    ct = verd["contested_score"]
    mt = verd["method_transfer_score"]
    ct_band = verd["contested_band"]
    mt_band = verd["method_transfer_band"]

    # Verbal read for the two axes. Deliberately non-quantitative.
    if ct_band == "high":
        contested_read = (
            "The way papers on this topic cite each other, and the "
            "frequency of surveys and reviews, look consistent with a "
            "contested field — one where researchers disagree enough for "
            "an LBD engine to potentially find those disagreements."
        )
    elif ct_band == "moderate":
        contested_read = (
            "The signal for whether the field is contested is mixed. "
            "Some indicators point that way (reviews, citation patterns) "
            "and some don't."
        )
    else:
        contested_read = (
            "This looks like a consolidated field where researchers "
            "largely agree with each other — few surveys, dominant venue, "
            "clean citation structure. That's exactly the pattern where "
            "contradiction-based discovery finds nothing (this is what "
            "we measured on our own domain)."
        )

    if mt_band == "high":
        transfer_read = (
            "Distinct schools of thought are visible in the citation "
            "graph, so method-transfer leads (a method from one strand "
            "applied to an open problem in another) are more likely."
        )
    else:
        transfer_read = (
            "The citation graph doesn't show cleanly separated schools, "
            "so method-transfer leads (a method from one strand applied "
            "to another's problem) would be harder to find."
        )

    diag = (
        f"{contested_read} {transfer_read} "
        "This is our best guess from cheap metadata alone; it is a "
        "hypothesis we haven't validated (see the domain-coherence "
        "predictor finding), not a guarantee."
    )
    conf = "hypothesis-only"
    return diag, conf


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def preflight(query: str, *, per_page: int = DEFAULT_PER_PAGE,
              min_year: int = DEFAULT_MIN_YEAR,
              force_refresh: bool = False) -> PreflightResult:
    """One-shot preflight for a query. Cache-hit on repeat calls."""
    slug = _slugify(query)
    cache_path = _cache_path(slug)
    if cache_path.exists() and not force_refresh:
        cached = json.loads(cache_path.read_text())
    else:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached = _fetch(query, per_page=per_page, min_year=min_year)
        cache_path.write_text(json.dumps(cached, indent=2))

    records = cached.get("results", [])
    n_match = (cached.get("meta") or {}).get("count") or len(records)
    feats = F.features(records)
    verd = F.verdict(feats)
    cost = _estimate_build_cost(n_match)
    summary = _consumer_summary(query, records, n_match, feats, verd, cost)

    return PreflightResult(
        query=query,
        slug=slug,
        n_openalex_matches=n_match,
        n_sampled=len(records),
        features=feats,
        verdict=verd,
        consumer_summary=summary,
        dev_details={
            "cost_projection": cost,
            "credit_headers": cached.get("credit_headers"),
            "openalex_filter": _build_filter(query, min_year),
            "cache_path": str(_try_relative(cache_path)),
            "top_paper_titles": [
                r.get("display_name") for r in records[:5]
            ],
        },
    )
