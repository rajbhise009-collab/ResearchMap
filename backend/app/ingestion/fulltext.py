"""arXiv full-text retrieval, storage, and chunking (Phase 1.5).

This is the critical-path fix for the extraction bottleneck: the
abstract-only run produced ~8 own-work limitations and ~6 future-work
items across 30 papers, which starves the persistent-limitations and
orphaned-future-work scorers. arXiv full text (80% coverage measured on
this corpus) is where limitations and future-work paragraphs actually
live.

Pipeline:
  1. Resolve a Paper to an arXiv id (from its arXiv DOI, an arxiv.org
     landing URL, or a title search).
  2. Fetch the PDF from arxiv.org, extract text with pypdf.
  3. Cache the extracted text under data/cache/fulltext/<paper_id>.txt.
  4. Papers with no arXiv full text are flagged `abstract_only` and stay
     in the corpus — we measure the difference, we don't drop them.

Chunking: `chunk_fulltext` splits text that would exceed a token budget
into section-aware chunks. For Gemini 3.6 Flash's context this never
triggers on a single paper (papers are ~10-40k tokens, context is far
larger), so it is a documented safety mechanism, dormant on this
model/corpus — see docs/abstract-vs-fulltext.md.

Uses only free endpoints (arXiv). No paid API.
"""

from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from backend.app.config import REPO_ROOT
from backend.app.models import Paper

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_DOI_PREFIX = "10.48550/arxiv."
FULLTEXT_CACHE = REPO_ROOT / "data" / "cache" / "fulltext"

# ~4 chars per token is the usual rough English estimate.
CHARS_PER_TOKEN = 4
# Default per-request token budget for chunking. Set far below Gemini
# 3.6 Flash's real context so the mechanism is testable; a real paper
# never approaches this, so chunking stays dormant on this corpus.
DEFAULT_CHUNK_TOKEN_BUDGET = 200_000


# --- arXiv id resolution ------------------------------------------------


def _arxiv_id_from_doi(doi: str | None) -> Optional[str]:
    if not doi:
        return None
    v = doi.strip().lower()
    for pfx in ("https://doi.org/", "http://doi.org/", "doi:"):
        if v.startswith(pfx):
            v = v[len(pfx):]
    if v.startswith(ARXIV_DOI_PREFIX):
        return v[len(ARXIV_DOI_PREFIX):]
    return None


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm_title(t: str) -> str:
    return _NON_ALNUM.sub(" ", t.lower()).strip()


def resolve_arxiv_id(
    paper: Paper, *, client: httpx.Client, allow_title_search: bool = True
) -> Optional[str]:
    """Return an arXiv id for `paper`, or None. Tries DOI first, then a
    title search against the arXiv Atom API (exact normalized match)."""
    from_doi = _arxiv_id_from_doi(paper.doi)
    if from_doi:
        return from_doi
    if not allow_title_search or not paper.title:
        return None
    query = re.sub(r"[^A-Za-z0-9 ]+", " ", paper.title)[:220]
    if not query.strip():
        return None
    try:
        r = client.get(ARXIV_API, params={
            "search_query": f"ti:{query}", "start": "0", "max_results": "3",
        })
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    want = _norm_title(paper.title)
    for entry in re.split(r"<entry>", r.text)[1:]:
        m_title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        m_id = re.search(r"<id>http[s]?://arxiv\.org/abs/([0-9]{4}\.[0-9]{4,6})", entry)
        if m_title and m_id and _norm_title(re.sub(r"\s+", " ", m_title.group(1))) == want:
            return m_id.group(1)
    return None


# --- PDF fetch + text extraction ---------------------------------------


def fetch_pdf_text(arxiv_id: str, *, client: httpx.Client) -> Optional[str]:
    """Fetch the arXiv PDF and extract its text with pypdf. Returns None
    on any fetch/parse failure — the caller flags the paper abstract_only."""
    from pypdf import PdfReader

    url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    if "application/pdf" not in r.headers.get("content-type", "") and not r.content[:4] == b"%PDF":
        return None
    try:
        reader = PdfReader(io.BytesIO(r.content))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception:
        return None
    text = _clean_pdf_text("\n".join(pages))
    return text or None


_WS_RUN = re.compile(r"[ \t]+")
_NL_RUN = re.compile(r"\n{3,}")


def _clean_pdf_text(text: str) -> str:
    """Light cleanup: de-hyphenate line breaks, collapse whitespace.
    Deliberately conservative — we keep section structure for chunking."""
    # Join words split across line breaks: "hallu-\ncination" -> "hallucination"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = _WS_RUN.sub(" ", text)
    text = _NL_RUN.sub("\n\n", text)
    return text.strip()


# --- Chunking -----------------------------------------------------------


@dataclass
class Chunk:
    index: int
    text: str
    est_tokens: int


_SECTION_HEADING = re.compile(
    r"\n(?=(?:\d+\s+|\d+\.\s+)?(?:abstract|introduction|related work|"
    r"background|method|methodology|approach|experiment|evaluation|result|"
    r"discussion|limitation|conclusion|future work|references|appendix)\b)",
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def chunk_fulltext(
    text: str, *, token_budget: int = DEFAULT_CHUNK_TOKEN_BUDGET
) -> list[Chunk]:
    """Split `text` into chunks each within `token_budget` tokens.

    If the whole text fits, returns a single chunk (the common case for
    this model/corpus). Otherwise splits on section headings, packing
    consecutive sections into chunks up to the budget; a single section
    larger than the budget is hard-split on paragraph boundaries.
    """
    if estimate_tokens(text) <= token_budget:
        return [Chunk(index=0, text=text, est_tokens=estimate_tokens(text))]

    # Split on section headings, keeping the heading with its body.
    parts = _SECTION_HEADING.split(text)
    # Further hard-split any oversize part.
    units: list[str] = []
    for part in parts:
        if estimate_tokens(part) <= token_budget:
            units.append(part)
        else:
            units.extend(_hard_split(part, token_budget))

    chunks: list[Chunk] = []
    buf = ""
    for unit in units:
        if buf and estimate_tokens(buf) + estimate_tokens(unit) > token_budget:
            chunks.append(Chunk(len(chunks), buf.strip(), estimate_tokens(buf)))
            buf = unit
        else:
            buf = (buf + "\n" + unit) if buf else unit
    if buf.strip():
        chunks.append(Chunk(len(chunks), buf.strip(), estimate_tokens(buf)))
    return chunks


def _hard_split(text: str, token_budget: int) -> list[str]:
    """Split an oversize section into <=budget pieces. Tries paragraph
    boundaries first; any single paragraph still over budget is split on
    word boundaries so nothing exceeds the budget."""
    # Break into paragraph-or-smaller units, word-splitting oversize ones.
    units: list[str] = []
    for para in text.split("\n\n"):
        if estimate_tokens(para) <= token_budget:
            units.append(para)
            continue
        words = para.split(" ")
        buf = ""
        for w in words:
            if buf and estimate_tokens(buf) + estimate_tokens(w) + 1 > token_budget:
                units.append(buf)
                buf = w
            else:
                buf = (buf + " " + w) if buf else w
        if buf:
            units.append(buf)

    # Pack units back up to the budget.
    out: list[str] = []
    buf = ""
    for u in units:
        if buf and estimate_tokens(buf) + estimate_tokens(u) > token_budget:
            out.append(buf)
            buf = u
        else:
            buf = (buf + "\n\n" + u) if buf else u
    if buf:
        out.append(buf)
    return out


# --- Cache --------------------------------------------------------------


def _safe(pid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", pid)


def cache_path(paper_id: str) -> Path:
    return FULLTEXT_CACHE / f"{_safe(paper_id)}.txt"


def load_cached_fulltext(paper_id: str) -> Optional[str]:
    p = cache_path(paper_id)
    return p.read_text(encoding="utf-8") if p.exists() else None


def store_fulltext(paper_id: str, text: str) -> None:
    FULLTEXT_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path(paper_id).write_text(text, encoding="utf-8")


# --- Top-level orchestration -------------------------------------------


@dataclass
class FulltextResult:
    paper_id: str
    arxiv_id: Optional[str]
    fulltext: Optional[str]
    abstract_only: bool
    reason: str
    from_cache: bool = False


def retrieve_fulltext(
    paper: Paper, *, client: httpx.Client, use_cache: bool = True
) -> FulltextResult:
    """Resolve → fetch → cache full text for one paper. Never raises;
    on any failure returns abstract_only=True with a reason."""
    if use_cache:
        cached = load_cached_fulltext(paper.id)
        if cached:
            return FulltextResult(paper.id, None, cached, False, "cache-hit", True)

    arxiv_id = resolve_arxiv_id(paper, client=client)
    if not arxiv_id:
        return FulltextResult(paper.id, None, None, True, "no-arxiv-id")

    text = fetch_pdf_text(arxiv_id, client=client)
    if not text:
        return FulltextResult(paper.id, arxiv_id, None, True, "pdf-fetch-or-parse-failed")

    store_fulltext(paper.id, text)
    return FulltextResult(paper.id, arxiv_id, text, False, "retrieved")


__all__ = [
    "Chunk",
    "FulltextResult",
    "chunk_fulltext",
    "estimate_tokens",
    "fetch_pdf_text",
    "load_cached_fulltext",
    "resolve_arxiv_id",
    "retrieve_fulltext",
    "store_fulltext",
]
