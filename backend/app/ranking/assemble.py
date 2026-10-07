"""Assemble ranked EvidenceCards from scorer output + the corpus.

Deterministic, no API calls. Re-runs the scorers (free) so cards are always
consistent with the code, resolves every evidence-trail id to a concrete
paper/claim/limitation/relationship, attaches all applicable caveats, and
ranks by trust = score x confidence.
"""

from __future__ import annotations

import json

from backend.app.config import REPO_ROOT
from backend.app.models import Opportunity
from backend.app.ranking.schema import (
    Caveat, EvidenceCard, EvidenceItem, SupportingPaper, tier_for,
)
from backend.app.reasoning import scorers as S
from backend.app.reasoning.corpus_view import ReasoningCorpus, load_reasoning_corpus

CONFIRMATIONS = REPO_ROOT / "data" / "reasoning" / "structural_hole_confirmations.json"


def _lookups(corpus: ReasoningCorpus):
    claims, lims, fws, fw_paper = {}, {}, {}, {}
    for pid, ext in corpus._loaded.extractions.items():
        for c in ext.claims:
            claims[c.id] = c
        for l in ext.limitations:
            lims[l.id] = l
        for f in ext.future_work:
            fws[f.id] = f
            fw_paper[f.id] = pid
    rel_ids = {r.id for r in corpus.contradictions}
    return claims, lims, fws, fw_paper, rel_ids


def _resolve(tid: str, corpus, L) -> EvidenceItem:
    claims, lims, fws, fw_paper, rel_ids = L
    if tid.startswith("rel:") or tid in rel_ids:
        return EvidenceItem(kind="relationship", id=tid)
    if tid.startswith("method:"):
        return EvidenceItem(kind="method", id=tid, text=tid.split(":", 1)[1])
    if tid in claims:
        c = claims[tid]
        return EvidenceItem(kind="claim", id=tid, paper_id=c.paper_id, text=c.text)
    if tid in lims:
        l = lims[tid]
        return EvidenceItem(kind="limitation", id=tid, paper_id=l.paper_id, text=l.text)
    if tid in fws:
        return EvidenceItem(kind="future_work", id=tid, paper_id=fw_paper[tid], text=fws[tid].text)
    if tid in corpus.papers:
        return EvidenceItem(kind="paper", id=tid, paper_id=tid, text=corpus.papers[tid].title)
    return EvidenceItem(kind="unknown", id=tid)


def _supporting(corpus, paper_ids) -> list[SupportingPaper]:
    out = []
    for pid in paper_ids:
        p = corpus.papers.get(pid)
        if p is None:
            continue
        out.append(SupportingPaper(
            paper_id=pid, title=p.title, year=p.year, input_source=p.input_source,
            abstract_only=(p.input_source != "fulltext"),
            domain_centrality=p.domain_centrality))
    return out


def _caveats(scorer, opp, supporting, confirm_status, n_papers) -> list[Caveat]:
    cav: list[Caveat] = []
    if scorer == "orphaned_future_work":
        cav.append(Caveat(code="corpus_relative", label="Corpus-relative",
                          detail=(f"'Orphaned' means unaddressed WITHIN this {n_papers}-paper "
                                  "corpus, not the field; the two-stage matcher precision is ~0.64.")))
    n_ab = sum(1 for sp in supporting if sp.abstract_only)
    if n_ab:
        cav.append(Caveat(code="mixed_fidelity", label="Mixed-fidelity",
                          detail=(f"{n_ab} supporting paper(s) are abstract-only, which yield "
                                  "~11x fewer own-work limitations than full text.")))
    if opp.component_scores.get("generic_category") == 1.0:
        cav.append(Caveat(code="generic_category", label="Generic category",
                          detail="The limitation category is generic and may fail the actionability bar."))
    if scorer == "persistent_limitations" and "::" in opp.id:
        cav.append(Caveat(code="construct_gated", label="Construct-gated",
                          detail="Category split by sub-construct so distinct bottlenecks aren't pooled."))
    if scorer == "structural_holes":
        cs = confirm_status or "unconfirmed"
        det = ("A semantic shortlist "
               + (f"LLM-confirmed as '{cs}'" if confirm_status else "not yet LLM-confirmed")
               + " — a lead, not a finding.")
        cav.append(Caveat(code="semantic_lead", label="Semantic lead", detail=det))
    return cav


def build_evidence_cards(corpus: ReasoningCorpus | None = None, *,
                         scorers: list[str] | None = None,
                         confirmations_path=None,
                         scorer_kwargs: dict[str, dict] | None = None) -> list[EvidenceCard]:
    """Defaults reproduce LLM calibration exactly. A multi-domain library
    passes its own corpus, the scorers it ran, its confirmations file and
    per-scorer arguments (e.g. structural-hole k scaled with N)."""
    corpus = corpus or load_reasoning_corpus()
    L = _lookups(corpus)
    n_papers = len(corpus.papers)
    cp = confirmations_path or CONFIRMATIONS
    conf = json.loads(cp.read_text()) if cp.exists() else {}
    kwargs = scorer_kwargs or {}

    tagged: list[tuple[str, Opportunity]] = []
    for name, fn in S.SCORERS.items():
        if scorers is not None and name not in scorers:
            continue
        for o in fn(corpus, **kwargs.get(name, {})):
            tagged.append((name, o))
    tagged.sort(key=lambda t: -(t[1].score * t[1].confidence))

    cards: list[EvidenceCard] = []
    for rank, (scorer, o) in enumerate(tagged, 1):
        confirm_status = conf.get(o.id, {}).get("verdict") if scorer == "structural_holes" else None
        supporting = _supporting(corpus, o.supporting_paper_ids)
        trail = [_resolve(t, corpus, L) for t in o.evidence_trail]
        rel_ids = [t.id for t in trail if t.kind == "relationship"] + list(o.contradiction_ids)
        cards.append(EvidenceCard(
            id=o.id, rank=rank, gap_type=o.gap_type, scorer=scorer, title=o.title,
            score=round(o.score, 4), confidence=round(o.confidence, 4),
            confidence_tier=tier_for(o.confidence),
            trust=round(o.score * o.confidence, 4),
            confirm_status=confirm_status,
            component_scores={k: float(v) for k, v in o.component_scores.items()},
            explanation=o.explanation,
            caveats=_caveats(scorer, o, supporting, confirm_status, n_papers),
            supporting_papers=supporting, evidence_trail=trail,
            relationship_ids=sorted(set(rel_ids)),
        ))
    return cards


__all__ = ["build_evidence_cards"]
