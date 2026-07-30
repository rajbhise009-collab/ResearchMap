"""Pairwise contradiction detection — the LLM boundary. The LLM names a
pair's relationship; the weight stays deterministic code."""

from __future__ import annotations

from backend.app.models import Claim, PaperExtraction
from backend.app.relationships.contradiction import (
    build_pair_prompt, detect_relationships, parse_verdict, prompt_hash,
)
from backend.app.relationships.corpus_loader import LoadedCorpus
from backend.app.relationships.shortlist import CandidatePair


def _corpus():
    e1 = PaperExtraction(paper_id="p1", claims=[
        Claim(id="a", paper_id="p1", text="X improves calibration",
              type="finding", confidence=0.9)])
    e2 = PaperExtraction(paper_id="p2", claims=[
        Claim(id="b", paper_id="p2", text="X does not improve calibration",
              type="finding", confidence=0.1)])
    return LoadedCorpus(papers={}, extractions={"p1": e1, "p2": e2},
                        claim_paper={"a": "p1", "b": "p2"},
                        claim_source={"a": "fulltext", "b": "fulltext"})


class _ScriptLLM:
    name = "script"

    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def generate(self, prompt, *, validate=None):
        self.calls += 1
        return self.reply


def test_parse_verdict_valid_and_malformed():
    assert parse_verdict('{"relationship":"contradicts","explanation":"x"}').relationship == "contradicts"
    assert parse_verdict('{"relationship":"none"}').relationship == "none"
    assert parse_verdict("not json") is None
    assert parse_verdict('{"relationship":"banana"}') is None
    assert parse_verdict('{"explanation":"no rel key"}') is None


def test_prompt_contains_both_claims_and_no_format_error():
    p = build_pair_prompt(text_a="A text", text_b="B text",
                          paper_a="p1", paper_b="p2")
    assert "A text" in p and "B text" in p and "p1" in p and "p2" in p


def test_contradiction_persisted_with_provenance_and_det_weight():
    corpus = _corpus()
    pairs = [CandidatePair("a", "b", 0.9)]
    llm = _ScriptLLM('{"relationship":"contradicts","explanation":"opposite"}')
    rels, stats = detect_relationships(corpus, pairs, llm, model_name="m")
    assert len(rels) == 1
    r = rels[0]
    assert r.type == "contradicts"
    assert r.weight == 0.9                 # 0.9 sim x 1.0 (both fulltext), code-computed
    assert r.from_paper_id == "p1" and r.to_paper_id == "p2"
    assert r.detector_model == "m" and r.prompt_hash == prompt_hash()
    assert r.evidence_note == "opposite"
    assert stats["contradicts"] == 1 and stats["persisted"] == 1


def test_none_verdict_persists_nothing():
    corpus = _corpus()
    pairs = [CandidatePair("a", "b", 0.9)]
    llm = _ScriptLLM('{"relationship":"none","explanation":"different constructs"}')
    rels, stats = detect_relationships(corpus, pairs, llm, model_name="m")
    assert rels == []
    assert stats["none"] == 1 and stats["persisted"] == 0


def test_malformed_response_counted_not_crashed():
    corpus = _corpus()
    pairs = [CandidatePair("a", "b", 0.9)]
    llm = _ScriptLLM("garbage")
    rels, stats = detect_relationships(corpus, pairs, llm, model_name="m")
    assert rels == []
    assert stats["malformed"] == 1
