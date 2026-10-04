"""Stage-level spend gate: projection recorded, x2 (classification) / x1.5
(extraction) refusal against remaining ceiling, and the 1.5x per-call
overrun halt. Fake clients and a temp ledger only — no network."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.app.corpus import multi_domain_reason as R
from backend.app.extraction import spend_gate as G
from backend.app.extraction.spend_ledger import SpendLedger
from backend.app.models import Claim, PaperExtraction


def _ledger_with(cap_inr: float, spent_inr: float = 0.0) -> SpendLedger:
    led = SpendLedger.load()
    led.path.write_text(json.dumps({
        "cap_inr": cap_inr, "cap_usd": cap_inr / 84.0, "fx_usd_to_inr": 84.0,
        "entries": ([{"stage": "prior", "cost_usd": spent_inr / 84.0,
                      "cost_inr": spent_inr}] if spent_inr else []),
    }))
    return led


def _projections() -> list[dict]:
    p = Path(os.environ["SPEND_PROJECTIONS_PATH"])
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_preflight_records_projection_and_allows_when_padded_fits():
    _ledger_with(cap_inr=100.0, spent_inr=60.0)          # remaining 40
    row = G.preflight(stage="s", projected_inr=19.0, n_calls=10,
                      multiplier=G.CLASSIFICATION_GATE_MULT)   # 38 <= 40
    assert row["allowed"] is True
    assert _projections()[-1]["padded_inr"] == 38.0


def test_classification_gate_refuses_when_projection_x2_exceeds_remaining():
    _ledger_with(cap_inr=100.0, spent_inr=60.0)          # remaining 40
    with pytest.raises(G.SpendGateRefused):
        G.preflight(stage="s", projected_inr=21.0, n_calls=10,
                    multiplier=G.CLASSIFICATION_GATE_MULT)   # 42 > 40
    rows = _projections()
    assert rows[-1]["allowed"] is False, "a refused projection is still recorded"


def test_extraction_gate_uses_1_5x():
    _ledger_with(cap_inr=100.0, spent_inr=60.0)          # remaining 40
    G.preflight(stage="e", projected_inr=26.0, n_calls=1,
                multiplier=G.EXTRACTION_GATE_MULT)          # 39 fits at x1.5
    with pytest.raises(G.SpendGateRefused):
        G.preflight(stage="e", projected_inr=27.0, n_calls=1,
                    multiplier=G.EXTRACTION_GATE_MULT)      # 40.5 does not


def test_overrun_monitor_halts_above_1_5x_projection():
    led = _ledger_with(cap_inr=1000.0)
    mon = G.OverrunMonitor(projected_inr_per_call=1.0, ledger=led)
    for _ in range(3):   # 3 calls at ₹1.4 each — within 1.5x
        led.append_correction({"stage": "t", "cost_usd": 1.4 / 84, "cost_inr": 1.4})
    assert mon.check(3) is None
    led.append_correction({"stage": "t", "cost_usd": 3.0 / 84, "cost_inr": 3.0})
    assert mon.check(4) is not None    # (4.2 + 3.0) / 4 = 1.8 > 1.5


# ---- wired into the classifier ------------------------------------------

@dataclass
class _Pair:
    from_claim_id: str
    to_claim_id: str
    similarity: float = 0.9


def _exts(n=6):
    return [PaperExtraction.model_construct(
        paper_id=f"openalex:W{i}", claims=[Claim.model_construct(
            id=f"openalex:W{i}:c1", paper_id=f"openalex:W{i}",
            text=f"claim {i}", type="finding")]) for i in range(n)]


PAIRS = [_Pair(f"openalex:W{i}:c1", f"openalex:W{i+1}:c1") for i in range(5)]


class _Fake:
    """Answers every call; bills `inr_per_call` to the (temp) ledger the way
    the real client would."""

    def __init__(self, inr_per_call=0.0):
        self.calls, self.inr = 0, inr_per_call

    def generate(self, prompt, **kw):
        self.calls += 1
        if self.inr:
            SpendLedger.load().append_correction(
                {"stage": "fake", "cost_usd": self.inr / 84, "cost_inr": self.inr})
        return json.dumps({"relationship": "none", "explanation": "x"})


@pytest.fixture
def reason_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_reason_dir", lambda slug: tmp_path / slug)
    return tmp_path


def test_classifier_refuses_before_any_call_when_gate_fails(reason_dir):
    per = R.projected_inr_per_pair()
    _ledger_with(cap_inr=per * 5 * 2 - 0.01)   # x2 of 5 pairs just misses
    llm = _Fake()
    res = R.classify_pairs("diet-and-mortality", _exts(), PAIRS, llm=llm)
    assert llm.calls == 0
    assert res["halted"].startswith("gate refused")
    assert _projections()[-1]["stage"] == "contradiction_diet-and-mortality"


def test_classifier_runs_when_gate_passes_and_records_projection(reason_dir):
    per = R.projected_inr_per_pair()
    _ledger_with(cap_inr=per * 5 * 2 + 1.0)
    llm = _Fake(inr_per_call=per)
    res = R.classify_pairs("diet-and-mortality", _exts(), PAIRS, llm=llm)
    assert llm.calls == 5 and res["halted"] is None
    row = _projections()[-1]
    assert row["n_calls"] == 5 and row["multiplier"] == 2.0 and row["allowed"]


def test_classifier_halts_when_cost_per_call_exceeds_1_5x(reason_dir):
    per = R.projected_inr_per_pair()
    _ledger_with(cap_inr=1000.0)
    llm = _Fake(inr_per_call=per * 2)          # 2x projection every call
    res = R.classify_pairs("diet-and-mortality", _exts(), PAIRS, llm=llm)
    assert llm.calls == 3, "halts as soon as the check starts (min 3 calls)"
    assert "exceeds 1.5x" in res["halted"]


def test_shared_shortlist_defaults_are_0_80_and_2():
    from backend.app.corpus import multi_domain_reason_incremental as I
    import inspect
    assert R.LIBRARY_THRESHOLD == 0.80 and R.LIBRARY_MAX_PER_CLAIM == 2
    assert I.LIBRARY_THRESHOLD is R.LIBRARY_THRESHOLD
    sig = inspect.signature(R.compute_shortlist)
    assert sig.parameters["threshold"].default == 0.80
    assert sig.parameters["max_per_claim"].default == 2
    assert inspect.signature(R.dry_run).parameters["threshold"].default == 0.80
