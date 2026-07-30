"""Citation graph (intra-corpus edge filtering) + future-work matching
(including the small-corpus 'indeterminate' guard)."""

from __future__ import annotations

import numpy as np

from backend.app.models import Claim, FutureWork, PaperExtraction
from backend.app.relationships.citation_graph import build_citation_graph
from backend.app.relationships.corpus_loader import LoadedCorpus, PaperMeta
from backend.app.relationships.future_work_match import match_future_work


def _meta(pid, year):
    return PaperMeta(paper_id=pid, openalex_id=f"https://openalex.org/{pid.split(':')[-1]}",
                     title=pid, year=year, doi=None, input_source="fulltext",
                     domain_centrality="core", provenance="snowball")


def test_citation_graph_keeps_only_intra_corpus_edges():
    papers = {"openalex:W1": _meta("openalex:W1", 2020),
              "openalex:W2": _meta("openalex:W2", 2021)}
    corpus = LoadedCorpus(papers=papers, extractions={})
    refs = {
        "openalex:W1": ["W2", "W999"],   # W2 in corpus, W999 not
        "openalex:W2": ["W1"],
    }
    edges = build_citation_graph(corpus, refs)
    got = {(e.from_paper_id, e.to_paper_id) for e in edges}
    assert got == {("openalex:W1", "openalex:W2"), ("openalex:W2", "openalex:W1")}


def _fw_corpus():
    # p_old (2018) has a future-work item; p_new (2022) has a matching claim.
    fw = FutureWork(id="fw1", paper_id="p_old", text="explore selective abstention for LLMs")
    e_old = PaperExtraction(paper_id="p_old", claims=[], future_work=[fw])
    e_new = PaperExtraction(paper_id="p_new", claims=[
        Claim(id="cnew", paper_id="p_new", text="we propose selective abstention for LLMs",
              type="method", confidence=0.5)])
    papers = {"p_old": _meta("p_old", 2018), "p_new": _meta("p_new", 2022)}
    return LoadedCorpus(papers=papers, extractions={"p_old": e_old, "p_new": e_new},
                        claim_paper={"cnew": "p_new"}, claim_source={"cnew": "fulltext"})


def test_future_work_addressed_by_later_similar_paper():
    corpus = _fw_corpus()
    # Identical vectors -> cosine 1.0 -> addressed.
    v = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    matches = match_future_work(corpus, ["fw1"], v, ["cnew"], v,
                                threshold=0.8, topical_threshold=0.65,
                                min_near_later=1)
    m = matches[0]
    assert m.status == "addressed"
    assert m.addressed_by == "p_new"


def test_future_work_indeterminate_when_too_few_near_later():
    corpus = _fw_corpus()
    # Orthogonal vectors: no match AND no topically-near later paper. With
    # min_near_later=5 and only 1 (unrelated) later paper, the result must
    # be 'indeterminate', NOT 'unaddressed' (small-corpus guard).
    fwv = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    cvec = np.array([[0.0, 1.0, 0.0]], dtype=np.float32)
    matches = match_future_work(corpus, ["fw1"], fwv, ["cnew"], cvec,
                                threshold=0.8, topical_threshold=0.65,
                                min_near_later=5)
    assert matches[0].status == "indeterminate_small_corpus"
    assert matches[0].near_later_papers == 0


def test_future_work_unaddressed_when_enough_near_later_but_no_match():
    # 6 later papers that ARE topically near (cosine ~0.7) but none MATCH
    # (>=0.8): enough same-thread later work to plausibly have seen the
    # answer, so 'unaddressed' is warranted.
    fw = FutureWork(id="fw1", paper_id="p_old", text="explore selective abstention")
    e_old = PaperExtraction(paper_id="p_old", claims=[], future_work=[fw])
    laters = {f"p{i}": _meta(f"p{i}", 2022) for i in range(6)}
    papers = {"p_old": _meta("p_old", 2018), **laters}
    exts = {"p_old": e_old}
    claim_ids, cp, cs = [], {}, {}
    for i in range(6):
        cid = f"c{i}"
        exts[f"p{i}"] = PaperExtraction(paper_id=f"p{i}", claims=[
            Claim(id=cid, paper_id=f"p{i}", text="near topic", type="finding", confidence=0.5)])
        claim_ids.append(cid); cp[cid] = f"p{i}"; cs[cid] = "fulltext"
    corpus = LoadedCorpus(papers=papers, extractions=exts, claim_paper=cp, claim_source=cs)
    fwv = np.array([[1.0, 0.0]], dtype=np.float32)
    # cosine ~0.7 to fw: near (>=0.65) but not a match (<0.8).
    cvec = np.array([[0.7, 0.7141428]] * 6, dtype=np.float32)
    matches = match_future_work(corpus, ["fw1"], fwv, claim_ids, cvec,
                                threshold=0.8, topical_threshold=0.65,
                                min_near_later=5)
    assert matches[0].status == "unaddressed"
    assert matches[0].near_later_papers == 6
