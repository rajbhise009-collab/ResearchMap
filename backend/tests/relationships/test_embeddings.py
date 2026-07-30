"""Embedding provider interface + deterministic mock."""

from __future__ import annotations

import math

from backend.app.relationships.embeddings import MockEmbeddingClient, l2_normalize


def test_l2_normalize_unit_and_zero_safe():
    v = l2_normalize([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-6)
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]


def test_mock_is_deterministic_and_unit():
    m = MockEmbeddingClient(dim=64)
    a = m.embed(["same text"])[0]
    b = m.embed(["same text"])[0]
    assert a == b
    assert len(a) == 64
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, abs_tol=1e-5)


def test_mock_distinct_texts_differ():
    m = MockEmbeddingClient(dim=64)
    assert m.embed(["alpha"])[0] != m.embed(["beta"])[0]


def test_mock_batch_order_preserved():
    m = MockEmbeddingClient(dim=16)
    out = m.embed(["one", "two", "three"])
    assert len(out) == 3
    assert out[0] == m.embed(["one"])[0]
    assert out[2] == m.embed(["three"])[0]
