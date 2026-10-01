"""Regression tests for the per-pair contradiction titles.

The failure these guard against: PA2 of iteration-2 made every genuine
card's headline read "Two papers report findings that genuinely disagree",
turning the title into a verdict chip. Within a library, titles must:
- be unique;
- name both the exposure and the outcome at stake;
- never contain a verdict word (genuine, settled, resolved, confirmed, ...).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.api.contradiction_titles import (
    VERDICT_WORDS, TOPIC_TITLES,
    dedupe_titles, make_set_aside_title, make_title, make_verdict_label,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _assert_no_verdict_words(title: str) -> None:
    low = title.lower()
    for w in VERDICT_WORDS:
        assert w not in low.split(), f"{w!r} appears in {title!r}"


def test_known_topic_yields_specific_question_style_title():
    t = make_title("red meat / stroke", "", "")
    assert "red meat" in t.lower()
    assert "stroke" in t.lower()
    assert t.endswith("?") or "?" in t
    _assert_no_verdict_words(t)


def test_curated_titles_never_use_verdict_words():
    for key, title in TOPIC_TITLES.items():
        _assert_no_verdict_words(title)


def test_fallback_derivation_names_exposure_and_outcome():
    a = "Unprocessed red meat consumption is not associated with incident stroke."
    b = "Red meat is associated with an increased risk of stroke."
    t = make_title(None, a, b)
    low = t.lower()
    # Either "red" or "meat" (whichever shared exposure word was picked).
    assert "red" in low or "meat" in low
    assert "stroke" in low
    _assert_no_verdict_words(t)


def test_fallback_generic_still_safe_without_verdict_words():
    t = make_title(None, "noise one", "noise two")
    _assert_no_verdict_words(t)


def test_verdict_label_distinct_from_title():
    assert make_verdict_label("genuine") == (
        "Checked by hand against the abstracts: a real disagreement")
    assert make_verdict_label("artifact") == (
        "Set aside: the two papers measure different things")
    assert make_verdict_label("duplicate") == (
        "Set aside: duplicate of another pair")
    # The LLM-cal library has no audit data; the label must not render.
    assert make_verdict_label("whatever") is None


def test_set_aside_title_prefixes_but_keeps_topic():
    s = make_set_aside_title("artifact", "alcohol / MI dose-shape", "", "")
    assert "set aside" in s.lower()
    assert "alcohol" in s.lower() and "heart attack" in s.lower()


def test_dedupe_appends_distinguisher_on_collision_only():
    pairs = [
        ("Red meat and stroke: ...", "2010 vs 2016"),
        ("Red meat and stroke: ...", "updated meta-analysis"),
        ("Alcohol and stroke: ...", "no shared basis"),
    ]
    out = dedupe_titles(pairs)
    assert out[0].endswith("(2010 vs 2016)")
    assert out[1].endswith("(updated meta-analysis)")
    assert out[2] == "Alcohol and stroke: ..."  # no collision ⇒ unchanged


def test_diet_audit_produces_unique_titles():
    """End-to-end: run the title maker over the real diet audit JSON and
    confirm all genuine titles are unique and verdict-word-free."""
    audit = json.loads((REPO_ROOT / "data" / "domains" / "diet-and-mortality"
                        / "reasoning" / "contradiction_audit.json").read_text())
    titles = []
    for v in audit["verdicts"]:
        t = make_title(v.get("topic"), v.get("a_text_starts", ""),
                       v.get("b_text_starts", ""))
        _assert_no_verdict_words(t)
        titles.append(t)
    # Within a library, titles need to be unique after dedupe. The audit
    # includes a `duplicate` verdict whose topic deliberately says "restated",
    # which already differentiates it from the earlier pair.
    assert len(set(titles)) == len(titles), (
        f"duplicate titles: {titles}")
