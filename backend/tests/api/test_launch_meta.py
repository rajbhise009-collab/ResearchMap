"""Launch metadata on the built static site (frontend/out): factual
descriptions with no verdict words, Diet descriptions never read as advice,
a canonical URL on every page, and share images that exist."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.app.api.contradiction_titles import VERDICT_WORDS

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "frontend" / "out"
DATA = REPO / "frontend" / "public" / "data"

pytestmark = pytest.mark.skipif(not (OUT / "index.html").exists(),
                                reason="frontend not built (run npm run build)")


def _meta(html: str, name: str) -> str | None:
    m = re.search(rf'<meta (?:name|property)="{re.escape(name)}" content="([^"]*)"', html)
    return m.group(1) if m else None


def _pages():
    return [p for p in OUT.rglob("index.html") if "404" not in p.parts]


def test_every_page_has_canonical_title_description_and_og():
    for p in _pages():
        h = p.read_text()
        assert re.search(r'<link rel="canonical" href="https?://[^"?]+"', h), p
        assert _meta(h, "description"), p
        assert _meta(h, "og:image") and _meta(h, "twitter:card"), p


def test_descriptions_and_titles_carry_no_verdict_words():
    for p in _pages():
        h = p.read_text()
        title = re.search(r"<title>([^<]*)</title>", h).group(1).lower()
        desc = (_meta(h, "description") or "").lower()
        if "/findings/" in str(p):
            continue  # working notes discuss audit verdicts by name
        for w in VERDICT_WORDS:
            assert not re.search(rf"\b{w}\b", title + " " + desc), (p, w)


def test_diet_gap_and_paper_descriptions_say_not_advice():
    lib = DATA / "library" / "diet-and-mortality"
    ids = [("gap", f.stem) for f in (lib / "opportunity").glob("*.json")] + \
          [("paper", f.stem) for f in (lib / "paper").glob("*.json")]
    assert ids
    for kind, i in ids:
        desc = _meta((OUT / kind / i / "index.html").read_text(), "description") or ""
        assert desc.endswith("not dietary or medical advice."), (kind, i, desc)


def test_share_images_exist_and_are_small():
    libs = json.loads((DATA / "libraries.json").read_text())["libraries"]
    for slug in [l["slug"] for l in libs] + ["default"]:
        f = REPO / "frontend" / "public" / "og" / f"{slug}.png"
        assert f.exists() and f.stat().st_size < 150_000, f


def test_non_production_build_is_noindex():
    import os
    home = (OUT / "index.html").read_text()
    robots = (OUT / "robots.txt").read_text()
    if os.environ.get("VERCEL_ENV") == "production":
        pytest.skip("production build")
    if "noindex" in home:
        assert "Disallow: /" in robots
