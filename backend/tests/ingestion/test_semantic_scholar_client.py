"""Semantic Scholar client behaviour — HTTP mocked with respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from backend.app.ingestion.semantic_scholar import S2_BASE, SemanticScholarClient
from backend.app.models import Paper, Source


def _s2_paper(pid="abc", doi="10.1/x", cites=5):
    return {
        "paperId": pid,
        "title": f"Paper {pid}",
        "abstract": "Abstract.",
        "year": 2023,
        "authors": [{"name": "A. Author"}],
        "venue": "V",
        "citationCount": cites,
        "externalIds": {"DOI": doi},
        "references": [],
        "openAccessPdf": None,
    }


@respx.mock
def test_search_paginates_by_offset():
    respx.get(f"{S2_BASE}/paper/search").mock(
        side_effect=[
            httpx.Response(200, json={"data": [_s2_paper("a"), _s2_paper("b")], "next": 2}),
            httpx.Response(200, json={"data": [_s2_paper("c")], "next": None}),
        ]
    )
    with SemanticScholarClient() as client:
        papers = list(client.search("t", limit=10))
    assert [p.id for p in papers] == ["s2:a", "s2:b", "s2:c"]


@respx.mock
def test_enrich_looks_up_by_doi_and_skips_papers_without_doi():
    lookup = respx.get(f"{S2_BASE}/paper/DOI:10.1/x").mock(
        return_value=httpx.Response(200, json=_s2_paper("abc", "10.1/x", cites=99))
    )
    with SemanticScholarClient() as client:
        input_papers = [
            Paper(id="openalex:W1", source=Source.OPENALEX, source_id="W1",
                  doi="10.1/x", title="Paper W1"),
            Paper(id="openalex:W2", source=Source.OPENALEX, source_id="W2",
                  doi=None, title="Paper W2"),  # skipped
        ]
        enriched = list(client.enrich(input_papers))
    assert lookup.call_count == 1
    assert len(enriched) == 1
    assert enriched[0].citations_in_count == 99


@respx.mock
def test_get_by_id_returns_none_on_404():
    respx.get(f"{S2_BASE}/paper/unknown").mock(return_value=httpx.Response(404))
    with SemanticScholarClient() as client:
        assert client.get_by_id("s2:unknown") is None
