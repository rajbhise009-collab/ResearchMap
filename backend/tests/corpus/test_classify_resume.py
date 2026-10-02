"""The contradiction classifier must save each verdict as it returns, and a
restart must never re-pay for a saved verdict."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from backend.app.corpus import multi_domain_reason as R
from backend.app.models import Claim, PaperExtraction


@dataclass
class _Pair:
    from_claim_id: str
    to_claim_id: str
    similarity: float = 0.9


def _exts():
    out = []
    for i in range(6):
        pid = f"openalex:W{i}"
        out.append(PaperExtraction.model_construct(
            paper_id=pid, claims=[Claim.model_construct(
                id=f"{pid}:c1", paper_id=pid, text=f"claim {i}", type="finding")]))
    return out


PAIRS = [_Pair(f"openalex:W{i}:c1", f"openalex:W{i+1}:c1") for i in range(5)]


class _KillAfter:
    """Answers N calls, then simulates the process being killed."""

    def __init__(self, n):
        self.n, self.calls = n, 0

    def generate(self, prompt, **kw):
        if self.calls >= self.n:
            raise KeyboardInterrupt
        self.calls += 1
        rel = "contradicts" if self.calls == 2 else "supports"
        return json.dumps({"relationship": rel, "explanation": "x"})


class _Counting:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, **kw):
        self.calls += 1
        return json.dumps({"relationship": "none", "explanation": "y"})


@pytest.fixture
def isolated_reason_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_reason_dir", lambda slug: tmp_path / slug)
    return tmp_path / "diet-and-mortality"


def test_kill_mid_run_loses_nothing_and_restart_does_not_repay(isolated_reason_dir):
    exts = _exts()
    with pytest.raises(KeyboardInterrupt):
        R.classify_pairs("diet-and-mortality", exts, PAIRS, llm=_KillAfter(3))

    log = (isolated_reason_dir / "verdicts.jsonl").read_text().splitlines()
    assert len(log) == 3, "every returned verdict must be on disk before the kill"
    # materialize ran in `finally`, so the JSON files already reflect them
    contra = json.loads((isolated_reason_dir / "contradictions.json").read_text())
    assert contra["n"] == 1

    second = _Counting()
    res = R.classify_pairs("diet-and-mortality", exts, PAIRS, llm=second)
    assert second.calls == 2, "only the two unsaved pairs may be classified"
    assert res["stats"]["skipped_already_classified"] == 3

    total = sum(json.loads((isolated_reason_dir / f).read_text())["n"]
                for f in ("contradictions.json", "supports.json", "nones.json"))
    assert total == 5

    third = _Counting()
    R.classify_pairs("diet-and-mortality", exts, PAIRS, llm=third)
    assert third.calls == 0


def test_paid_parse_failures_are_saved_and_not_repaid(isolated_reason_dir):
    class _Garbage:
        calls = 0

        def generate(self, prompt, **kw):
            _Garbage.calls += 1
            return "not json"

    R.classify_pairs("diet-and-mortality", _exts(), PAIRS[:2], llm=_Garbage())
    fails = json.loads((isolated_reason_dir / "failures.json").read_text())
    assert fails["n"] == 2
    again = _Counting()
    R.classify_pairs("diet-and-mortality", _exts(), PAIRS[:2], llm=again)
    assert again.calls == 0


def test_existing_verdict_files_are_preserved(isolated_reason_dir):
    isolated_reason_dir.mkdir(parents=True)
    old = {"from_claim_id": PAIRS[0].from_claim_id,
           "to_claim_id": PAIRS[0].to_claim_id, "explanation": "audited"}
    (isolated_reason_dir / "contradictions.json").write_text(
        json.dumps({"n": 1, "items": [old]}))
    llm = _Counting()
    R.classify_pairs("diet-and-mortality", _exts(), PAIRS, llm=llm)
    assert llm.calls == 4
    contra = json.loads((isolated_reason_dir / "contradictions.json").read_text())
    assert contra["items"][0]["explanation"] == "audited"
