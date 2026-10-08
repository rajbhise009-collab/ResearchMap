"""Cross-library search-gate collision tests.

Three ambiguous queries — "calibration", "bias", "fairness" — appear in
more than one library's vocabulary. The gate must route each to the
library whose coverage of that word is strongest and refuse if the
match is weak everywhere.

These are permanent regression tests per the multi-domain-expansion
spec.
"""

from __future__ import annotations

import math
from pathlib import Path
import json

import pytest

from backend.app.api.search_index import tokenize as _tokenize

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "frontend" / "public" / "data"


def _load_index(slug: str) -> dict | None:
    """Load a library's search index. `llm-calibration` lives at the
    ROOT for backward-compat; the others live under /library/<slug>/."""
    if slug == "llm-calibration":
        path = DATA / "search-index.json"
    else:
        path = DATA / "library" / slug / "search-index.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


# Every built library (any number of them).
LIBRARIES = tuple(l["slug"] for l in json.loads((DATA / "libraries.json").read_text())["libraries"])


def _term_score(index: dict, term: str) -> tuple[float, float]:
    """Return (breadth, idf-weighted coverage) for `term` in `index`.
    breadth = share of docs that contain the term.
    coverage = idf(term) if present else 0.

    The index stores STEMMED tokens (so the query must be stemmed the
    same way before lookup — matching how the frontend actually
    tokenizes a query at search time)."""
    if not index:
        return (0.0, 0.0)
    stems = _tokenize(term)
    if not stems:
        return (0.0, 0.0)
    stem = stems[0]
    n = index.get("n_docs", 0) or 0
    idf = index.get("idf", {}).get(stem, 0.0)
    # Document frequency from the index's own idf, which the builder computes
    # over each document's FULL vocabulary as ln((N+1)/(df+0.5))
    # (backend/app/api/search_index.py). The per-document `terms` lists are
    # truncated to each document's top-weighted words, so counting stems in
    # them undercounts common words (e.g. "fairness": 5 of 102 by the lists,
    # 79 of 102 in fact) and made this test flip when documents were added.
    df = ((n + 1) / math.exp(idf) - 0.5) if (idf and n) else 0.0
    breadth = df / n if n else 0.0
    return (breadth, idf)


def _route(term: str) -> tuple[str | None, dict]:
    """Route a term to the library with strongest breadth. Returns
    (chosen_slug or None, per-library scores)."""
    scores = {}
    for slug in LIBRARIES:
        idx = _load_index(slug)
        scores[slug] = {"breadth": _term_score(idx, term)[0],
                         "idf": _term_score(idx, term)[1],
                         "available": idx is not None}
    # A term is meaningfully covered when it appears in ≥5% of a library's
    # docs. Otherwise we refuse — a weak hit dressed up as a routing
    # decision is exactly the honesty failure the search gate exists for.
    strong = {s: v for s, v in scores.items() if v["breadth"] >= 0.05}
    if not strong:
        return (None, scores)
    winner = max(strong, key=lambda s: strong[s]["breadth"])
    return (winner, scores)


ANY_INDEX_MISSING = not all((DATA / ("search-index.json" if s == "llm-calibration"
                                       else f"library/{s}/search-index.json")).exists()
                              for s in LIBRARIES)


pytestmark = pytest.mark.skipif(
    ANY_INDEX_MISSING,
    reason="needs the multi-library snapshot (run "
           "python -m backend.app.api.multi_library_export first)",
)


def test_calibration_routes_to_llm_calibration():
    """`calibration` is central to LLM calibration (used across 100+
    papers) and only a peripheral fairness term (calibration-fairness
    tradeoff, a handful of papers). Router must pick llm-calibration."""
    winner, scores = _route("calibration")
    assert winner == "llm-calibration", scores
    # Fairness has SOME coverage — we don't want zero — just less than LLM-cal.
    llm_cal_breadth = scores["llm-calibration"]["breadth"]
    fair_breadth = scores["ml-fairness"]["breadth"]
    assert llm_cal_breadth > fair_breadth


def test_fairness_routes_to_ml_fairness():
    """`fairness` is the name of the ml-fairness library."""
    winner, _ = _route("fairness")
    assert winner == "ml-fairness"


def test_bias_routes_to_ml_fairness_or_refuses_if_thin():
    """`bias` shows up in fairness (algorithmic bias) and lightly in
    diet/LLM-cal (statistical / measurement bias). If ml-fairness has
    the strongest breadth, route there; otherwise refuse — a bare
    statistical-bias hit is not what a user searching 'bias' wants."""
    winner, scores = _route("bias")
    # Either route to fairness, or refuse — both are honest. The one
    # thing NOT allowed is to route to a library with thin coverage.
    if winner is not None:
        assert winner == "ml-fairness", scores
        assert scores["ml-fairness"]["breadth"] >= 0.05


def test_route_refuses_out_of_domain_term():
    """A truly out-of-domain query gets None from the router — this is
    the search gate's honesty invariant carried across libraries."""
    winner, _ = _route("quantum")   # no library covers quantum theory
    assert winner is None


def test_all_libraries_have_a_search_index():
    for slug in LIBRARIES:
        idx = _load_index(slug)
        assert idx is not None, slug
        assert idx.get("n_docs", 0) > 0, slug
        assert isinstance(idx.get("docs"), list), slug


# ---- terms shared with the social media & adolescent mental health library
# (added 2026-10-09). Skipped if that library is not built.

SOCIAL = "social-media-teen-mental-health"


@pytest.mark.skipif(SOCIAL not in LIBRARIES, reason="social-media library not built")
@pytest.mark.parametrize("term", ["social media", "adolescents", "depression", "screen time"])
def test_social_terms_route_to_social_library(term):
    winner, scores = _route(term)
    assert winner == SOCIAL, scores


@pytest.mark.skipif(SOCIAL not in LIBRARIES, reason="social-media library not built")
def test_mortality_still_routes_to_diet():
    winner, scores = _route("mortality")
    assert winner == "diet-and-mortality", scores


@pytest.mark.skipif(SOCIAL not in LIBRARIES, reason="social-media library not built")
def test_social_question_is_answered_only_by_social_library():
    from backend.app.api.search_index import search
    q = "social media and teenage depression"
    verdicts = {s: search(_load_index(s), q)["verdict"] for s in LIBRARIES}
    assert verdicts[SOCIAL] == "in_domain", verdicts
    assert all(v != "in_domain" for s, v in verdicts.items() if s != SOCIAL), verdicts
