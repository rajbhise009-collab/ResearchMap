"""Multi-library snapshot exporter.

Extends the LLM-cal-only exporter (backend/app/api/export.py) to produce
per-library subdirectories under `frontend/public/data/library/<slug>/`
plus a top-level `libraries.json` manifest the frontend uses for the
selector.

For each library:
  - meta.json, papers.json, opportunities.json, stats.json,
    search-index.json, language.json, plus per-paper and per-opportunity
    directories.

The LLM-cal library keeps writing to the ROOT `frontend/public/data/`
too, for backward compatibility with any deployed URL that already
points there — the multi-library selector treats it as the default.

Usage:
    python -m backend.app.api.multi_library_export
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.api import export as llm_cal_export  # noqa: E402


DEFAULT_ROOT = REPO_ROOT / "frontend" / "public" / "data"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


# ---- Library manifests ---------------------------------------------------
# The one place that lists all three libraries. If a fourth is added, the
# manifest grows here and the frontend selector picks it up automatically.

LLM_CAL_MANIFEST = {
    "slug": "llm-calibration",
    "name": "Language-model reliability",
    "short_name": "LLM calibration",
    "blurb": ("How language models express confidence, when they should "
              "refuse to answer, how their uncertainty is measured, "
              "and why they state false things as fact."),
    "n_papers": 113,
    "is_default": True,
    "not_advice_note": None,
}

DIET_MANIFEST = {
    "slug": "diet-and-mortality",
    "name": "Diet and all-cause mortality",
    "short_name": "Diet & mortality",
    "blurb": ("What the epidemiology and clinical-trial literature says "
              "about diet — food groups, dietary patterns, and specific "
              "regimes — and mortality-related outcomes."),
    "n_papers": 100,
    "is_default": False,
    # Raj-required disclaimer for a biomedical library.
    "not_advice_note": (
        "Research-literature analysis, not dietary or medical advice. "
        "The papers behind these results contradict each other on some "
        "of the most common questions (red meat, saturated fat, alcohol, "
        "low-carb). Take medical decisions to a clinician who knows you."
    ),
}

FAIRNESS_MANIFEST = {
    "slug": "ml-fairness",
    "name": "Algorithmic fairness in machine learning",
    "short_name": "ML fairness",
    "blurb": ("Definitions and metrics for fair machine-learning "
              "classifiers, incompatibility results between them, "
              "bias-mitigation methods, and audits of deployed systems."),
    "n_papers": 100,
    "is_default": False,
    "not_advice_note": None,
}


LIBRARIES = [LLM_CAL_MANIFEST, DIET_MANIFEST, FAIRNESS_MANIFEST]


# ---- Per-library snapshot writer -----------------------------------------

def write_llm_calibration_snapshot(out_root: Path) -> dict:
    """Reuse the existing LLM-cal exporter into a per-library subdir.
    Also keeps the root snapshot up-to-date so the current frontend keeps
    working during the multi-library transition."""
    # 1. Existing root path (unchanged behaviour)
    llm_cal_export.export(out_root)
    # 2. Per-library copy
    lib_dir = out_root / "library" / "llm-calibration"
    llm_cal_export.export(lib_dir)
    return {"slug": "llm-calibration", "root_and_library_dir": True}


def write_multi_domain_snapshot(slug: str, out_root: Path) -> dict:
    """Write a domain's snapshot under out_root/library/<slug>/. Reads
    from data/domains/<slug>/ prelabel + extractions + reasoning.

    Emits the same file set as the LLM-cal snapshot so the frontend can
    read from any library with one code path:
      meta.json, papers.json, stats.json, search-index.json,
      language.json, findings.json, relationships.json, opportunities.json
      + paper/{wid}.json per paper (with extraction embedded)
      + opportunity/{slug}.json per confirmed contradiction (as a
        contradiction-typed gap card).
    """
    from backend.app.corpus.multi_domain import _prelabel_path
    from backend.app.corpus.multi_domain_reason import (
        DOMAINS,   # aliased to accept full or short slug
        assertion_strength_distribution,
        gap_type_counts,
        load_extractions,
    )
    from backend.app.api import language as lang_mod

    if slug not in DOMAINS:
        raise KeyError(slug)

    lib_dir = out_root / "library" / slug
    lib_dir.mkdir(parents=True, exist_ok=True)

    prelabel = json.loads(_prelabel_path(DOMAINS[slug]).read_text())
    entries = prelabel["entries"]
    exts = load_extractions(slug)
    ext_by_pid = {e.paper_id: e for e in exts}

    # meta.json
    (lib_dir / "meta.json").write_text(json.dumps({
        "slug": slug,
        "schema_version": "1.0.0",
        "n_papers": len(entries),
    }, indent=2))

    # papers.json (summary list)
    papers = [
        {
            "paper_id": e.get("openalex_id") or f"openalex:{e['wid']}",
            "wid": e["wid"],
            "title": e.get("title"),
            "year": e.get("year"),
            "doi": e.get("doi"),
            "venue": e.get("venue"),
            "domain_centrality": e.get("domain_centrality"),
            "input_source": e.get("input_source"),
            "abstract_only": e.get("input_source") != "fulltext",
        }
        for e in entries
    ]
    (lib_dir / "papers.json").write_text(json.dumps(
        {"total": len(papers), "items": papers}, indent=2))

    # per-paper detail: paper/{wid}.json with full extraction embedded
    paper_dir = lib_dir / "paper"
    paper_dir.mkdir(exist_ok=True)
    for e in entries:
        pid = f"openalex:{e['wid']}"
        ext = ext_by_pid.get(pid)
        detail = {
            "paper_id": pid, "wid": e["wid"],
            "title": e.get("title"), "year": e.get("year"),
            "doi": e.get("doi"), "venue": e.get("venue"),
            "domain_centrality": e.get("domain_centrality"),
            "input_source": e.get("input_source"),
            "abstract_only": e.get("input_source") != "fulltext",
            "abstract": e.get("abstract"),
            "claims": [c.model_dump() for c in (ext.claims or [])] if ext else [],
            "limitations": [l.model_dump() for l in (ext.limitations or [])] if ext else [],
            "future_work": [f.model_dump() for f in (ext.future_work or [])] if ext else [],
            "methodologies": [m.model_dump() for m in (ext.methodologies or [])] if ext else [],
            "cites": [], "cited_by": [],
            "consumer": lang_mod.consumer_paper({
                "abstract_only": e.get("input_source") != "fulltext",
            }),
        }
        (paper_dir / f"{e['wid']}.json").write_text(json.dumps(detail))

    # opportunities.json + per-opportunity detail (from confirmed
    # contradictions since that's the only scoring output we have for
    # the multi-domain libraries in this run).
    contra_path = REPO_ROOT / "data" / "domains" / slug / "reasoning" / "contradictions.json"
    contradictions = []
    if contra_path.exists():
        contradictions = json.loads(contra_path.read_text()).get("items", [])
    opp_dir = lib_dir / "opportunity"
    opp_dir.mkdir(exist_ok=True)
    opportunity_summaries = []
    for i, c in enumerate(contradictions, 1):
        opp_slug = (f"opp-contra-{slug}-{i:02d}-"
                    f"{_slug(c['a_paper_id'])}-{_slug(c['b_paper_id'])}")[:120]
        card = {
            "id": opp_slug, "slug": opp_slug, "rank": i,
            "gap_type": "disagreement",
            "scorer": "unresolved_contradictions",
            "title": f"Two papers disagree ({slug})",
            "similarity": c.get("similarity"),
            "explanation": c.get("explanation"),
            "a_paper_id": c.get("a_paper_id"), "b_paper_id": c.get("b_paper_id"),
            "a_text": c.get("a_text"), "b_text": c.get("b_text"),
            "supporting_papers": [c.get("a_paper_id"), c.get("b_paper_id")],
            "confidence_tier": "medium",
            "confirm_status": None,
            "consumer": {
                "headline": "Two papers report findings that disagree",
                "kind": "A disagreement between papers",
                "kind_id": "disagreement",
                "strength": "Worth a look",
                "why": c.get("explanation", "")[:400],
                "caveats": [],
                "paper_count": 2,
            },
        }
        (opp_dir / f"{opp_slug}.json").write_text(json.dumps(card))
        opportunity_summaries.append({
            "id": opp_slug, "slug": opp_slug, "rank": i,
            "gap_type": "disagreement", "consumer": card["consumer"],
        })
    (lib_dir / "opportunities.json").write_text(json.dumps({
        "schema_version": "1.0.0",
        "total": len(opportunity_summaries),
        "items": opportunity_summaries,
    }))

    # stats.json
    n_full = sum(1 for e in entries if e.get("input_source") == "fulltext")
    strength = assertion_strength_distribution(exts) if exts else {}
    gap = gap_type_counts(exts) if exts else {}
    (lib_dir / "stats.json").write_text(json.dumps({
        "papers": len(entries), "full_text": n_full,
        "abstract_only": len(entries) - n_full,
        "n_extractions": len(exts),
        "assertion_strength": strength,
        "gap_type_counts": gap,
        "n_confirmed_contradictions": len(contradictions),
        "scorer_yields": {
            "unresolved_contradictions": len(contradictions),
            "persistent_limitations": 0,       # not scored on these libs yet
            "orphaned_future_work": 0,
            "structural_holes": 0,
            "structural_holes_substantive": 0,
        },
        "core": sum(1 for e in entries if e.get("domain_centrality") == "core"),
        "peripheral": sum(1 for e in entries
                           if e.get("domain_centrality") == "peripheral"),
        "spend_to_date_usd": 0.0,
        "manifest_hash": None,
        "relationships": len(contradictions),
        "note": ("Multi-domain library — extraction 59% (diet) or 51% "
                 "(fairness) of 100-paper target; only contradiction "
                 "scoring ran (structural-hole confirmations and future-"
                 "work matching skipped per Gate-3 cuts)."),
    }, indent=2))

    # search-index.json — per-library term index (title + abstract)
    idx = _build_search_index(entries)
    (lib_dir / "search-index.json").write_text(json.dumps(idx))

    # language.json — copy the shared translation layer so the frontend
    # loads the same shape from any library.
    (lib_dir / "language.json").write_text(json.dumps(lang_mod.language_pack()))

    # findings.json — reuse the shared findings docs (multi-domain, etc.)
    from backend.app.api import data as data_mod
    (lib_dir / "findings.json").write_text(json.dumps({
        "items": data_mod.findings(),
    }))

    # relationships.json — for now, just the contradiction pairs
    (lib_dir / "relationships.json").write_text(json.dumps({
        "items": [
            {"from_paper_id": c.get("a_paper_id"),
             "to_paper_id": c.get("b_paper_id"),
             "type": "contradicts",
             "note": c.get("explanation", "")[:400]}
            for c in contradictions
        ],
    }))

    return {"slug": slug, "n_papers": len(entries),
            "n_extractions": len(exts),
            "n_paper_files": len(entries),
            "n_opportunity_files": len(opportunity_summaries)}


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")


def _build_search_index(entries: list[dict]) -> dict:
    """Small term-weight index for the frontend search gate. Each doc is
    represented by its title + abstract tokens; the gate matches an
    incoming query against these to decide in-domain / borderline / OOD
    per this library."""
    from collections import Counter
    import math

    docs = []
    df = Counter()
    for e in entries:
        text = f"{e.get('title') or ''} {e.get('abstract') or ''}"
        toks = set(_TOKEN_RE.findall(text.lower()))
        docs.append({"wid": e["wid"], "title": e.get("title"),
                     "terms": sorted(toks)})
        for t in toks:
            df[t] += 1
    n = max(1, len(docs))
    idf = {t: math.log(n / c) for t, c in df.items()}
    max_idf = max(idf.values()) if idf else 0.0
    return {
        "n_docs": n,
        "max_idf": max_idf,
        "idf": idf,
        "docs": docs,
        "synonyms": {},
        "stopwords": [],
    }


# ---- Cross-library router ------------------------------------------------


def libraries_manifest() -> dict:
    """Top-level `libraries.json`. The frontend uses this both to
    populate the selector and to know where to fetch each library's
    snapshot files."""
    return {
        "libraries": [
            {**m, "snapshot_path":
                (f"/data/library/{m['slug']}"
                 if not m.get("is_default") else "/data")}
            for m in LIBRARIES
        ],
        "default_slug": next(
            (m["slug"] for m in LIBRARIES if m.get("is_default")),
            LIBRARIES[0]["slug"],
        ),
    }


def main() -> int:
    out_root = DEFAULT_ROOT.resolve()   # absolute, so export.py's
                                          # relative_to(REPO_ROOT) print
                                          # in the LLM-cal reuse works.
    out_root.mkdir(parents=True, exist_ok=True)

    print("→ llm-calibration snapshot (root + library subdir)")
    r0 = write_llm_calibration_snapshot(out_root)
    print(f"  {json.dumps(r0)}")

    for slug in ("diet-and-mortality", "ml-fairness"):
        print(f"→ {slug} snapshot")
        r = write_multi_domain_snapshot(slug, out_root)
        print(f"  {json.dumps(r)}")

    manifest = libraries_manifest()
    (out_root / "libraries.json").write_text(json.dumps(manifest, indent=2))
    print(f"→ libraries.json written ({len(manifest['libraries'])} libraries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
