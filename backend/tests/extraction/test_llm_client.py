"""LLMClient interface tests. Live Gemini is never called — the
generate-level tests drive a mocked httpx transport and a no-wait
limiter, so no network and no real sleeping."""

from __future__ import annotations

import json

import httpx
import pytest

from backend.app.extraction.errors import RetryableResponseError
from backend.app.extraction.llm_client import (
    DailyQuotaError,
    GeminiLLMClient,
    MockLLMClient,
    ProgrammableMockLLMClient,
)
from backend.app.extraction.rate_limiter import RateLimiter


def _instant_limiter():
    """A limiter that never actually waits (sleep is a no-op) so
    retry-path tests don't burn real time."""
    return RateLimiter(max_rpm=1_000_000, max_tpm=10**12,
                       clock=lambda: 0.0, sleep=lambda s: None)


def _gemini_with_transport(handler, monkeypatch):
    """Build a GeminiLLMClient wired to a MockTransport, an instant
    limiter, and a no-op time.sleep so backoff waits are free."""
    import backend.app.extraction.llm_client as mod
    monkeypatch.setattr(mod.time, "sleep", lambda s: None, raising=False)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return GeminiLLMClient(
        api_key="fake", model_name="gemini-3.6-flash", validate_model=False,
        client=http, limiter=_instant_limiter(),
    )


def _q429(quota_id: str, retry_delay: str = "0s") -> httpx.Response:
    return httpx.Response(429, json={"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": quota_id}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo",
         "retryDelay": retry_delay},
    ]}})


def _ok(text: str = '{"ok":1}') -> httpx.Response:
    return httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
    })


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


def test_generate_aborts_immediately_on_daily_quota(monkeypatch):
    """Per-day 429 → DailyQuotaError on the FIRST hit, no retries."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _q429("GenerateRequestsPerDayPerProjectPerModel-FreeTier")

    client = _gemini_with_transport(handler, monkeypatch)
    with pytest.raises(DailyQuotaError):
        client.generate("Paper ID: `x`\nprompt")
    assert calls["n"] == 1          # no wasteful retries against a per-day wall
    assert client.daily_quota_hits == 1


def test_generate_retries_on_perminute_quota_then_succeeds(monkeypatch):
    """Per-minute 429 IS transient → retried, then succeeds. Routed to
    the rpm counter."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return _q429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
        return _ok()

    client = _gemini_with_transport(handler, monkeypatch)
    out = client.generate("Paper ID: `x`\nprompt")
    assert out == '{"ok":1}'
    assert calls["n"] == 2
    assert client.retries_rpm == 1
    assert client.retries_tpm == 0
    assert client.daily_quota_hits == 0


def test_generate_retries_on_pertoken_quota_and_routes_to_tpm(monkeypatch):
    """Per-token 429 is transient AND should be attributed to the TPM
    counter, so we can see which limit is binding."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return _q429("GenerateContentInputTokensPerModelPerMinute-FreeTier")
        return _ok()

    client = _gemini_with_transport(handler, monkeypatch)
    assert client.generate("Paper ID: `x`\nprompt") == '{"ok":1}'
    assert client.retries_tpm == 1
    assert client.retries_rpm == 0


def test_generate_retries_on_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else _ok()

    client = _gemini_with_transport(handler, monkeypatch)
    assert client.generate("Paper ID: `x`\nprompt") == '{"ok":1}'
    assert client.retries_5xx == 1


def test_generate_retries_schema_invalid_then_hardfails(monkeypatch):
    """A 200 whose body fails the caller's validator is retried up to the
    TIGHT schema budget, then the typed RetryableResponseError
    propagates. NEVER returns the bad text. Schema-invalid 200s consume
    daily quota, so the budget is deliberately small (2)."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _ok('{"not":"a valid extraction"}')

    def validate(text):
        raise RetryableResponseError("schema", "bad enum value")

    client = _gemini_with_transport(handler, monkeypatch)
    with pytest.raises(RetryableResponseError) as exc:
        client.generate("Paper ID: `x`\nprompt", validate=validate)
    assert exc.value.kind == "schema"
    # Only the SCHEMA budget is spent — not the (larger) transport one.
    assert calls["n"] == GeminiLLMClient.MAX_SCHEMA_ATTEMPTS  # == 2
    assert client.retries_schema == GeminiLLMClient.MAX_SCHEMA_ATTEMPTS - 1


def test_transport_and_schema_budgets_are_independent(monkeypatch):
    """A run of transient 429s (transport budget) followed by a
    schema-valid 200 succeeds — the transient retries do not eat into
    the schema budget, and vice versa. Here: 3 per-minute 429s (within
    the transport budget of 5) then a valid 200."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] <= 3:
            return _q429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
        return _ok('{"good":1}')

    def validate(text):
        if "good" not in text:
            raise RetryableResponseError("schema", "bad")

    client = _gemini_with_transport(handler, monkeypatch)
    assert client.generate("Paper ID: `x`\np", validate=validate) == '{"good":1}'
    assert calls["n"] == 4            # 3 transient + 1 success
    assert client.retries_rpm == 3
    assert client.retries_schema == 0


def test_schema_budget_smaller_than_transport():
    assert (GeminiLLMClient.MAX_SCHEMA_ATTEMPTS
            < GeminiLLMClient.MAX_TRANSPORT_ATTEMPTS)
    assert GeminiLLMClient.MAX_SCHEMA_ATTEMPTS == 2
    assert GeminiLLMClient.MAX_TRANSPORT_ATTEMPTS == 5


def test_generate_schema_invalid_then_valid_succeeds(monkeypatch):
    """If a later attempt validates, the retry succeeds (no hard fail)."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _ok('bad' if calls["n"] == 1 else '{"good":1}')

    def validate(text):
        if "good" not in text:
            raise RetryableResponseError("schema", "bad")

    client = _gemini_with_transport(handler, monkeypatch)
    assert client.generate("Paper ID: `x`\nprompt", validate=validate) == '{"good":1}'
    assert calls["n"] == 2
    assert client.successes == 1


def test_generate_invokes_limiter_before_each_request(monkeypatch):
    """The limiter's acquire() gates every request (RPM+TPM)."""
    acquired = {"n": 0, "tokens": []}

    class SpyLimiter(RateLimiter):
        def acquire(self, est_tokens):
            acquired["n"] += 1
            acquired["tokens"].append(est_tokens)
            return super().acquire(est_tokens)

    def handler(request):
        return _ok()

    import backend.app.extraction.llm_client as mod
    monkeypatch.setattr(mod.time, "sleep", lambda s: None, raising=False)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    spy = SpyLimiter(max_rpm=10**6, max_tpm=10**12,
                     clock=lambda: 0.0, sleep=lambda s: None)
    client = GeminiLLMClient(api_key="fake", model_name="gemini-3.6-flash",
                             validate_model=False, client=http, limiter=spy)
    client.generate("Paper ID: `x`\n" + "word " * 100)
    assert acquired["n"] == 1
    assert acquired["tokens"][0] > 0   # estimated input tokens passed in


def test_stats_summary_reports_categories(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return _q429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
        return _ok()

    client = _gemini_with_transport(handler, monkeypatch)
    client.generate("Paper ID: `x`\nprompt")
    s = client.stats_summary()
    assert s["successes"] == 1
    assert s["retries_rpm"] == 1
    assert s["total_requests"] == 2
    assert "effective_rpm" in s


def _fixed_rng():
    import random
    r = random.Random()
    r.uniform = lambda a, b: 0.0  # kill jitter for deterministic asserts
    return r


def test_retry_delay_parses_retryinfo_body():
    """A 429 with Google's RetryInfo.retryDelay in the body should be
    honored (plus a 1s pad), not blind exponential backoff. Jitter is
    zeroed here for a deterministic assertion."""
    import httpx
    client = GeminiLLMClient(api_key="fake", model_name="gemini-3.6-flash",
                             validate_model=False, rng=_fixed_rng())
    resp = httpx.Response(429, json={"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo",
         "retryDelay": "39s"},
    ]}})
    assert client._retry_delay_seconds(resp, attempt=0) == 40.0


def test_retry_delay_falls_back_to_exponential():
    import httpx
    client = GeminiLLMClient(api_key="fake", model_name="gemini-3.6-flash",
                             validate_model=False, rng=_fixed_rng())
    resp = httpx.Response(429, json={"error": {}})
    # attempt=3 -> 2**3 = 8, jitter zeroed
    assert client._retry_delay_seconds(resp, attempt=3) == 8.0


def test_retry_delay_applies_jitter_within_band():
    """With real jitter, the delay stays within ±10% of the base."""
    import httpx
    client = GeminiLLMClient(api_key="fake", model_name="gemini-3.6-flash",
                             validate_model=False)
    resp = httpx.Response(429, json={"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo",
         "retryDelay": "10s"},
    ]}})
    for _ in range(20):
        d = client._retry_delay_seconds(resp, attempt=0)
        assert 11.0 * 0.9 <= d <= 11.0 * 1.1  # base = 10 + 1 pad


def test_gemini_client_reads_model_from_config(monkeypatch):
    """When no model_name is passed, it comes from GEMINI_MODEL config."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-flash-latest")
    from backend.app import config as cfg
    cfg.get_settings.cache_clear()
    client = GeminiLLMClient(validate_model=False)
    assert client.model_name == "gemini-flash-latest"
    cfg.get_settings.cache_clear()
