"""Non-arXiv open-access full-text retrieval — Unpaywall + Europe PMC.

The snowball reached into published journal literature (Nature, Springer,
Elsevier), which arXiv does not cover, collapsing full-text coverage to
19%. This recovers legal OA copies for those papers:

  1. Unpaywall (primary) — `GET api.unpaywall.org/v2/{doi}?email=…`
     returns `is_oa` + `oa_locations[]`; we take the first location with
     a `url_for_pdf`, fetch the PDF, and pypdf-extract it. Free; the only
     requirement is an email query param (verified against the live API,
     2026-07).
  2. Europe PMC (secondary) — for papers Unpaywall has no PDF for, search
     `DOI:{doi}`; if the article has a PMCID and is open-access, fetch
     `/{pmcid}/fullTextXML` (JATS) and extract the <body> text. Verified
     endpoint: `…/webservices/rest/{PMCID}/fullTextXML` (PMC-prefixed id,
     no extra /PMC/ path segment).

Recovered text is cached to the same store as arXiv full text
(`data/cache/fulltext/<paper_id>.txt`) so the extractor picks it up with
no change. Never raises; returns a source tag or None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

from backend.app.ingestion.fulltext import (
    _clean_pdf_text,
    fetch_pdf_text_from_url,
    load_cached_fulltext,
    store_fulltext,
)
from backend.app.models import Paper

UNPAYWALL = "https://api.unpaywall.org/v2"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
MIN_FULLTEXT_CHARS = 3000  # below this it's an abstract/landing stub, not full text


@dataclass
class OAResult:
    paper_id: str
    fulltext: Optional[str]
    source: Optional[str]   # "unpaywall" | "europepmc" | None
    abstract_only: bool
    reason: str
    from_cache: bool = False


def _unpaywall_pdf_urls(doi: str, *, email: str, client: httpx.Client) -> list[str]:
    """Return candidate PDF URLs from Unpaywall, best location first."""
    try:
        r = client.get(f"{UNPAYWALL}/{doi}", params={"email": email})
        r.raise_for_status()
    except httpx.HTTPError:
        return []
    d = r.json()
    if not d.get("is_oa"):
        return []
    locs = []
    if d.get("best_oa_location"):
        locs.append(d["best_oa_location"])
    locs.extend(d.get("oa_locations") or [])
    urls: list[str] = []
    for loc in locs:
        u = (loc or {}).get("url_for_pdf")
        if u and u not in urls:
            urls.append(u)
    return urls


def _epmc_fulltext(doi: str, *, client: httpx.Client) -> Optional[str]:
    """Europe PMC: DOI -> PMCID (if OA) -> JATS body text."""
    try:
        r = client.get(f"{EPMC}/search", params={
            "query": f"DOI:{doi}", "format": "json", "resultType": "core",
        })
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    results = (r.json().get("resultList") or {}).get("result") or []
    if not results:
        return None
    art = results[0]
    pmcid = art.get("pmcid")
    if not pmcid or art.get("isOpenAccess") != "Y":
        return None
    try:
        ft = client.get(f"{EPMC}/{pmcid}/fullTextXML")
        ft.raise_for_status()
    except httpx.HTTPError:
        return None
    return _jats_body_text(ft.text)


def _jats_body_text(xml: str) -> Optional[str]:
    """Extract readable text from a JATS full-text XML <body>. References
    live in <back>, so taking <body> alone drops the bibliography."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    body = root.find(".//body")
    if body is None:
        return None
    text = " ".join(t for t in body.itertext() if t and t.strip())
    return _clean_pdf_text(text) or None


def retrieve_oa_fulltext(
    paper: Paper, *, email: str, client: httpx.Client, use_cache: bool = True
) -> OAResult:
    """Recover OA full text for a paper via Unpaywall then Europe PMC.
    Caches to the shared full-text store on success."""
    if use_cache:
        cached = load_cached_fulltext(paper.id)
        if cached:
            return OAResult(paper.id, cached, None, False, "cache-hit", True)
    if not paper.doi:
        return OAResult(paper.id, None, None, True, "no-doi")

    # 1. Unpaywall PDF.
    for url in _unpaywall_pdf_urls(paper.doi, email=email, client=client):
        text = fetch_pdf_text_from_url(url, client=client)
        if text and len(text) >= MIN_FULLTEXT_CHARS:
            store_fulltext(paper.id, text)
            return OAResult(paper.id, text, "unpaywall", False, "unpaywall-pdf")

    # 2. Europe PMC full text.
    text = _epmc_fulltext(paper.doi, client=client)
    if text and len(text) >= MIN_FULLTEXT_CHARS:
        store_fulltext(paper.id, text)
        return OAResult(paper.id, text, "europepmc", False, "europepmc-xml")

    return OAResult(paper.id, None, None, True, "no-oa-fulltext")


__all__ = ["OAResult", "retrieve_oa_fulltext"]
