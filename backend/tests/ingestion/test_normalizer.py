"""Normalization + dedup — the trickiest part of Phase 1."""

from __future__ import annotations

from backend.app.ingestion.normalizer import (
    deduplicate,
    from_openalex,
    from_semantic_scholar,
    normalize_doi,
    normalize_title,
)
from backend.app.models import Paper, Source


# --- normalize_title / normalize_doi ------------------------------------


def test_normalize_title_strips_case_punct_diacritics():
    assert normalize_title("Attention Is All You Need!") == "attention is all you need"
    assert normalize_title("Café  \tRésumé") == "cafe resume"
    assert normalize_title("") == ""


def test_normalize_title_strips_inline_html_tags():
    """OpenAlex serves inline HTML in titles — leaving `<i>` in place
    turns `<i>When</i>` into stray `i` tokens and defeats dedup."""
    a = normalize_title("How Can We Know <i>When</i> Language Models Know?")
    b = normalize_title("How Can We Know When Language Models Know?")
    assert a == b
    assert "i" not in a.split()  # the tag name must not survive as a token
    # Common inline markup variants seen in the wild.
    assert normalize_title("CO<sub>2</sub> Adsorption") == "co 2 adsorption"
    assert normalize_title("Generative <scp>AI</scp>") == "generative ai"


def test_normalize_doi_strips_url_prefixes_and_lowercases():
    assert normalize_doi("https://doi.org/10.1/ABC") == "10.1/abc"
    assert normalize_doi("doi:10.1/xyz") == "10.1/xyz"
    assert normalize_doi(None) is None
    assert normalize_doi("  ") is None


# --- OpenAlex mapping ---------------------------------------------------


def _openalex_record(**over):
    base = {
        "id": "https://openalex.org/W2741809807",
        "doi": "https://doi.org/10.5555/abc",
        "title": "A Great Paper",
        "publication_year": 2023,
        "authorships": [
            {"author": {"display_name": "Alice A."}},
            {"author": {"display_name": "Bob B."}},
        ],
        "host_venue": {"display_name": "Some Journal"},
        "abstract_inverted_index": {"Hello": [0], "world": [1]},
        "cited_by_count": 42,
        "referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"],
        "open_access": {"is_oa": True},
    }
    base.update(over)
    return base


def test_from_openalex_maps_all_fields():
    p = from_openalex(_openalex_record())
    assert p.id == "openalex:W2741809807"
    assert p.source == Source.OPENALEX.value
    assert p.doi == "10.5555/abc"
    assert p.title == "A Great Paper"
    assert p.year == 2023
    assert p.authors == ["Alice A.", "Bob B."]
    assert p.venue == "Some Journal"
    assert p.abstract == "Hello world"
    assert p.citations_in_count == 42
    assert p.citations_out == ["openalex:W1", "openalex:W2"]
    assert p.oa_fulltext_available is True


def test_from_openalex_survives_missing_optional_fields():
    p = from_openalex({"id": "https://openalex.org/W9", "title": "X"})
    assert p.id == "openalex:W9"
    assert p.abstract is None
    assert p.citations_in_count == 0
    assert p.citations_out == []


# --- Semantic Scholar mapping -------------------------------------------


def test_from_semantic_scholar_maps_all_fields():
    record = {
        "paperId": "abc123",
        "title": "Another Paper",
        "abstract": "An abstract.",
        "year": 2022,
        "authors": [{"name": "Carol C."}],
        "venue": "SomeConf",
        "citationCount": 17,
        "externalIds": {"DOI": "10.5555/Abc"},
        "references": [{"paperId": "ref1"}, {"paperId": "ref2"}],
        "openAccessPdf": {"url": "https://example.com/x.pdf"},
    }
    p = from_semantic_scholar(record)
    assert p.id == "s2:abc123"
    assert p.doi == "10.5555/abc"
    assert p.citations_out == ["s2:ref1", "s2:ref2"]
    assert p.oa_fulltext_available is True
    assert p.citations_in_count == 17


# --- Dedup behaviour ----------------------------------------------------


def _p(pid, *, source, doi=None, title="T", year=2024, abstract=None,
       citations_in_count=0, citations_out=None, authors=None):
    return Paper(
        id=pid, source=source, source_id=pid.split(":", 1)[-1], doi=doi,
        title=title, abstract=abstract, year=year,
        authors=list(authors or []),
        citations_in_count=citations_in_count,
        citations_out=list(citations_out or []),
    )


def test_dedup_collapses_by_doi():
    a = _p("openalex:W1", source=Source.OPENALEX, doi="10.1/x", abstract="A",
           citations_in_count=100, citations_out=["openalex:R1"])
    b = _p("s2:XYZ", source=Source.SEMANTIC_SCHOLAR, doi="10.1/x", title="T",
           citations_in_count=200, citations_out=["s2:R2"])
    out = deduplicate([a, b])
    assert len(out) == 1
    merged = out[0]
    assert merged.doi == "10.1/x"
    # Higher citation count wins.
    assert merged.citations_in_count == 200
    # Citations union'd.
    assert set(merged.citations_out) == {"openalex:R1", "s2:R2"}


def test_dedup_collapses_by_title_year_when_doi_missing():
    a = _p("openalex:W2", source=Source.OPENALEX, doi=None,
           title="Attention Is All You Need", year=2017, abstract="a")
    b = _p("s2:ABC", source=Source.SEMANTIC_SCHOLAR, doi=None,
           title="attention is all you need!", year=2017)
    out = deduplicate([a, b])
    assert len(out) == 1


def test_dedup_preserves_order_of_first_occurrence():
    a = _p("openalex:W1", source=Source.OPENALEX, doi="10.1/a", title="Alpha")
    b = _p("openalex:W2", source=Source.OPENALEX, doi="10.1/b", title="Beta")
    c = _p("s2:X", source=Source.SEMANTIC_SCHOLAR, doi="10.1/a", title="Alpha")
    out = deduplicate([a, b, c])
    assert [p.id for p in out] == ["openalex:W1", "openalex:W2"]


def test_dedup_prefers_record_with_doi_and_abstract():
    with_doi = _p("openalex:W1", source=Source.OPENALEX, doi="10.1/x", abstract="a",
                   title="Attention Is All You Need", year=2017)
    without_doi = _p("s2:X", source=Source.SEMANTIC_SCHOLAR, doi=None,
                     title="Attention Is All You Need", year=2017,
                     citations_in_count=5000)
    out = deduplicate([without_doi, with_doi])
    assert len(out) == 1
    # The winning record keeps the DOI-bearing paper's ID.
    assert out[0].doi == "10.1/x"
    # But higher citation count from the other record is preserved.
    assert out[0].citations_in_count == 5000


# --- Cross-year preprint / published pair dedup (pass 3) ----------------


def test_dedup_collapses_preprint_and_published_across_years():
    """Real case from v3 live grading: `W3199958362` (2021 journal) and
    `W3162385798` (2020 preprint) — same paper, no shared DOI, same
    authors. Pass 2 (title, year) misses; pass 3 catches."""
    preprint = _p(
        "openalex:W3162385798", source=Source.OPENALEX, doi=None,
        title="How Can We Know When Language Models Know? "
              "On the Calibration of Language Models for Question Answering",
        year=2020,
        authors=["Zhengbao Jiang", "Jun Araki", "Haibo Ding", "Graham Neubig"],
        citations_in_count=40,
    )
    journal = _p(
        "openalex:W3199958362", source=Source.OPENALEX, doi=None,
        title="How Can We Know When Language Models Know? "
              "On the Calibration of Language Models for Question Answering",
        year=2021,
        authors=["Zhengbao Jiang", "Jun Araki", "Haibo Ding", "Graham Neubig"],
        citations_in_count=163,
    )
    out = deduplicate([preprint, journal])
    assert len(out) == 1
    # Higher-citation (journal) wins _pick_primary → its ID survives,
    # matching the existing behaviour verified by
    # test_dedup_prefers_record_with_doi_and_abstract.
    assert out[0].id == "openalex:W3199958362"
    assert out[0].citations_in_count == 163
    # And the journal's later year is what the merged record reports.
    assert out[0].year == 2021


def test_dedup_does_not_collapse_same_title_different_authors():
    """Two distinct papers that happen to share a generic title but
    were written by different teams must NOT be merged."""
    a = _p(
        "openalex:W1", source=Source.OPENALEX, doi=None,
        title="A Survey of Neural Networks", year=2020,
        authors=["Alice Author"],
    )
    b = _p(
        "openalex:W2", source=Source.OPENALEX, doi=None,
        title="A Survey of Neural Networks", year=2021,
        authors=["Bob Bystander"],
    )
    out = deduplicate([a, b])
    assert len(out) == 2, "distinct-author same-titled papers must survive"


def test_dedup_does_not_collapse_when_year_gap_exceeds_window():
    """A 2018 paper and a 2024 paper sharing a title + author is a
    coincidence, not the same work. Must not merge."""
    early = _p(
        "openalex:W1", source=Source.OPENALEX, doi=None,
        title="Attention Is All You Need", year=2017,
        authors=["Ashish Vaswani"],
    )
    late = _p(
        "openalex:W2", source=Source.OPENALEX, doi=None,
        title="Attention Is All You Need", year=2024,
        authors=["Ashish Vaswani"],
    )
    out = deduplicate([early, late])
    assert len(out) == 2


def test_dedup_refuses_cross_year_merge_when_authors_missing():
    """Positive author evidence is required. If either record has no
    authors we cannot vouch that the title match is more than a
    coincidence, so we must not merge."""
    no_authors = _p(
        "openalex:W1", source=Source.OPENALEX, doi=None,
        title="Rare Common Title", year=2020, authors=[],
    )
    with_authors = _p(
        "openalex:W2", source=Source.OPENALEX, doi=None,
        title="Rare Common Title", year=2021,
        authors=["Some Person"],
    )
    out = deduplicate([no_authors, with_authors])
    assert len(out) == 2


def test_dedup_cross_year_pass_tolerates_author_format_variants():
    """OpenAlex might emit "John A. Doe" while Semantic Scholar emits
    "J. Doe" for the same person. Last-name normalization must bridge
    both — the shared token is "doe"."""
    openalex_form = _p(
        "openalex:W1", source=Source.OPENALEX, doi=None,
        title="Cross Format Test", year=2020,
        authors=["John A. Doe", "María Müller"],
    )
    s2_form = _p(
        "s2:X", source=Source.SEMANTIC_SCHOLAR, doi=None,
        title="Cross Format Test", year=2021,
        authors=["J. Doe", "M. Muller"],  # ascii + initial + diacritic-stripped
    )
    out = deduplicate([openalex_form, s2_form])
    assert len(out) == 1


def test_dedup_cross_year_within_window_but_not_at_zero_or_beyond():
    """Boundary check: |Δyear| = 1 and 2 → merge; |Δyear| = 3 → don't."""
    from backend.app.ingestion.normalizer import CROSS_YEAR_WINDOW
    assert CROSS_YEAR_WINDOW == 2  # test is meaningful only for this window
    base = _p(
        "openalex:W_base", source=Source.OPENALEX, doi=None,
        title="Boundary Paper", year=2020, authors=["Same Author"],
    )
    one_off = _p(
        "openalex:W_one", source=Source.OPENALEX, doi=None,
        title="Boundary Paper", year=2021, authors=["Same Author"],
    )
    two_off = _p(
        "openalex:W_two", source=Source.OPENALEX, doi=None,
        title="Boundary Paper", year=2022, authors=["Same Author"],
    )
    three_off = _p(
        "openalex:W_three", source=Source.OPENALEX, doi=None,
        title="Boundary Paper", year=2023, authors=["Same Author"],
    )
    out = deduplicate([base, one_off, two_off, three_off])
    # base absorbs one_off (Δ=1) and two_off (Δ=2). three_off (Δ=3) survives.
    assert [p.id for p in out] == ["openalex:W_base", "openalex:W_three"]


def test_author_helpers_normalize_expected_formats():
    """Direct unit tests for the author-normalization primitives."""
    from backend.app.ingestion.normalizer import (
        _authors_overlap,
        _normalize_last_name,
    )
    assert _normalize_last_name("John A. Doe") == "doe"
    assert _normalize_last_name("J. Doe") == "doe"
    assert _normalize_last_name("Doe, John") == "doe"
    # Diacritic-only case (á, ü, ö) — NFKD decomposes and ASCII-encoding
    # drops the combining marks, leaving the base letter.
    assert _normalize_last_name("María Müller") == "muller"
    assert _normalize_last_name("Ø. Smørrebrød") == "smrrebrd"
    assert _normalize_last_name("") == ""
    assert _normalize_last_name("   ") == ""

    assert _authors_overlap(["J. Doe"], ["John A. Doe", "K. Roe"]) is True
    assert _authors_overlap(["A. Smith"], ["B. Jones"]) is False
    # Empty on either side → never overlap (protects against false merges).
    assert _authors_overlap([], ["A. Smith"]) is False
    assert _authors_overlap(["A. Smith"], []) is False
