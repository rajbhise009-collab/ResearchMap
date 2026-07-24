"""LLMClient interface tests. GeminiLLMClient is instantiated but
never has .generate() invoked — no live spend."""

from __future__ import annotations

import pytest

from backend.app.extraction.llm_client import (
    GeminiLLMClient,
    MockLLMClient,
    ProgrammableMockLLMClient,
)


def test_mock_llm_extracts_paper_id_from_prompt(tmp_path):
    """MockLLMClient regex-extracts `Paper ID: `<id>`` from the
    rendered prompt and returns the canned JSON for that id."""
    # Set up a fake extractions dir with one canned file.
    (tmp_path / "openalex:W1.json").write_text('{"paper_id": "openalex:W1"}')
    mock = MockLLMClient(extractions_dir=tmp_path)
    prompt = "some header\nPaper ID: `openalex:W1`\nrest of prompt"
    assert mock.generate(prompt) == '{"paper_id": "openalex:W1"}'


def test_mock_llm_refuses_without_paper_id_marker(tmp_path):
    mock = MockLLMClient(extractions_dir=tmp_path)
    with pytest.raises(RuntimeError):
        mock.generate("prompt with no id marker")


def test_mock_llm_refuses_unknown_paper(tmp_path):
    mock = MockLLMClient(extractions_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        mock.generate("Paper ID: `openalex:W_unknown`")


def test_programmable_mock_returns_sequence():
    mock = ProgrammableMockLLMClient(["one", "two", "three"])
    assert mock.generate("prompt A") == "one"
    assert mock.generate("prompt B") == "two"
    assert mock.generate("prompt C") == "three"
    assert mock.call_count == 3


def test_programmable_mock_raises_when_exhausted():
    mock = ProgrammableMockLLMClient(["one"])
    mock.generate("x")
    with pytest.raises(StopIteration):
        mock.generate("x")


def test_gemini_client_refuses_without_api_key():
    """The Gemini client MUST refuse to instantiate without an API key.
    Otherwise an autonomy-policy violation (paid-API spend without
    approval) could slip through."""
    with pytest.raises(RuntimeError):
        GeminiLLMClient()


def test_gemini_client_instantiates_with_explicit_key():
    """Given an explicit key + explicit model + validate_model=False, the
    constructor succeeds without any network call. No .generate() is
    invoked — that would be a paid API call, and validate_model=False
    skips the models.list check that would otherwise hit the network."""
    client = GeminiLLMClient(
        api_key="fake-test-key",
        model_name="gemini-3.6-flash",
        validate_model=False,
    )
    assert client.name == "gemini:gemini-3.6-flash"
    assert client.model_name == "gemini-3.6-flash"
    assert client.endpoint.endswith(
        "/models/gemini-3.6-flash:generateContent"
    )
    # We deliberately do NOT call client.generate(). That would spend.


def test_is_daily_quota_429_true_for_perday():
    import httpx
    from backend.app.extraction.llm_client import _is_daily_quota_429
    resp = httpx.Response(429, json={"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId":
            "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
    ]}})
    assert _is_daily_quota_429(resp) is True


def test_is_daily_quota_429_false_for_perminute():
    import httpx
    from backend.app.extraction.llm_client import _is_daily_quota_429
    resp = httpx.Response(429, json={"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId":
            "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
    ]}})
    assert _is_daily_quota_429(resp) is False


def test_is_daily_quota_429_false_for_pertoken():
    import httpx
    from backend.app.extraction.llm_client import _is_daily_quota_429
    resp = httpx.Response(429, json={"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId":
            "GenerateContentInputTokensPerModelPerMinute-FreeTier"}]},
    ]}})
    assert _is_daily_quota_429(resp) is False


def test_generate_aborts_immediately_on_daily_quota():
    """Per-day 429 → DailyQuotaError on the FIRST hit, no retries."""
    import httpx
    from backend.app.extraction.llm_client import DailyQuotaError

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaId":
                "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        ]}})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client = GeminiLLMClient(api_key="fake", model_name="gemini-2.5-flash-lite",
                             validate_model=False, client=http)
    with pytest.raises(DailyQuotaError):
        client.generate("Paper ID: `x`\nprompt")
    # Exactly ONE call — no wasteful retries against a per-day wall.
    assert calls["n"] == 1
    assert client.daily_quota_hits == 1


def test_generate_retries_on_perminute_quota_then_succeeds():
    """Per-minute 429 IS transient → retried with backoff, then succeeds."""
    import httpx

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"details": [
                {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                 "violations": [{"quotaId":
                    "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
                {"@type": "type.googleapis.com/google.rpc.RetryInfo",
                 "retryDelay": "0s"},
            ]}})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "{\"ok\":1}"}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
        })

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client = GeminiLLMClient(api_key="fake", model_name="gemini-2.5-flash-lite",
                             validate_model=False, client=http)
    out = client.generate("Paper ID: `x`\nprompt")
    assert out == '{"ok":1}'
    assert calls["n"] == 2  # one 429 retry, then success
    assert client.rate_limit_hits == 1
    assert client.daily_quota_hits == 0


def test_retry_delay_parses_retryinfo_body():
    """A 429 with Google's RetryInfo.retryDelay in the body should be
    honored exactly (plus a 1s pad), not blind exponential backoff."""
    import httpx
    client = GeminiLLMClient(api_key="fake", model_name="gemini-3.6-flash",
                             validate_model=False)
    resp = httpx.Response(429, json={"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo",
         "retryDelay": "39s"},
    ]}})
    assert client._retry_delay_seconds(resp, rl_attempt=0) == 40.0


def test_retry_delay_falls_back_to_exponential():
    import httpx
    client = GeminiLLMClient(api_key="fake", model_name="gemini-3.6-flash",
                             validate_model=False)
    resp = httpx.Response(429, json={"error": {}})
    # rl_attempt=3 -> 2**3 = 8
    assert client._retry_delay_seconds(resp, rl_attempt=3) == 8.0


def test_gemini_client_reads_model_from_config(monkeypatch):
    """When no model_name is passed, it comes from GEMINI_MODEL config."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-flash-latest")
    from backend.app import config as cfg
    cfg.get_settings.cache_clear()
    client = GeminiLLMClient(validate_model=False)
    assert client.model_name == "gemini-flash-latest"
    cfg.get_settings.cache_clear()
