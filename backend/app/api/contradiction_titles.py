"""Deterministic per-pair titles for contradiction cards.

The regression we fixed: PA2 of iteration-2 put the audit verdict string
("Two papers report findings that genuinely disagree") into
`consumer.headline`, which is the per-pair card title. The verdict is a
single label that is identical across every genuine card and must not be
the title. Titles must name the exposure and the outcome and describe the
specific disagreement at stake.

The title is derived in code from the audited `topic` string plus the
two claim texts — never from an LLM. The verdict goes into a separate
`verdict_label` field, read by the UI as a small chip.

Vocabulary — titles must NEVER contain any of these words, because they
collapse the plain-language question into the verdict chip's job:

    genuine, genuinely, settled, resolved, confirmed

Collision rule: when two titles collide after derivation, we append the
specific question clause from the audit `reason`, never a number.
"""

from __future__ import annotations

import re
from typing import Iterable

VERDICT_WORDS = {"genuine", "genuinely", "settled", "resolved", "confirmed"}

# Hand-curated titles for the exact `topic` strings in the hand audits.
# Each is a plain question that names exposure and outcome. The map is the
# single place to add a new entry when a future audit introduces a new
# `topic` — the fallback below handles unaudited pairs.
TOPIC_TITLES: dict[str, str] = {
    # social media & adolescent mental health (audit 2026-10-09)
    "smartphones and adolescent well-being":
        "Smartphones and teenagers' well-being: a real decline, or too small to matter?",
    "rising depression across birth cohorts":
        "Depression across generations: a real rise, or an artifact of recall?",
    "screen time / well-being at low use":
        "A little screen time and children's well-being: no difference, or slightly better?",
    "cyberbullying and suicidality":
        "Cyberbullying and suicidal thoughts: mixed evidence, or a strong link?",
    "social media use and life satisfaction":
        "Social media and life satisfaction: a decline, or a trivial effect?",
    "red meat / stroke":
        "Red meat and stroke: no association, or an increased risk?",
    "red meat / type 2 diabetes":
        "Red meat and type-2 diabetes: no association, or an increased risk?",
    "alcohol / MI dose-shape":
        "Alcohol and heart attack: is the risk-curve the same for men's "
        "drinking-days and for weekly totals across populations?",
    "alcohol / stroke — is there an association?":
        "Alcohol and stroke: is there any overall association?",
    "alcohol / ischemic stroke dose-shape":
        "Alcohol and ischemic stroke: a J-shaped curve or a straight line?",
    "alcohol / all-cause mortality — J-shape vs quality-adjusted null":
        "Alcohol and all-cause mortality: does a protective J-shape survive "
        "adjustment for abstainer-bias and study quality?",
    "triglycerides / coronary heart disease — independent of other risk factors?":
        "Triglycerides and coronary heart disease: a raised risk, or no link "
        "once other risk factors are accounted for?",
    "triglycerides / coronary heart disease — EPIC-Norfolk estimate (duplicate)":
        "Triglycerides and coronary heart disease: the EPIC-Norfolk cohort "
        "estimate (restated)",
    "triglycerides / coronary heart disease — Reykjavik estimate (duplicate)":
        "Triglycerides and coronary heart disease: the Reykjavik cohort "
        "estimate (restated)",
    "alcohol / all-cause mortality — duplicate of previous":
        "Alcohol and all-cause mortality: does the protective J-shape "
        "survive abstainer-bias correction? (restated)",
}


# ----- helpers for the fallback (used for unaudited domains, future libs) --

_STRIP = re.compile(r"[^a-z0-9\- ]+")


def _norm(s: str) -> str:
    return _STRIP.sub("", (s or "").lower()).strip()


def _tokens(s: str) -> list[str]:
    return [t for t in _norm(s).split() if len(t) > 2]


_NEGATION = {"not", "no", "fail", "fails", "failed", "fewer", "less",
             "lower", "null", "neutral", "neither"}
_POSITIVE = {"associated", "increased", "higher", "greater", "elevated",
             "linked", "linear", "linearly", "positive"}


def _looks_null(text: str) -> bool:
    toks = set(_tokens(text))
    return bool(toks & _NEGATION) and not bool(toks & _POSITIVE)


def _looks_positive(text: str) -> bool:
    return bool(set(_tokens(text)) & _POSITIVE)


def _top_shared_noun(a: str, b: str, pool: Iterable[str]) -> str | None:
    sa, sb = set(_tokens(a)), set(_tokens(b))
    shared = [p for p in pool if p in sa and p in sb]
    return shared[0] if shared else None


_EXPOSURE_WORDS = (
    "alcohol", "wine", "beer", "coffee", "tea", "meat", "red", "processed",
    "fish", "dairy", "milk", "fruit", "vegetable", "sodium", "salt", "sugar",
    "carbohydrate", "fat", "protein", "fiber", "mediterranean", "vegan",
    "vegetarian", "ketogenic",
)
_OUTCOME_WORDS = (
    "mortality", "death", "stroke", "infarction", "diabetes", "cardiovascular",
    "cancer", "disease", "hypertension",
)


def _derive_from_texts(a_text: str, b_text: str) -> str:
    """Fallback for pairs without a mapped audit topic. Picks a shared
    exposure word and a shared outcome word from the two claims and
    builds a plain question. Never includes verdict words."""
    exp = _top_shared_noun(a_text, b_text, _EXPOSURE_WORDS)
    out = _top_shared_noun(a_text, b_text, _OUTCOME_WORDS)
    if exp and out:
        if _looks_null(a_text) and _looks_positive(b_text):
            return (f"{exp.capitalize()} and {out}: no association, or an "
                    "increased risk?")
        if _looks_positive(a_text) and _looks_null(b_text):
            return (f"{exp.capitalize()} and {out}: an increased risk, or no "
                    "association?")
        return f"{exp.capitalize()} and {out}: two papers disagree on the finding."
    # Last-resort generic (still no verdict words). The caller is expected
    # to dedupe collisions by appending the audit reason snippet.
    return "Two papers disagree on the finding."


# ----- public API ----------------------------------------------------------


def make_title(topic: str | None, a_text: str, b_text: str) -> str:
    """Deterministic topic-specific title for one contradiction pair.

    Prefers the hand-curated `TOPIC_TITLES` mapping (keyed on the audit's
    `topic` field); falls back to a plain exposure-outcome question derived
    from the two claim texts when no entry matches. Never contains any
    `VERDICT_WORDS`.
    """
    if topic and topic in TOPIC_TITLES:
        title = TOPIC_TITLES[topic]
    else:
        title = _derive_from_texts(a_text or "", b_text or "")
    # Belt-and-braces: strip the forbidden words from any manual addition
    # that slipped in. A title that would depend on them is a bad title.
    low = title.lower()
    for w in VERDICT_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", low):
            raise ValueError(
                f"TOPIC_TITLES entry contains forbidden verdict word "
                f"{w!r}: {title!r}")
    return title


def make_verdict_label(verdict: str) -> str | None:
    """Plain-wording label chip for the per-pair verdict. Returns None
    for libraries with no audit data (so no label renders at all)."""
    if verdict == "genuine":
        return "Checked by hand against the abstracts: a real disagreement"
    if verdict == "artifact":
        return "Set aside: the two papers measure different things"
    if verdict == "duplicate":
        return "Set aside: duplicate of another pair"
    if verdict == "unaudited":
        return "Flagged by the system, not yet checked"
    return None


def make_set_aside_title(verdict: str, topic: str | None,
                         a_text: str, b_text: str) -> str:
    """Topic-naming title for set-aside cards. Starts from the same
    derivation but prefixes with 'Set aside — ' so the gaps list reads
    clearly without hiding the question."""
    base = make_title(topic, a_text, b_text)
    if verdict == "duplicate":
        return f"Set aside (duplicate pair): {base}"
    if verdict == "artifact":
        return f"Set aside (different measures): {base}"
    return base


def dedupe_titles(items: list[tuple[str, str]]) -> list[str]:
    """Resolve collisions. `items` is a list of (title, distinguisher)
    pairs; the distinguisher is a short clause from the audit `reason`
    that is only appended when a title would otherwise collide.
    Returns the final list in input order."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for title, _ in items:
        seen[title] = seen.get(title, 0) + 1
    counts: dict[str, int] = {}
    for title, distinguisher in items:
        if seen[title] > 1 and distinguisher:
            counts[title] = counts.get(title, 0) + 1
            out.append(f"{title} ({distinguisher})")
        else:
            out.append(title)
    return out
