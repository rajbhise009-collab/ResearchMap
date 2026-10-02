"""Gemini Batch API client — for the 200-paper corpus run ONLY.

Batch mode is 50% of standard cost with a target 24h turnaround
(usually faster). Non-urgent full-corpus extraction is exactly its use
case. It is DELIBERATELY NOT used for the 21-paper abstract-vs-fulltext
comparison — that run must stay identical to the abstract arm
(synchronous generateContent), or the comparison confounds input source
with request path.

Endpoints (v1beta):
  POST   /models/{model}:batchGenerateContent   — submit a job
  GET    /batches/{batch_id}                     — poll job state
Results come back inline or as a downloadable JSONL file; each result
carries the `metadata.key` we set per request so we can map it back to
a paper id.

This client does NOT parse/validate/cache — that stays in the
Extractor. It returns raw text per key; a batch runner feeds those
through `Extractor._parse_validate_augment`-equivalent path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from backend.app.config import get_settings

API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# The live v1beta API reports states with a BATCH_STATE_ prefix
# (BATCH_STATE_RUNNING, BATCH_STATE_SUCCEEDED, ...). Some docs/older
# surfaces use JOB_STATE_. Match on the suffix so both work.
_TERMINAL_SUFFIXES = {"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"}
TERMINAL_STATES = {
    f"{p}_{s}"
    for p in ("JOB_STATE", "BATCH_STATE")
    for s in _TERMINAL_SUFFIXES
}


@dataclass
class BatchJob:
    batch_id: str
    state: str
    raw: dict = field(default_factory=dict)

    @property
    def done(self) -> bool:
        return self.state in TERMINAL_STATES or self.state.endswith(
            tuple(_TERMINAL_SUFFIXES)
        )

    @property
    def succeeded(self) -> bool:
        return self.state.endswith("SUCCEEDED")


class GeminiBatchClient:
    """Submit + poll + collect a batch of generateContent requests.

    Same startup discipline as GeminiLLMClient: requires GEMINI_API_KEY,
    validates the model, and reports the model in provenance so batch
    extractions carry the same (model, input_source, prompt_hash) key as
    synchronous ones.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
        client=None,
        validate_model: bool = True,
    ) -> None:
        settings = get_settings()
        key = api_key
        if key is None and settings.gemini_api_key is not None:
            key = settings.gemini_api_key.get_secret_value()
        if not key:
            raise RuntimeError(
                "GeminiBatchClient requires GEMINI_API_KEY. Batch mode is a "
                "PAID/quota-consuming path; ensure approval before use."
            )
        self._api_key = key
        self._model_name = model_name or settings.gemini_model
        self._temperature = temperature
        self._client = client
        self.name = f"gemini-batch:{self._model_name}"
        if validate_model:
            self._validate_model()

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_client(self):
        import httpx
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(120.0, connect=10.0),
                headers={"User-Agent": "ResearchMap/0.1"},
            )
        return self._client

    def _validate_model(self) -> None:
        client = self._get_client()
        resp = client.get(f"{API_BASE}/models",
                          params={"key": self._api_key, "pageSize": 200})
        resp.raise_for_status()
        wanted = self._model_name if self._model_name.startswith("models/") \
            else f"models/{self._model_name}"
        names = {m.get("name") for m in resp.json().get("models", [])}
        if wanted not in names:
            raise RuntimeError(
                f"Configured GEMINI_MODEL={self._model_name!r} not in models.list."
            )

    # --- Submit -----------------------------------------------------

    def submit(self, requests: dict[str, str], *, display_name: str) -> str:
        """Submit inline batch requests. `requests` maps a key (paper id)
        to a rendered prompt. Returns the batch id.

        Inline is capped at 20MB; the 200-paper full-text corpus may
        exceed that, in which case the caller should split into multiple
        batches (see `chunk_requests`)."""
        client = self._get_client()
        inline = [
            {
                "request": {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": self._temperature,
                        "response_mime_type": "application/json",
                    },
                },
                "metadata": {"key": key},
            }
            for key, prompt in requests.items()
        ]
        payload = {
            "batch": {
                "display_name": display_name,
                "input_config": {"requests": {"requests": inline}},
            }
        }
        r = client.post(
            f"{API_BASE}/models/{self._model_name}:batchGenerateContent",
            params={"key": self._api_key}, json=payload,
        )
        r.raise_for_status()
        body = r.json()
        # The create response returns the operation/batch resource name.
        name = body.get("name") or body.get("batch", {}).get("name") or ""
        return name.rsplit("/", 1)[-1] if name else ""

    # --- Poll -------------------------------------------------------

    def poll(self, batch_id: str) -> BatchJob:
        client = self._get_client()
        r = client.get(f"{API_BASE}/batches/{batch_id}",
                       params={"key": self._api_key})
        r.raise_for_status()
        body = r.json()
        state = (
            body.get("metadata", {}).get("state")
            or body.get("state")
            or "JOB_STATE_UNSPECIFIED"
        )
        return BatchJob(batch_id=batch_id, state=state, raw=body)

    def wait(self, batch_id: str, *, poll_interval_s: float = 30.0,
             timeout_s: float = 26 * 3600) -> BatchJob:
        """Poll until terminal or timeout. Batch target is 24h, so the
        default timeout is 26h."""
        start = time.time()
        while True:
            job = self.poll(batch_id)
            if job.done:
                return job
            if time.time() - start > timeout_s:
                return job
            time.sleep(poll_interval_s)

    # --- Results ----------------------------------------------------

    def results(self, job: BatchJob) -> dict[str, str]:
        """Raw response text per key (see results_with_usage)."""
        return {k: text for k, (text, _u) in self.results_with_usage(job).items()}

    def results_with_usage(self, job: BatchJob) -> dict[str, tuple[str, dict]]:
        """(text, usageMetadata) per key from a SUCCEEDED job's inline
        responses. The usage block is what the ledger needs to bill each
        result. (File-based results would need a download step; inline is
        what `submit` uses.)"""
        out: dict[str, tuple[str, dict]] = {}
        resp = job.raw.get("response", {}) or {}
        inlined = (
            (resp.get("inlinedResponses") or {}).get("inlinedResponses")
            or resp.get("inlined_responses")
            or []
        )
        for item in inlined:
            key = (item.get("metadata") or {}).get("key")
            r = item.get("response") or {}
            try:
                text = r["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError):
                text = ""
            if key:
                out[key] = (text, r.get("usageMetadata") or {})
        return out


def record_batch_usage(results: dict[str, tuple[str, dict]], *, stage: str,
                       model: str, ledger=None) -> float:
    """Bill every returned batch result to the spend ledger at the batch
    rate (50% off). Returns the INR recorded. Call exactly once per
    collected job — callers guard with a `ledger_recorded` flag."""
    from backend.app.extraction.spend_ledger import SpendLedger
    ledger = ledger or SpendLedger.load()
    total = 0.0
    for _key, (_text, usage) in results.items():
        e = ledger.record(
            stage=stage, model=model, batch=True,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            candidates_tokens=int(usage.get("candidatesTokenCount") or 0),
            thoughts_tokens=int(usage.get("thoughtsTokenCount") or 0),
        )
        total += e.cost_inr
    return total


def chunk_requests(
    requests: dict[str, str], *, max_bytes: int = 18_000_000
) -> list[dict[str, str]]:
    """Split a request map so each chunk's rendered prompts stay under
    the inline 20MB cap (18MB headroom). Deterministic (sorted keys)."""
    chunks: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    size = 0
    for key in sorted(requests):
        prompt = requests[key]
        b = len(prompt.encode("utf-8")) + len(key) + 64
        if cur and size + b > max_bytes:
            chunks.append(cur)
            cur, size = {}, 0
        cur[key] = prompt
        size += b
    if cur:
        chunks.append(cur)
    return chunks


__all__ = ["BatchJob", "GeminiBatchClient", "chunk_requests", "TERMINAL_STATES",
           "record_batch_usage"]
