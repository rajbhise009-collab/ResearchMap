"""Semantic Scholar enrichment client.

Purpose is enrichment, not primary search. Given papers already ingested
(typically from OpenAlex), we fetch S2's version and merge it in — S2
often has better citation counts, TLDRs, and open-access PDF URLs.

If no API key is configured, we still hit the public endpoint (S2 allows
unauthenticated traffic at a stricter rate limit).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.app.config import get_settings
from backend.app.ingestion.lit_source import LitSource
from backend.app.ingestion.normalizer import from_semantic_scholar
from backend.app.models import Paper


S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,title,abstract,year,authors,venue,citationCount,externalIds,references,openAccessPdf,tldr"


class SemanticScholarClient(LitSource):
    """Enrichment-first Semantic Scholar client."""

    name = "semantic_scholar"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        base_url: str = S2_BASE,
    ) -> None:
        settings = get_settings()
        key = api_key
        if key is None and settings.semantic_scholar_api_key is not None:
            key = settings.semantic_scholar_api_key.get_secret_value()
        self._api_key = key
        self._base_url = base_url.rstrip("/")
        headers = {"User-Agent": "ResearchMap/0.1"}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=headers,
        )

    # --- LitSource API ---

    def search(self, query: str, *, limit: int) -> Iterator[Paper]:
        if limit <= 0:
            return
        offset = 0
        remaining = limit
        while remaining > 0:
            page = self._request(
                "/paper/search",
                params={"query": query, "limit": min(remaining, 100),
                        "offset": offset, "fields": S2_FIELDS},
            )
            data = page.get("data") or []
            if not data:
                return
            for record in data:
                if remaining <= 0:
                    return
                try:
                    yield from_semantic_scholar(record)
                    remaining -= 1
                except Exception:  # noqa: BLE001
                    continue
            offset += len(data)
            if page.get("next") is None:
                return

    def get_by_id(self, paper_id: str) -> Paper | None:
        native = paper_id.split(":", 1)[-1] if paper_id.startswith("s2:") else paper_id
        record = self._request(f"/paper/{native}", params={"fields": S2_FIELDS})
        if not record or not record.get("paperId"):
            return None
        return from_semantic_scholar(record)

    # --- Enrichment API ---

    def enrich(self, papers: Iterable[Paper]) -> Iterator[Paper]:
        """Yield S2 versions of the given papers, looked up by DOI when
        available. Papers without a DOI are skipped (nothing to look up
        deterministically); callers can still `deduplicate` the results
        back into their OpenAlex records.
        """
        for paper in papers:
            if not paper.doi:
                continue
            record = self._request(f"/paper/DOI:{paper.doi}", params={"fields": S2_FIELDS})
            if not record or not record.get("paperId"):
                continue
            try:
                yield from_semantic_scholar(record)
            except Exception:  # noqa: BLE001
                continue

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SemanticScholarClient:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # --- Internals ---

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _request(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        response = self._client.get(url, params=params or {})
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()


__all__ = ["S2_BASE", "S2_FIELDS", "SemanticScholarClient"]
