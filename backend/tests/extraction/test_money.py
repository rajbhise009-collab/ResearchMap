"""config/money.json is the only spending limit; enforced by SpendLedger."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from backend.app.extraction import money
from backend.app.extraction.spend_ledger import SpendCapExceededError, SpendLedger


def _cfg(tmp_path, **kw):
    c = {"account_total_inr": 100, "safety_buffer_inr": 10, "console_spent_inr": None,
         "console_spent_date": None, "growth_horizon_weeks": 12, "growth_horizon_start": "2026-10-12",
         "weekly_budget_max_inr": 60, "queued_domain_reserve_weeks": 4, **kw}
    p = tmp_path / "money.json"
    p.write_text(json.dumps(c))
    return p, c


def _ledger(tmp_path, entries):
    p = tmp_path / "ledger.json"
    usd = sum(e["cost_inr"] for e in entries) / 84.0
    p.write_text(json.dumps({"cap_inr": 5000, "cap_usd": 5000 / 84, "fx_usd_to_inr": 84.0,
                             "cumulative_usd": usd, "cumulative_inr": usd * 84, "entries": entries}))
    return p


def test_ceiling_is_account_minus_buffer_on_the_ledger(tmp_path):
    _p, c = _cfg(tmp_path)
    assert money.ceiling_inr(c) == 90
    assert money.remaining_inr(c, 30.0, []) == 60


def test_console_figure_replaces_ledger_up_to_its_date(tmp_path):
    _p, c = _cfg(tmp_path, console_spent_inr=20, console_spent_date="2026-10-01")
    before = dt.datetime(2026, 9, 30, tzinfo=money.IST).timestamp()
    after = dt.datetime(2026, 10, 3, tzinfo=money.IST).timestamp()
    entries = [{"ts": before, "cost_inr": 30.0}, {"ts": after, "cost_inr": 5.0}]
    assert money.remaining_inr(c, 35.0, entries) == pytest.approx(90 - 20 - 5)
    with pytest.raises(ValueError):
        money.remaining_inr({**c, "console_spent_date": None}, 35.0, entries)


def test_enforced_at_call_time(tmp_path, monkeypatch):
    mp, _c = _cfg(tmp_path)
    lp = _ledger(tmp_path, [{"ts": 1.0, "cost_inr": 89.0, "cost_usd": 89.0 / 84, "stage": "x"}])
    monkeypatch.setenv("SPEND_LEDGER_PATH", str(lp))
    monkeypatch.setenv("MONEY_CONFIG_PATH", str(mp))
    SpendLedger.reset_for_tests()
    led = SpendLedger(lp)
    assert led.snapshot()["cap_inr"] == pytest.approx(90.0)
    with pytest.raises(SpendCapExceededError):
        led.check_headroom(prompt_tokens_est=2_000_000, output_tokens_est=2_000_000, batch=False, stage="t")


def test_weekly_pacing_and_queued_affordability(tmp_path):
    _p, c = _cfg(tmp_path)
    assert money.weeks_left(c, dt.date(2026, 10, 12)) == 12
    assert money.weeks_left(c, dt.date(2027, 6, 1)) == 1
    assert money.weekly_budget_inr(120.0, c, dt.date(2026, 10, 12)) == 10.0
    assert money.weekly_budget_inr(5000.0, c, dt.date(2026, 10, 12)) == 60.0   # capped
    assert money.queued_affordable(20.0, 70.0, 10.0, c)          # 30 + 40 <= 70
    assert not money.queued_affordable(21.0, 70.0, 10.0, c)
