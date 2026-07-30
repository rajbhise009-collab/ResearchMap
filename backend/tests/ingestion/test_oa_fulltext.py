"""Unit tests for the non-arXiv OA full-text helpers (pure functions;
no network)."""

from __future__ import annotations

import httpx

from backend.app.ingestion import oa_fulltext
from backend.app.ingestion.oa_fulltext import _jats_body_text, _unpaywall_pdf_urls


JATS = """<?xml version="1.0"?>
<article>
  <front><article-meta><title-group>
    <article-title>A study of hallucination</article-title>
  </title-group></article-meta></front>
  <body>
    <sec><title>Introduction</title>
      <p>Large language models hallucinate under uncertainty.</p></sec>
    <sec><title>Limitations</title>
      <p>Our method fails on long inputs.</p></sec>
  </body>
  <back><ref-list><ref><mixed-citation>Smith 2020 REFERENCE NOISE</mixed-citation></ref></ref-list></back>
</article>"""


def test_jats_body_text_extracts_body_and_drops_references():
    text = _jats_body_text(JATS)
    assert text is not None
    assert "Large language models hallucinate" in text
    assert "Our method fails on long inputs" in text
    # <back>/references must NOT leak into the body text.
    assert "REFERENCE NOISE" not in text


def test_jats_body_text_bad_xml_returns_none():
    assert _jats_body_text("<not xml") is None
    assert _jats_body_text("<article><front/></article>") is None  # no body


def test_unpaywall_pdf_urls_prefers_best_then_locations():
    payload = {
        "is_oa": True,
        "best_oa_location": {"url_for_pdf": "https://x/best.pdf"},
        "oa_locations": [
            {"url_for_pdf": "https://x/best.pdf"},          # dup, skipped
            {"url_for_pdf": None},                            # no pdf, skipped
            {"url_for_pdf": "https://x/second.pdf"},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    urls = _unpaywall_pdf_urls("10.1/x", email="e@x.com", client=client)
    assert urls == ["https://x/best.pdf", "https://x/second.pdf"]


def test_unpaywall_not_oa_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"is_oa": False})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _unpaywall_pdf_urls("10.1/x", email="e@x.com", client=client) == []


def test_pdf_bytes_rejects_non_pdf():
    from backend.app.ingestion.fulltext import _pdf_bytes_to_text
    assert _pdf_bytes_to_text(b"<html>not a pdf</html>") is None
