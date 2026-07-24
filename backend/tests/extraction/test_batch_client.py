"""Gemini Batch client tests — HTTP mocked, no live batch submission."""

from __future__ import annotations

import httpx
import pytest
import respx

from backend.app.extraction.batch_client import (
    BatchJob,
    GeminiBatchClient,
    chunk_requests,
)


API = "https://generativelanguage.googleapis.com/v1beta"


def _client(**kw):
    return GeminiBatchClient(api_key="fake", model_name="gemini-3.6-flash",
                             validate_model=False, **kw)


def test_batch_client_refuses_without_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from backend.app import config as cfg
    cfg.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        GeminiBatchClient(validate_model=False)
    cfg.get_settings.cache_clear()


@respx.mock
def test_submit_returns_batch_id():
    route = respx.post(
        f"{API}/models/gemini-3.6-flash:batchGenerateContent"
    ).mock(return_value=httpx.Response(200, json={"name": "batches/abc123"}))
    c = _client()
    bid = c.submit({"p1": "prompt one", "p2": "prompt two"},
                   display_name="test-run")
    assert bid == "abc123"
    # Inline requests carry the per-key metadata.
    sent = route.calls[0].request
    import json
    body = json.loads(sent.content)
    reqs = body["batch"]["input_config"]["requests"]["requests"]
    keys = {r["metadata"]["key"] for r in reqs}
    assert keys == {"p1", "p2"}


@respx.mock
def test_poll_reports_state():
    respx.get(f"{API}/batches/abc123").mock(
        return_value=httpx.Response(200, json={"metadata": {"state": "JOB_STATE_RUNNING"}})
    )
    job = _client().poll("abc123")
    assert job.state == "JOB_STATE_RUNNING"
    assert not job.done


def test_batchjob_terminal_flags():
    assert BatchJob("x", "JOB_STATE_SUCCEEDED").succeeded
    assert BatchJob("x", "JOB_STATE_SUCCEEDED").done
    assert BatchJob("x", "JOB_STATE_FAILED").done
    assert not BatchJob("x", "JOB_STATE_FAILED").succeeded
    assert not BatchJob("x", "JOB_STATE_RUNNING").done


def test_results_maps_text_by_key():
    job = BatchJob("x", "JOB_STATE_SUCCEEDED", raw={
        "response": {"inlinedResponses": {"inlinedResponses": [
            {"metadata": {"key": "p1"},
             "response": {"candidates": [{"content": {"parts": [{"text": "{\"a\":1}"}]}}]}},
            {"metadata": {"key": "p2"},
             "response": {"candidates": [{"content": {"parts": [{"text": "{\"b\":2}"}]}}]}},
        ]}}
    })
    out = _client().results(job)
    assert out == {"p1": '{"a":1}', "p2": '{"b":2}'}


def test_chunk_requests_splits_on_size():
    # Three ~1MB prompts with a 2.5MB cap → 2 chunks.
    big = "x" * 1_000_000
    reqs = {f"p{i}": big for i in range(3)}
    chunks = chunk_requests(reqs, max_bytes=2_500_000)
    assert len(chunks) == 2
    # Every key present exactly once across chunks.
    seen = [k for ch in chunks for k in ch]
    assert sorted(seen) == ["p0", "p1", "p2"]


def test_chunk_requests_single_chunk_when_small():
    reqs = {"p1": "short", "p2": "also short"}
    assert len(chunk_requests(reqs)) == 1
