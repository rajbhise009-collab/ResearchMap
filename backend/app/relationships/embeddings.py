"""Embedding provider — behind an interface, like every other external
dependency. Claims are embedded to shortlist candidate pairs cheaply
before any pairwise LLM call.

- `EmbeddingClient` — the interface.
- `MockEmbeddingClient` — deterministic, offline, free. Hash-seeded unit
  vectors; identical text -> identical vector, so tests and the offline
  pipeline are reproducible without a network.
- `GeminiEmbeddingClient` — real embeddings via the Gemini embedContent
  API (paid; gated by the relationship-layer dry-run).

Vectors are L2-normalized so cosine similarity is a plain dot product.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from backend.app.config import get_settings


def l2_normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0.0:
        return v
    return [x / n for x in v]


class EmbeddingClient(ABC):
    name: str = "abstract-embedding-client"
    dim: int = 768

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized vector per input text, in order."""


class MockEmbeddingClient(EmbeddingClient):
    """Deterministic hash-based embeddings for offline use and tests.

    Not semantically meaningful in general, but stable and cheap: the
    same text always maps to the same unit vector, so shortlist logic can
    be tested deterministically. Seeded per-text with SHA-256.
    """

    name = "mock-embedding"

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def _one(self, text: str) -> list[float]:
        # Expand a SHA-256 digest into `dim` floats deterministically.
        vec: list[float] = []
        counter = 0
        while len(vec) < self.dim:
            h = hashlib.sha256(f"{text}|{counter}".encode()).digest()
            for i in range(0, len(h), 4):
                if len(vec) >= self.dim:
                    break
                # Map 4 bytes -> float in [-1, 1].
                n = int.from_bytes(h[i:i + 4], "big")
                vec.append((n / 2**31) - 1.0)
            counter += 1
        return l2_normalize(vec)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]


class GeminiEmbeddingClient(EmbeddingClient):
    """Real embeddings via Gemini `:embedContent`. Paid — construct only
    after the dry-run gate clears."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self, *, api_key: str | None = None, model_name: str | None = None,
        dim: int | None = None, client=None, stage: str = "embedding",
        ledger=None,
    ) -> None:
        settings = get_settings()
        key = api_key
        if key is None and settings.gemini_api_key is not None:
            key = settings.gemini_api_key.get_secret_value()
        if not key:
            raise RuntimeError("GeminiEmbeddingClient requires GEMINI_API_KEY.")
        self._api_key = key
        self._model_name = model_name or settings.gemini_embedding_model
        self.dim = dim or settings.embedding_dim
        self.name = f"gemini:{self._model_name}"
        self._client = client
        # Every paid chunk is checked against, and recorded in, the spend
        # ledger (estimated tokens, upper-bound rate — see spend_ledger.py).
        self.stage = stage
        self._ledger = ledger

    def _get_client(self):
        import httpx
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(120.0, connect=10.0),
                headers={"User-Agent": "ResearchMap/0.1"},
            )
        return self._client

    BATCH = 100  # batchEmbedContents cap

    def embed(self, texts: list[str]) -> list[list[float]]:
        from backend.app.extraction.rate_limiter import estimate_tokens
        from backend.app.extraction.spend_ledger import SpendLedger
        ledger = self._ledger or SpendLedger.load()
        client = self._get_client()
        out: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            chunk = texts[i:i + self.BATCH]
            est_in = sum(estimate_tokens(t) for t in chunk)
            ledger.check_embedding_headroom(input_tokens_est=est_in,
                                            stage=self.stage)
            payload = {"requests": [
                {
                    "model": f"models/{self._model_name}",
                    "content": {"parts": [{"text": t}]},
                    "outputDimensionality": self.dim,
                }
                for t in chunk
            ]}
            r = client.post(
                f"{self.API_BASE}/models/{self._model_name}:batchEmbedContents",
                params={"key": self._api_key}, json=payload,
            )
            r.raise_for_status()
            ledger.record_embedding(stage=self.stage, model=self._model_name,
                                    input_tokens_est=est_in, n_texts=len(chunk))
            for emb in r.json().get("embeddings") or []:
                values = emb.get("values") or []
                out.append(l2_normalize([float(x) for x in values]))
        return out


__all__ = [
    "EmbeddingClient",
    "MockEmbeddingClient",
    "GeminiEmbeddingClient",
    "l2_normalize",
]
