"""Phase-4 scorers on the multi-domain libraries: cards, plan, and the
paid runner's save-as-you-go / no-re-pay behaviour (fake batch client,
temp ledger — no network)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.app.api.contradiction_titles import VERDICT_WORDS
from backend.app.api.library_cards import scorer_cards, scorer_plan
from backend.app.reasoning import run_library_scorers as RS

REPO = Path(__file__).resolve().parents[3]
LIBS = ("diet-and-mortality", "ml-fairness")


@pytest.mark.parametrize("slug", LIBS)
def test_cards_unique_topic_titles_no_verdict_words(slug):
    cards, yields, skipped = scorer_cards(slug)
    heads = [c["consumer"]["headline"] for c in cards]
    assert len(heads) == len(set(heads))
    for h in heads:
        assert len(h) > 20 and "another line of work" not in h
        assert not any(re.search(rf"\b{w}\b", h.lower()) for w in VERDICT_WORDS), h
    for c in cards:
        assert c["slug"].startswith(f"opp-{slug}-")
        assert c["consumer"]["strength"] in ("Strong", "Worth a look", "Unverified lead")
    assert sum(v for k, v in yields.items() if k != "structural_holes_substantive") == len(cards)
    for reason in skipped.values():
        assert reason and reason[0].islower()


def test_orphaned_future_work_runs_only_with_matcher_output():
    run, skipped = scorer_plan("ml-fairness")
    assert "orphaned_future_work" not in run and "orphaned_future_work" in skipped
    run, skipped = scorer_plan("diet-and-mortality")
    assert "orphaned_future_work" in run and not skipped


def test_diet_disagreement_cards_unchanged_by_new_scorers():
    o = json.loads((REPO / "frontend/public/data/library/diet-and-mortality/opportunities.json").read_text())
    contra = [i for i in o["items"] if i["slug"].startswith("opp-contra-")]
    assert len(contra) == 10 and o["audit"]["confirmed"] == 5
    assert all(i.get("verdict") for i in contra)


def test_hole_confirm_k_scales_with_n():
    assert RS.n_clusters_for(100) == 10 and RS.n_clusters_for(9) == 3


class _FakeBatch:
    def __init__(self):
        self.submits = 0

    def submit(self, prompts, display_name):
        self.submits += 1
        self.keys = list(prompts)
        return "batches/fake"

    def wait(self, bid, poll_interval_s=0):
        class J:
            succeeded = True
        return J()

    def results_with_usage(self, job):
        usage = {"promptTokenCount": 300, "candidatesTokenCount": 50, "thoughtsTokenCount": 200}
        return {k: (json.dumps({"verdict": "trivial", "reason": "x"}), usage) for k in self.keys}


def test_batch_driver_saves_state_and_never_repays(tmp_path, monkeypatch):
    from backend.app.extraction.spend_ledger import SpendLedger
    monkeypatch.setattr(RS, "_state", lambda slug, stage: tmp_path / f"{stage}.json")
    fake = _FakeBatch()
    prompts = {"a": "prompt one", "b": "prompt two"}
    raw, money = RS._run_batch("x", "hole_confirm", prompts, client=fake)
    assert fake.submits == 1 and set(raw) == {"a", "b"}
    n_entries = len(SpendLedger.load()._read().entries)
    assert n_entries == 2 and money["calls"] == 2 and not money["overrun"]
    # restart with the saved state: no new submit, no new billing
    raw2, _ = RS._run_batch("x", "hole_confirm", prompts, client=fake)
    assert fake.submits == 1 and len(SpendLedger.load()._read().entries) == n_entries
