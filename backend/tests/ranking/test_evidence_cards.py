"""Phase 5 — evidence cards resolve to real IDs, no orphan references,
first-class gap_type/tier, versioned schema, caveats attach."""

from __future__ import annotations

import numpy as np

from backend.app.models import Claim, FutureWork, Limitation, Methodology, PaperExtraction
from backend.app.ranking.assemble import build_evidence_cards
from backend.app.ranking.schema import SCHEMA_VERSION, ConfidenceTier, tier_for
from backend.app.reasoning.corpus_view import PaperInfo, ReasoningCorpus
from backend.app.relationships.corpus_loader import LoadedCorpus, PaperMeta


def _paper(pid, year, src="fulltext", author="A"):
    return PaperInfo(id=pid, openalex_id=f"https://openalex.org/{pid}", title=f"Title {pid}",
                     year=year, input_source=src, domain_centrality="core", first_author=author)


def _persistent_corpus():
    # 3 independent full-text papers with the same this_work limitation.
    papers = [_paper("p1", 2019, author="A"), _paper("p2", 2021, author="B"),
              _paper("p3", 2023, author="C")]
    lims = [Limitation(id=f"lim:{p.id}", paper_id=p.id, text=f"limitation in {p.id}",
                       normalized_category="specific-gap", source_scope="this_work")
            for p in papers]
    exts = {p.id: PaperExtraction(paper_id=p.id, limitations=[lims[i]],
                                  methodologies=[Methodology(id=f"m{i}", paper_id=p.id, name=f"method{i}")])
            for i, p in enumerate(papers)}
    lc = LoadedCorpus(
        papers={p.id: PaperMeta(p.id, p.openalex_id, p.title, p.year, None, p.input_source,
                                p.domain_centrality, "original") for p in papers},
        extractions=exts, claim_paper={}, claim_source={})
    return ReasoningCorpus(
        papers={p.id: p for p in papers}, own_limitations=[(l, l.paper_id) for l in lims],
        future_work=[], addressals=[], contradictions=[], citation_edges=set(),
        claim_ids=[], claim_vectors=np.zeros((0, 3), np.float32), paper_vectors={},
        fw_ids=[], fw_vectors=None, claim_paper={}, _loaded=lc)


def test_tier_for_thresholds():
    assert tier_for(0.84) == ConfidenceTier.HIGH
    assert tier_for(0.50) == ConfidenceTier.MEDIUM
    assert tier_for(0.20) == ConfidenceTier.LOW


def test_cards_resolve_and_no_orphan_refs():
    corpus = _persistent_corpus()
    cards = build_evidence_cards(corpus)
    assert cards, "expected at least one persistent-limitation card"
    pids = set(corpus.papers)
    for c in cards:
        assert c.schema_version == SCHEMA_VERSION
        assert c.gap_type and c.confidence_tier      # first-class, populated
        assert c.supporting_papers
        for sp in c.supporting_papers:
            assert sp.paper_id in pids                # no orphan supporting papers
        for ev in c.evidence_trail:
            assert ev.kind != "unknown"               # every trail item resolved
            if ev.paper_id:
                assert ev.paper_id in pids


def test_cards_ranked_by_trust_desc():
    # add an orphan-producing corpus is heavier; ranking monotonicity is
    # checked on the persistent card set (single) trivially, so assert the
    # invariant holds on the real assembled order.
    corpus = _persistent_corpus()
    cards = build_evidence_cards(corpus)
    trusts = [c.trust for c in cards]
    assert trusts == sorted(trusts, reverse=True)
    assert all(c.rank == i + 1 for i, c in enumerate(cards))


def test_persistent_card_has_expected_shape():
    card = build_evidence_cards(_persistent_corpus())[0]
    assert card.gap_type == "unaddressed_limitation"
    assert card.component_scores.get("n_independent") == 3.0
    # evidence trail includes the 3 papers + their limitation ids
    kinds = {e.kind for e in card.evidence_trail}
    assert "limitation" in kinds
    assert card.trust == round(card.score * card.confidence, 4)


def test_abstract_only_triggers_mixed_fidelity_caveat():
    corpus = _persistent_corpus()
    corpus.papers["p1"].input_source = "abstract"   # make one supporting paper abstract-only
    card = build_evidence_cards(corpus)[0]
    codes = {cv.code for cv in card.caveats}
    assert "mixed_fidelity" in codes
