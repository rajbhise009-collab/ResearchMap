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

    # opportunities.json + per-opportunity detail with per-pair audit
    # verdicts attached. Genuine ones headline; artifact + duplicate go
    # in the "set aside" section on the UI. Never hidden.
    from backend.app.api.contradiction_audit import (
        attach_verdicts, audit_summary,
    )
    from backend.app.api.cites_both import load_cites_both, _wid as _oawid
    cites_both = load_cites_both(slug) or {"records": []}
    # Build a lookup keyed by canonical (a_wid, b_wid) sorted pair for
    # attaching cites-both to each contradiction card.
    cb_by_pair = {}
    for rec in cites_both.get("records", []):
        key = tuple(sorted([_oawid(rec["a_paper_id"]),
                             _oawid(rec["b_paper_id"])]))
        cb_by_pair[key] = rec
    contra_path = REPO_ROOT / "data" / "domains" / slug / "reasoning" / "contradictions.json"
    contradictions = []
    if contra_path.exists():
        contradictions = json.loads(contra_path.read_text()).get("items", [])
    audited_contradictions = attach_verdicts(slug, contradictions)
    audit_counts = audit_summary(slug, contradictions)

    from backend.app.api.contradiction_titles import (
        make_title, make_verdict_label, make_set_aside_title, dedupe_titles,
    )

    _verdict_strength = {
        "genuine": "Worth a look",
        "artifact": "Unverified lead",
        "duplicate": "Unverified lead",
        "unaudited": "Unverified lead",
    }

    # Pre-derive per-pair titles so collisions are resolved before any
    # downstream consumer sees them. The distinguisher is the first clause
    # of the audit `reason` — only appended when a title would otherwise
    # collide (never a number).
    pre_titled = []
    for c in audited_contradictions:
        verdict = c["audit"]["verdict"]
        topic = c["audit"].get("topic") or None
        a_text = c.get("a_text", "")
        b_text = c.get("b_text", "")
        if verdict in ("artifact", "duplicate"):
            base = make_set_aside_title(verdict, topic, a_text, b_text)
        else:
            base = make_title(topic, a_text, b_text)
        reason = (c["audit"].get("reason") or "").split(".")[0]
        distinguisher = reason[:60].strip() if reason else ""
        pre_titled.append((base, distinguisher))
    resolved_titles = dedupe_titles(pre_titled)

    opp_dir = lib_dir / "opportunity"
    opp_dir.mkdir(exist_ok=True)
    opportunity_summaries = []
    for i, (c, headline) in enumerate(
            zip(audited_contradictions, resolved_titles), 1):
        opp_slug = (f"opp-contra-{slug}-{i:02d}-"
                    f"{_slug(c['a_paper_id'])}-{_slug(c['b_paper_id'])}")[:120]
        verdict = c["audit"]["verdict"]
        pair_key = tuple(sorted([_oawid(c.get("a_paper_id", "")),
                                    _oawid(c.get("b_paper_id", ""))]))
        cites_both_rec = cb_by_pair.get(pair_key)
        card = {
            "id": opp_slug, "slug": opp_slug, "rank": i,
            "gap_type": "disagreement",
            "scorer": "unresolved_contradictions",
            "title": headline,
            "similarity": c.get("similarity"),
            "explanation": c.get("explanation"),
            "a_paper_id": c.get("a_paper_id"), "b_paper_id": c.get("b_paper_id"),
            "a_text": c.get("a_text"), "b_text": c.get("b_text"),
            "supporting_papers": [
                {"paper_id": c.get("a_paper_id"),
                 "title": next((e.get("title") for e in entries
                                if f"openalex:{e['wid']}" == c.get("a_paper_id")), None)},
                {"paper_id": c.get("b_paper_id"),
                 "title": next((e.get("title") for e in entries
                                if f"openalex:{e['wid']}" == c.get("b_paper_id")), None)},
            ],
            "supporting_paper_ids": [c.get("a_paper_id"), c.get("b_paper_id")],
            "confidence_tier": "medium" if verdict == "genuine" else "low",
            "confirm_status": None,
            "audit": c["audit"],  # verdict + reason + basis + date
            "cites_both": ({"query_date": cites_both.get("query_date"),
                             "total": cites_both_rec["total_cites_both"],
                             "top": cites_both_rec["top"]}
                            if cites_both_rec else None),
            "consumer": {
                "headline": headline,
                "kind": "A disagreement between papers",
                "kind_id": "disagreement",
                "strength": _verdict_strength.get(verdict, "Unverified lead"),
                "why": c.get("explanation", "")[:400],
                "verdict": verdict,
                "verdict_label": make_verdict_label(verdict),
                "verdict_reason": c["audit"].get("reason", ""),
                "verdict_basis": c["audit"].get("basis", ""),
                "verdict_topic": c["audit"].get("topic", ""),
                "caveats": [],
                "paper_count": 2,
            },
        }
        (opp_dir / f"{opp_slug}.json").write_text(json.dumps(card))
        opportunity_summaries.append({
            "id": opp_slug, "slug": opp_slug, "rank": i,
            "gap_type": "disagreement", "consumer": card["consumer"],
            "verdict": verdict,
        })
    (lib_dir / "opportunities.json").write_text(json.dumps({
        "schema_version": "1.0.0",
        "total": len(opportunity_summaries),
        "audit": audit_counts,
        "items": opportunity_summaries,
    }))

    # stats.json — with EXTRACTION COVERAGE plainly stated so the UI
    # can render "Claims read from N of M papers" instead of the raw
    # "M papers" number that hides partial extraction. Two separate
    # lines so the UI never has to parse them apart:
    # - coverage_note: ALWAYS shown; the plain "N of M read" + "we
    #   stopped reading to stay within budget" sentence when partial.
    # - zero_note:    ONLY shown on libraries whose confirmed-
    #   contradictions count is 0 (so Diet, which has 5 confirmed,
    #   never sees it). Phrases "zero" as a floor — unread papers
    #   could hold disagreements — not a ceiling, which was backwards.
    n_full = sum(1 for e in entries if e.get("input_source") == "fulltext")
    n_extracted = len(exts)
    n_missing = len(entries) - n_extracted
    coverage_note = (
        f"Claims read from {n_extracted} of {len(entries)} papers."
        + (f" We stopped reading to stay within budget, so the remaining "
           f"{n_missing} papers are not reflected in these results."
           if n_missing > 0 else "")
    )
    zero_note = (
        "Zero here means none were found among the papers read. "
        "It does not mean none exist."
        if audit_counts["confirmed"] == 0 else None
    )
    strength = assertion_strength_distribution(exts) if exts else {}
    gap = gap_type_counts(exts) if exts else {}

    # Code-only persistent-limitations count: a limitation category
    # that recurs in ≥3 extracted papers (own_work scope) counts as a
    # "persistent" one. Mirrors the LLM-cal scorer's minimum-paper
    # threshold without running the full Phase-4 engine (which needs
    # claim embeddings + addressal relations the multi-domain libs
    # don't have yet).
    from collections import defaultdict
    cat_papers: dict[str, set] = defaultdict(set)
    for ext in exts:
        for lim in (ext.limitations or []):
            if lim.source_scope == "this_work":
                cat_papers[lim.normalized_category or "uncategorized"].add(
                    ext.paper_id)
    n_persistent = sum(1 for ps in cat_papers.values() if len(ps) >= 3)

    (lib_dir / "stats.json").write_text(json.dumps({
        "papers": len(entries), "full_text": n_full,
        "abstract_only": len(entries) - n_full,
        "n_extractions": n_extracted,
        "extraction_coverage_note": coverage_note,
        "zero_finding_note": zero_note,
        "extraction_coverage_share": (n_extracted / len(entries)) if entries else 0.0,
        "assertion_strength": strength,
        "gap_type_counts": gap,
        "n_confirmed_contradictions": audit_counts["confirmed"],
        "raw_flagged_contradictions": audit_counts["raw_flagged"],
        "contradiction_audit": audit_counts,
        "scorer_yields": {
            "unresolved_contradictions": audit_counts["confirmed"],
            "persistent_limitations": n_persistent,
            "orphaned_future_work": 0,    # paid, out of this iteration's budget
            "structural_holes": 0,        # needs embeddings; deferred
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

    # search-index.json — same shape as the LLM-cal library uses. The
    # frontend's `search()` reads `doc.terms` as a {token→weight} dict
    # and reads `doc.type`/`ref`/`title`/`kind`/`strength`; the earlier
    # per-library builder wrote `wid` and a sorted-list `terms`, which
    # Quick Search silently matched zero hits against. Build the real
    # shape by reusing `search_index.build_index` over the opportunity
    # cards + paper detail records this library just produced.
    from backend.app.api.search_index import build_index as _build_real_idx
    _opp_cards_for_idx = []
    for _summary in opportunity_summaries:
        _p = (opp_dir / f"{_summary['slug']}.json")
        _opp_cards_for_idx.append(json.loads(_p.read_text()))
    _paper_details_for_idx = []
    for _e in entries:
        _p = (paper_dir / f"{_e['wid']}.json")
        if _p.exists():
            _paper_details_for_idx.append(json.loads(_p.read_text()))
    idx = _build_real_idx(_opp_cards_for_idx, _paper_details_for_idx)
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
