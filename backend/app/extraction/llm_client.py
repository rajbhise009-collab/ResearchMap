"""LLMClient interface.

Deliberately narrow. An LLM in ResearchMap does ONE job: given a
rendered prompt (from `prompt_versions.load(version).render(...)`),
return the raw text the model produced. Parsing, schema validation,
retry, cache, and provenance all live in the orchestrator
(`extractor.py`) — not on this interface.

If you find yourself wanting to add a method here that asks the model
"which is better / more promising / more important" — stop. That logic
belongs in `reasoning/` as deterministic code.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from backend.app.config import get_settings
from backend.app.extraction.errors import RetryableResponseError
from backend.app.extraction.rate_limiter import RateLimiter, estimate_tokens

# A `validate` callback inspects a 200 response's text and raises
# RetryableResponseError if it is unusable (bad JSON / schema-invalid /
# paper_id mismatch). Returning None means the response is usable.
Validator = Callable[[str], None]


# Substring that marks a per-DAY quota violation in a 429 QuotaFailure.
# Per-minute / per-token quotas use different quotaIds (…PerMinute…,
# …Tokens…) and ARE transient, so we retry those.
_DAILY_QUOTA_MARKER = "PerDay"


class DailyQuotaError(RuntimeError):
    """Raised when a 429 is a per-day quota exhaustion — which cannot
    clear before the daily reset, so retrying is pure waste and the run
    should abort immediately."""


def _is_daily_quota_429(response) -> bool:
    """True iff the 429 body carries a QuotaFailure whose quotaId marks a
    per-DAY quota (e.g. GenerateRequestsPerDayPerProjectPerModel-FreeTier).
    Per-minute / per-token violations return False (retry those)."""
    try:
        details = response.json().get("error", {}).get("details", [])
    except Exception:
        return False
    for d in details:
        if not str(d.get("@type", "")).endswith("QuotaFailure"):
            continue
        for v in d.get("violations", []):
            qid = str(v.get("quotaId", ""))
            if _DAILY_QUOTA_MARKER in qid:
                return True
    return False


class LLMClient(ABC):
    """The only interface the pipeline uses to talk to an LLM."""

    name: str = "abstract"

    @abstractmethod
    def generate(self, prompt: str, *, validate: Validator | None = None) -> str:
        """Given a fully-rendered prompt, return the raw model output.

        If `validate` is provided, the implementation calls it on the
        response text and treats a raised `RetryableResponseError` as an
        unusable response worth retrying (within the implementation's
        bounded attempts). The retry layer — rate limiting, transient
        HTTP/429 handling, and unusable-response retries — lives in the
        implementation; the orchestrator supplies the validator.

        Malformed/exhausted responses raise, never return a
        placeholder."""
        raise NotImplementedError


# --- Mock client ---------------------------------------------------------


# The v1.0.0/extract.md prompt places `Paper ID: `<paper_id>`` in a
# line the mock can regex out to find which canned extraction to
# return. Keep this regex in sync with the prompt template.
_MOCK_PAPER_ID_RE = re.compile(r"Paper ID:\s*`([^`]+)`")


class MockLLMClient(LLMClient):
    """Reads pre-computed extractions from disk, keyed by paper_id.

    Regex-extracts the paper_id from the rendered prompt (rather than
    requiring the orchestrator to set it explicitly). Ignores the rest
    of the prompt. Returns the canned JSON as a raw string — as if the
    model had produced it.

    If no canned extraction exists for the requested paper, raises
    FileNotFoundError. The mock never fabricates output.
    """

    name = "mock-seed"

    def __init__(self, extractions_dir: Path | None = None) -> None:
        self._dir = extractions_dir or (get_settings().seed_dir / "extractions")

    def generate(self, prompt: str, *, validate: Validator | None = None) -> str:
        m = _MOCK_PAPER_ID_RE.search(prompt)
        if not m:
            raise RuntimeError(
                "MockLLMClient could not find `Paper ID: \\`<id>\\`` in the "
                "rendered prompt. Prompt template must include this marker "
                "so the mock knows which extraction to return."
            )
        paper_id = m.group(1)
        path = self._dir / f"{paper_id}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"MockLLMClient has no canned extraction for paper "
                f"{paper_id!r} (looked at {path}). Refusing to fabricate."
            )
        text = path.read_text(encoding="utf-8")
        if validate is not None:
            validate(text)  # canned seed extractions are valid → passes
        return text


# --- Failing mock (for tests) -------------------------------------------


class ProgrammableMockLLMClient(LLMClient):
    """Returns a deterministic sequence of responses; used in tests.

    Each `.generate()` returns the next scripted response. If a
    `validate` callback is given and raises `RetryableResponseError`,
    the mock advances to the next scripted response (simulating a
    retry) until one validates or the list is exhausted — at which
    point the last RetryableResponseError propagates. This lets tests
    script "garbage, then valid" and "garbage×N" sequences without a
    live client."""

    name = "programmable-mock"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def total_requests(self) -> int:
        """Alias so the Extractor can count attempts uniformly across
        real and mock clients."""
        return self._call_count

    def generate(self, prompt: str, *, validate: Validator | None = None) -> str:
        last_err: RetryableResponseError | None = None
        while self._call_count < len(self._responses):
            r = self._responses[self._call_count]
            self._call_count += 1
            if validate is None:
                return r
            try:
                validate(r)
                return r
            except RetryableResponseError as e:
                last_err = e
                continue
        if last_err is not None:
            raise last_err
        raise StopIteration(
            f"ProgrammableMockLLMClient exhausted after "
            f"{self._call_count} calls; no more responses queued."
        )


# --- Real Gemini client (implemented, NOT executed in tests) ------------


class GeminiLLMClient(LLMClient):
    """Real Gemini Flash 2.5 client.

    This implementation makes real HTTP calls when `.generate()` is
    invoked. Under the autonomy policy that gates paid-API spend, the
    orchestrator refuses to instantiate this client without a spend
    approval; the test suite exercises only MockLLMClient and
    ProgrammableMockLLMClient.
    """

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    # ONE unified attempt budget covering transient failures (per-minute
    # / per-token 429s, 5xx, timeouts/connection errors) AND unusable
    # 200 responses (bad JSON / schema-invalid / paper_id mismatch).
    # Per-DAY 429s are NOT retried — they abort immediately.
    MAX_ATTEMPTS = 5
    BACKOFF_CAP_S = 120.0

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
        client=None,  # injected httpx.Client for tests
        raw_log_dir: Path | None = None,
        validate_model: bool = True,
        limiter: RateLimiter | None = None,
        rng=None,
    ) -> None:
        settings = get_settings()
        key = api_key
        if key is None and settings.gemini_api_key is not None:
            key = settings.gemini_api_key.get_secret_value()
        if not key:
            raise RuntimeError(
                "GeminiLLMClient requires GEMINI_API_KEY. This client makes "
                "PAID API calls; ensure the spend gate has been approved "
                "before instantiating."
            )
        self._api_key = key
        # Model comes from config/env, never hardcoded — model names are
        # volatile and a bad one must fail loudly at startup, not as a
        # mid-run 404.
        self._model_name = model_name or settings.gemini_model
        self._temperature = temperature
        import random
        self._rng = rng or random.Random()
        import httpx  # noqa: F401 — pulled into scope for _get_client
        self._client = client
        self.name = f"gemini:{self._model_name}"

        # Shared client-side rate limiter (RPM + TPM). One instance per
        # client; passing an explicit limiter lets a run share one across
        # clients. Defaults come from config.
        self._limiter = limiter or RateLimiter(
            max_rpm=settings.gemini_max_rpm,
            max_tpm=settings.gemini_max_tpm,
            rng=self._rng,
        )

        # --- Observability counters (read by the runner for a summary).
        self.total_requests = 0          # HTTP requests actually sent
        self.successes = 0               # usable responses returned
        self.total_prompt_tokens = 0
        self.total_output_tokens = 0
        self.total_latency_s = 0.0
        self.retries_rpm = 0             # per-minute 429 retries
        self.retries_tpm = 0             # per-token 429 retries
        self.retries_5xx = 0             # 5xx / server-error retries
        self.retries_conn = 0            # timeout / connection-error retries
        self.retries_schema = 0          # unusable-200 (validation) retries
        self.daily_quota_hits = 0        # per-day 429s (abort, never retried)
        self.limiter_delays_tpm = 0      # requests the limiter held for TPM
        self.limiter_delays_rpm = 0      # requests the limiter held for RPM
        # Back-compat aliases some older callers/reports read.
        self.rate_limit_hits = 0
        self.server_error_hits = 0
        self._raw_log_dir = raw_log_dir
        self._per_paper_attempts: dict[str, int] = {}

        # Fail loudly at startup if the configured model doesn't resolve.
        if validate_model:
            self._validate_model()

    @property
    def calls(self) -> int:
        """Back-compat: older code reads `.calls` as the request count."""
        return self.total_requests

    @property
    def limiter_wait_s(self) -> float:
        return self._limiter.total_wait_s

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def endpoint(self) -> str:
        return f"{self.API_BASE}/models/{self._model_name}:generateContent"

    def _get_client(self):
        import httpx
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(120.0, connect=10.0),
                headers={"User-Agent": "ResearchMap/0.1"},
            )
        return self._client

    def _validate_model(self) -> None:
        """Confirm the configured model resolves in models.list, and that
        it supports generateContent. Raises with the available Flash
        alternatives named, so a bad model name is caught at startup."""
        client = self._get_client()
        resp = client.get(
            f"{self.API_BASE}/models",
            params={"key": self._api_key, "pageSize": 200},
        )
        resp.raise_for_status()
        models = resp.json().get("models", [])
        # models.list returns "models/<name>"; accept either form.
        wanted = self._model_name if self._model_name.startswith("models/") \
            else f"models/{self._model_name}"
        by_name = {m.get("name"): m for m in models}
        match = by_name.get(wanted)
        if match is None:
            flash = sorted(
                m["name"].removeprefix("models/")
                for m in models
                if "flash" in m.get("name", "").lower()
                and "generateContent" in (m.get("supportedGenerationMethods") or [])
            )
            raise RuntimeError(
                f"Configured GEMINI_MODEL={self._model_name!r} does not "
                f"resolve in models.list. Available Flash models "
                f"supporting generateContent: {flash}"
            )
        methods = match.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            raise RuntimeError(
                f"Model {self._model_name!r} exists but does not support "
                f"generateContent (supports: {methods})."
            )

    def _retry_delay_seconds(self, response, attempt: int) -> float:
        """Wait before a transient retry. Honor Gemini's RetryInfo.
        retryDelay from the 429 body when present; else exponential
        backoff. Always add ±jitter and cap at BACKOFF_CAP_S."""
        base = None
        header = response.headers.get("retry-after") if response is not None else None
        if header and header.isdigit():
            base = float(header)
        if base is None and response is not None:
            try:
                for d in response.json().get("error", {}).get("details", []):
                    if str(d.get("@type", "")).endswith("RetryInfo"):
                        m = re.match(r"^([0-9]+(?:\.[0-9]+)?)s$",
                                     str(d.get("retryDelay", "")))
                        if m:
                            base = float(m.group(1)) + 1.0
            except Exception:
                pass
        if base is None:
            base = 2.0 ** attempt
        base = min(base, self.BACKOFF_CAP_S)
        jitter = 1.0 + self._rng.uniform(-0.10, 0.10)
        return max(0.0, base * jitter)

    @staticmethod
    def _quota_kind_429(response) -> str:
        """Classify a 429: 'day' (abort), 'tpm', 'rpm', or 'other'."""
        try:
            details = response.json().get("error", {}).get("details", [])
        except Exception:
            return "other"
        for d in details:
            if not str(d.get("@type", "")).endswith("QuotaFailure"):
                continue
            for v in d.get("violations", []):
                qid = str(v.get("quotaId", ""))
                if "PerDay" in qid:
                    return "day"
                if "Token" in qid or "token" in qid:
                    return "tpm"
                if "PerMinute" in qid or "Minute" in qid:
                    return "rpm"
        return "other"

    @staticmethod
    def _extract_text(body: dict) -> str:
        candidates = body.get("candidates") or []
        if not candidates:
            raise ValueError("no candidates in Gemini response")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        if not parts:
            raise ValueError("no parts in Gemini candidate")
        text = parts[0].get("text")
        if not text:
            raise ValueError("empty text in Gemini part")
        return text

    def generate(self, prompt: str, *, validate: Validator | None = None) -> str:
        import httpx
        client = self._get_client()
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self._temperature,
                "response_mime_type": "application/json",
            },
        }
        est_in = estimate_tokens(prompt)

        last_transient: Exception | None = None
        last_validation: RetryableResponseError | None = None

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            # --- Rate-limit gate (RPM + TPM) before every request.
            wait = self._limiter.acquire(est_in)
            if wait.tpm_bound:
                self.limiter_delays_tpm += 1
                if self._raw_log_dir is not None:
                    print(f"[limiter] held {wait.tpm_wait_s:.1f}s for TPM "
                          f"(est_in={est_in})", flush=True)
            elif wait.rpm_wait_s > 0:
                self.limiter_delays_rpm += 1

            # --- Send. Connection/timeout errors are transient.
            self.total_requests += 1
            t0 = time.time()
            try:
                response = client.post(
                    self.endpoint, params={"key": self._api_key}, json=payload,
                )
            except (httpx.TransportError, httpx.TimeoutException) as e:
                self.total_latency_s += time.time() - t0
                last_transient = e
                if attempt < self.MAX_ATTEMPTS:
                    self.retries_conn += 1
                    time.sleep(min(2.0 ** attempt, self.BACKOFF_CAP_S)
                               * (1.0 + self._rng.uniform(-0.10, 0.10)))
                    continue
                break
            self.total_latency_s += time.time() - t0

            # --- Classify HTTP status.
            if response.status_code == 429:
                self.rate_limit_hits += 1
                kind = self._quota_kind_429(response)
                if kind == "day":
                    self.daily_quota_hits += 1
                    raise DailyQuotaError(
                        "Gemini daily free-tier quota exhausted "
                        "(GenerateRequestsPerDayPerProjectPerModel-FreeTier "
                        f"for {self._model_name}). Retrying cannot succeed "
                        "until the daily reset (~midnight Pacific). Aborting "
                        "the run — resume after reset; cached work is kept."
                    )
                last_transient = httpx.HTTPStatusError(
                    "429", request=response.request, response=response)
                if attempt < self.MAX_ATTEMPTS:
                    if kind == "tpm":
                        self.retries_tpm += 1
                    else:
                        self.retries_rpm += 1
                    time.sleep(self._retry_delay_seconds(response, attempt))
                    continue
                break

            if response.status_code >= 500:
                self.server_error_hits += 1
                last_transient = httpx.HTTPStatusError(
                    str(response.status_code), request=response.request,
                    response=response)
                if attempt < self.MAX_ATTEMPTS:
                    self.retries_5xx += 1
                    time.sleep(min(2.0 ** attempt, self.BACKOFF_CAP_S)
                               * (1.0 + self._rng.uniform(-0.10, 0.10)))
                    continue
                break

            response.raise_for_status()  # any other 4xx → hard error
            body = response.json()

            usage = body.get("usageMetadata") or {}
            self.total_prompt_tokens += int(usage.get("promptTokenCount") or 0)
            self.total_output_tokens += int(usage.get("candidatesTokenCount") or 0)

            try:
                text = self._extract_text(body)
            except (KeyError, IndexError, TypeError, ValueError) as e:
                # Malformed envelope — treat as a transient/unusable 200.
                last_transient = RuntimeError(f"unexpected response shape: {e}")
                if attempt < self.MAX_ATTEMPTS:
                    time.sleep(min(2.0 ** attempt, self.BACKOFF_CAP_S))
                    continue
                break

            self._tee_raw(prompt, text)

            # --- Unusable-response check (bad JSON / schema / paper_id).
            if validate is not None:
                try:
                    validate(text)
                except RetryableResponseError as e:
                    last_validation = e
                    if attempt < self.MAX_ATTEMPTS:
                        self.retries_schema += 1
                        # Small backoff — the model is deterministic-ish at
                        # temp 0, but a fresh sample may self-correct.
                        time.sleep(min(2.0 ** attempt, self.BACKOFF_CAP_S)
                                   * (1.0 + self._rng.uniform(-0.10, 0.10)))
                        continue
                    # Exhausted on validation → propagate the typed error.
                    raise
            self.successes += 1
            return text

        # Exhausted the attempt budget.
        if last_validation is not None:
            raise last_validation
        raise RuntimeError(
            f"Gemini request failed after {self.MAX_ATTEMPTS} attempts: "
            f"{last_transient!s}"
        ) from last_transient

    def _tee_raw(self, prompt: str, text: str) -> None:
        if self._raw_log_dir is None:
            return
        m = re.search(r"Paper ID:\s*`([^`]+)`", prompt)
        paper_id = m.group(1) if m else "unknown"
        self._per_paper_attempts[paper_id] = (
            self._per_paper_attempts.get(paper_id, 0) + 1)
        attempt = self._per_paper_attempts[paper_id]
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", paper_id)
        self._raw_log_dir.mkdir(parents=True, exist_ok=True)
        (self._raw_log_dir / f"{safe}.attempt{attempt}.txt").write_text(
            text, encoding="utf-8")

    def stats_summary(self) -> dict:
        """End-of-run observability. effective_rpm = successes over the
        wall-clock span the client was active (approx via total latency +
        limiter waits)."""
        active_s = self.total_latency_s + self.limiter_wait_s
        eff_rpm = (self.successes / active_s * 60.0) if active_s > 0 else 0.0
        return {
            "total_requests": self.total_requests,
            "successes": self.successes,
            "retries_rpm": self.retries_rpm,
            "retries_tpm": self.retries_tpm,
            "retries_5xx": self.retries_5xx,
            "retries_conn": self.retries_conn,
            "retries_schema": self.retries_schema,
            "daily_quota_hits": self.daily_quota_hits,
            "limiter_wait_s": round(self.limiter_wait_s, 1),
            "limiter_delays_rpm": self.limiter_delays_rpm,
            "limiter_delays_tpm": self.limiter_delays_tpm,
            "effective_rpm": round(eff_rpm, 2),
        }


__all__ = [
    "DailyQuotaError",
    "GeminiLLMClient",
    "LLMClient",
    "MockLLMClient",
    "ProgrammableMockLLMClient",
]
