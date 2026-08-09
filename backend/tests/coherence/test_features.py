"""Tests for backend.app.coherence.features.

These pin the feature math on small hand-verifiable fixtures so future
changes to the composite scoring can't silently drift the individual
components. The composite scoring (contested_score / method_transfer_
score) is a hypothesis and is deliberately not asserted to any
particular value — see docs/findings/domain-coherence-predictor.md for
why. But it IS asserted to be deterministic and bounded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.coherence import features as F


# --------------------------------------------------------------------------
# Fixtures — tiny hand-built OpenAlex-shaped records.
# --------------------------------------------------------------------------

def _rec(id_: str, *, year: int, refs: list[str] | None = None,
         type_: str = "article", venue: str | None = None,
         title: str = "Paper") -> dict:
    return {
        "id": f"https://openalex.org/{id_}",
        "publication_year": year,
        "type": type_,
        "referenced_works": [f"https://openalex.org/{r}" for r in (refs or [])],
        "primary_location": {"source": {"id": venue}} if venue else None,
        "display_name": title,
    }


# --------------------------------------------------------------------------
# Reference-rate: a hand-crackable arithmetic case.
# --------------------------------------------------------------------------

def test_intracorpus_reference_rate_hand_check():
    """3 papers; W1 cites {W2, X}, W2 cites {W1}, W3 cites nothing.
    Intra-corpus references / all references, averaged over papers WITH
    at least one reference:
      W1: 1/2 = 0.5   (W2 in corpus, X not)
      W2: 1/1 = 1.0
      W3: skipped
    → mean = 0.75"""
    corpus = [
        _rec("W1", year=2020, refs=["W2", "X999"]),
        _rec("W2", year=2020, refs=["W1"]),
        _rec("W3", year=2020, refs=[]),
    ]
    assert F.intracorpus_reference_rate(corpus) == pytest.approx(0.75)


def test_intracorpus_reference_rate_empty():
    assert F.intracorpus_reference_rate([]) == 0.0
    assert F.intracorpus_reference_rate([_rec("W1", year=2020, refs=[])]) == 0.0


# --------------------------------------------------------------------------
# Reciprocity: distinguish "loops present" from "loops absent".
# --------------------------------------------------------------------------

def test_reciprocity_zero_when_no_loops():
    corpus = [_rec("W1", year=2020, refs=["W2"]),
              _rec("W2", year=2020, refs=[])]
    assert F.citation_reciprocity(corpus) == 0.0


def test_reciprocity_positive_when_loop_present():
    """4 directed edges, 2 of them reciprocated ⇒ 0.5."""
    corpus = [
        _rec("W1", year=2020, refs=["W2", "W3"]),  # W1→W2, W1→W3
        _rec("W2", year=2020, refs=["W1"]),        # W2→W1  (reciprocal of W1→W2)
        _rec("W3", year=2020, refs=[]),
    ]
    # Edges: (W1,W2), (W1,W3), (W2,W1). Reciprocated: (W1,W2) & (W2,W1) ⇒ 2 of 3.
    assert F.citation_reciprocity(corpus) == pytest.approx(2 / 3)


# --------------------------------------------------------------------------
# Modularity: known cases.
# --------------------------------------------------------------------------

def test_modularity_zero_on_empty_graph():
    """No edges → the local-moving pass has nothing to move; return 0.0."""
    corpus = [_rec(f"W{i}", year=2020, refs=[]) for i in range(5)]
    assert F.citation_modularity(corpus) == 0.0


def test_modularity_positive_on_clear_two_cluster_graph():
    """Two triangles with no edge between them: perfectly modular."""
    corpus = [
        _rec("A1", year=2020, refs=["A2", "A3"]),
        _rec("A2", year=2020, refs=["A1", "A3"]),
        _rec("A3", year=2020, refs=["A1", "A2"]),
        _rec("B1", year=2020, refs=["B2", "B3"]),
        _rec("B2", year=2020, refs=["B1", "B3"]),
        _rec("B3", year=2020, refs=["B1", "B2"]),
    ]
    q = F.citation_modularity(corpus)
    # Newman: two equal cliques of size 3 → Q ≈ 0.5. Accept any value
    # above 0.4 (greedy can undershoot slightly).
    assert q > 0.4, f"expected two-clique modularity > 0.4, got {q}"


def test_modularity_deterministic_across_runs():
    """The greedy local-moving pass must produce the same Q every time —
    no dict iteration order, no randomness."""
    corpus = [
        _rec("A1", year=2020, refs=["A2", "A3"]),
        _rec("A2", year=2020, refs=["A1"]),
        _rec("A3", year=2020, refs=["A1"]),
        _rec("B1", year=2020, refs=["B2"]),
        _rec("B2", year=2020, refs=["B1"]),
    ]
    q1 = F.citation_modularity(corpus)
    q2 = F.citation_modularity(corpus)
    q3 = F.citation_modularity(corpus)
    assert q1 == q2 == q3


# --------------------------------------------------------------------------
# Review ratio, venue concentration, term-vector spread.
# --------------------------------------------------------------------------

def test_review_ratio_counts_both_signals():
    """Either OpenAlex `type == 'review'` OR a title matching the hint
    pattern counts; the fraction is over all papers."""
    corpus = [
        _rec("W1", year=2020, title="Foo bar", type_="review"),
        _rec("W2", year=2020, title="A survey of X"),
        _rec("W3", year=2020, title="Ordinary paper"),
        _rec("W4", year=2020, title="Empirical evaluation of Y"),
    ]
    assert F.review_ratio(corpus) == pytest.approx(0.5)


def test_venue_concentration_hhi():
    """Two venues at 3:1 split → 0.75² + 0.25² = 0.625."""
    corpus = [
        _rec("W1", year=2020, venue="V1"),
        _rec("W2", year=2020, venue="V1"),
        _rec("W3", year=2020, venue="V1"),
        _rec("W4", year=2020, venue="V2"),
    ]
    assert F.venue_concentration(corpus) == pytest.approx(0.625)


def test_venue_concentration_ignores_missing_venues():
    """Papers without a venue (arXiv preprints without published record)
    drop from the denominator so preprint-heavy fields aren't penalised."""
    corpus = [
        _rec("W1", year=2020, venue="V1"),
        _rec("W2", year=2020, venue="V1"),
        _rec("W3", year=2020, venue=None),  # dropped
    ]
    assert F.venue_concentration(corpus) == pytest.approx(1.0)


def test_term_vector_spread_bounds():
    """Two identical titles → Jaccard distance 0. Two disjoint → 1."""
    same = [
        _rec("W1", year=2020, title="Fast attention transformer"),
        _rec("W2", year=2020, title="Fast attention transformer"),
    ]
    assert F.term_vector_spread(same) == pytest.approx(0.0)

    disjoint = [
        _rec("W1", year=2020, title="apple banana cherry"),
        _rec("W2", year=2020, title="xylophone yak zebra"),
    ]
    assert F.term_vector_spread(disjoint) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Composite scores: bounded, deterministic, but NOT asserted to particular values.
# --------------------------------------------------------------------------

def test_composite_scores_bounded_and_deterministic():
    corpus = [
        _rec("W1", year=2020, refs=["W2"], title="A survey of foo"),
        _rec("W2", year=2020, refs=["W1"], title="Bar"),
        _rec("W3", year=2020, refs=[], title="Baz"),
    ]
    f = F.features(corpus)
    v1 = F.verdict(f)
    v2 = F.verdict(f)
    assert v1 == v2  # deterministic
    for k in ("contested_score", "method_transfer_score"):
        assert 0.0 <= v1[k] <= 1.0, f"{k} out of [0,1]: {v1[k]}"


def test_verdict_carries_the_hypothesis_caveat():
    """Every verdict MUST carry the "n=1, not validated" caveat — if the
    caveat is ever accidentally removed, this test catches it."""
    f = F.features([_rec("W1", year=2020, refs=[])])
    v = F.verdict(f)
    assert "n=1" in v["caveat"] or "not validated" in v["caveat"].lower()
    assert "hypothesis" in v["caveat"].lower()


# --------------------------------------------------------------------------
# On the real cached OpenAlex fetch (skipped if the cache isn't present).
# --------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[3]
CACHE = REPO / "data" / "coherence"


@pytest.mark.skipif(not (CACHE / "llm-calibration" / "openalex.json").exists(),
                    reason="live-fetch cache not present")
def test_llm_calibration_features_within_expected_ranges():
    """The measured domain — features shouldn't drift silently. If OpenAlex
    reshapes their response or a feature function changes, this catches
    it. Uses ranges wide enough to survive minor OpenAlex churn."""
    payload = json.loads((CACHE / "llm-calibration" / "openalex.json").read_text())
    f = F.features(payload["results"])
    assert f["n_papers"] == 100
    assert 0.01 < f["intracorpus_reference_rate"] < 0.10
    assert 0.10 < f["review_ratio"] < 0.30
    assert 0.20 < f["citation_modularity"] < 0.55
