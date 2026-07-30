"""OpenAlex client — primary literature source.

Auth model (2026-02-13 onward): every request MUST carry a query
parameter `api_key=YOUR_KEY`. The old polite-pool `mailto` convention
has been retired; unauthenticated calls are capped at 100 credits/day
and return HTTP 409 when the quota is exhausted. There is no header
alternative to the query parameter — the docs are explicit about that.

Credit accounting: every response carries these headers, which we
capture and log per run:
    X-RateLimit-Limit          daily budget in credits
    X-RateLimit-Remaining      credits left in today's budget
    X-RateLimit-Credits-Used   cost of THIS request
    X-RateLimit-Reset          seconds until midnight-UTC reset

Cost note: `search=` list endpoints cost 10× more than `filter=` list
endpoints (10 credits vs 1 credit per call, as of 2026-02). Callers
should reach for `search_filtered()` whenever a structured filter would
give the same result set as a free-text search.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.app.config import get_settings
from backend.app.ingestion.lit_source import LitSource
from backend.app.ingestion.normalizer import from_openalex, openalex_id
from backend.app.models import Paper


OPENALEX_BASE = "https://api.openalex.org"


@dataclass
class CreditLedger:
    """Accumulates per-request credit usage across one client session.

    We total `credits_used_this_run` from `X-RateLimit-Credits-Used`
    because it's the only value that survives concurrent traffic from
    other clients sharing the same key — `Remaining` can drop from
    other sources between requests.
    """

    calls: int = 0
    credits_used_this_run: int = 0
    last_limit: int | None = None
    last_remaining: int | None = None
    last_reset_seconds: int | None = None
    per_endpoint: dict[str, int] = field(default_factory=dict)

    def record(self, endpoint: str, headers: httpx.Headers) -> None:
        self.calls += 1
        cost = _read_int(headers, "X-RateLimit-Credits-Used")
        if cost is not None:
            self.credits_used_this_run += cost
            self.per_endpoint[endpoint] = self.per_endpoint.get(endpoint, 0) + cost
        limit = _read_int(headers, "X-RateLimit-Limit")
        remaining = _read_int(headers, "X-RateLimit-Remaining")
        reset = _read_int(headers, "X-RateLimit-Reset")
        if limit is not None:
            self.last_limit = limit
        if remaining is not None:
            self.last_remaining = remaining
        if reset is not None:
            self.last_reset_seconds = reset

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "credits_used_this_run": self.credits_used_this_run,
            "per_endpoint_credits": dict(self.per_endpoint),
            "daily_limit": self.last_limit,
            "daily_remaining": self.last_remaining,
            "seconds_until_reset": self.last_reset_seconds,
        }


def _read_int(headers: httpx.Headers, name: str) -> int | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class OpenAlexClient(LitSource):
    """OpenAlex Works search + fetch with credit accounting."""

    name = "openalex"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        base_url: str = OPENALEX_BASE,
        page_size: int = 25,
    ) -> None:
        settings = get_settings()
        key = api_key
        if key is None and settings.openalex_api_key is not None:
            key = settings.openalex_api_key.get_secret_value()
        if not key:
            raise RuntimeError(
                "OpenAlexClient requires OPENALEX_API_KEY. "
                "OpenAlex made keys mandatory on 2026-02-13; the old "
                "polite-pool mailto no longer works. Get a free key at "
                "https://openalex.org/settings/api or use SeedLitSource "
                "for the offline pipeline."
            )
        self._api_key = key
        self._base_url = base_url.rstrip("/")
        self._page_size = page_size
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": "ResearchMap/0.1"},
        )
        self.credits = CreditLedger()

    # --- LitSource API ---

    def search(self, query: str, *, limit: int) -> Iterator[Paper]:
        """Free-text search across title/abstract/fulltext.

        Costs 10 credits per page. Prefer `search_filtered()` when a
        structured filter would work.
        """
        yield from self._paginated_works(
            base_params={"search": query} if query else {},
            limit=limit,
            endpoint_label="works.search" if query else "works.list",
        )

    def search_filtered(
        self,
        *,
        search: str | None = None,
        filter: str | None = None,
        sort: str | None = None,
        limit: int,
    ) -> Iterator[Paper]:
        """Filter-first search — cheapest way to run a structured query.

        A filter-only call costs 1 credit per page; adding `search`
        promotes it to a 10-credit-per-page search endpoint. Pass
        `filter` alone whenever possible.
        """
        params: dict[str, str] = {}
        endpoint_label = "works.list"
        if filter:
            params["filter"] = filter
        if search:
            params["search"] = search
            endpoint_label = "works.search"
        if sort:
            params["sort"] = sort
        yield from self._paginated_works(
            base_params=params, limit=limit, endpoint_label=endpoint_label
        )

    def raw_works(
        self,
        *,
        filter: str,
        sort: str | None = None,
        limit: int,
        per_page: int = 50,
    ) -> Iterator[dict]:
        """Yield RAW OpenAlex Work records (not normalized Paper objects)
        for a filter query. Snowball traversal needs raw fields
        (`referenced_works`, `topics`, `cited_by_count`,
        `abstract_inverted_index`) that the Paper model drops.

        1 credit per page (filter-only list endpoint). Paginates by
        cursor up to `limit` records.
        """
        if limit <= 0:
            return
        remaining = limit
        cursor = "*"
        while remaining > 0:
            params = {
                "filter": filter,
                "per-page": str(min(per_page, remaining)),
                "cursor": cursor,
            }
            if sort:
                params["sort"] = sort
            payload = self._request(path="/works", params=params,
                                     endpoint_label="works.list")
            body = payload.get("body") or {}
            results = body.get("results") or []
            if not results:
                return
            for record in results:
                if remaining <= 0:
                    return
                yield record
                remaining -= 1
            cursor = (body.get("meta") or {}).get("next_cursor")
            if not cursor:
                return

    def get_by_id(self, paper_id: str) -> Paper | None:
        """Singleton fetch — free (0 credits)."""
        native = paper_id.split(":", 1)[-1] if paper_id.startswith("openalex:") else paper_id
        payload = self._request(path=f"/works/{native}", endpoint_label="works.singleton")
        record = payload.get("body") or {}
        if not record or not record.get("id"):
            return None
        return from_openalex(record)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OpenAlexClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # --- Internals ---

    def _paginated_works(
        self,
        *,
        base_params: dict[str, str],
        limit: int,
        endpoint_label: str,
    ) -> Iterator[Paper]:
        if limit <= 0:
            return
        remaining = limit
        cursor = "*"
        while remaining > 0:
            params = {
                **base_params,
                "per-page": str(min(self._page_size, remaining)),
                "cursor": cursor,
            }
            payload = self._request(path="/works", params=params,
                                     endpoint_label=endpoint_label)
            body = payload.get("body") or {}
            results = body.get("results") or []
            if not results:
                return
            for record in results:
                if remaining <= 0:
                    return
                try:
                    yield from_openalex(record)
                    remaining -= 1
                except Exception:  # noqa: BLE001 — validation failure = skip
                    continue
            cursor = (body.get("meta") or {}).get("next_cursor")
            if not cursor:
                return

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _request(
        self,
        *,
        path: str,
        params: dict[str, str] | None = None,
        endpoint_label: str,
    ) -> dict:
        merged = {**(params or {}), "api_key": self._api_key}
        url = f"{self._base_url}{path}"
        response = self._client.get(url, params=merged)
        # Always record credit headers, even on 4xx — the request still
        # counted against the daily budget.
        self.credits.record(endpoint_label, response.headers)
        if response.status_code == 409:
            raise OpenAlexQuotaError(
                f"OpenAlex returned 409 (quota exhausted). "
                f"Daily limit={self.credits.last_limit}, "
                f"remaining={self.credits.last_remaining}."
            )
        if response.status_code >= 500 or response.status_code == 429:
            response.raise_for_status()  # tenacity retries
        response.raise_for_status()
        return {"body": response.json(), "headers": dict(response.headers)}


class OpenAlexQuotaError(RuntimeError):
    """Raised when the API reports 409 (daily credit budget exhausted)."""


__all__ = [
    "CreditLedger",
    "OPENALEX_BASE",
    "OpenAlexClient",
    "OpenAlexQuotaError",
    "openalex_id",
]
