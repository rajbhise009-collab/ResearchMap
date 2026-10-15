"""The pace of new (queued) libraries: config/growth.json
max_queued_builds_per_month (default 1) and min_weekly_growth_reserve_inr
(default ₹15), checked by backend/app/grow/queued.pace_check after the money
rule and before the free dry run. A queued build never cuts into the weekly
growth reserve, and at most N are started per calendar month."""
from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

import pytest

from backend.app.grow import queued

REPO = Path(__file__).resolve().parents[3]
CFG = {"max_per_month": 1, "min_weekly_reserve_inr": 15.0}
OCT = [{"slug": "nudge-effectiveness", "date": "2026-10-12"}]


def test_defaults_when_the_settings_are_absent(tmp_path):
    p = tmp_path / "growth.json"
    p.write_text(json.dumps({"paused": False}))
    assert queued.pace_config(p) == {"max_per_month": 1, "min_weekly_reserve_inr": 15.0}


def test_settings_are_read_from_config(tmp_path):
    p = tmp_path / "growth.json"
    p.write_text(json.dumps({"max_queued_builds_per_month": 2, "min_weekly_growth_reserve_inr": 20}))
    assert queued.pace_config(p) == {"max_per_month": 2, "min_weekly_reserve_inr": 20.0}


def test_committed_config_has_both_settings():
    """Both settings are in config/growth.json and valid (their defaults, 1
    and ₹15, are pinned by test_defaults_when_the_settings_are_absent; the
    offline e2e clone raises the monthly limit for its own mock world)."""
    c = json.loads((REPO / "config" / "growth.json").read_text())
    assert isinstance(c["max_queued_builds_per_month"], int) and c["max_queued_builds_per_month"] >= 1
    assert float(c["min_weekly_growth_reserve_inr"]) >= 15


def _check(ref, log=OCT, **kw):
    args = dict(proj_inr=10.0, available_inr=1000.0, growth_committed_inr=16.0, weeks_after=10)
    return queued.pace_check(ref=dt.date.fromisoformat(ref), cfg=CFG, log=log, **{**args, **kw})


def test_one_start_per_calendar_month():
    r = _check("2026-10-19")
    assert not r["ok"] and r["blocked_by"] == "month" and "nudge-effectiveness" in r["reason"]
    assert _check("2026-11-02")["ok"]                         # a new month
    two = {**CFG, "max_per_month": 2}
    assert queued.pace_check(proj_inr=10, available_inr=1000, growth_committed_inr=16, weeks_after=10,
                             ref=dt.date(2026, 10, 19), cfg=two, log=OCT)["ok"]


def test_never_cuts_into_the_weekly_growth_reserve():
    # Mon 19 Oct's real figures: available ₹179.05, growth ₹16.28, ego depletion ₹55.69, 10 weeks after
    r = _check("2026-11-02", available_inr=179.05, growth_committed_inr=16.28, proj_inr=55.69)
    assert not r["ok"] and r["blocked_by"] == "reserve"
    assert r["reserve_needed_inr"] == 150.0 and r["left_after_inr"] < 150.0
    # exactly at the reserve passes; one paisa under does not
    need = 15.0 * 10
    ok = _check("2026-11-02", available_inr=need + 16.0 + 10.0 * 1.5, growth_committed_inr=16.0, proj_inr=10.0)
    under = _check("2026-11-02", available_inr=need + 16.0 + 10.0 * 1.5 - 0.01, growth_committed_inr=16.0,
                   proj_inr=10.0)
    assert ok["ok"] and not under["ok"]


def test_any_allowed_build_leaves_at_least_the_reserve():
    rnd = random.Random(7)
    for _ in range(2000):
        kw = dict(proj_inr=rnd.uniform(0, 150), available_inr=rnd.uniform(0, 600),
                  growth_committed_inr=rnd.uniform(0, 60), weeks_after=rnd.randint(0, 12))
        r = _check("2026-11-02", log=[], **kw)
        if r["ok"]:
            left = kw["available_inr"] - kw["growth_committed_inr"] - kw["proj_inr"] * 1.5
            assert left >= 15.0 * kw["weeks_after"] - 1e-6


def test_record_start_is_counted(tmp_path):
    p = tmp_path / "queued_builds.json"
    queued.record_start("growth-mindset", "2026-11-02", "test", path=p)
    log = queued.builds_log(p)
    assert log[-1]["slug"] == "growth-mindset"
    r = queued.pace_check(proj_inr=1, available_inr=1000, growth_committed_inr=0, weeks_after=1,
                          ref=dt.date(2026, 11, 9), cfg=CFG, log=log)
    assert not r["ok"] and r["blocked_by"] == "month"


def test_monday_19_october_starts_no_queued_build():
    """Monday 19 Oct as it stood when the limits were added (given, not read,
    so the test never depends on later data): Nudges started on 12 Oct;
    available ₹179.05, growth budget ₹16.28, 11 weeks left; default limits.
    October's one build is used; and either queued library would cut into
    the ₹15 weekly reserve anyway."""
    ref = dt.date(2026, 10, 19)
    defaults = {"max_per_month": queued.DEFAULT_MAX_PER_MONTH,
                "min_weekly_reserve_inr": queued.DEFAULT_MIN_WEEKLY_RESERVE_INR}
    for slug, proj in (("ego-depletion", 55.69), ("growth-mindset", 42.59)):
        kw = dict(proj_inr=proj, available_inr=179.05, growth_committed_inr=16.28, weeks_after=10, ref=ref,
                  cfg=defaults)
        r = queued.pace_check(**kw, log=OCT)
        assert not r["ok"] and r["blocked_by"] == "month", (slug, r)
        r2 = queued.pace_check(**kw, log=[])                      # even with no start this month
        assert not r2["ok"] and r2["blocked_by"] == "reserve", (slug, r2)
        assert r2["weekly_growth_after_inr"] < 15


def test_the_committed_start_log_records_nudges():
    log = queued.builds_log()
    assert any(e["slug"] == "nudge-effectiveness" and e["date"] == "2026-10-12" for e in log)
    assert all({"slug", "date"} <= set(e) for e in log)


def test_the_run_checks_pace_before_the_dry_run_and_logs_each_start():
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    block = src[src.index("queued_start_decision(weight") if "queued_start_decision(weight" in src
                else src.index("allowed, why = queued_start_decision("):]
    assert block.index("queued.pace_check(") < block.index("dry_gate(") < block.index("queued.start(")
    assert block.index("queued.start(") < block.index("queued.record_start(")
