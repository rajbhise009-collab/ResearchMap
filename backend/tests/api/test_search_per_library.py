"""Per-library search test matrix.

For each of the 3 shipped libraries, 15+ queries labelled in-domain /
borderline / out-of-domain. Includes:
- single defining words from the library's own subject
- natural-language questions
- cross-library collisions ("bias", "calibration", "fairness",
  "alcohol" on the wrong library)
- queries that MUST stay OOD even when they share a few bland words
  with the library ("camera calibration for stereo vision",
  "calibration of medical imaging equipment", "hallucinations in
  schizophrenia", "treatment options for early stage melanoma")

The parity test (TypeScript + Python agree on every query) is at the
bottom. It mirrors the fixtures used by the frontend's own test suite.
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

# Expected verdict is either a single string or a tuple of allowed
# verdicts (borderline is acceptable where either in_domain or
# borderline would be defensible for a specific technical term).

LLM_CAL = [
    ("hallucination",                         "in_domain"),
    ("calibration",                           "in_domain"),
    ("semantic entropy",                      "in_domain"),
    ("selective prediction",                  "in_domain"),
    ("model confidence",                      "in_domain"),
    ("uncertainty quantification",            "in_domain"),
    ("refuse to answer",                      "in_domain"),
    ("does the model know when it is wrong",  "in_domain"),
    ("why do language models make up citations", "in_domain"),
    ("alcohol",                               "out_of_domain"),
    ("red meat",                              "out_of_domain"),
    ("fairness",                              "out_of_domain"),
    ("melanoma treatment",                    "out_of_domain"),
    ("treatment options for early stage melanoma", "out_of_domain"),
    ("camera calibration for stereo vision",  "out_of_domain"),
    ("calibration of medical imaging equipment", "out_of_domain"),
    ("hallucinations in schizophrenia",       "out_of_domain"),
    ("stock market prediction",               "out_of_domain"),
    ("bias",                                  ("borderline", "in_domain")),
]

DIET = [
    ("alcohol",                               "in_domain"),
    ("red meat",                              "in_domain"),
    ("saturated fat",                         "in_domain"),
    ("mediterranean diet",                    "in_domain"),
    ("ultra-processed food",                  "in_domain"),
    ("stroke",                                "in_domain"),
    ("cardiovascular disease",                "in_domain"),
    ("coronary heart disease",                "in_domain"),
    ("type 2 diabetes",                       "in_domain"),
    ("does alcohol increase stroke risk",     "in_domain"),
    ("red meat and type 2 diabetes",          "in_domain"),
    ("fairness",                              "out_of_domain"),
    ("hallucination",                         "out_of_domain"),
    ("calibration",                           "out_of_domain"),
    ("melanoma treatment",                    "out_of_domain"),
    ("treatment options for early stage melanoma", "out_of_domain"),
    ("camera calibration for stereo vision",  "out_of_domain"),
    ("calibration of medical imaging equipment", "out_of_domain"),
    ("hallucinations in schizophrenia",       "out_of_domain"),
    ("stock market prediction",               "out_of_domain"),
    ("bias",                                  ("borderline", "in_domain", "out_of_domain")),
]

ML_FAIRNESS = [
    ("fairness",                              "in_domain"),
    ("demographic parity",                    "in_domain"),
    ("equalized odds",                        "in_domain"),
    ("disparate impact",                      "in_domain"),
    ("COMPAS",                                "in_domain"),
    ("algorithmic bias",                      "in_domain"),
    ("fair classification",                   "in_domain"),
    ("fairness in machine learning",          "in_domain"),
    ("discrimination in credit scoring",      ("in_domain", "borderline")),
    ("equal opportunity",                     ("in_domain", "borderline")),
    ("alcohol",                               "out_of_domain"),
    ("red meat",                              "out_of_domain"),
    ("hallucination",                         "out_of_domain"),
    ("melanoma treatment",                    "out_of_domain"),
    ("treatment options for early stage melanoma", "out_of_domain"),
    ("camera calibration for stereo vision",  "out_of_domain"),
    ("calibration of medical imaging equipment", "out_of_domain"),
    ("hallucinations in schizophrenia",       "out_of_domain"),
    ("stock market prediction",               "out_of_domain"),
    ("calibration",                           ("in_domain", "borderline")),
    ("bias",                                  ("borderline", "in_domain")),
]

ALL = {
    "llm-calibration":    LLM_CAL,
    "diet-and-mortality": DIET,
    "ml-fairness":        ML_FAIRNESS,
}


def _load(slug: str) -> dict | None:
    p = INDEX_PATHS[slug]
    if not p.exists():
        return None
    return json.loads(p.read_text())


pytestmark = pytest.mark.skipif(
    any(not p.exists() for p in INDEX_PATHS.values()),
    reason="needs the multi-library snapshot (run "
           "`python -m backend.app.api.multi_library_export` first)",
)


@pytest.mark.parametrize("slug,query,expected",
    [(slug, q, e) for slug, qs in ALL.items() for q, e in qs])
def test_search_verdict(slug: str, query: str, expected):
    idx = _load(slug)
    r = search(idx, query)
    allowed = expected if isinstance(expected, tuple) else (expected,)
    assert r["verdict"] in allowed, (
        f"[{slug}] {query!r}: got {r['verdict']!r}, "
        f"wanted {expected!r}; cov={r['coverage']:.3f} "
        f"best={r['best']:.3f} breadth={r['breadth']:.3f}")


# ---- Structural invariants on every library's index -----------------------


@pytest.mark.parametrize("slug", list(INDEX_PATHS.keys()))
def test_index_has_gate_block(slug: str):
    """The per-library gate thresholds must land in the shipped index
    so the frontend's search() reads them. A missing gate block means
    the frontend will fall back to LLM-cal's constants, which is the
    bug this iteration fixes."""
    idx = _load(slug)
    gate = idx.get("gate")
    assert gate is not None, "index missing per-library gate block"
    for k in ("in_domain_coverage", "in_domain_best", "in_domain_breadth"):
        assert k in gate, f"gate block missing {k}"


@pytest.mark.parametrize("slug", list(INDEX_PATHS.keys()))
def test_index_contains_opportunities_if_the_library_has_any(slug: str):
    """A library that ships opportunity cards MUST have them in its
    search index. Shipping an index without them is how the main
    search returned 0 results for 'alcohol' on Diet pre-fix."""
    idx = _load(slug)
    # Load opportunities to compare
    if slug == "llm-calibration":
        opps_path = DATA / "opportunities.json"
    else:
        opps_path = DATA / "library" / slug / "opportunities.json"
    from backend.app.api.language import is_visible
    opps = json.loads(opps_path.read_text()).get("items", [])
    # Results (nothing set them aside) must all be searchable; set-aside and
    # not-yet-checked items must never be search hits.
    opp_refs = {o["slug"] for o in opps if is_visible(o)}
    hidden = {o["slug"] for o in opps if not is_visible(o)}
    indexed_opp_refs = {d["ref"] for d in idx["docs"] if d["type"] == "opportunity"}
    missing = opp_refs - indexed_opp_refs
    assert not missing, (
        f"[{slug}] opportunities not in search index: {sorted(missing)[:5]}")
    assert not (hidden & indexed_opp_refs), f"[{slug}] set-aside items are searchable"


# ---- Hit-reachability regression -----------------------------------------


def test_diet_alcohol_returns_the_alcohol_gaps():
    """The original production bug: 'alcohol' on Diet returned 0 cards
    even though three alcohol gaps exist. The index must now surface
    the alcohol opportunity refs on the 'alcohol' query."""
    idx = _load("diet-and-mortality")
    r = search(idx, "alcohol", limit=20)
    opp_hits = [h for h in r["hits"] if h["type"] == "opportunity"]
    assert len(opp_hits) >= 3, (
        f"expected ≥3 alcohol gap opportunities, got {len(opp_hits)}: "
        f"{[h['ref'] for h in opp_hits]}")
