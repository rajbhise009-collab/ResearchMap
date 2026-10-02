"""Batch extraction must be billed to the ledger at half price, exactly once."""

from __future__ import annotations

import json

import pytest

from backend.app.extraction.batch_client import BatchJob, record_batch_usage
from backend.app.extraction.spend_ledger import SpendLedger

USAGE = {"promptTokenCount": 10_000, "candidatesTokenCount": 1_000,
         "thoughtsTokenCount": 1_000}


@pytest.fixture
def ledger(tmp_path):
    return SpendLedger(path=tmp_path / "l.json")


def test_batch_entry_is_half_of_sync(ledger):
    s = ledger.record(stage="x", model="m", batch=False, prompt_tokens=10_000,
                      candidates_tokens=1_000, thoughts_tokens=1_000)
    b = ledger.record(stage="x", model="m", batch=True, prompt_tokens=10_000,
                      candidates_tokens=1_000, thoughts_tokens=1_000)
    assert b.cost_usd == pytest.approx(s.cost_usd * 0.5)
    # 10k in @ $1.50/M + 2k out @ $7.50/M = 0.015 + 0.015
    assert s.cost_usd == pytest.approx(0.030)


def test_record_batch_usage_marks_batch_and_bills_each_result(ledger):
    results = {"p1": ("{}", USAGE), "p2": ("{}", USAGE)}
    inr = record_batch_usage(results, stage="extract_x_batch", model="m",
                             ledger=ledger)
    entries = json.loads(ledger.path.read_text())["entries"]
    assert len(entries) == 2
    assert all(e["batch"] is True for e in entries)
    assert inr == pytest.approx(2 * 0.015 * 84.0)


class _FakeBatchClient:
    """Returns one SUCCEEDED job whose two results carry usage metadata."""

    def __init__(self, pids):
        self.pids = pids
        self.submitted = None

    def submit(self, prompts, *, display_name):
        self.submitted = dict(prompts)
        return "fake-batch-1"

    def poll(self, batch_id):
        inlined = [{"metadata": {"key": pid},
                    "response": {"candidates": [{"content": {"parts": [{"text": "not json"}]}}],
                                 "usageMetadata": USAGE}}
                   for pid in self.pids]
        return BatchJob(batch_id, "BATCH_STATE_SUCCEEDED",
                        {"response": {"inlinedResponses": {"inlinedResponses": inlined}}})

    def results_with_usage(self, job):
        from backend.app.extraction.batch_client import GeminiBatchClient
        return GeminiBatchClient.results_with_usage(self, job)


def test_collect_bills_once_even_if_run_twice(tmp_path, monkeypatch):
    from backend.app.corpus import multi_domain_extract as M
    led = SpendLedger(path=tmp_path / "l.json")
    monkeypatch.setattr(SpendLedger, "_instance", led)
    monkeypatch.setattr(M, "_extractions_dir", lambda slug: tmp_path / slug)
    (tmp_path / "diet").mkdir()
    pids = ["openalex:W1", "openalex:W2"]
    M._batch_state_path("diet").write_text(json.dumps({
        "batch_id": "fake-batch-1", "slug": "diet",
        "input_source": {p: "abstract" for p in pids},
        "n_submitted": 2, "ledger_recorded": False}))
    monkeypatch.setattr(M, "_prelabel_path", lambda cfg: tmp_path / "pre.json")
    (tmp_path / "pre.json").write_text(json.dumps({"entries": [
        {"wid": "W1", "title": "a", "abstract": "x"},
        {"wid": "W2", "title": "b", "abstract": "y"}]}))
    client = _FakeBatchClient(pids)
    r1 = M.batch_collect("diet", client=client)
    r2 = M.batch_collect("diet", client=client)
    entries = json.loads(led.path.read_text())["entries"]
    assert len(entries) == 2, "second collect must not re-bill"
    assert all(e["batch"] for e in entries)
    # the fake returns non-JSON, so both hard-fail by name — nothing cached
    assert {p for p, _ in r1["hard_fails"]} == set(pids)
    assert r2["status"] == "collected"
