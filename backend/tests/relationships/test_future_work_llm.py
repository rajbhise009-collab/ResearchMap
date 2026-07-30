"""Two-stage future-work matcher: shortlist + citation prior + parsing +
persistence/drift for FutureWorkAddressal."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from backend.app.config import REPO_ROOT
from backend.app.db.tables import FutureWorkAddressalRow
from backend.app.models import FutureWork, FutureWorkAddressal, PaperExtraction
from backend.app.relationships import future_work_llm as F
from backend.app.relationships.citation_graph import CitationEdge
from backend.app.relationships.corpus_loader import LoadedCorpus, PaperMeta
from backend.app.relationships.store import RelationshipStore, schema_columns

MIG = REPO_ROOT / "backend/app/db/migrations/008_future_work_addressals.sql"


def _meta(pid, year):
    return PaperMeta(paper_id=pid, openalex_id=None, title=f"title {pid}", year=year,
                     doi=None, input_source="fulltext", domain_centrality="core",
                     provenance="snowball")


def _corpus():
    fw = FutureWork(id="fw1", paper_id="p_old", text="explore selective abstention")
    e_old = PaperExtraction(paper_id="p_old", claims=[], future_work=[fw])
    from backend.app.models import Claim
    e_new = PaperExtraction(paper_id="p_new", claims=[
        Claim(id="cnew", paper_id="p_new", text="we propose selective abstention",
              type="method", confidence=0.5)])
    papers = {"p_old": _meta("p_old", 2018), "p_new": _meta("p_new", 2022)}
    return LoadedCorpus(papers=papers, extractions={"p_old": e_old, "p_new": e_new},
                        claim_paper={"cnew": "p_new"}, claim_source={"cnew": "fulltext"})


def test_shortlist_records_citation_prior_and_later_only():
    corpus = _corpus()
    v = np.array([[1.0, 0.0]], dtype=np.float32)          # fw vector
    cv = np.array([[0.95, 0.31]], dtype=np.float32)        # claim ~0.95 cosine
    cv = cv / np.linalg.norm(cv)
    edges = [CitationEdge("p_new", "p_old")]               # p_new cites p_old
    cands = F.shortlist_candidates(corpus, ["fw1"], v, ["cnew"], cv, edges,
                                   shortlist_threshold=0.70, max_papers_per_fw=4)
    assert len(cands) == 1
    c = cands[0]
    assert c.from_paper_id == "p_old" and c.to_paper_id == "p_new"
    assert c.cites_source is True                          # citation prior recorded
    assert c.similarity >= 0.70


def test_shortlist_no_citation_when_no_edge():
    corpus = _corpus()
    v = np.array([[1.0, 0.0]], dtype=np.float32)
    cv = np.array([[0.95, 0.31]], dtype=np.float32); cv = cv / np.linalg.norm(cv)
    cands = F.shortlist_candidates(corpus, ["fw1"], v, ["cnew"], cv, [],
                                   shortlist_threshold=0.70, max_papers_per_fw=4)
    assert cands[0].cites_source is False


def test_shortlist_excludes_below_threshold():
    corpus = _corpus()
    v = np.array([[1.0, 0.0]], dtype=np.float32)
    cv = np.array([[0.0, 1.0]], dtype=np.float32)          # orthogonal -> below 0.70
    assert F.shortlist_candidates(corpus, ["fw1"], v, ["cnew"], cv, [],
                                  shortlist_threshold=0.70) == []


def test_parse_verdict_valid_and_bad():
    assert F.parse_verdict('{"label":"addressed","justification":"x","addressing_element":"y"}')[0] == "addressed"
    assert F.parse_verdict('{"label":"partial"}')[0] == "partial"
    assert F.parse_verdict("nope") is None
    assert F.parse_verdict('{"label":"banana"}') is None


def test_addressal_round_trip_and_drift(tmp_path: Path):
    c = F.AddressalCandidate("fw1", "p_old", "p_new", 2022, "T", "c1",
                             "we propose abstention", 0.81, True)
    a = F.to_addressal(c, "addressed", "does it", "the method", model_name="m", ph="h")
    store = RelationshipStore(root=tmp_path)
    store.save_addressals([a])
    back = store.load_addressals()
    assert back[0].label == "addressed" and back[0].cites_source is True
    assert back[0].similarity == 0.81 and back[0].detector_model == "m"
    # drift: Pydantic fields == ORM columns == migration DDL
    assert set(FutureWorkAddressal.model_fields) == schema_columns(FutureWorkAddressalRow)
    sql = MIG.read_text()
    m = re.search(r"CREATE TABLE IF NOT EXISTS future_work_addressals \((.*?)\);", sql, re.DOTALL)
    ddl = set()
    for line in m.group(1).splitlines():
        line = line.strip().rstrip(",")
        if line and not line.upper().startswith(("PRIMARY", "FOREIGN", "CONSTRAINT")):
            ddl.add(line.split()[0])
    assert ddl == schema_columns(FutureWorkAddressalRow), ddl ^ schema_columns(FutureWorkAddressalRow)
