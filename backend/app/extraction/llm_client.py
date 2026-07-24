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
from abc import ABC, abstractmethod
from pathlib import Path

from backend.app.config import get_settings


class LLMClient(ABC):
    """The only interface the pipeline uses to talk to an LLM."""

    name: str = "abstract"

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Given a fully-rendered prompt, return the raw model output
        as a string. Implementations do NOT parse or validate — that
        is the orchestrator's job.

        Malformed responses (empty string, HTTP failure, refusal)
        should raise, never return a placeholder."""
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

    def generate(self, prompt: str) -> str:
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
        return path.read_text(encoding="utf-8")


# --- Failing mock (for tests) -------------------------------------------


class ProgrammableMockLLMClient(LLMClient):
    """Returns a deterministic sequence of responses; used to exercise
    retry-on-repair and hard-fail-after-max-retries paths in tests.

    Give it a list of strings; each call to `.generate()` returns the
    next one. When the list is exhausted, raises StopIteration."""

    name = "programmable-mock"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def generate(self, prompt: str) -> str:
        if self._call_count >= len(self._responses):
            raise StopIteration(
                f"ProgrammableMockLLMClient exhausted after "
                f"{self._call_count} calls; no more responses queued."
            )
        r = self._responses[self._call_count]
        self._call_count += 1
        return r


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

    # 429s are transient (rate limit), NOT extraction failures. Retry
    # with exponential backoff up to this many times per call before
    # giving up. Counted separately from parse/validation retries.
    # Tuned for free-tier per-minute quotas: 8 retries with backoff up
    # to 64s covers a full quota-window reset.
    MAX_RATE_LIMIT_RETRIES = 8
    RATE_LIMIT_BACKOFF_CAP_S = 64.0

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
        client=None,  # injected httpx.Client for tests
        raw_log_dir: Path | None = None,
        validate_model: bool = True,
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
        import httpx  # noqa: F401 — pulled into scope for _get_client
        self._client = client
        self.name = f"gemini:{self._model_name}"

        # --- Observability. Every call updates the per-run counters
        # below; the runner reads them after each extract() to compute
        # per-paper cost and to attribute retries.
        self.calls = 0
        self.total_prompt_tokens = 0
        self.total_output_tokens = 0
        self.total_latency_s = 0.0
        self.rate_limit_hits = 0  # 429s, counted separately from failures
        self.server_error_hits = 0  # 5xx transient errors, retried
        self._raw_log_dir = raw_log_dir
        self._per_paper_attempts: dict[str, int] = {}

        # Fail loudly at startup if the configured model doesn't resolve.
        if validate_model:
            self._validate_model()

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

    def _retry_delay_seconds(self, response, rl_attempt: int) -> float:
        """How long to wait after a 429. Gemini returns a precise
        RetryInfo.retryDelay (e.g. "39s") in the error BODY (not the
        Retry-After header), so honor that when present — blind
        exponential backoff otherwise wastes minutes per rate-limited
        call. Falls back to exponential, capped."""
        # 1) Retry-After header (rare for this API but cheap to check).
        header = response.headers.get("retry-after")
        if header and header.isdigit():
            return float(header)
        # 2) RetryInfo in the JSON error body.
        try:
            details = response.json().get("error", {}).get("details", [])
            for d in details:
                if d.get("@type", "").endswith("RetryInfo"):
                    delay = d.get("retryDelay", "")
                    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)s$", str(delay))
                    if m:
                        # small pad so we clear the window edge
                        return float(m.group(1)) + 1.0
        except Exception:
            pass
        # 3) Exponential fallback, capped.
        return min(2.0 ** rl_attempt, self.RATE_LIMIT_BACKOFF_CAP_S)

    def generate(self, prompt: str) -> str:
        import time
        import httpx
        client = self._get_client()
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self._temperature,
                "response_mime_type": "application/json",
            },
        }

        # --- Request with 429 backoff. A 429 is a rate limit, not an
        # extraction failure; we retry it here (below the orchestrator's
        # parse/validation retry loop) with exponential backoff and count
        # it separately.
        response = None
        for rl_attempt in range(self.MAX_RATE_LIMIT_RETRIES + 1):
            t0 = time.time()
            response = client.post(
                self.endpoint,
                params={"key": self._api_key},
                json=payload,
            )
            self.total_latency_s += time.time() - t0
            if response.status_code == 429:
                self.rate_limit_hits += 1
                if rl_attempt < self.MAX_RATE_LIMIT_RETRIES:
                    sleep_s = self._retry_delay_seconds(response, rl_attempt)
                    time.sleep(sleep_s)
                    continue
            elif response.status_code >= 500:
                # Transient server error (503/500) — common on preview
                # models. Retry with plain exponential backoff, capped,
                # counted separately from rate limits.
                self.server_error_hits += 1
                if rl_attempt < self.MAX_RATE_LIMIT_RETRIES:
                    time.sleep(min(2.0 ** rl_attempt, self.RATE_LIMIT_BACKOFF_CAP_S))
                    continue
            break

        self.calls += 1
        assert response is not None
        response.raise_for_status()
        body = response.json()

        # Usage stats — Gemini returns these under usageMetadata.
        usage = body.get("usageMetadata") or {}
        self.total_prompt_tokens += int(usage.get("promptTokenCount") or 0)
        self.total_output_tokens += int(usage.get("candidatesTokenCount") or 0)

        # Gemini's response shape: candidates[0].content.parts[0].text
        try:
            candidates = body.get("candidates") or []
            if not candidates:
                raise ValueError("no candidates in Gemini response")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            if not parts:
                raise ValueError("no parts in Gemini candidate")
            text = parts[0].get("text")
            if not text:
                raise ValueError("empty text in Gemini part")
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise RuntimeError(
                f"Gemini returned an unexpected response shape: {e}"
            ) from e

        # Tee raw response to disk if requested.
        if self._raw_log_dir is not None:
            import re as _re
            m = _re.search(r"Paper ID:\s*`([^`]+)`", prompt)
            paper_id = m.group(1) if m else "unknown"
            self._per_paper_attempts[paper_id] = (
                self._per_paper_attempts.get(paper_id, 0) + 1
            )
            attempt = self._per_paper_attempts[paper_id]
            safe = _re.sub(r"[^A-Za-z0-9_.-]+", "_", paper_id)
            self._raw_log_dir.mkdir(parents=True, exist_ok=True)
            (self._raw_log_dir / f"{safe}.attempt{attempt}.txt").write_text(
                text, encoding="utf-8"
            )
        return text


__all__ = [
    "GeminiLLMClient",
    "LLMClient",
    "MockLLMClient",
    "ProgrammableMockLLMClient",
]
