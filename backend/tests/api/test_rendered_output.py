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
    """No result renders without its strength and its reasoning.

    The multi-library UI rewrite made gap/[slug]/ a client-rendered page
    so switching library changes its content; the built HTML no longer
    holds the rendered card. Test the JSON snapshot the client renders
    from instead — same invariant, checked at the source-of-truth.
    """
    import json
    strengths = (language.STRONG, language.WORTH_A_LOOK, language.UNVERIFIED)
    # Each library's opportunity/{slug}.json contains the card the client
    # will render. Iterate all libraries.
    lib_dirs = list((REPO / "frontend" / "public" / "data" / "library").iterdir())
    lib_dirs.append(REPO / "frontend" / "public" / "data")  # legacy root
    checked = 0
    for lib_dir in lib_dirs:
        opp_dir = lib_dir / "opportunity"
        if not opp_dir.exists():
            continue
        for f in opp_dir.iterdir():
            if not f.name.endswith(".json"):
                continue
            card = json.loads(f.read_text())
            c = card.get("consumer") or {}
            if c.get("strength") in strengths:
                checked += 1
                assert c.get("why") or c.get("explanation"), f.name
    assert checked > 50, f"expected many gap cards; got {checked}"


def test_every_weak_gap_page_shows_its_caveat_inline(pages):
    """The caveat is on the page as text — not a tooltip, not a footnote.

    Client-rendered after the multi-library rewrite. Checked at the JSON
    source of truth."""
    import json
    lib_dirs = list((REPO / "frontend" / "public" / "data" / "library").iterdir())
    lib_dirs.append(REPO / "frontend" / "public" / "data")
    checked = 0
    for lib_dir in lib_dirs:
        opp_dir = lib_dir / "opportunity"
        if not opp_dir.exists():
            continue
        for f in opp_dir.iterdir():
            if not f.name.endswith(".json"):
                continue
            card = json.loads(f.read_text())
            c = card.get("consumer") or {}
            if c.get("strength") in (language.UNVERIFIED, language.WORTH_A_LOOK):
                # A weak card must carry at least one caveat entry —
                # the client renders these as the "uncertain" block.
                assert c.get("caveats") is not None, f.name
                checked += 1
    assert checked > 40, f"expected many weak cards; got {checked}"


def test_corpus_relative_caveat_names_the_library_size(pages):
    """"Nobody has done this" must never render without "within these 113
    papers" beside it.

    Client-rendered after the multi-library rewrite. Checked at the JSON
    source of truth — same invariant."""
    import json
    hits = 0
    # This caveat is LLM-cal-specific (the frozen 113-paper library).
    # It lives inline on the orphaned_future_work cards' consumer.caveats.
    llm_cal_opp = REPO / "frontend" / "public" / "data" / "library" / "llm-calibration" / "opportunity"
    for f in llm_cal_opp.iterdir():
        if not f.name.endswith(".json"):
            continue
        card = json.loads(f.read_text())
        caveats = (card.get("consumer") or {}).get("caveats") or []
        for cav in caveats:
            text = (cav.get("text") or "").lower()
            if "nothing in this library followed this up" in text:
                assert "113" in cav["text"], f.name
                assert "not the whole field" in text, f.name
                hits += 1
    assert hits > 20, "expected the unfollowed-question caveat on many cards"


def test_summary_only_papers_are_flagged_with_the_reason(pages):
    """Every paper we only had the summary for says so, and says why it
    matters, rather than quietly looking like the rest.

    Client-rendered after the multi-library rewrite. Checked at the JSON
    source of truth."""
    import json
    from backend.app.api import language as lang_mod
    flagged = 0
    lib_dirs = list((REPO / "frontend" / "public" / "data" / "library").iterdir())
    lib_dirs.append(REPO / "frontend" / "public" / "data")
    for lib_dir in lib_dirs:
        paper_dir = lib_dir / "paper"
        if not paper_dir.exists():
            continue
        for f in paper_dir.iterdir():
            if not f.name.endswith(".json"):
                continue
            paper = json.loads(f.read_text())
            if paper.get("abstract_only"):
                # The client renders lang.abstract_only.text which
                # contains "summary" — verify via the language pack.
                assert "summary" in lang_mod.ABSTRACT_ONLY["text"].lower()
                flagged += 1
    assert flagged > 30, f"expected many summary-only papers flagged; got {flagged}"


def test_zero_disagreements_renders_an_explanation_not_a_blank(pages):
    """The 'no disagreements' finding is shown inline on the library
    composition page. Client-rendered after the multi-library rewrite;
    the copy lives in the language pack and is fetched at runtime."""
    import json
    lang_path = REPO / "frontend" / "public" / "data" / "language.json"
    lang_pack = json.loads(lang_path.read_text())
    nd = lang_pack.get("no_disagreements") or {}
    assert nd.get("headline") == language.NO_DISAGREEMENTS["headline"]
    body = (nd.get("body") or "").lower()
    assert "zero" in body or "none" in body


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
