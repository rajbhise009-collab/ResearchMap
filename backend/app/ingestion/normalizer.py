"""Normalization + deduplication.

Turns provider-specific JSON into validated `Paper` objects and collapses
duplicates that arrive from multiple sources.

Dedup order (deterministic, most-specific first):
  1. Same normalized DOI  → merge.
  2. Same (normalized-title, year) tuple → merge.
  3. Same normalized title, year within ±CROSS_YEAR_WINDOW, AND
     at least one shared normalized last-name → merge.
  4. One record has an arXiv DOI (10.48550/arxiv.*) and the other has
     a non-arXiv DOI, same normalized title, AND at least one shared
     normalized last-name → merge. Fires regardless of year gap.

The whole point of these passes is scoring integrity — two records for
the same work would fake independent replication and inflate any
downstream score that counts distinct papers reporting a claim.

Survivor rule (deterministic, order-independent) — see
docs/merge-policy.md:
  1. Non-arXiv DOI beats arXiv-DOI beats no-DOI.
  2. Presence of a `venue` string.
  3. Higher `citations_in_count`.
  4. Lexically-lower `id` as the final tiebreak.

Merge policy is per-field (documented in the same file). Nothing is
silently lost: every collapsed record's ID lands in the survivor's
`merged_from` list, transitively.

The final output of `deduplicate()` is sorted by `id` so the same input
in any order yields byte-identical results.
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


# --- Merge policy -------------------------------------------------------
#
# Formal policy documented in docs/merge-policy.md; the constants and
# helpers here are the runtime realisation of that policy.

ARXIV_DOI_PREFIX = "10.48550/arxiv."

# Policy for combining citations_in_count on merge. Choices:
#   "max"      — take the larger of the two (default). Under-counts if
#                a citer references BOTH versions, but that's rare;
#                over-counting via sum() would systematically double-
#                count anyone who cites the preprint and separately the
#                journal, inflating persistent-limitation and support
#                scores.
#   "sum"      — add both. Only sensible if citation graphs are known
#                to be disjoint per side, which OpenAlex+S2 do NOT
#                guarantee.
#   "survivor" — keep the survivor's count as-is, ignoring the loser.
#                Silently loses information from the merged record.
# Change deliberately — this is a ranking-input decision, not a detail.
CITATIONS_MERGE_POLICY = "max"


def _is_arxiv_doi(doi: str | None) -> bool:
    """True iff `doi` looks like an arXiv-issued preprint DOI.

    arXiv assigns DOIs of the form `10.48550/arxiv.<paperid>`. The
    prefix is case-preserved by the API but we normalise-lower before
    comparing (matches `Paper.doi` post-normalization)."""
    if not doi:
        return False
    return doi.lower().startswith(ARXIV_DOI_PREFIX)


def _survivor_key(p: Paper) -> tuple[int, int, int]:
    """Deterministic tiebreak — higher wins. Total ties are broken by
    lex-lower id inside `_pick_survivor`.

    Tiers, in priority order:
      1. `is_pub_doi` — has a DOI that is NOT an arXiv DOI. Published
         version beats preprint.
      2. `has_venue`  — a venue string implies canonical publication.
      3. `citations_in_count` — proxy for canonical-version citations.
    """
    is_pub_doi = int(bool(p.doi) and not _is_arxiv_doi(p.doi))
    has_venue = int(bool((p.venue or "").strip()))
    return (is_pub_doi, has_venue, p.citations_in_count)


def _pick_survivor(a: Paper, b: Paper) -> tuple[Paper, Paper]:
    """Return (survivor, loser). Symmetric — swapping a and b returns
    (survivor, loser) with survivor identity unchanged."""
    ka, kb = _survivor_key(a), _survivor_key(b)
    if ka > kb:
        return a, b
    if kb > ka:
        return b, a
    # Total tie on every policy tier — break with lex-lower id so the
    # choice is independent of iteration order.
    return (a, b) if a.id <= b.id else (b, a)


# --- Merging ------------------------------------------------------------


def _merge(survivor: Paper, loser: Paper) -> Paper:
    """Combine `loser` INTO `survivor` under the documented per-field
    policy. See docs/merge-policy.md for the full table.

    Summary:
      • Identity fields (id, source, source_id, title): survivor-only.
      • Fill-in fields (doi, abstract, year, authors, venue, fulltext):
        keep survivor's if truthy, else take loser's.
      • citations_in_count: policy-controlled (CITATIONS_MERGE_POLICY).
      • citations_out: order-stable union, survivor's first.
      • oa_fulltext_available: OR.
      • merged_from: transitive union of every collapsed ID (survivor's
        existing merged_from + loser.id + loser.merged_from), dedup'd
        and stripped of the survivor's own id.
    """
    data = survivor.model_dump()
    other = loser.model_dump()

    # Fill-in — take loser's only when survivor's is empty.
    for field in ("doi", "abstract", "year", "venue", "fulltext"):
        if not data.get(field) and other.get(field):
            data[field] = other[field]
    if not data.get("authors") and other.get("authors"):
        data["authors"] = other["authors"]

    # citations_in_count — policy-controlled.
    a_count = data.get("citations_in_count", 0) or 0
    b_count = other.get("citations_in_count", 0) or 0
    if CITATIONS_MERGE_POLICY == "max":
        data["citations_in_count"] = max(a_count, b_count)
    elif CITATIONS_MERGE_POLICY == "sum":
        data["citations_in_count"] = a_count + b_count
    elif CITATIONS_MERGE_POLICY == "survivor":
        data["citations_in_count"] = a_count
    else:
        raise ValueError(
            f"Unknown CITATIONS_MERGE_POLICY={CITATIONS_MERGE_POLICY!r}; "
            "expected one of 'max' | 'sum' | 'survivor'."
        )

    # OA availability — either side is enough.
    data["oa_fulltext_available"] = bool(
        data.get("oa_fulltext_available") or other.get("oa_fulltext_available")
    )

    # citations_out — order-stable union.
    seen: set[str] = set()
    combined: list[str] = []
    for cite in list(data.get("citations_out", [])) + list(other.get("citations_out", [])):
        if cite and cite not in seen:
            seen.add(cite)
            combined.append(cite)
    data["citations_out"] = combined

    # merged_from — every collapsed ID, transitively, order-stable,
    # with the survivor's own id stripped so it never merges into itself.
    survivor_id = data["id"]
    combined_merged_from: list[str] = []
    seen_ids: set[str] = set()
    stream = (
        list(data.get("merged_from") or [])
        + [other["id"]]
        + list(other.get("merged_from") or [])
    )
    for src in stream:
        if src and src != survivor_id and src not in seen_ids:
            seen_ids.add(src)
            combined_merged_from.append(src)
    data["merged_from"] = combined_merged_from

    return Paper.model_validate(data)


def deduplicate(papers: Iterable[Paper]) -> list[Paper]:
    """Collapse duplicate Papers via four deterministic passes.

    Passes (most-specific first):
      1. Same normalized DOI.
      2. Same (normalized-title, year).
      3. Same normalized title, |Δyear| ≤ CROSS_YEAR_WINDOW,
         at least one shared normalized last-name.
      4. arXiv-DOI ↔ non-arXiv-DOI, same normalized title, ≥1 shared
         normalized last-name. No year gap constraint — the DOI pair
         is already strong evidence.

    Output is sorted by `id` so the same input in any order yields
    byte-identical results.
    """
    by_id: dict[str, Paper] = {}
    doi_index: dict[str, str] = {}                              # doi -> paper.id
    title_year_index: dict[tuple[str, int | None], str] = {}    # (norm_title, year) -> paper.id
    title_index: dict[str, list[str]] = {}                      # norm_title -> [paper.id, …]

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

        # Pass 4 — arXiv/non-arXiv DOI pair + title + shared author.
        # Catches preprint/journal collapses even when the year gap
        # exceeds CROSS_YEAR_WINDOW.
        if match_id is None and paper.doi:
            norm_t = normalize_title(paper.title)
            if norm_t:
                paper_is_arxiv = _is_arxiv_doi(paper.doi)
                for candidate_id in title_index.get(norm_t, []):
                    candidate = by_id[candidate_id]
                    if not candidate.doi:
                        continue
                    candidate_is_arxiv = _is_arxiv_doi(candidate.doi)
                    # Exactly one side must be arXiv — otherwise this
                    # pass adds no information beyond pass 1/2/3.
                    if paper_is_arxiv == candidate_is_arxiv:
                        continue
                    if _authors_overlap(paper.authors, candidate.authors):
                        match_id = candidate_id
                        break

        if match_id is not None:
            existing = by_id[match_id]
            survivor, loser = _pick_survivor(existing, paper)
            merged = _merge(survivor, loser)
            by_id[match_id] = merged
            _register(match_id, merged)
            continue

        # New paper — registered in every index.
        by_id[paper.id] = paper
        _register(paper.id, paper)

    # Sort by id so the output is deterministic regardless of input
    # order — this is the property the order-independence test checks.
    return sorted(by_id.values(), key=lambda p: p.id)


__all__ = [
    "ARXIV_DOI_PREFIX",
    "CITATIONS_MERGE_POLICY",
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
