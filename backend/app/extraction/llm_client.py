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

    name = "gemini-flash-2.5"

    ENDPOINT = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
        temperature: float = 0.0,
        client=None,  # injected httpx.Client for tests
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
        self._model_name = model_name
        self._temperature = temperature
        # Lazy import — httpx is a dependency for the ingestion side too,
        # but keep the import local so importing this module has no
        # side effects during tests that don't instantiate the client.
        import httpx  # noqa: F401 — pulled into scope for _get_client
        self._client = client
        self.name = f"gemini-{model_name}"

    def _get_client(self):
        import httpx
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers={"User-Agent": "ResearchMap/0.1"},
            )
        return self._client

    def generate(self, prompt: str) -> str:
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
        response = client.post(
            self.ENDPOINT,
            params={"key": self._api_key},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
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
            return text
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise RuntimeError(
                f"Gemini returned an unexpected response shape: {e}"
            ) from e


__all__ = [
    "GeminiLLMClient",
    "LLMClient",
    "MockLLMClient",
    "ProgrammableMockLLMClient",
]
