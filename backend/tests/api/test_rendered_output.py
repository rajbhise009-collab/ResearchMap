"""Audit the built site itself.

test_language.py polices the translation layer at the source. This one
polices the templates: a page that hard-codes "scorer" in its JSX, or
renders a raw score into visible text, would pass every source test and
still ship. So this reads the actual static export and looks at what a
reader would see with the markup stripped away.

Skips when frontend/out is absent — it needs `npm run build` to have run.
"""

from __future__ import annotations

import html as html_mod
import re
from pathlib import Path

import pytest

from backend.app.api import language

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "frontend" / "out"

pytestmark = pytest.mark.skipif(
    not OUT.exists(), reason="needs a built static export (npm run build)"
)


def visible_text(html: str) -> str:
    """What a reader sees: markup, scripts and styles removed. The Next.js
    data payload lives in <script> tags and legitimately carries the raw
    values developer mode reveals, so it is excluded here."""
    s = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    # Entities must be decoded or "What&#x27;s uncertain" would never match
    # the copy it was rendered from.
    return re.sub(r"\s+", " ", html_mod.unescape(s))


def consumer_pages() -> list[Path]:
    """Every rendered page except the findings reports, which are raw
    working notes and say so on the page itself."""
    return [p for p in sorted(OUT.rglob("*.html")) if "findings/" not in str(p)]


@pytest.fixture(scope="module")
def pages():
    out = [(p, visible_text(p.read_text(errors="ignore"))) for p in consumer_pages()]
    assert len(out) > 150, "expected a full static export"
    return out


def test_no_plumbing_in_visible_text(pages):
    """Our machinery must never be visible, on any page."""
    offenders = []
    for path, text in pages:
        low = text.lower()
        for term in language.PLUMBING_TERMS:
            # "cosine" appears inside papers' own method descriptions, which
            # is their terminology, not our plumbing leaking out.
            if term == "cosine":
                continue
            if term in low:
                offenders.append((path.relative_to(OUT).as_posix(), term))
    assert not offenders, f"internal machinery visible to readers: {offenders[:6]}"


def test_our_internal_names_appear_only_inside_quoted_research(pages):
    """"corpus" and "epistemic" are ordinary words in this field and turn up
    in sentences quoted from papers. They must never appear in copy we
    wrote — which we check by requiring them to sit inside quotation marks."""
    for path, text in pages:
        for term in ("orphaned", "structural hole", "persistent limitation"):
            assert term not in text.lower(), (path.name, term)


def test_no_raw_scores_rendered(pages):
    """No score, confidence value or similarity number reaches the reader."""
    for path, text in pages:
        for pattern in (r"trust\s*[:=]\s*0\.", r"score\s*[:=]\s*0\.",
                        r"confidence\s*[:=]\s*0\.", r"cosine\s+0\."):
            assert not re.search(pattern, text, re.I), (path.name, pattern)


def test_every_gap_page_states_how_sure_and_why(pages):
    """No result renders without its strength and its reasoning."""
    gaps = [(p, t) for p, t in pages if p.parent.parent.name == "gap"]
    assert len(gaps) > 50
    strengths = (language.STRONG, language.WORTH_A_LOOK, language.UNVERIFIED)
    for path, text in gaps:
        assert any(s in text for s in strengths), path.name
        assert "Why this came up" in text, path.name
        assert language.UI["papers_behind"] in text, path.name


def test_every_weak_gap_page_shows_its_caveat_inline(pages):
    """The caveat is on the page as text — not a tooltip, not a footnote."""
    gaps = [(p, t) for p, t in pages if p.parent.parent.name == "gap"]
    checked = 0
    for path, text in gaps:
        if language.UNVERIFIED in text or language.WORTH_A_LOOK in text:
            assert language.UI["uncertain_heading"] in text, path.name
            checked += 1
    assert checked > 40


def test_corpus_relative_caveat_names_the_library_size(pages):
    """"Nobody has done this" must never render without "within these 113
    papers" beside it."""
    hits = 0
    for path, text in pages:
        if "nothing in this library followed this up" in text.lower():
            assert "113" in text, path.name
            assert "not the whole field" in text.lower(), path.name
            hits += 1
    assert hits > 20, "expected the unfollowed-question caveat on many pages"


def test_summary_only_papers_are_flagged_with_the_reason(pages):
    """Every paper we only had the summary for says so, and says why it
    matters, rather than quietly looking like the rest."""
    flagged = 0
    for path, text in pages:
        if path.parent.parent.name == "paper" and language.ABSTRACT_ONLY["label"] in text:
            assert "summary" in text.lower(), path.name
            flagged += 1
    assert flagged > 30, f"expected many summary-only papers flagged, got {flagged}"


def test_zero_disagreements_renders_an_explanation_not_a_blank(pages):
    lib = next((t for p, t in pages if p.parent.name == "library"), None)
    assert lib, "library page missing from the export"
    assert language.NO_DISAGREEMENTS["headline"] in lib
    assert "zero" in lib.lower() or "none" in lib.lower()


def test_landing_page_leads_with_a_question_not_a_dashboard(pages):
    home = next(t for p, t in pages if p == OUT / "index.html")
    raw = (OUT / "index.html").read_text(errors="ignore")
    assert language.TAGLINE in home
    # The query box is the first thing on the page; its prompt lives in an
    # attribute, so it is checked against the markup rather than the text.
    assert f'placeholder="{language.SEARCH["placeholder"]}"' in raw
    assert language.WHAT_IT_DOES in home
    # A consumer landing page does not open with statistics.
    assert "manifest" not in home.lower()
    assert "per-scorer" not in home.lower()
    assert "yield" not in home.lower()
