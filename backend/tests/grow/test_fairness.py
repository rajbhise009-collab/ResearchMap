"""No library is starved by a fixed order (weekly-grow run #5 gave Social
media 0 papers and skipped its future-work matching because the libraries
before it used the budget)."""
from __future__ import annotations

import datetime as dt

import pytest

from backend.app.grow import core

LIBS = ["diet-and-mortality", "ml-fairness", "social-media-teen-mental-health"]


@pytest.fixture()
def fair(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "fairness_path", lambda: tmp_path / "fairness.json")
    return tmp_path / "fairness.json"


def _prepared(n=5, inr=1.0):
    return {s: {"items": [{"inr": inr, "entry": {"wid": f"{s}-{i}"}} for i in range(n)], "dropped": {}}
            for s in LIBS}


def test_a_budget_for_one_paper_a_week_rotates_through_every_library(fair):
    seen = []
    for week in range(6):
        ref = dt.date(2026, 10, 12) + dt.timedelta(weeks=week)
        prep = _prepared()
        order = core.fair_order(LIBS, "extraction", papers={s: 100 for s in LIBS},
                                candidates={s: 5 for s in LIBS})
        picked = core.allocate(prep, core.Budget(1.5), {s: 100 for s in LIBS}, order)   # fits exactly 1 paper
        got = [s for s in LIBS if picked[s]]
        assert len(got) == 1
        seen.append(got[0])
        for s in LIBS:
            core.record_fairness(s, "extraction", served=bool(picked[s]), ref=ref)
    # every library served within any 3 consecutive weeks; none starved
    for i in range(len(seen) - 2):
        assert set(seen[i:i + 3]) == set(LIBS), seen


def test_owed_follow_on_goes_first_next_week(fair):
    ref = dt.date(2026, 10, 12)
    for s in LIBS:
        core.record_fairness(s, "followon", served=True, ref=ref)
    # social media's future-work matching was skipped for budget
    core.record_fairness(LIBS[2], "followon", served=False, ref=ref, owed=["fw_match"])
    assert core.fair_order(LIBS, "followon")[0] == LIBS[2]
    # once done, the owed mark clears
    core.record_fairness(LIBS[2], "followon", served=True, ref=ref + dt.timedelta(weeks=1), owed=[])
    assert core.fair_order(LIBS, "followon")[-1] == LIBS[2]


def test_followon_owed_reads_skipped_steps():
    assert core.followon_owed({"fw_match": "skipped: over weekly budget", "disagreement_unchecked_pairs": 3}) == \
        ["fw_match", "disagreement"]
    assert core.followon_owed({"fw_match": {"n": 2}, "disagreement_unchecked_pairs": 0}) == []


def test_never_served_library_goes_first(fair):
    core.record_fairness(LIBS[0], "extraction", served=True, ref=dt.date(2026, 10, 12))
    core.record_fairness(LIBS[1], "extraction", served=True, ref=dt.date(2026, 10, 12))
    assert core.fair_order(LIBS, "extraction")[0] == LIBS[2]
