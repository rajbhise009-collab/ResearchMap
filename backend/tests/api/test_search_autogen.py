"""Per-library search test sets, generated from each library's OWN index, so
every library (including ones the weekly workflow builds) is covered without
hand-written queries.

For each built library (frontend/public/data/libraries.json):
  - its 15 most distinctive two-word phrases taken from its own document
    titles (both words in at most 15% of this library's documents and rarer
    in every other library) -> never refused, and at least 80% in_domain. Phrases, because that is
    what readers type; single words are deliberately answered "borderline"
    by the search gate unless they are very specific;
  - 5 refusal cases far from every library -> out_of_domain.
"""
from __future__ import annotations

import pytest

from backend.app.api.search_index import search
from backend.app.api.search_phrases import INDEX, REFUSE, queries

CASES = [(s, q) for s in INDEX for q in queries(s)]


def test_every_library_gets_at_least_15_generated_in_domain_queries():
    for s in INDEX:
        assert len(queries(s)) >= 15, (s, queries(s))


@pytest.mark.parametrize("slug,query", CASES)
def test_generated_phrase_is_never_refused(slug, query):
    r = search(INDEX[slug], query)
    assert r["verdict"] in ("in_domain", "borderline"), (slug, query, r["verdict"])


@pytest.mark.parametrize("slug", list(INDEX))
def test_most_generated_phrases_are_in_domain(slug):
    v = [search(INDEX[slug], q)["verdict"] for q in queries(slug)]
    assert v.count("in_domain") >= 0.8 * len(v), (slug, list(zip(queries(slug), v)))


@pytest.mark.parametrize("slug,query", [(s, q) for s in INDEX for q in REFUSE])
def test_far_queries_are_refused_on_every_library(slug, query):
    assert search(INDEX[slug], query)["verdict"] == "out_of_domain", (slug, query)
