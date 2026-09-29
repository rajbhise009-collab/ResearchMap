"""Tests for the persistent spend ledger.

These use a temp-path ledger so they don't touch the real
`data/spend_ledger.json`. The env-var disable (SPEND_LEDGER_DISABLED=1)
is exercised too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.extraction.spend_ledger import (
    CAP_INR,
    CAP_USD,
    FX_USD_TO_INR,
    SpendCapExceededError,
    SpendLedger,
)


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    """Isolated ledger; reset the singleton and point at tmp_path."""
    monkeypatch.delenv("SPEND_LEDGER_DISABLED", raising=False)
    SpendLedger.reset_for_tests()
    ledger = SpendLedger(path=tmp_path / "ledger.json")
    return ledger


def test_fresh_ledger_reports_full_headroom(tmp_ledger):
    snap = tmp_ledger.snapshot()
    assert snap["n_calls"] == 0
    assert snap["cumulative_usd"] == 0.0
    assert snap["remaining_usd"] == pytest.approx(CAP_USD)
    assert snap["remaining_inr"] == pytest.approx(CAP_INR)


def test_check_headroom_allows_call_that_fits(tmp_ledger):
    # ~150k input + 5k output ≈ $0.26 — well under the cap.
    tmp_ledger.check_headroom(
        prompt_tokens_est=150_000, output_tokens_est=5_000,
        batch=False, stage="extract",
    )


def test_check_headroom_refuses_call_that_would_exceed_cap(tmp_ledger):
    # 100M input tokens obviously blows the cap.
    with pytest.raises(SpendCapExceededError) as exc_info:
        tmp_ledger.check_headroom(
            prompt_tokens_est=100_000_000, output_tokens_est=5_000,
            batch=False, stage="extract",
        )
    err = exc_info.value
    assert err.projected_usd > CAP_USD
    assert err.cumulative_usd == 0.0


def test_record_persists_across_reloads(tmp_ledger, tmp_path):
    tmp_ledger.record(
        stage="extract_diet_W123", model="gemini-3.6-flash", batch=False,
        prompt_tokens=15_000, candidates_tokens=1_800, thoughts_tokens=2_200,
    )
    # Re-open from disk — different instance.
    other = SpendLedger(path=tmp_path / "ledger.json")
    snap = other.snapshot()
    assert snap["n_calls"] == 1
    # 15k in @ $1.50/M + (1800+2200) out @ $7.50/M = 0.0225 + 0.030 = $0.0525
    assert snap["cumulative_usd"] == pytest.approx(0.0525)


def test_thoughts_tokens_are_billed(tmp_ledger):
    """Regression: earlier accounting counted only candidatesTokenCount
    and under-reported spend by ~40%. Ledger MUST count thoughts too."""
    tmp_ledger.record(
        stage="extract", model="gemini-3.6-flash", batch=False,
        prompt_tokens=0, candidates_tokens=1_000, thoughts_tokens=1_000,
    )
    snap = tmp_ledger.snapshot()
    # 2000 output tokens @ $7.50/M = $0.015
    assert snap["cumulative_usd"] == pytest.approx(0.015)


def test_headroom_check_after_recording_uses_cumulative(tmp_ledger):
    """Simulate having burned ~$10 already; a next call whose projection
    would push past cap must refuse."""
    # Force cumulative near the cap by inflating a fake bill.
    tmp_ledger.record(
        stage="prior", model="gemini-3.6-flash", batch=False,
        prompt_tokens=0, candidates_tokens=int((CAP_USD - 0.01) * 1e6 / 7.50),
        thoughts_tokens=0,
    )
    # Now a tiny call whose projection is $0.02 would push cumulative past cap.
    with pytest.raises(SpendCapExceededError):
        tmp_ledger.check_headroom(
            prompt_tokens_est=10_000, output_tokens_est=1_000,
            batch=False, stage="next_extract",
        )


def test_env_disable_skips_guard(tmp_ledger, monkeypatch):
    monkeypatch.setenv("SPEND_LEDGER_DISABLED", "1")
    # 100M tokens would normally raise; disabled → passes silently.
    tmp_ledger.check_headroom(
        prompt_tokens_est=100_000_000, output_tokens_est=5_000,
        batch=False, stage="test",
    )


def test_stage_breakdown_in_snapshot(tmp_ledger):
    for stage in ("extract_diet", "extract_diet", "extract_fairness",
                  "contradiction_diet"):
        tmp_ledger.record(
            stage=stage, model="gemini-3.6-flash", batch=False,
            prompt_tokens=1_000, candidates_tokens=100, thoughts_tokens=100,
        )
    snap = tmp_ledger.snapshot()
    by = snap["by_stage"]
    assert by["extract_diet"]["calls"] == 2
    assert by["extract_fairness"]["calls"] == 1
    assert by["contradiction_diet"]["calls"] == 1
    assert snap["n_calls"] == 4


def test_ledger_file_carries_fx_rate_and_cap(tmp_ledger):
    """A reader opening ledger.json must see the enforced numbers."""
    tmp_ledger.record(
        stage="t", model="m", batch=False,
        prompt_tokens=100, candidates_tokens=100, thoughts_tokens=100,
    )
    d = json.loads(tmp_ledger.path.read_text())
    assert d["cap_inr"] == CAP_INR
    assert d["cap_usd"] == pytest.approx(CAP_USD)
    assert d["fx_usd_to_inr"] == FX_USD_TO_INR
    assert d["cumulative_usd"] > 0
