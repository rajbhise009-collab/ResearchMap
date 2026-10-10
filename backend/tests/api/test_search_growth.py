"""Search must stay right as a library GROWS (weekly growth adds papers).

Weekly-grow run #7 added one ML fairness paper that used "demographic
parity"; the phrase's idf fell just under the specific-term bypass while the
breadth gate, which counted only each document's shipped top terms, missed
most of the documents using it -> a core term flipped to borderline.

This rebuilds each library's index exactly as the export does (the shipped
index is reproduced byte for byte), then adds papers: copies of the
library's own papers that use each core query's words (more papers on the
library's own topics — what growth does). Every core query must stay
in_domain at every step, and the generated phrase sets must still pass."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from backend.app.api.search_index import build_index, search, tokenize

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "frontend" / "public" / "data" / "library"
GROWING = ["diet-and-mortality", "ml-fairness", "social-media-teen-mental-health"]


def _inputs(slug):
    d = DATA / slug
    summ = json.loads((d / "opportunities.json").read_text())["items"]
    cards = [json.loads((d / "opportunity" / f"{o['slug']}.json").read_text()) for o in summ]
    entries = json.loads((REPO / "data" / "domains" / slug / "prelabelled.json").read_text())["entries"]
    papers = [json.loads((d / "paper" / f"{e['wid']}.json").read_text())
              for e in entries if (d / "paper" / f"{e['wid']}.json").exists()]
    return cards, papers


def _core_queries(slug):
    """The fixed in_domain cases for this library (per-library and typing
    expansion sets) — the terms a library must never lose."""
    import importlib.util
    out = []
    for name in ("test_search_per_library", "test_search_typing"):
        spec = importlib.util.spec_from_file_location(name, REPO / "backend" / "tests" / "api" / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        if name == "test_search_per_library":
            key = {"diet-and-mortality": "DIET", "ml-fairness": "ML_FAIRNESS"}.get(slug)
            out += [q for q, want in getattr(m, key, []) if want == "in_domain"] if key else []
        else:
            out += [full for s, _pre, full in m.EXPAND_CASES if s == slug]
    return sorted(set(out))


def _donors(papers, query):
    want = set(tokenize(query))
    text = lambda p: " ".join(str(p.get(k) or "") for k in ("title", "abstract")) + " " + \
        " ".join(c.get("text", "") for c in p.get("claims", []))
    return [p for p in papers if want <= set(tokenize(text(p)))]


def _grow(papers, donors, k):
    extra = []
    for i in range(k):
        for j, p in enumerate(donors):
            q = copy.deepcopy(p)
            q["wid"] = f"W99{i:03d}{j:04d}"
            q["paper_id"] = f"openalex:{q['wid']}"
            extra.append(q)
    return papers + extra


@pytest.mark.parametrize("slug", GROWING)
def test_core_terms_stay_in_domain_as_the_library_grows(slug):
    cards, papers = _inputs(slug)
    queries = _core_queries(slug)
    if not queries:
        # no hand-written set (e.g. social media): its generated phrases that
        # are in_domain today are its core terms
        from backend.app.api.search_phrases import queries as generated
        base = build_index(cards, papers)
        queries = [q for q in generated(slug) if search(base, q)["verdict"] == "in_domain"]
    assert queries, slug
    donors = {q: _donors(papers, q)[:3] for q in queries}
    all_donors = [p for q in queries for p in donors[q]]
    for k in (1, 4, 10):
        idx = build_index(cards, _grow(papers, all_donors, k))
        bad = [(q, r["verdict"], r["coverage"], r["best"], r["breadth"]) for q in queries
               for r in [search(idx, q)] if r["verdict"] != "in_domain"]
        assert not bad, (slug, f"+{k} copies of each core topic's papers", bad)


def test_demographic_parity_stays_in_domain_at_every_growth_step():
    """The run #7 case, one paper at a time: more papers using the
    library's core phrase must never make it LESS in-domain."""
    cards, papers = _inputs("ml-fairness")
    donor = _donors(papers, "demographic parity")
    assert donor, "no ML fairness paper uses the phrase"
    for k in range(0, 11):
        idx = build_index(cards, _grow(papers, donor[:1], k))
        r = search(idx, "demographic parity")
        assert r["verdict"] == "in_domain", (k, r["verdict"], r["coverage"], r["best"], r["breadth"])
        assert search(idx, "demographic par", expand_trailing=True)["verdict"] == "in_domain", k


@pytest.mark.parametrize("slug", GROWING)
def test_generated_phrases_and_refusals_hold_after_growth(slug):
    """After growth (+5 copies of the library's first 10 papers) the
    generated phrase set still lands >= 80% in_domain and far queries are
    still refused."""
    from backend.app.api.search_phrases import REFUSE, queries
    cards, papers = _inputs(slug)
    idx = build_index(cards, _grow(papers, papers[:10], 5))
    v = [search(idx, q)["verdict"] for q in queries(slug)]
    assert v.count("in_domain") >= 0.8 * len(v), list(zip(queries(slug), v))
    assert all(search(idx, q)["verdict"] == "out_of_domain" for q in REFUSE)
