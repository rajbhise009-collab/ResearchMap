"""Ledger audit: only entries with the exact mock-test signature in a burst
of exactly 10 inside one second are proven mock; the correction is appended
once and never edits history. Temp ledger only."""

from __future__ import annotations

import copy
import json

from backend.app.corpus import ledger_audit as A
from backend.app.extraction.spend_ledger import SpendLedger


def _e(ts, stage="unknown", p=5, c=3, t=0, usd=0.00003):
    return {"ts": ts, "stage": stage, "model": "gemini-3.6-flash", "batch": False,
            "prompt_tokens": p, "candidates_tokens": c, "thoughts_tokens": t,
            "billed_output_tokens": c + t, "cost_usd": usd, "cost_inr": usd * 84}


def _entries():
    real = [_e(0.0, stage="extract_diet", p=900, c=1200, usd=0.01)]
    burst = [_e(100.0 + i * 0.002) for i in range(10)]          # proven
    short = [_e(200.0 + i * 0.002) for i in range(9)]           # 9: not proven
    slow = [_e(300.0 + i * 0.5) for i in range(10)]             # 4.5 s: not proven
    odd = [_e(400.0, p=6)]                                      # wrong signature
    return real + burst + short + slow + odd


def test_only_exact_bursts_of_ten_are_proven():
    proven, bursts = A.proven_mock_indices(_entries())
    assert proven == list(range(1, 11))
    assert bursts[0]["proven_mock"] and not any(b["proven_mock"] for b in bursts[1:])


def test_correction_appended_once_and_history_untouched():
    led = SpendLedger.load()
    entries = _entries()
    led.path.write_text(json.dumps({"cap_inr": 950, "cap_usd": 950 / 84,
                                    "fx_usd_to_inr": 84, "entries": entries}))
    before = copy.deepcopy(entries)
    e = A.append_correction(led)
    assert e["cost_usd"] == -sum(x["cost_usd"] for x in before[1:11])
    assert A.append_correction(led) is None, "second run is a no-op"
    after = led._read().entries
    assert after[:len(before)] == before and len(after) == len(before) + 1
    rep = A.audit(after)
    assert rep["correction_present"]
    assert abs(rep["corrected_cumulative_inr"]
               - (rep["raw_cumulative_inr"] - rep["unknown_stage"]["proven_mock_inr"])) < 1e-6


def test_freeze_cap_refuses_any_new_spend():
    led = SpendLedger.load()
    led.path.write_text(json.dumps({"cap_inr": 950, "cap_usd": 950 / 84,
                                    "fx_usd_to_inr": 84, "entries": _entries()}))
    A.freeze_cap(led)
    assert led.snapshot()["remaining_inr"] == 0.0
