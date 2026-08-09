"""Tests for the reusable scaling tool.

Two flavours:

1. Pure unit tests on the fixed-k lesson enforcement — feed the tool a
   fake scorer that hits its own ceiling, verify the caveat fires.

2. Reproduction check: run the tool on the actual 113-paper corpus and
   pin key numbers against the hand-run study in
   docs/findings/corpus-scaling-study.md. Any divergence here means one
   of the two — the doc or the tool — is wrong; the test message says
   which numbers to look at.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.reasoning.corpus_view import ReasoningCorpus
from backend.app.reasoning import scaling_tool as ST


# --------------------------------------------------------------------------
# Unit tests: bounded-yield detection (the fixed-k lesson)
# --------------------------------------------------------------------------

def _bounded_scorer(cap: int) -> ST.ScorerSpec:
    """Return a scorer that outputs min(N, cap) items — its ceiling is
    exactly `cap`. Used to test that the tool detects a parameter that
    bounds yield by construction."""
    return ST.ScorerSpec(
        name="bounded",
        fn=lambda c, **_: [None] * min(len(c.papers), cap),
        params={"cap": cap},
        bounded_yield=lambda p: p.get("cap"),
    )


class _FakePaper:
    """The tool only touches `.input_source` on paper metadata."""
    def __init__(self, input_source: str = "fulltext"):
        self.input_source = input_source


class _FakeCorpus:
    """Just enough of a ReasoningCorpus for the tool's subsample/run
    path. Uses the papers dict for len() and stratification only."""
    def __init__(self, N: int):
        self.papers = {f"P{i}": _FakePaper() for i in range(N)}


def _identity_subset(_corpus, keep: set[str]):
    """Bypass the heavy ReasoningCorpus subset — the bounded scorer only
    needs `len(sub.papers)`. Simulate a subsampled corpus by mutating a
    shallow copy of the papers dict."""
    sub = type("Sub", (), {})()
    sub.papers = {k: _corpus.papers[k] for k in keep if k in _corpus.papers}
    return sub


def test_bounded_scorer_without_scaling_gets_flagged():
    """A scorer whose parameters cap yield at 5, with no scale_with_n,
    must produce a caveat pointing at that ceiling."""
    fake = _FakeCorpus(50)
    scorer = _bounded_scorer(cap=5)
    report = ST.run(
        fake, corpus_name="fake", Ns=[10, 20, 30, 40, 50], draws=2,
        scorers=[scorer], subset_fn=_identity_subset,
    )
    c = report.curves[0]
    joined = " ".join(c.caveats)
    assert "parameter_bound" in joined, \
        f"expected fixed-parameter caveat, got: {c.caveats}"
    assert "_caps_yield_at_5" in joined, \
        f"caveat should name the ceiling (5) — got: {c.caveats}"


def test_bounded_scorer_with_scale_with_n_is_not_flagged():
    """The same scorer, but with the bounding parameter scaled with N,
    should NOT get the fixed-parameter warning — instead it should get
    the "parameter_scaled_with_N" note so the reader knows the curve
    reflects the scaled param, not the deployment default."""
    fake = _FakeCorpus(50)
    scorer = ST.ScorerSpec(
        name="bounded_but_scaled",
        fn=lambda c, **kw: [None] * min(len(c.papers), kw["cap"]),
        params={"cap": 5},
        scale_with_n={"cap": lambda N: N // 5},
        bounded_yield=lambda p: p.get("cap"),
    )
    report = ST.run(
        fake, corpus_name="fake", Ns=[10, 20, 30, 40, 50], draws=2,
        scorers=[scorer], subset_fn=_identity_subset,
    )
    c = report.curves[0]
    joined = " ".join(c.caveats)
    assert "parameter_scaled_with_N" in joined
    assert "parameter_bound" not in joined


# --------------------------------------------------------------------------
# All-zero → bound_only caveat, not silent absence
# --------------------------------------------------------------------------

def test_all_zero_scorer_gets_bound_caveat():
    """A scorer that always returns [] must NOT silently look like "true
    zero everywhere." The curve must carry a bound-only caveat."""
    fake = _FakeCorpus(50)
    empty = ST.ScorerSpec(name="always_zero", fn=lambda c, **_: [])
    report = ST.run(
        fake, corpus_name="fake", Ns=[10, 20, 50], draws=3,
        scorers=[empty], subset_fn=_identity_subset,
    )
    c = report.curves[0]
    joined = " ".join(c.caveats)
    assert "all_zeros:bound_only" in joined
    # And the slope is unmeasurable (log of zero is undefined).
    assert c.fit_confidence == "unmeasurable"
    assert c.slope is None


# --------------------------------------------------------------------------
# Fit confidence bands
# --------------------------------------------------------------------------

def test_slope_fit_confidence_bands():
    """`_fit_slope` on obvious inputs returns the expected band."""
    # 5 clean points on y = N^1.5 → high confidence
    pts_clean = [ST.CurvePoint(N=N, values=[N ** 1.5]) for N in (10, 20, 40, 80, 160)]
    slope, conf = ST._fit_slope(pts_clean)
    assert conf == "high"
    assert 1.4 < slope < 1.6

    # All-zero → unmeasurable, slope None
    pts_zero = [ST.CurvePoint(N=N, values=[0]) for N in (10, 20, 40)]
    slope, conf = ST._fit_slope(pts_zero)
    assert conf == "unmeasurable"
    assert slope is None

    # Single non-zero point → low confidence, no slope
    pts_sparse = [ST.CurvePoint(N=10, values=[0]),
                  ST.CurvePoint(N=20, values=[5]),
                  ST.CurvePoint(N=40, values=[0])]
    slope, conf = ST._fit_slope(pts_sparse)
    assert conf == "low"


# --------------------------------------------------------------------------
# Reproduction check: the tool must reproduce the hand-run study
# --------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(not (REPO / "data" / "relationships" / "claim_embeddings.npy").exists(),
                    reason="requires the full 113-paper reasoning corpus")
def test_reproduces_hand_run_scaling_study():
    """Run the tool over our 113-paper corpus and verify it reproduces
    the numbers pinned in docs/findings/corpus-scaling-study.md. If any
    of these assertions fails, one of the tool or the doc is wrong and
    the failure message says which pair to reconcile."""
    from backend.app.reasoning.corpus_view import load_reasoning_corpus
    corpus = load_reasoning_corpus()
    report = ST.run(corpus, corpus_name="llm-calibration-113")
    curves = {c.scorer: c for c in report.curves}

    # candidate curve: 36, 98, 119, 187, 256 (hand-run doc)
    cand = curves["contra_candidates"]
    means = [p.mean for p in cand.points]
    for actual, expected in zip(means, [36.0, 98.2, 119.2, 187.2, 256.0]):
        assert abs(actual - expected) < 0.05, \
            f"candidate curve drift: got {means}, doc says [36.0, 98.2, ...]"

    # confirmed = 0 everywhere, with bound
    conf = curves["contra_confirmed"]
    assert all(p.mean == 0 for p in conf.points)
    assert any("bound_only" in c for c in conf.caveats)

    # orphan_unaddressed: 20, 35, 45, 57, 63 (hand-run doc)
    orph = curves["orphaned_future_work"]
    orph_means = [p.mean for p in orph.points]
    for actual, expected in zip(orph_means, [19.8, 34.8, 45.0, 57.4, 63.0]):
        assert abs(actual - expected) < 0.05, \
            f"orphan curve drift: got {orph_means}"

    # persistent: 0.2, 0.6, 0.6, 1.0, 1.0
    persist = curves["persistent_limitations"]
    pm = [p.mean for p in persist.points]
    for actual, expected in zip(pm, [0.2, 0.6, 0.6, 1.0, 1.0]):
        assert abs(actual - expected) < 0.05, f"persistent drift: {pm}"

    # structural holes with scale_with_n=√N: [5.2, 13.2, 16.0, 19.2, 11.0]
    # exactly matches the hand-run k=√N row of the correction table.
    sh = curves["structural_holes"]
    sh_means = [p.mean for p in sh.points]
    for actual, expected in zip(sh_means, [5.2, 13.2, 16.0, 19.2, 11.0]):
        assert abs(actual - expected) < 0.1, f"structural-holes drift: {sh_means}"

    # log-log slope on candidates: linear regression gives ~1.77;
    # doc's endpoint-only fit gives 1.89. Documented divergence — assert
    # the regression form here and let the doc quote both.
    assert 1.7 < cand.slope < 1.85, \
        f"candidate slope drift from regression: {cand.slope}"


def test_cost_projection_grounded_at_reference_point():
    """The projection must anchor at the actual measured point, not do
    `pairs = N^slope` with an implicit intercept of 1 (which is what an
    early version did and produced $293 at N=800 vs the hand-run's $40)."""
    fake = _FakeCorpus(50)
    # candidate curve returning 10*N pairs (linear scale)
    scorer = ST.ScorerSpec(name="contra_candidates",
                           fn=lambda c, **_: [None] * (10 * len(c.papers)))
    report = ST.run(fake, corpus_name="fake", Ns=[10, 20, 50], draws=2,
                    scorers=[scorer], subset_fn=_identity_subset,
                    cost_target_Ns=[100])
    row = report.cost_projection[0]
    # At N=50 we measured 500 pairs; slope~1 → at N=100 expect ~1000
    assert 900 < row["estimated_contradiction_pairs"] < 1100, \
        f"projection ignored the reference point: {row}"
