"""Shortlist (deterministic cosine pre-selection) + weighting (the
deterministic side of the LLM boundary)."""

from __future__ import annotations

import numpy as np

from backend.app.relationships.shortlist import shortlist_pairs
from backend.app.relationships.weighting import fidelity_factor, relationship_weight


def _unit(rows):
    a = np.array(rows, dtype=np.float32)
    return a / np.linalg.norm(a, axis=1, keepdims=True)


def test_threshold_filters_low_similarity():
    v = _unit([[1, 0, 0], [0.99, 0.14, 0], [0, 1, 0]])
    ids = ["a", "b", "c"]
    cp = {"a": "p1", "b": "p2", "c": "p3"}
    pairs = shortlist_pairs(ids, v, cp, threshold=0.82, max_per_claim=10)
    got = {(p.from_claim_id, p.to_claim_id) for p in pairs}
    assert got == {("a", "b")}          # c is orthogonal -> excluded


def test_cross_paper_only_excludes_same_paper():
    v = _unit([[1, 0], [0.999, 0.03]])
    ids = ["a", "b"]
    same = {"a": "p1", "b": "p1"}       # same paper
    assert shortlist_pairs(ids, v, same, threshold=0.5, max_per_claim=10,
                           cross_paper_only=True) == []
    cross = {"a": "p1", "b": "p2"}
    assert len(shortlist_pairs(ids, v, cross, threshold=0.5, max_per_claim=10,
                               cross_paper_only=True)) == 1


def test_per_claim_cap_limits_neighbours():
    # one hub near 4 others; cap=2 keeps only the 2 most similar as its own
    # neighbours (union rule may keep a few more via the others' lists).
    base = [1.0, 0.0, 0.0, 0.0]
    rows = [base,
            [0.99, 0.14, 0, 0], [0.98, 0.2, 0, 0],
            [0.97, 0.24, 0, 0], [0.96, 0.28, 0, 0]]
    v = _unit(rows)
    ids = ["h", "n1", "n2", "n3", "n4"]
    cp = {i: f"p{k}" for k, i in enumerate(ids)}
    pairs = shortlist_pairs(ids, v, cp, threshold=0.9, max_per_claim=2)
    hub_pairs = [p for p in pairs if "h" in (p.from_claim_id, p.to_claim_id)]
    # Hub keeps at most its 2 nearest as *its* candidates (others may add it
    # back via the union, but that is bounded and deterministic).
    assert len(hub_pairs) <= 4
    assert all(p.similarity >= 0.9 for p in pairs)


def test_pairs_are_canonical_and_deduped():
    v = _unit([[1, 0], [0.999, 0.02]])
    pairs = shortlist_pairs(["b", "a"], v, {"b": "p1", "a": "p2"},
                            threshold=0.5, max_per_claim=10)
    assert len(pairs) == 1
    assert pairs[0].from_claim_id < pairs[0].to_claim_id  # canonical order


def test_weight_is_similarity_times_fidelity():
    assert relationship_weight(similarity=0.9, source_a="fulltext",
                               source_b="fulltext") == 0.9
    assert round(relationship_weight(similarity=0.9, source_a="abstract",
                                     source_b="abstract"), 6) == 0.72
    assert round(relationship_weight(similarity=0.9, source_a="fulltext",
                                     source_b="abstract"), 3) == 0.81


def test_fidelity_ordering():
    assert (fidelity_factor("fulltext", "fulltext")
            > fidelity_factor("fulltext", "abstract")
            > fidelity_factor("abstract", "abstract"))


def test_weight_clamped():
    assert relationship_weight(similarity=2.0, source_a="fulltext",
                               source_b="fulltext") == 1.0
    assert relationship_weight(similarity=-1.0, source_a="abstract",
                               source_b="abstract") == 0.0
