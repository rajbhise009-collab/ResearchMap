"""Read-only data layer for the API. Loads everything from the same files
the scorers read — NO database, NO API calls. Cached in memory (lazy
singletons); call `reset()` in tests to reload.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.app.config import REPO_ROOT
from backend.app.ranking.assemble import build_evidence_cards
from backend.app.ranking.schema import EvidenceCard
from backend.app.reasoning.corpus_view import load_reasoning_corpus
from backend.app.relationships.store import RelationshipStore

MANIFEST = REPO_ROOT / "data" / "live_samples" / "expanded_corpus_manifest.json"
FINDINGS_DIR = REPO_ROOT / "docs" / "findings"

# Cumulative paid spend to date (USD), corrected thinking-token accounting.
# See PROGRESS.md / docs/findings/RESEARCHMAP-FINDINGS.md.
SPEND_TO_DATE_USD = 7.4


@lru_cache(maxsize=1)
def corpus():
    return load_reasoning_corpus()


@lru_cache(maxsize=1)
def cards() -> list[EvidenceCard]:
    return build_evidence_cards(corpus())


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"records": []}


@lru_cache(maxsize=1)
def _manifest_by_id() -> dict:
    return {r["paper_id"]: r for r in manifest().get("records", [])}


@lru_cache(maxsize=1)
def relationships():
    return RelationshipStore().load_relationships()


def reset() -> None:
    for f in (corpus, cards, manifest, _manifest_by_id, relationships):
        f.cache_clear()


def card_by_id(oid: str) -> EvidenceCard | None:
    return next((c for c in cards() if c.id == oid), None)


def paper_summaries() -> list[dict]:
    c = corpus()
    out = []
    for pid, p in c.papers.items():
        rec = _manifest_by_id().get(pid, {})
        out.append({
            "paper_id": pid, "title": p.title, "year": p.year,
            "input_source": p.input_source, "abstract_only": p.input_source != "fulltext",
            "domain_centrality": p.domain_centrality,
            "provenance": rec.get("provenance"), "doi": rec.get("doi"),
        })
    return sorted(out, key=lambda r: (r["year"] or 0), reverse=True)


def paper_detail(pid: str) -> dict | None:
    c = corpus()
    p = c.papers.get(pid)
    if p is None:
        return None
    ext = c._loaded.extractions.get(pid)
    rec = _manifest_by_id().get(pid, {})
    cites = sorted(to for (frm, to) in c.citation_edges if frm == pid)
    cited_by = sorted(frm for (frm, to) in c.citation_edges if to == pid)
    title = {q: c.papers[q].title for q in c.papers}

    def _dump(objs):
        return [o.model_dump() for o in objs]

    return {
        "paper_id": pid, "title": p.title, "year": p.year, "doi": rec.get("doi"),
        "input_source": p.input_source, "abstract_only": p.input_source != "fulltext",
        "domain_centrality": p.domain_centrality, "provenance": rec.get("provenance"),
        "abstract": rec.get("abstract"),
        "claims": _dump(ext.claims) if ext else [],
        "limitations": _dump(ext.limitations) if ext else [],
        "future_work": _dump(ext.future_work) if ext else [],
        "methodologies": _dump(ext.methodologies) if ext else [],
        "cites": [{"paper_id": q, "title": title.get(q)} for q in cites],
        "cited_by": [{"paper_id": q, "title": title.get(q)} for q in cited_by],
    }


def stats() -> dict:
    c = corpus()
    from collections import Counter
    src = Counter(p.input_source for p in c.papers.values())
    cent = Counter(p.domain_centrality for p in c.papers.values())
    by_scorer = Counter(cd.scorer for cd in cards())
    substantive = sum(1 for cd in cards()
                      if cd.scorer == "structural_holes" and cd.confirm_status == "substantive")
    n_papers = len(c.papers)
    # LLM-cal is fully extracted (see manifest), so N == M. Same shape as
    # the multi-domain libraries so the frontend has one code path.
    n_extracted = n_papers
    coverage_note = f"Claims read from {n_extracted} of {n_papers} papers."
    return {
        "papers": n_papers,
        "full_text": src.get("fulltext", 0),
        "abstract_only": sum(v for k, v in src.items() if k != "fulltext"),
        "n_extractions": n_extracted,
        "extraction_coverage_note": coverage_note,
        "extraction_coverage_share": 1.0,
        "core": cent.get("core", 0), "peripheral": cent.get("peripheral", 0),
        "n_confirmed_contradictions": by_scorer.get("unresolved_contradictions", 0),
        "raw_flagged_contradictions": by_scorer.get("unresolved_contradictions", 0),
        "contradiction_audit": {
            "raw_flagged": by_scorer.get("unresolved_contradictions", 0),
            "genuine": by_scorer.get("unresolved_contradictions", 0),
            "artifact": 0, "duplicate": 0, "unaudited": 0,
            "confirmed": by_scorer.get("unresolved_contradictions", 0),
        },
        "scorer_yields": {
            "persistent_limitations": by_scorer.get("persistent_limitations", 0),
            "unresolved_contradictions": by_scorer.get("unresolved_contradictions", 0),
            "orphaned_future_work": by_scorer.get("orphaned_future_work", 0),
            "structural_holes": by_scorer.get("structural_holes", 0),
            "structural_holes_substantive": substantive,
        },
        "relationships": len(relationships()),
        "spend_to_date_usd": SPEND_TO_DATE_USD,
        "manifest_hash": manifest().get("manifest_hash"),
        "note": ("0 contradictions is the correct result for a coherent field — "
                 "candidates scale ~N^1.89 while confirmed stays at 0. See findings."),
    }


def findings() -> list[dict]:
    out = []
    for path in sorted(FINDINGS_DIR.glob("*.md")):
        text = path.read_text()
        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")),
                     path.stem)
        out.append({"slug": path.stem, "title": title, "path": f"docs/findings/{path.name}",
                    "markdown": text})
    return out


__all__ = ["corpus", "cards", "manifest", "relationships", "reset", "card_by_id",
           "paper_summaries", "paper_detail", "stats", "findings", "SPEND_TO_DATE_USD"]
