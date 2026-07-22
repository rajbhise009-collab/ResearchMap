"""OpenAlex client behaviour — HTTP mocked with respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from backend.app.ingestion.openalex import (
    OPENALEX_BASE,
    OpenAlexClient,
    OpenAlexQuotaError,
)


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "TEST-KEY-12345")
    from backend.app import config as cfg
    cfg.get_settings.cache_clear()
    yield "TEST-KEY-12345"


def _sample_work(wid: str, doi: str | None = None, cites: int = 10):
    return {
        "id": f"https://openalex.org/{wid}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": f"Paper {wid}",
        "publication_year": 2023,
        "authorships": [{"author": {"display_name": "X. Y"}}],
        "abstract_inverted_index": {"An": [0], "abstract": [1]},
        "cited_by_count": cites,
        "referenced_works": [],
        "open_access": {"is_oa": False},
    }


def _credit_headers(*, used: int = 10, remaining: int = 99_990, limit: int = 100_000, reset: int = 3600):
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Credits-Used": str(used),
        "X-RateLimit-Reset": str(reset),
    }


def test_client_refuses_without_api_key():
    # `_isolated_env` fixture already blanks OPENALEX_API_KEY.
    with pytest.raises(RuntimeError) as exc_info:
        OpenAlexClient()
    # Error message names the current auth model so users know why.
    assert "OPENALEX_API_KEY" in str(exc_info.value)


@respx.mock
def test_client_paginates_via_cursor(api_key):
    respx.get(f"{OPENALEX_BASE}/works").mock(
        side_effect=[
            httpx.Response(200, headers=_credit_headers(), json={
                "results": [_sample_work("W1"), _sample_work("W2")],
                "meta": {"next_cursor": "PAGE2"},
            }),
            httpx.Response(200, headers=_credit_headers(used=10, remaining=99_980), json={
                "results": [_sample_work("W3")],
                "meta": {"next_cursor": None},
            }),
        ]
    )
    with OpenAlexClient() as client:
        papers = list(client.search("transformer", limit=10))
    assert [p.id for p in papers] == ["openalex:W1", "openalex:W2", "openalex:W3"]


@respx.mock
def test_client_stops_at_limit(api_key):
    respx.get(f"{OPENALEX_BASE}/works").mock(
        return_value=httpx.Response(200, headers=_credit_headers(), json={
            "results": [_sample_work(f"W{i}") for i in range(5)],
            "meta": {"next_cursor": "next"},
        })
    )
    with OpenAlexClient() as client:
        papers = list(client.search("transformer", limit=2))
    assert len(papers) == 2


@respx.mock
def test_client_skips_malformed_records(api_key):
    respx.get(f"{OPENALEX_BASE}/works").mock(
        return_value=httpx.Response(200, headers=_credit_headers(), json={
            "results": [
                {"garbage": True},  # no id → mapper raises → skipped
                _sample_work("W2"),
            ],
            "meta": {"next_cursor": None},
        })
    )
    with OpenAlexClient() as client:
        papers = list(client.search("transformer", limit=10))
    assert [p.id for p in papers] == ["openalex:W2"]


@respx.mock
def test_client_sends_api_key_query_param(api_key):
    """Auth model 2026-02-13+: api_key as query param, NOT header."""
    route = respx.get(f"{OPENALEX_BASE}/works").mock(
        return_value=httpx.Response(200, headers=_credit_headers(),
                                     json={"results": [], "meta": {}})
    )
    with OpenAlexClient() as client:
        list(client.search("x", limit=1))
    assert route.called
    called_url = str(route.calls[0].request.url)
    assert "api_key=TEST-KEY-12345" in called_url
    # And critically: mailto is NOT sent — the polite pool is retired.
    assert "mailto=" not in called_url
    # And the key is NOT in Authorization / x-api-key headers — the
    # docs are explicit that query param is the only supported form.
    req_headers = route.calls[0].request.headers
    assert "authorization" not in {h.lower() for h in req_headers.keys()}
    assert "x-api-key" not in {h.lower() for h in req_headers.keys()}


@respx.mock
def test_client_records_credit_usage_across_pages(api_key):
    respx.get(f"{OPENALEX_BASE}/works").mock(
        side_effect=[
            httpx.Response(200, headers=_credit_headers(used=10, remaining=99_990),
                            json={"results": [_sample_work("W1")],
                                  "meta": {"next_cursor": "PAGE2"}}),
            httpx.Response(200, headers=_credit_headers(used=10, remaining=99_980),
                            json={"results": [_sample_work("W2")],
                                  "meta": {"next_cursor": None}}),
        ]
    )
    with OpenAlexClient() as client:
        list(client.search("x", limit=10))
        ledger = client.credits.as_dict()
    assert ledger["calls"] == 2
    assert ledger["credits_used_this_run"] == 20
    assert ledger["daily_limit"] == 100_000
    assert ledger["daily_remaining"] == 99_980  # last-seen value


@respx.mock
def test_search_filtered_uses_cheaper_endpoint(api_key):
    """search_filtered without a `search` param should use the filter-only
    (1-credit) endpoint and label the call as works.list."""
    route = respx.get(f"{OPENALEX_BASE}/works").mock(
        return_value=httpx.Response(
            200, headers=_credit_headers(used=1, remaining=99_999),
            json={"results": [_sample_work("W1")], "meta": {"next_cursor": None}},
        )
    )
    with OpenAlexClient() as client:
        list(client.search_filtered(filter="type:article", limit=5))
        ledger = client.credits.as_dict()
    called_url = str(route.calls[0].request.url)
    assert "filter=type%3Aarticle" in called_url
    assert "search=" not in called_url
    assert ledger["per_endpoint_credits"] == {"works.list": 1}


@respx.mock
def test_client_raises_quota_error_on_409(api_key):
    respx.get(f"{OPENALEX_BASE}/works").mock(
        return_value=httpx.Response(
            409, headers=_credit_headers(used=0, remaining=0),
            json={"error": "quota exhausted"},
        )
    )
    with OpenAlexClient() as client:
        with pytest.raises(OpenAlexQuotaError):
            list(client.search("x", limit=1))
