"""Normalization + deduplication.

Turns provider-specific JSON into validated `Paper` objects and collapses
duplicates that arrive from multiple sources.

Dedup order (deterministic, most-specific first):
  1. Same normalized DOI  → merge.
  2. Same (normalized-title, year) tuple → merge.
  3. Same normalized title, year within ±CROSS_YEAR_WINDOW, AND
     at least one shared normalized last-name → merge.
     Catches the preprint-vs-published case (arXiv 2020 → journal 2021,
     no shared DOI) that pass 2 misses. This is a scoring-integrity
     fix: two records for the same work would fake independent
     replication and inflate any downstream score that counts the
     number of distinct papers reporting a claim.

When merging, we PREFER the record with a real DOI, then the one with an
abstract, then the one with more citations. `citations_out` lists are
union'd. The union order is stable so tests are reproducible.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from backend.app.models import Paper, Source


# --- Public ID helpers ---------------------------------------------------


def openalex_id(raw: str) -> str:
    """Strip the API URL prefix if present. `openalex:W123...`."""
    tail = raw.rsplit("/", 1)[-1]
    return f"openalex:{tail}"


def semantic_scholar_id(raw: str) -> str:
    return f"s2:{raw}"


def seed_id(seq: int | str) -> str:
    return f"seed:{int(seq):04d}"


# --- Normalization ------------------------------------------------------


_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")
# OpenAlex titles often contain inline HTML: `<i>When</i>`, `<sub>2</sub>`,
# `<scp>AI</scp>`. Left untouched they leak into the normalized key as
# lone `i` / `sub` / `scp` tokens and defeat title-based dedup.
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize_title(title: str) -> str:
    """Case-fold, strip HTML tags/diacritics/punctuation, collapse whitespace.

    Used only for dedup keys — the original title is preserved on the
    Paper record.
    """
    ascii_title = _HTML_TAG_RE.sub(" ", title)
    ascii_title = unicodedata.normalize("NFKD", ascii_title)
    ascii_title = ascii_title.encode("ascii", "ignore").decode("ascii")
    ascii_title = ascii_title.lower()
    ascii_title = _NON_ALNUM_RE.sub(" ", ascii_title)
    ascii_title = _WHITESPACE_RE.sub(" ", ascii_title).strip()
    return ascii_title


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    v = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    return v or None


# Distance (in publication years) within which two same-titled papers
# with a shared author are treated as the same work. Preprint → journal
# lag is typically 6-18 months; 2 covers almost every real case without
# risking collisions with distinct same-titled papers years apart.
CROSS_YEAR_WINDOW = 2

_AUTHOR_LAST_NAME_RE = re.compile(r"[^a-z\-]")


def _normalize_last_name(author: str) -> str:
    """Reduce an author string to a normalized last-name token.

    Handles the common formats OpenAlex + Semantic Scholar emit:
      "John A. Doe"    → "doe"
      "J. Doe"         → "doe"
      "Doe, John"      → "doe"
      "María Müller"   → "muller"          (diacritics stripped)

    Returns an empty string if the input has no usable letters, which
    is the correct sentinel for author-overlap (empty set ∩ anything =
    ∅ ⇒ no match)."""
    if not author or not author.strip():
        return ""
    ascii_name = unicodedata.normalize("NFKD", author).encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.lower().strip()
    if not ascii_name:
        return ""
    # "Last, First" form — take the part before the comma.
    if "," in ascii_name:
        last = ascii_name.split(",", 1)[0].strip()
    else:
        parts = [p for p in ascii_name.split() if p]
        last = parts[-1] if parts else ""
    return _AUTHOR_LAST_NAME_RE.sub("", last)


def _author_last_names(authors: list[str]) -> set[str]:
    return {name for name in (_normalize_last_name(a) for a in authors) if name}


def _authors_overlap(a: list[str], b: list[str]) -> bool:
    """True iff at least one normalized last-name is shared.

    Requires positive evidence — if either paper has no parseable
    authors, we refuse to declare a match. That protects against
    false-positive merges of two distinct same-titled papers where one
    record simply lacks author metadata."""
    left = _author_last_names(a)
    right = _author_last_names(b)
    return bool(left and right and (left & right))


# --- OpenAlex → Paper ---------------------------------------------------


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex serves abstracts as an inverted index. Rebuild it."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for token, ixs in inverted_index.items():
        for i in ixs:
            positions[i] = token
    if not positions:
        return None
    ordered = [positions[i] for i in sorted(positions)]
    return " ".join(ordered).strip() or None


def from_openalex(record: dict) -> Paper:
    """Map an OpenAlex Work JSON object to a Paper."""
    raw_id = record.get("id") or record.get("openalex")
    if not raw_id:
        raise ValueError("OpenAlex record missing 'id'")
    authorships = record.get("authorships") or []
    authors: list[str] = []
    for a in authorships:
        author = a.get("author") or {}
        name = author.get("display_name")
        if name:
            authors.append(name)

    host_venue = record.get("host_venue") or record.get("primary_location") or {}
    venue_source = host_venue.get("source") if isinstance(host_venue, dict) else None
    venue = None
    if isinstance(venue_source, dict):
        venue = venue_source.get("display_name")
    if not venue and isinstance(host_venue, dict):
        venue = host_venue.get("display_name")

    referenced = record.get("referenced_works") or []
    citations_out = [openalex_id(r) for r in referenced if isinstance(r, str) and r]

    oa_info = record.get("open_access") or {}
    oa_available = bool(oa_info.get("is_oa"))

    abstract = _reconstruct_abstract(record.get("abstract_inverted_index"))

    return Paper(
        id=openalex_id(raw_id),
        source=Source.OPENALEX,
        source_id=raw_id.rsplit("/", 1)[-1],
        doi=normalize_doi(record.get("doi")),
        title=(record.get("title") or record.get("display_name") or "").strip() or "Untitled",
        abstract=abstract,
        year=record.get("publication_year"),
        authors=authors,
        venue=venue,
        citations_out=citations_out,
        citations_in_count=int(record.get("cited_by_count") or 0),
        oa_fulltext_available=oa_available,
        fulltext=None,
    )


# --- Semantic Scholar → Paper ------------------------------------------


def from_semantic_scholar(record: dict) -> Paper:
    """Map a Semantic Scholar Paper JSON to a Paper."""
    paper_id = record.get("paperId")
    if not paper_id:
        raise ValueError("Semantic Scholar record missing 'paperId'")
    authors = [a.get("name") for a in (record.get("authors") or []) if a.get("name")]
    external_ids = record.get("externalIds") or {}
    doi = normalize_doi(external_ids.get("DOI"))
    venue = record.get("venue") or None
    referenced = record.get("references") or []
    citations_out = [semantic_scholar_id(r["paperId"]) for r in referenced if isinstance(r, dict) and r.get("paperId")]
    return Paper(
        id=semantic_scholar_id(paper_id),
        source=Source.SEMANTIC_SCHOLAR,
        source_id=paper_id,
        doi=doi,
        title=(record.get("title") or "").strip() or "Untitled",
        abstract=record.get("abstract"),
        year=record.get("year"),
        authors=authors,
        venue=venue,
        citations_out=citations_out,
        citations_in_count=int(record.get("citationCount") or 0),
        oa_fulltext_available=bool((record.get("openAccessPdf") or {}).get("url")),
        fulltext=None,
    )


# --- Merging + dedup ----------------------------------------------------


def _merge(primary: Paper, other: Paper) -> Paper:
    """Merge `other` into `primary` and return a new Paper.

    Fields on `primary` win; empty fields fall back to `other`. Citations
    are union'd preserving primary-first order.
    """
    data = primary.model_dump()
    other_data = other.model_dump()

    for field in ("doi", "abstract", "year", "venue", "fulltext"):
        if not data.get(field) and other_data.get(field):
            data[field] = other_data[field]

    if not data.get("authors") and other_data.get("authors"):
        data["authors"] = other_data["authors"]

    data["citations_in_count"] = max(
        data.get("citations_in_count", 0), other_data.get("citations_in_count", 0)
    )
    data["oa_fulltext_available"] = bool(
        data.get("oa_fulltext_available") or other_data.get("oa_fulltext_available")
    )

    seen: set[str] = set()
    combined: list[str] = []
    for cite in list(data.get("citations_out", [])) + list(other_data.get("citations_out", [])):
        if cite and cite not in seen:
            seen.add(cite)
            combined.append(cite)
    data["citations_out"] = combined

    return Paper.model_validate(data)


def _pick_primary(a: Paper, b: Paper) -> tuple[Paper, Paper]:
    """Return (primary, secondary). Prefers records with a DOI, then those
    with an abstract, then higher citation counts. Ties break by source
    priority: OpenAlex first (its metadata is more complete)."""
    def score(p: Paper) -> tuple[int, int, int, int]:
        source_rank = {
            Source.OPENALEX.value: 3,
            Source.SEMANTIC_SCHOLAR.value: 2,
            Source.SEED.value: 1,
        }.get(p.source, 0)
        return (
            1 if p.doi else 0,
            1 if p.abstract else 0,
            p.citations_in_count,
            source_rank,
        )
    return (a, b) if score(a) >= score(b) else (b, a)


def deduplicate(papers: Iterable[Paper]) -> list[Paper]:
    """Collapse duplicate Papers via three deterministic passes.

    Passes (most-specific first):
      1. Same normalized DOI.
      2. Same (normalized-title, year).
      3. Same normalized title, |Δyear| ≤ CROSS_YEAR_WINDOW,
         at least one shared normalized last-name.

    Order-stable: the first occurrence of a paper keeps its position
    in the output list.
    """
    seen_order: list[str] = []  # paper.id in encounter order
    by_id: dict[str, Paper] = {}
    doi_index: dict[str, str] = {}                       # doi -> paper.id
    title_year_index: dict[tuple[str, int | None], str] = {}  # (norm_title, year) -> paper.id
    title_index: dict[str, list[str]] = {}               # norm_title -> [paper.id, …]

    def _register(pid: str, p: Paper) -> None:
        """Update every index for a paper that now lives in by_id under
        this id. Safe to call after both new-paper insert and merge."""
        if p.doi:
            doi_index[p.doi] = pid
        norm_t = normalize_title(p.title)
        title_year_index[(norm_t, p.year)] = pid
        if norm_t and pid not in title_index.setdefault(norm_t, []):
            title_index[norm_t].append(pid)

    for paper in papers:
        match_id: str | None = None

        # Pass 1 — DOI.
        if paper.doi and paper.doi in doi_index:
            match_id = doi_index[paper.doi]

        # Pass 2 — exact (title, year).
        if match_id is None:
            key = (normalize_title(paper.title), paper.year)
            if key[0] and key in title_year_index:
                match_id = title_year_index[key]

        # Pass 3 — cross-year title + shared author.
        if match_id is None and paper.year is not None:
            norm_t = normalize_title(paper.title)
            if norm_t:
                for candidate_id in title_index.get(norm_t, []):
                    candidate = by_id[candidate_id]
                    if candidate.year is None:
                        continue
                    delta = abs(candidate.year - paper.year)
                    if delta == 0 or delta > CROSS_YEAR_WINDOW:
                        # Same-year handled by pass 2; too-far apart is
                        # too risky to merge on title+author alone.
                        continue
                    if _authors_overlap(paper.authors, candidate.authors):
                        match_id = candidate_id
                        break

        if match_id is not None:
            existing = by_id[match_id]
            primary, secondary = _pick_primary(existing, paper)
            merged = _merge(primary, secondary)
            by_id[match_id] = merged
            _register(match_id, merged)
            continue

        # New paper — appended to seen_order and registered in every index.
        by_id[paper.id] = paper
        seen_order.append(paper.id)
        _register(paper.id, paper)

    return [by_id[pid] for pid in seen_order]


__all__ = [
    "CROSS_YEAR_WINDOW",
    "deduplicate",
    "from_openalex",
    "from_semantic_scholar",
    "normalize_doi",
    "normalize_title",
    "openalex_id",
    "seed_id",
    "semantic_scholar_id",
]
