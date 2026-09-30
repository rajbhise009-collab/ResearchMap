"""Cites-both fetcher — filter syntax, exclusion of A/B, top-N clamp,
graceful when the audit is empty. Uses respx to mock OpenAlex."""

from __future__ import annotations

import httpx
import pytest
import respx

from backend.app.api.cites_both import query_cites_both, _wid


def _work(wid, title="t", year=2020, cited=10, venue="J"):
    return {
        "id": f"https://openalex.org/{wid}",
        "doi": f"10.1000/{wid}",
        "display_name": title,
        "publication_year": year,
        "cited_by_count": cited,
        "primary_location": {"source": {"display_name": venue}},
    }


@respx.mock
def test_query_uses_cites_A_and_cites_B_and_filter():
    route = respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json={
            "meta": {"count": 3},
            "results": [_work("W100", cited=200),
                         _work("W101", cited=100),
                         _work("W102", cited=50)],
        })
    )
    q = query_cites_both("openalex:W1", "openalex:W2",
                          api_key="fake", top_n=5)
    assert route.called
    call = route.calls[0]
    # Filter must be AND across two cites terms (comma-separated).
    # httpx URL-encodes both the colon and the comma; unquote first.
    from urllib.parse import unquote
    decoded = unquote(call.request.url.query.decode())
    assert "cites:W1,cites:W2" in decoded
    assert q["total_cites_both"] == 3
    assert [t["wid"] for t in q["top"]] == ["W100", "W101", "W102"]


@respx.mock
def test_query_excludes_A_and_B_themselves():
    # OpenAlex sometimes returns A or B if their own metadata cross-cites
    # each other. Those must not appear in the third-party list.
    respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json={
            "meta": {"count": 5},
            "results": [_work("W1", cited=999),   # is A — exclude
                         _work("W2", cited=888),   # is B — exclude
                         _work("W100", cited=200),
                         _work("W101", cited=100)],
        })
    )
    q = query_cites_both("openalex:W1", "openalex:W2",
                          api_key="fake", top_n=10)
    wids = [t["wid"] for t in q["top"]]
    assert "W1" not in wids and "W2" not in wids
    assert wids == ["W100", "W101"]


@respx.mock
def test_query_clamps_top_n():
    respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json={
            "meta": {"count": 100},
            "results": [_work(f"W{i}", cited=200 - i) for i in range(30)],
        })
    )
    q = query_cites_both("openalex:WA", "openalex:WB",
                          api_key="fake", top_n=5)
    assert len(q["top"]) == 5


def test_wid_normalizer_handles_formats():
    assert _wid("openalex:W123") == "W123"
    assert _wid("https://openalex.org/W456") == "W456"
    assert _wid("W789") == "W789"
    assert _wid("") == ""
    assert _wid(None) == ""
