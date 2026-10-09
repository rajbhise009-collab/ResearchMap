"""Phase 6 pilot: the time-split machinery is deterministic, leak-free and
computes its statistics correctly. (Whether the engine predicts anything is
a finding, not a test: docs/findings/validation-pilot-2026-10.md.)"""
from __future__ import annotations

import math

import pytest

from backend.app.validation import time_split as T


def test_hypergeometric_tail_matches_direct_count():
    # 10 items, 3 successes, draw 4: P(X >= 2)
    want = sum(math.comb(3, i) * math.comb(7, 4 - i) for i in (2, 3)) / math.comb(10, 4)
    assert T._hypergeom_sf(2, 10, 3, 4) == pytest.approx(want)
    assert T._hypergeom_sf(0, 10, 3, 4) == pytest.approx(1.0)


@pytest.fixture(scope="module")
def frozen():
    from backend.app.reasoning.library_corpus import load_library_corpus
    rc = load_library_corpus("ml-fairness")
    return rc, T._frozen(rc, 2018)


def test_frozen_corpus_contains_nothing_after_the_freeze(frozen):
    rc, fz = frozen
    assert fz.papers and all(p.year <= 2018 for p in fz.papers.values())
    assert all(fz.claim_paper[c] in fz.papers for c in fz.claim_ids)
    assert all(a.to_paper_id in fz.papers and a.from_paper_id in fz.papers for a in fz.addressals)
    assert all(m.paper_id in fz.papers for _fw, m in fz.future_work)
    assert all(a in fz.papers and b in fz.papers for a, b in fz.citation_edges)
    assert len(fz.claim_ids) == len(fz.claim_vectors)


def test_run_is_deterministic():
    a = T.run("ml-fairness", 2018)
    b = T.run("ml-fairness", 2018)
    assert a.ranked == b.ranked and a.tau == b.tau and a.precision == b.precision
