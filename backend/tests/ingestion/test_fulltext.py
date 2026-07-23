"""arXiv full-text pipeline tests — chunking + resolution (HTTP mocked)."""

from __future__ import annotations

import httpx
import respx

from backend.app.ingestion.fulltext import (
    Chunk,
    chunk_fulltext,
    estimate_tokens,
    resolve_arxiv_id,
    retrieve_fulltext,
)
from backend.app.models import Paper, Source


def _paper(pid="openalex:W1", doi=None, title="A Great Paper"):
    return Paper(id=pid, source=Source.OPENALEX, source_id="W1",
                 doi=doi, title=title, year=2024)


# --- Chunking ----------------------------------------------------------


def test_small_text_is_one_chunk():
    text = "Short paper body."
    chunks = chunk_fulltext(text, token_budget=1000)
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].text == text


def test_oversize_text_splits_on_sections():
    body = (
        "Title stuff.\n"
        "\nIntroduction\n" + ("intro para. " * 200) +
        "\nMethod\n" + ("method para. " * 200) +
        "\nConclusion\n" + ("concl para. " * 200)
    )
    # Force a tiny budget so it must split.
    budget = estimate_tokens(body) // 3
    chunks = chunk_fulltext(body, token_budget=budget)
    assert len(chunks) >= 2
    # Every chunk within budget (allow the last to be smaller).
    for c in chunks:
        assert c.est_tokens <= budget + 5  # tolerance for join chars
    # Chunk indices are contiguous from 0.
    assert [c.index for c in chunks] == list(range(len(chunks)))
    # No text lost (roughly — concatenation preserves the words).
    joined = " ".join(c.text for c in chunks)
    assert "method para." in joined and "concl para." in joined


def test_single_giant_section_hard_splits():
    giant = "OneSection\n" + ("word " * 5000)
    budget = 200
    chunks = chunk_fulltext(giant, token_budget=budget)
    assert len(chunks) > 1
    for c in chunks:
        assert c.est_tokens <= budget + 5


# --- arXiv id resolution -----------------------------------------------


def test_resolve_arxiv_id_from_arxiv_doi():
    p = _paper(doi="10.48550/arxiv.2012.00955")
    with httpx.Client() as client:
        # No network call needed — DOI resolves directly.
        assert resolve_arxiv_id(p, client=client, allow_title_search=False) == "2012.00955"


def test_resolve_arxiv_id_from_normalized_doi_url():
    p = _paper(doi="https://doi.org/10.48550/arXiv.1706.03762")
    with httpx.Client() as client:
        assert resolve_arxiv_id(p, client=client, allow_title_search=False) == "1706.03762"


def test_resolve_arxiv_id_non_arxiv_doi_without_title_search_is_none():
    p = _paper(doi="10.1162/tacl_a_00407")
    with httpx.Client() as client:
        assert resolve_arxiv_id(p, client=client, allow_title_search=False) is None


@respx.mock
def test_resolve_arxiv_id_via_title_search():
    atom = """<feed><entry>
      <title>A Great Paper</title>
      <id>http://arxiv.org/abs/2401.12345</id>
    </entry></feed>"""
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=atom)
    )
    p = _paper(doi=None, title="A Great Paper")
    with httpx.Client() as client:
        assert resolve_arxiv_id(p, client=client) == "2401.12345"


@respx.mock
def test_resolve_arxiv_id_title_search_requires_exact_match():
    atom = """<feed><entry>
      <title>A Completely Different Paper</title>
      <id>http://arxiv.org/abs/2401.99999</id>
    </entry></feed>"""
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=atom)
    )
    p = _paper(doi=None, title="A Great Paper")
    with httpx.Client() as client:
        assert resolve_arxiv_id(p, client=client) is None


# --- retrieve_fulltext end-to-end (mocked) -----------------------------


@respx.mock
def test_retrieve_fulltext_flags_abstract_only_when_no_arxiv():
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text="<feed></feed>")
    )
    p = _paper(doi=None, title="Journal Only Paper")
    with httpx.Client() as client:
        res = retrieve_fulltext(p, client=client, use_cache=False)
    assert res.abstract_only is True
    assert res.fulltext is None
    assert res.reason == "no-arxiv-id"


@respx.mock
def test_retrieve_fulltext_flags_abstract_only_on_pdf_failure():
    p = _paper(doi="10.48550/arxiv.2012.00955")
    respx.get("https://arxiv.org/pdf/2012.00955").mock(
        return_value=httpx.Response(404)
    )
    with httpx.Client() as client:
        res = retrieve_fulltext(p, client=client, use_cache=False)
    assert res.abstract_only is True
    assert res.arxiv_id == "2012.00955"
    assert res.reason == "pdf-fetch-or-parse-failed"
