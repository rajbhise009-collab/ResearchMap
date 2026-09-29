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
    from data/domains/<slug>/ prelabel + extractions + reasoning."""
    from backend.app.corpus.multi_domain import _prelabel_path
    from backend.app.corpus.multi_domain_reason import (
        DOMAINS,   # aliased to accept full or short slug
        assertion_strength_distribution,
        gap_type_counts,
        load_extractions,
    )

    if slug not in DOMAINS:
        raise KeyError(slug)

    lib_dir = out_root / "library" / slug
    lib_dir.mkdir(parents=True, exist_ok=True)

    prelabel = json.loads(_prelabel_path(DOMAINS[slug]).read_text())
    entries = prelabel["entries"]

    # meta.json
    (lib_dir / "meta.json").write_text(json.dumps({
        "slug": slug,
        "schema_version": "1.0.0",
        "n_papers": len(entries),
    }, indent=2))

    # papers.json
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

    # stats.json
    n_full = sum(1 for e in entries if e.get("input_source") == "fulltext")
    exts = load_extractions(slug)
    strength = assertion_strength_distribution(exts) if exts else {}
    gap = gap_type_counts(exts) if exts else {}
    reasoning_dir = REPO_ROOT / "data" / "domains" / slug / "reasoning"
    contra_path = reasoning_dir / "contradictions.json"
    n_contra = 0
    if contra_path.exists():
        n_contra = json.loads(contra_path.read_text()).get("n", 0)
    (lib_dir / "stats.json").write_text(json.dumps({
        "papers": len(entries), "full_text": n_full,
        "abstract_only": len(entries) - n_full,
        "n_extractions": len(exts),
        "assertion_strength": strength,
        "gap_type_counts": gap,
        "n_confirmed_contradictions": n_contra,
    }, indent=2))

    # search-index.json — build a per-library term index (title + abstract)
    idx = _build_search_index(entries)
    (lib_dir / "search-index.json").write_text(json.dumps(idx))

    # opportunities.json — placeholder until full Phase-4 scoring wires
    # up in a follow-up. For now: gap_type_counts summary only.
    (lib_dir / "opportunities.json").write_text(json.dumps({
        "note": "per-domain scoring output pending; see stats.json for "
                "gap_type_counts summary",
        "total": 0, "items": [],
    }))

    return {"slug": slug, "n_papers": len(entries), "n_extractions": len(exts)}


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
