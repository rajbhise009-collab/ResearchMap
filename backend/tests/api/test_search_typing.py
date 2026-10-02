"""Permanent tests for the type-ahead "typing" state.

The regression this guards against: before this fix, typing a prefix of
a library's own defining word (e.g. "alc" on Diet) returned
verdict=out_of_domain, which hid the retrieval hits behind the
"this library doesn't cover that" panel. The settled state after any
pause was an empty page.

Rules enforced:
- A half-typed trailing word NEVER lands as out_of_domain. With
  prefix_last=True, verdict is "typing" (or in_domain / borderline when
  the complete tokens justify it).
- Prefix hits are present in `hits` so the UI can render them.
- On Enter (expand_trailing=True), the trailing prefix is expanded to
  its best-DF match and the verdict reads as if that full word had
  been typed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.api.search_index import search

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "frontend" / "public" / "data"

INDEX_PATHS = {
    "llm-calibration":    DATA / "search-index.json",
    "diet-and-mortality": DATA / "library" / "diet-and-mortality" / "search-index.json",
    "ml-fairness":        DATA / "library" / "ml-fairness" / "search-index.json",
}


def _load(slug: str) -> dict | None:
    p = INDEX_PATHS[slug]
    return json.loads(p.read_text()) if p.exists() else None


pytestmark = pytest.mark.skipif(
    any(not p.exists() for p in INDEX_PATHS.values()),
    reason="needs the multi-library snapshot",
)


# ---- Mid-typing: prefix of a defining word stays in typing/in state ----

TYPING_CASES = [
    ("diet-and-mortality", "alc"),          # prefix of "alcohol"
    ("diet-and-mortality", "alcohol str"),  # trailing "str" = prefix of "stroke"
    ("diet-and-mortality", "red me"),       # prefix of "red meat"
    ("diet-and-mortality", "satur"),        # prefix of "saturated"
    ("ml-fairness",        "fair"),         # prefix of "fairness"
    ("ml-fairness",        "demographic par"),
    ("llm-calibration",    "halluc"),
    ("llm-calibration",    "semantic ent"),
]


@pytest.mark.parametrize("slug,query", TYPING_CASES)
def test_mid_typing_never_lands_out_of_domain(slug, query):
    """A half-typed trailing word must not refuse mid-stroke. The
    verdict must be one of in_domain / borderline / typing — anything
    the UI treats as "show results, no refusal". `out_of_domain` is
    the ONLY forbidden outcome."""
    idx = _load(slug)
    r = search(idx, query, prefix_last=True)
    assert r["verdict"] != "out_of_domain", (
        f"[{slug}] {query!r}: got {r['verdict']!r} — a half-typed "
        f"trailing word must never refuse. coverage={r['coverage']}, "
        f"typing={r.get('typing')}")


@pytest.mark.parametrize("slug,query", TYPING_CASES)
def test_mid_typing_produces_hits(slug, query):
    idx = _load(slug)
    r = search(idx, query, prefix_last=True)
    assert r["hits"], (
        f"[{slug}] {query!r}: expected ≥1 hit via prefix expansion, "
        f"got {r['n_matched']}")


# ---- Enter / Ask: expand_trailing swaps prefix for best completion ----

EXPAND_CASES = [
    # (slug, query_with_prefix,         baseline_query_that_should_match_verdict)
    ("diet-and-mortality", "alc",       "alcohol"),
    ("diet-and-mortality", "red me",    "red meat"),
    ("ml-fairness",        "demographic par", "demographic parity"),
    ("llm-calibration",    "halluc",   "hallucination"),
]


@pytest.mark.parametrize("slug,prefix_query,full_query", EXPAND_CASES)
def test_enter_expands_trailing_to_best_match(slug, prefix_query, full_query):
    idx = _load(slug)
    r_prefix = search(idx, prefix_query, expand_trailing=True)
    r_full   = search(idx, full_query)
    # Enter + prefix behaves like Enter + full word for the verdict:
    assert r_prefix["verdict"] == r_full["verdict"], (
        f"[{slug}] {prefix_query!r}+expand got {r_prefix['verdict']!r} "
        f"but {full_query!r} got {r_full['verdict']!r}")


# ---- Complete tokens still refuse the known failure modes --------------

COMPLETE_REFUSALS = [
    "melanoma treatment",
    "camera calibration for stereo vision",
    "stock market prediction",
    "treatment options for early stage melanoma",
    "calibration of medical imaging equipment",
    "hallucinations in schizophrenia",
]


@pytest.mark.parametrize("slug", list(INDEX_PATHS.keys()))
@pytest.mark.parametrize("query", COMPLETE_REFUSALS)
def test_complete_oods_still_refuse(slug, query):
    idx = _load(slug)
    r = search(idx, query)
    assert r["verdict"] == "out_of_domain", (
        f"[{slug}] {query!r}: must still refuse; got {r['verdict']}")


# ---- Partial trailing of an OOD query is "typing", not in-domain ------

@pytest.mark.parametrize("slug", list(INDEX_PATHS.keys()))
@pytest.mark.parametrize("query", [
    "melanoma tre",     # trailing of "melanoma treatment"
    "camera cal",       # trailing of "camera calibration"
    "stock mar",        # trailing of "stock market"
])
def test_partial_trailing_of_ood_is_typing_or_ood_never_in_domain(slug, query):
    """A half-typed OOD query must never flash in_domain or borderline
    mid-stroke. It can be `typing` (if the prefix has matches in the
    index — rare for these cases) OR `out_of_domain` (if the complete
    tokens are already OOD AND the trailing has no matches)."""
    idx = _load(slug)
    r = search(idx, query, prefix_last=True)
    assert r["verdict"] in ("typing", "out_of_domain"), (
        f"[{slug}] {query!r}: got {r['verdict']!r} — "
        f"a half-typed OOD query must not flash in_domain / borderline")
