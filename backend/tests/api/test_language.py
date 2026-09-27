"""The translation layer is the only thing standing between internal
vocabulary and the reader. These tests are what keep it honest."""

from __future__ import annotations

import json

import pytest

from backend.app.api import data, export, language


@pytest.fixture(scope="module")
def cards():
    return [{**c.model_dump(), "slug": export.slug(c.id)} for c in data.cards()]


# --------------------------------------------------------------------------
# No system jargon, no numeric internals.
# --------------------------------------------------------------------------

def _consumer_strings(block) -> list[str]:
    """Every string a reader could actually see in a consumer block."""
    out = []
    if isinstance(block, str):
        out.append(block)
    elif isinstance(block, dict):
        for k, v in block.items():
            if k in ("kind_id", "code"):  # machine keys, never rendered
                continue
            out.extend(_consumer_strings(v))
    elif isinstance(block, list):
        for v in block:
            out.extend(_consumer_strings(v))
    return out


def test_no_plumbing_reaches_the_reader_anywhere(cards):
    """Our own machinery — scorer names, snake_case fields, similarity
    values — must not appear in the consumer view even inside quoted text."""
    offenders = []
    for c in cards:
        for s in _consumer_strings(language.consumer_card(c)):
            for hit in language.jargon_hits(s, quoted=True):
                offenders.append((c["id"], hit, s[:90]))
    assert not offenders, f"plumbing reached the reader: {offenders[:5]}"


def test_authored_copy_avoids_our_internal_names(cards):
    """Copy we write must not use our internal names for things. Text
    quoted verbatim from a paper is exempt — the field's own terminology
    is the subject matter, and rewriting a researcher's sentence would be
    putting words in their mouth."""
    offenders = []
    for c in cards:
        cc = language.consumer_card(c)
        quoted = cc["headline_is_quoted"]
        authored = {k: v for k, v in cc.items()
                    if k not in ("headline", "why", "headline_is_quoted")}
        for s in _consumer_strings(authored):
            for hit in language.jargon_hits(s):
                offenders.append((c["id"], hit, s[:90]))
        # Headlines and explanations quote papers, so only plumbing is
        # disqualifying there — covered by the test above.
        for s in (cc["headline"], cc["why"]):
            for hit in language.jargon_hits(s, quoted=True):
                offenders.append((c["id"], hit, s[:90]))
        assert isinstance(quoted, bool)
    assert not offenders, f"internal vocabulary in authored copy: {offenders[:5]}"


def test_no_internal_jargon_in_the_shipped_language_pack():
    """The developer-mode block is exempt by design — its job is to show
    the internals everything else hides. The attribution block credits the
    data sources by name (OpenAlex, Europe PMC, arXiv, …) — those are the
    sources' own names, not our plumbing, and the plumbing check would
    misfire on `openalex` there."""
    exempt = {"dev", "attribution"}
    pack = {k: v for k, v in language.language_pack().items() if k not in exempt}
    offenders = []
    for s in _consumer_strings(pack):
        for hit in language.jargon_hits(s):
            offenders.append((hit, s[:90]))
    assert not offenders, f"internal vocabulary in the shipped copy: {offenders[:5]}"


def test_attribution_block_names_the_five_required_sources():
    """The public deploy has to credit every upstream data source. Change
    this list only alongside a matching update to what the pipeline actually
    consumes."""
    names = {n for n, _url, _note in language.ATTRIBUTION["items"]}
    required = {"OpenAlex", "Semantic Scholar", "Unpaywall", "Europe PMC", "arXiv"}
    assert required <= names, f"missing sources: {required - names}"
    for _n, url, _note in language.ATTRIBUTION["items"]:
        assert url.startswith("https://"), f"non-https attribution URL: {url}"


def test_no_numeric_internals_leak_into_headlines(cards):
    """Headlines carry real-world counts ("4 separate teams") but never a
    model score, a confidence value or a similarity number."""
    for c in cards:
        h = language.headline(c).lower()
        assert "0." not in h, f"decimal leaked into headline: {h}"
        for term in ("trust", "cosine", "component_score", "confidence"):
            assert term not in h, f"internal '{term}' in headline: {h}"


def test_every_card_gets_a_nonempty_plain_english_headline(cards):
    for c in cards:
        cc = language.consumer_card(c)
        assert cc["headline"].strip(), c["id"]
        assert len(cc["headline"]) > 12, (c["id"], cc["headline"])
        assert cc["why"].strip(), c["id"]
        assert cc["kind"] in {k["name"] for k in language.KINDS.values()}


# --------------------------------------------------------------------------
# Strength: words, and weakness that stays weak.
# --------------------------------------------------------------------------

def test_strength_is_one_of_three_words_each_with_a_meaning(cards):
    allowed = {language.STRONG, language.WORTH_A_LOOK, language.UNVERIFIED}
    for c in cards:
        s = language.strength_for(c)
        assert s in allowed
        assert language.STRENGTH_MEANING[s]


def test_unconfirmed_method_transfer_never_reads_as_strong(cards):
    """A similarity match must not outrank confirmed evidence in wording,
    however high its raw numbers happen to be."""
    holes = [c for c in cards if c["scorer"] == "structural_holes"]
    assert holes, "expected method-transfer leads in the corpus"
    for c in holes:
        s = language.strength_for(c)
        if c.get("confirm_status") == "substantive":
            assert s == language.WORTH_A_LOOK
        else:
            assert s == language.UNVERIFIED, c["id"]


def test_every_weak_result_carries_a_caveat_in_plain_english(cards):
    for c in cards:
        if language.strength_for(c) == language.STRONG:
            continue
        cav = language.caveats_for(c)
        assert cav, f"weak result with no caveat: {c['id']}"
        for x in cav:
            assert x["text"] and len(x["text"]) > 25
            assert not language.jargon_hits(x["text"])


def test_corpus_relative_caveat_names_the_real_limit(cards):
    """The library-not-the-field caveat must state the actual number of
    papers, so nobody reads "nobody has done this" as a claim about the
    whole field."""
    orphans = [c for c in cards if c["scorer"] == "orphaned_future_work"]
    assert orphans
    for c in orphans[:5]:
        texts = " ".join(x["text"] for x in language.caveats_for(c))
        assert "113" in texts
        assert "whole field" in texts or "not the whole field" in texts


def test_abstract_only_papers_say_what_is_missing():
    p = language.consumer_paper({"abstract_only": True})
    assert "summary" in p["fidelity"]["text"].lower()
    assert not language.jargon_hits(p["fidelity"]["text"])
    full = language.consumer_paper({"abstract_only": False})
    assert full["fidelity"]["label"] != p["fidelity"]["label"]


def test_the_zero_disagreement_case_explains_itself():
    """An empty result that says nothing teaches nothing."""
    body = language.NO_DISAGREEMENTS["body"]
    assert len(body) > 120
    assert "zero" in body.lower() or "none" in body.lower()
    assert not language.jargon_hits(body)


# --------------------------------------------------------------------------
# Terminology handling
# --------------------------------------------------------------------------

def test_readable_category_translates_or_de_slugs():
    assert language.readable_category("task-scope-limitation") == \
        "only tested on a narrow set of tasks"
    # Unknown slugs are de-slugged, not dropped and not invented.
    assert language.readable_category("some-new-category") == "some new category"


def test_kind_names_avoid_the_internal_names():
    for k in language.KINDS.values():
        assert not language.jargon_hits(k["name"])
        assert not language.jargon_hits(k["short"])
        assert len(k["long"]) > 60


def test_build_library_panel_states_cost_and_that_it_is_not_wired_up():
    b = language.BUILD_LIBRARY
    joined = " ".join(v for _, v in b["estimates"]).lower()
    assert "$" in joined, "the cost has to be shown, not hidden"
    assert "hour" in joined
    # The panel must explicitly state that clicking it does not build a
    # library — a public visitor who arrives here shouldn't think the
    # button will start something and then be surprised nothing happens.
    ny = b["not_yet"].lower()
    assert any(phrase in ny for phrase in (
        "isn't automated",     # "Building a library isn't automated yet"
        "not a working",       # "not a working button"
        "doesn't",             # older phrasing kept as a hedge
    )), f"not_yet copy must make the not-yet nature clear: {b['not_yet']!r}"
    assert "human" in ny, "should say a human has to start it"
