"""The smoke checks' settled search is chosen and verified against each
library's built index (backend/app/api/search_phrases.smoke_phrase_for).

Run #8 (2026-10-12) failed its smoke gate because the auto-picked phrase for
the new Nudges library ("financial products") was answered in_domain but
matched only paper titles: results=7 gaps=0 while the library shows 7
results, so the check (rightly) required gaps. The picker now verifies the
phrase reaches a result card. These tests build synthetic libraries from
each queued domain's own papers (ego depletion, growth mindset, nudges),
run the picker and then the smoke assertion itself on the built index.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.app.api.search_index import build_index, search
from backend.app.api.search_phrases import NEED_GAPS_MIN, HIT_LIMIT, smoke_phrase_for

ROOT = Path(__file__).resolve().parents[3]
QUEUED_DOMAINS = ["ego-depletion", "growth-mindset", "nudge-effectiveness"]


def _papers(slug: str) -> list[dict]:
    entries = json.loads((ROOT / "data" / "domains" / slug / "prelabelled.json").read_text())["entries"]
    return [{"wid": e["wid"], "title": e.get("title") or e["wid"], "abstract": e.get("abstract") or ""}
            for e in entries]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if len(s.split()) >= 6]


def _cards(slug: str, papers: list[dict], n: int) -> list[dict]:
    """n result cards in the shape the exporter writes: an open question
    taken from one of the library's own papers (its last abstract sentence),
    citing that paper."""
    out = []
    for p in papers:
        sents = _sentences(p["abstract"])
        if not sents:
            continue
        out.append({"slug": f"{slug}-synthetic-{len(out)}", "verdict": None,
                    "consumer": {"headline": sents[-1][:160], "kind": "An unfollowed question",
                                 "kind_id": "unfollowed_future_work", "strength": "Worth a look",
                                 "why": "A paper said this needed studying; no later paper here took it up."},
                    "supporting_papers": [{"title": p["title"]}]})
        if len(out) == n:
            break
    return out


def _library(slug: str, n_cards: int) -> tuple[dict, list[dict]]:
    papers = _papers(slug)
    cards = _cards(slug, papers, n_cards)
    return build_index(cards, papers), cards


def _smoke_assertion(idx: dict, pick: dict) -> tuple[bool, dict]:
    """What tools/qa/smoke.py asserts in the browser, on the built index:
    results, no refusal or edge banner, and gap cards when required."""
    r = search(idx, pick["query"], HIT_LIMIT, expand_trailing=True)
    hits = r.get("hits", [])
    gaps = sum(1 for h in hits if h.get("type") == "opportunity")
    ok = r["verdict"] == "in_domain" and len(hits) > 0 and (gaps > 0 or not pick["need_gaps"])
    return ok, {"verdict": r["verdict"], "hits": len(hits), "gaps": gaps}


@pytest.fixture(scope="module")
def libs() -> dict[str, tuple[dict, list[dict]]]:
    return {s: _library(s, 7) for s in QUEUED_DOMAINS}


@pytest.mark.parametrize("slug", QUEUED_DOMAINS)
def test_queued_domain_gets_a_phrase_that_reaches_results(libs, slug):
    idx, cards = libs[slug]
    others = [libs[s][0] for s in libs if s != slug]
    pick = smoke_phrase_for(slug, idx, others, shown_results=len(cards))
    assert len(cards) >= NEED_GAPS_MIN
    assert pick["need_gaps"] is True, pick                 # never loosened for a library with results
    assert pick["gap_hits"] > 0 and pick["verdict"] == "in_domain", pick
    ok, seen = _smoke_assertion(idx, pick)
    assert ok, (pick, seen)


def test_first_title_phrase_that_misses_every_result_is_not_picked(libs):
    """Run #8's shape: the most distinctive TITLE phrase is in_domain but
    matches papers only. The picker moves on to one that reaches a result."""
    from backend.app.api.search_phrases import queries_for
    found = 0
    for slug, (idx, cards) in libs.items():
        others = [libs[s][0] for s in libs if s != slug]
        for q in queries_for(idx, others):
            r = search(idx, q, HIT_LIMIT, expand_trailing=True)
            if r["verdict"] == "in_domain" and r["hits"] and not any(h["type"] == "opportunity" for h in r["hits"]):
                pick = smoke_phrase_for(slug, idx, others, shown_results=len(cards))
                assert pick["query"] != q and pick["gap_hits"] > 0, (slug, q, pick)
                found += 1
                break
    assert found, "expected at least one queued domain whose top title phrase hits papers only"


def test_library_with_few_results_is_checked_on_results_only_with_a_reason(libs):
    idx, cards = _library("growth-mindset", 2)
    others = [libs[s][0] for s in libs if s != "growth-mindset"]
    pick = smoke_phrase_for("growth-mindset", idx, others, shown_results=len(cards))
    assert pick["need_gaps"] is False and "fewer than 3" in pick["reason"], pick
    ok, seen = _smoke_assertion(idx, pick)
    assert ok, (pick, seen)


def test_when_no_phrase_reaches_a_result_the_check_still_requires_one(libs):
    """Result cards whose text no phrase can reach: the picker reports it and
    keeps need_gaps, so the smoke check fails loudly instead of passing."""
    papers = _papers("ego-depletion")
    cards = [{"slug": f"x-{i}", "verdict": None,
              "consumer": {"headline": "It is so.", "kind": "", "kind_id": "unfollowed_future_work",
                           "strength": "Worth a look", "why": "So it is."}} for i in range(4)]
    idx = build_index(cards, papers)
    others = [libs[s][0] for s in libs if s != "ego-depletion"]
    pick = smoke_phrase_for("ego-depletion", idx, others, shown_results=len(cards))
    assert pick["need_gaps"] is True and pick["gap_hits"] == 0 and pick["reason"].startswith("NO candidate"), pick
    ok, _seen = _smoke_assertion(idx, pick)
    assert not ok


def test_every_built_library_has_a_verified_phrase():
    """The site as built: every library's settled search passes the smoke
    assertion on its own index (the browser check repeats this)."""
    from backend.app.api.search_phrases import INDEX, LIBS, smoke_phrase
    facts = {l["slug"]: l for l in json.loads(
        (ROOT / "frontend" / "public" / "data" / "site-facts.json").read_text())["libraries"]}
    for lib in LIBS:
        pick = smoke_phrase(lib["slug"], facts[lib["slug"]]["results_total"])
        ok, seen = _smoke_assertion(INDEX[lib["slug"]], pick)
        assert ok, (lib["slug"], pick, seen)
