"""Search, and above all the honest out-of-domain answer.

The product promise is that a question this library cannot answer gets
told so plainly, instead of being handed the least-bad match dressed up as
a result. That promise is only as good as these tests.
"""

from __future__ import annotations

import pytest

from backend.app.api import data, export, language, search_index as S


@pytest.fixture(scope="module")
def index():
    cards = []
    for c in data.cards():
        card = {**c.model_dump(), "slug": export.slug(c.id)}
        card["consumer"] = language.consumer_card(card)
        cards.append(card)
    details = []
    for p in data.paper_summaries():
        d = data.paper_detail(p["paper_id"])
        d["wid"] = p["paper_id"].split(":")[-1]
        details.append(d)
    return S.build_index(cards, details)


# --------------------------------------------------------------------------
# The tokenizer, which the browser has to reproduce exactly.
# --------------------------------------------------------------------------

TOKENIZER_FIXTURES = [
    ("Detecting hallucinations", ["detect", "hallucination"]),
    ("MODEL calibration!!", ["model", "calibration"]),
    ("the and for with", []),
    ("uncertainties", ["uncertainty"]),
    ("running", ["runn"]),
    ("safely", ["safe"]),
    ("AI", ["ai"]),
    ("a x 42 llm", ["llm"]),
    ("Does the AI know when it does not know", ["ai", "know", "know"]),
]


@pytest.mark.parametrize("text,expected", TOKENIZER_FIXTURES)
def test_tokenizer_fixtures(text, expected):
    """These exact pairs are asserted again in the TypeScript twin. If this
    list changes, frontend/lib/search.ts must change with it."""
    assert S.tokenize(text) == expected


def test_short_domain_words_survive_tokenising():
    """"AI" is the likeliest word a reader will type; dropping it as too
    short would make the tool look broken."""
    assert "ai" in S.tokenize("what does AI get wrong")
    assert "llm" in S.tokenize("llm reliability")


def test_meaningful_verbs_are_not_stopwords():
    """"Does the model know when it doesn't know" is this library's central
    question — those words have to survive."""
    for w in ("know", "trust", "tell"):
        assert S.tokenize(f"does it {w} things") , w
        assert S._stem(w) not in S.STOPWORDS


# --------------------------------------------------------------------------
# In-domain: real questions get real answers.
# --------------------------------------------------------------------------

IN_DOMAIN = [
    "why do language models sound confident when they are wrong",
    "how do you measure uncertainty in LLMs",
    "when should a chatbot refuse to answer",
    "why does ChatGPT make things up",
    "detecting hallucinations",
    "model calibration",
    "fake citations in AI answers",
    "does the AI know when it does not know",
    "how reliable are LLM answers",
]


@pytest.mark.parametrize("q", IN_DOMAIN)
def test_in_domain_questions_are_answered(index, q):
    r = S.search(index, q)
    assert r["verdict"] == "in_domain", (q, r["coverage"], r["best"], r["breadth"])
    assert r["hits"], q


def test_everyday_phrasing_finds_the_technical_term(index):
    """Nobody types "hallucination" — they type "makes things up". If the
    everyday phrasing does not reach the papers, the tool is unusable."""
    r = S.search(index, "why does the AI make things up")
    assert r["verdict"] == "in_domain"
    titles = " ".join(h["title"].lower() for h in r["hits"][:6])
    assert "hallucinat" in titles


def test_abstention_question_finds_the_abstention_survey(index):
    r = S.search(index, "when should a chatbot refuse to answer")
    top = " ".join(h["title"].lower() for h in r["hits"][:3])
    assert "abstention" in top or "limits" in top


# --------------------------------------------------------------------------
# Out-of-domain: the honest refusal. The heart of the design.
# --------------------------------------------------------------------------

OUT_OF_DOMAIN = [
    "how do I bake sourdough bread",
    "treatment options for early stage melanoma",
    "best hiking trails in patagonia",
    "quantum computing error correction",
    "photosynthesis in desert plants",
    "how to train for a marathon",
    "who won the world cup in 1998",
    "tax deductions for small business",
    "symptoms of vitamin d deficiency",
]


@pytest.mark.parametrize("q", OUT_OF_DOMAIN)
def test_out_of_domain_questions_are_refused_not_fudged(index, q):
    r = S.search(index, q)
    assert r["verdict"] == "out_of_domain", (q, r["coverage"], r["best"], r["breadth"])


def test_out_of_domain_survives_incidental_vocabulary_overlap(index):
    """The failure mode this gate exists for: a question whose subject the
    library has never heard of, wrapped in ordinary words that do appear in
    it. "Treatment", "stage" and "early" are common English; "melanoma" is
    the actual subject, and it is absent. The absent word has to win."""
    r = S.search(index, "treatment options for early stage melanoma")
    assert r["verdict"] == "out_of_domain"
    assert "melanoma" in r["unknown"]
    # It is not that nothing matched — it is that what matched is not an answer.
    assert r["best"] > 0


def test_a_question_of_only_stopwords_is_empty_not_out_of_domain(index):
    """"How do I do that" is us having nothing to go on, which is a
    different thing from the library not covering the subject."""
    assert S.search(index, "how do I do that")["verdict"] == "empty"
    assert S.search(index, "")["verdict"] == "empty"


# --------------------------------------------------------------------------
# Borderline: the edge, labelled as the edge.
# --------------------------------------------------------------------------

BORDERLINE = [
    "image recognition accuracy",
    "speech recognition errors",
    "recommendation systems",
    "autonomous driving perception",
]


@pytest.mark.parametrize("q", BORDERLINE)
def test_generic_ml_questions_land_on_the_edge(index, q):
    """Every word is understood and a few papers match, but the library
    holds no body of work on it. That is "the edge of what we cover", not
    a confident answer."""
    r = S.search(index, q)
    assert r["verdict"] == "borderline", (q, r["coverage"], r["best"], r["breadth"])


def test_breadth_is_what_separates_covered_from_incidental(index):
    """A subject the library is actually about shows up across many papers;
    an incidental one shows up in a handful."""
    covered = S.search(index, "detecting hallucinations")
    incidental = S.search(index, "recommendation systems")
    assert covered["breadth"] > incidental["breadth"] * 2


# --------------------------------------------------------------------------
# Index shape
# --------------------------------------------------------------------------

def test_index_covers_opportunities_and_papers(index):
    kinds = {d["type"] for d in index["docs"]}
    assert kinds == {"opportunity", "paper"}
    assert len(index["docs"]) > 150


def test_every_hit_resolves_to_a_real_record(index):
    """A search result that points at nothing is worse than no result."""
    opp_refs = {export.slug(c.id) for c in data.cards()}
    paper_refs = {p["paper_id"].split(":")[-1] for p in data.paper_summaries()}
    r = S.search(index, "uncertainty in language models", limit=50)
    assert r["hits"]
    for h in r["hits"]:
        pool = opp_refs if h["type"] == "opportunity" else paper_refs
        assert h["ref"] in pool, h


def test_index_carries_no_paid_call_and_no_embeddings(index):
    """Search is built from the library's own words precisely so that it
    costs nothing and needs no server."""
    assert "embedding" not in index
    assert set(index) == {"n_docs", "max_idf", "idf", "docs", "synonyms",
                          "stopwords"}
