"""Per-scorer unit tests with small hand-built fixtures where the correct
output is known. Deterministic — no LLM, no network."""

from __future__ import annotations

import numpy as np
import pytest

from backend.app.models import (
    Claim, ClaimRelationship, FutureWork, FutureWorkAddressal, Limitation,
    Methodology, PaperExtraction,
)
from backend.app.reasoning import scorers as S
from backend.app.reasoning.corpus_view import PaperInfo, ReasoningCorpus
from backend.app.reasoning.fidelity import effective_count
from backend.app.reasoning.independence import independent_count
from backend.app.relationships.corpus_loader import LoadedCorpus, PaperMeta


def _paper(pid, year, src="fulltext", author="A"):
    return PaperInfo(id=pid, openalex_id=f"https://openalex.org/{pid}", title=f"T {pid}",
                     year=year, input_source=src, domain_centrality="core", first_author=author)


def _ext(pid, *, claims=(), lims=(), methods=(), fw=()):
    return PaperExtraction(paper_id=pid, claims=list(claims), limitations=list(lims),
                           methodologies=list(methods), future_work=list(fw))


def _corpus(papers, exts, *, own_lims=(), addressals=(), contradictions=(),
            edges=(), claim_ids=(), claim_vecs=None, fw=(), fw_ids=(), fw_vecs=None,
            claim_paper=None):
    lc = LoadedCorpus(
        papers={p.id: PaperMeta(p.id, p.openalex_id, p.title, p.year, None,
                                p.input_source, p.domain_centrality, "snowball")
                for p in papers},
        extractions=exts, claim_paper=claim_paper or {}, claim_source={})
    return ReasoningCorpus(
        papers={p.id: p for p in papers}, own_limitations=list(own_lims),
        future_work=list(fw), addressals=list(addressals),
        contradictions=list(contradictions), citation_edges=set(edges),
        claim_ids=list(claim_ids),
        claim_vectors=claim_vecs if claim_vecs is not None else np.zeros((0, 3), np.float32),
        paper_vectors={}, fw_ids=list(fw_ids), fw_vectors=fw_vecs,
        claim_paper=claim_paper or {}, _loaded=lc)


# --- independence + fidelity ---
def test_independence_collapses_shared_first_author():
    papers = {"p1": _paper("p1", 2020, author="Smith"),
              "p2": _paper("p2", 2021, author="Smith"),   # same author
              "p3": _paper("p3", 2022, author="Jones")}
    assert independent_count(["p1", "p2", "p3"], papers) == 2


def test_fidelity_up_weights_abstract():
    papers = {"a": _paper("a", 2020, src="abstract"), "f": _paper("f", 2020, src="fulltext")}
    assert effective_count(["a"], papers, corrected=True) == 3.0   # abstract 3x
    assert effective_count(["f"], papers, corrected=True) == 1.0
    assert effective_count(["a"], papers, corrected=False) == 1.0  # off


# --- 1. persistent limitations ---
def _lim(pid, cat):
    return Limitation(id=f"lim:{pid}:{cat}", paper_id=pid, text=f"limitation {cat} in {pid}",
                      normalized_category=cat, source_scope="this_work")


def test_persistent_fires_on_three_independent_papers():
    papers = [_paper("p1", 2019, author="A"), _paper("p2", 2021, author="B"),
              _paper("p3", 2023, author="C")]
    lims = [_lim("p1", "gap-x"), _lim("p2", "gap-x"), _lim("p3", "gap-x")]
    exts = {p.id: _ext(p.id, lims=[l for l in lims if l.paper_id == p.id],
                       methods=[Methodology(id=f"m{p.id}", paper_id=p.id, name=f"method-{p.id}")])
            for p in papers}
    c = _corpus(papers, exts, own_lims=[(l, l.paper_id) for l in lims])
    opps = S.score_persistent_limitations(c)
    assert len(opps) == 1
    assert opps[0].component_scores["n_independent"] == 3
    assert opps[0].gap_type == "unaddressed_limitation"
    assert opps[0].supporting_paper_ids and opps[0].evidence_trail


def test_persistent_below_floor_does_not_fire():
    papers = [_paper("p1", 2019, author="A"), _paper("p2", 2021, author="A")]  # same author -> 1
    lims = [_lim("p1", "gap-x"), _lim("p2", "gap-x")]
    exts = {p.id: _ext(p.id, lims=[l for l in lims if l.paper_id == p.id]) for p in papers}
    c = _corpus(papers, exts, own_lims=[(l, l.paper_id) for l in lims])
    assert S.score_persistent_limitations(c) == []


# --- 2. unresolved contradictions ---
def test_contradiction_non_trivial_when_no_cross_citation():
    papers = [_paper("p1", 2022), _paper("p2", 2023)]
    exts = {"p1": _ext("p1", claims=[Claim(id="ca", paper_id="p1", text="X improves", type="finding", confidence=0.5)]),
            "p2": _ext("p2", claims=[Claim(id="cb", paper_id="p2", text="X does not improve", type="finding", confidence=0.5)])}
    rel = ClaimRelationship(id="r1", from_claim_id="ca", to_claim_id="cb", type="contradicts",
                            weight=0.8, from_paper_id="p1", to_paper_id="p2", similarity=0.85)
    c = _corpus(papers, exts, contradictions=[rel])
    opps = S.score_unresolved_contradictions(c)
    assert len(opps) == 1
    assert opps[0].component_scores["non_trivial_no_cross_citation"] == 1.0
    assert opps[0].contradiction_ids == ["r1"]


def test_contradiction_trivial_when_cross_citation_lowers_score():
    papers = [_paper("p1", 2022), _paper("p2", 2023)]
    exts = {"p1": _ext("p1", claims=[Claim(id="ca", paper_id="p1", text="X improves", type="finding", confidence=0.5)]),
            "p2": _ext("p2", claims=[Claim(id="cb", paper_id="p2", text="X does not", type="finding", confidence=0.5)])}
    rel = ClaimRelationship(id="r1", from_claim_id="ca", to_claim_id="cb", type="contradicts",
                            weight=0.8, from_paper_id="p1", to_paper_id="p2", similarity=0.85)
    c = _corpus(papers, exts, contradictions=[rel], edges=[("p1", "p2")])
    opps = S.score_unresolved_contradictions(c)
    assert opps[0].component_scores["non_trivial_no_cross_citation"] == 0.0


# --- 3. orphaned future-work ---
def _orphan_corpus(*, addressed_label=None, n_near=6, age=5):
    src_year = 2026 - age
    papers = [_paper("src", src_year)] + [_paper(f"L{i}", 2026, author=f"au{i}") for i in range(n_near)]
    fwk = FutureWork(id="fw1", paper_id="src", text="explore abstention")
    exts = {"src": _ext("src", fw=[fwk])}
    claim_ids, cp, vecs = [], {}, []
    for i in range(n_near):
        cid = f"c{i}"; exts[f"L{i}"] = _ext(f"L{i}", claims=[Claim(id=cid, paper_id=f"L{i}", text="near", type="finding", confidence=0.5)])
        claim_ids.append(cid); cp[cid] = f"L{i}"; vecs.append([1.0, 0.0])
    addr = []
    if addressed_label:
        addr = [FutureWorkAddressal(id="a1", future_work_id="fw1", from_paper_id="src",
                                    to_paper_id="L0", label=addressed_label, similarity=0.8)]
    return _corpus(papers, exts, fw=[(fwk, PaperMeta("src", None, "s", src_year, None, "fulltext", "core", "snowball"))],
                   addressals=addr, claim_ids=claim_ids,
                   claim_vecs=np.array(vecs, np.float32), fw_ids=["fw1"],
                   fw_vecs=np.array([[1.0, 0.0]], np.float32), claim_paper=cp)


def test_orphan_fires_when_unaddressed_enough_near_and_old():
    opps = S.score_orphaned_future_work(_orphan_corpus(n_near=6, age=5))
    assert len(opps) == 1
    assert opps[0].gap_type == "unfollowed_future_work"
    assert "CORPUS-RELATIVE CAVEAT" in opps[0].explanation


def test_orphan_excluded_when_addressed():
    assert S.score_orphaned_future_work(_orphan_corpus(addressed_label="addressed")) == []
    assert S.score_orphaned_future_work(_orphan_corpus(addressed_label="partial")) == []


def test_orphan_indeterminate_excluded_when_too_few_near():
    # only 3 near-later papers < min_near_later(5) -> indeterminate -> excluded
    assert S.score_orphaned_future_work(_orphan_corpus(n_near=3, age=5)) == []


def test_orphan_trivial_when_recent():
    # age 1 < reason_orphan_min_years(2) -> not unfollowed long enough
    assert S.score_orphaned_future_work(_orphan_corpus(n_near=6, age=1)) == []


# --- 4. structural holes (semantic matcher) ---
def test_structural_holes_semantic_fires_on_cross_cluster_match():
    dim = 8
    papers = [_paper(f"p{i}", 2020 + i, author=f"a{i}") for i in range(8)]
    e = [np.eye(dim, dtype=np.float32)[i] for i in range(8)]
    v1 = np.array([0.9, 0.436, 0, 0, 0, 0, 0, 0], np.float32)
    v1 = v1 / np.linalg.norm(v1)          # cos ~0.9 to e[0]
    # p0: a method-type claim (embedding e0) + methodology "MethodX".
    # p1: a claim (embedding v1, near p0's method) + an own-work limitation.
    exts = {}
    exts["p0"] = _ext("p0", claims=[Claim(id="c0", paper_id="p0", text="apply MethodX",
                                          type="method", confidence=0.5)],
                      methods=[Methodology(id="m0", paper_id="p0", name="MethodX")])
    lim = Limitation(id="lim1", paper_id="p1", text="our evaluation set is small",
                     normalized_category="eval", source_scope="this_work")
    exts["p1"] = _ext("p1", claims=[Claim(id="c1", paper_id="p1", text="we detect X",
                                          type="finding", confidence=0.5)], lims=[lim])
    for i in range(2, 8):
        exts[f"p{i}"] = _ext(f"p{i}", claims=[Claim(id=f"c{i}", paper_id=f"p{i}",
                                                    text=f"filler {i}", type="finding", confidence=0.5)])
    claim_ids = [f"c{i}" for i in range(8)]
    claim_vecs = np.stack([e[0], v1] + [e[i] for i in range(2, 8)])
    cp = {f"c{i}": f"p{i}" for i in range(8)}
    c = _corpus(papers, exts, own_lims=[(lim, "p1")], claim_ids=claim_ids,
                claim_vecs=claim_vecs, claim_paper=cp)
    c.paper_vectors.update({f"p{i}": (e[0] if i == 0 else v1 if i == 1 else e[i])
                            for i in range(8)})
    opps = S.score_structural_holes(c)
    assert len(opps) >= 1
    hole = [o for o in opps if o.supporting_paper_ids == ["p0", "p1"]]
    assert hole, "expected a p0->p1 method-transfer hole"
    assert hole[0].component_scores["semantic_similarity"] >= 0.72
    assert "lim1" in hole[0].evidence_trail


def test_structural_holes_none_when_no_semantic_match():
    # same shape but p1's claim is orthogonal to p0's method -> no hole
    dim = 8
    papers = [_paper(f"p{i}", 2020 + i, author=f"a{i}") for i in range(8)]
    e = [np.eye(dim, dtype=np.float32)[i] for i in range(8)]
    lim = Limitation(id="lim1", paper_id="p1", text="small eval",
                     normalized_category="eval", source_scope="this_work")
    exts = {"p0": _ext("p0", claims=[Claim(id="c0", paper_id="p0", text="MethodX", type="method", confidence=0.5)],
                       methods=[Methodology(id="m0", paper_id="p0", name="MethodX")]),
            "p1": _ext("p1", claims=[Claim(id="c1", paper_id="p1", text="Y", type="finding", confidence=0.5)], lims=[lim])}
    for i in range(2, 8):
        exts[f"p{i}"] = _ext(f"p{i}", claims=[Claim(id=f"c{i}", paper_id=f"p{i}", text="f", type="finding", confidence=0.5)])
    c = _corpus(papers, exts, own_lims=[(lim, "p1")], claim_ids=[f"c{i}" for i in range(8)],
                claim_vecs=np.stack([e[i] for i in range(8)]),  # p0=e0, p1=e1 orthogonal
                claim_paper={f"c{i}": f"p{i}" for i in range(8)})
    c.paper_vectors.update({f"p{i}": e[i] for i in range(8)})
    assert S.score_structural_holes(c) == []


# --- 5. disjoint bridging gated off ---
def test_disjoint_bridging_off_by_default():
    c = _corpus([_paper("p1", 2020)], {"p1": _ext("p1")})
    c.paper_vectors["p1"] = np.array([1.0, 0.0], np.float32)
    assert S.score_disjoint_bridging(c) == []
