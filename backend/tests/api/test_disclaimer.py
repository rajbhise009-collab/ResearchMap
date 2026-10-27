"""The non-affiliation notice (frontend/lib/site.ts NON_AFFILIATION) must
appear, verbatim, in the footer of every page, on /about and on /terms, and
in the README. /about's meta description carries it too; its Open Graph and
Twitter descriptions, and the site title, do not change. Checked in the
source always, and in the built pages (frontend/out) when they exist."""
from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FE = REPO / "frontend"
OUT = FE / "out"
NOTICE = ("ResearchMap (research-map.com) is an independent project. It is not affiliated with, endorsed by, "
          "or connected to researchmap, the researcher database at researchmap.jp.")


def _text(page: Path) -> str:
    s = re.sub(r"<!-- -->", "", page.read_text())
    s = re.sub(r"<script\b.*?</script>", " ", s, flags=re.S)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s)


def _meta(page: Path, attr: str, name: str) -> str | None:
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)"', page.read_text())
    return html.unescape(m.group(1)) if m else None


def test_the_notice_text_is_exact_in_one_place():
    src = (FE / "lib" / "site.ts").read_text()
    assert f'export const NON_AFFILIATION =\n  "{NOTICE}";' in src


@pytest.mark.parametrize("rel", ["app/layout.tsx", "app/about/page.tsx", "app/terms/page.tsx"])
def test_footer_about_and_terms_render_the_notice(rel):
    src = (FE / rel).read_text()
    assert "NON_AFFILIATION" in src.split("export default", 1)[-1], rel


def test_readme_carries_the_notice():
    assert NOTICE in (REPO / "README.md").read_text()


def test_terms_shows_it_next_to_the_copyright_section():
    src = (FE / "app" / "terms" / "page.tsx").read_text()
    i, j = src.index("<strong>Copyright.</strong>"), src.index("{NON_AFFILIATION}")
    assert 0 < j - i < 900


needs_build = pytest.mark.skipif(not (OUT / "index.html").exists(), reason="no build output (frontend/out)")


@needs_build
@pytest.mark.parametrize("page", ["index.html", "about/index.html", "terms/index.html", "gaps/index.html",
                                  "papers/index.html", "404.html"])
def test_built_pages_show_the_notice(page):
    assert NOTICE in _text(OUT / page), page


@needs_build
def test_built_footer_carries_it_on_every_page():
    pages = [p for p in OUT.rglob("index.html")]
    assert len(pages) > 50
    missing = [str(p.relative_to(OUT)) for p in pages if 'class="foot-disclaimer"' not in p.read_text()]
    assert not missing, missing[:10]


@needs_build
def test_about_meta_description_only():
    about = OUT / "about" / "index.html"
    assert NOTICE in (_meta(about, "name", "description") or "")
    for attr, name in (("property", "og:description"), ("name", "twitter:description")):
        assert NOTICE not in (_meta(about, attr, name) or ""), name
    home = OUT / "index.html"
    assert NOTICE not in (_meta(home, "name", "description") or "")
    assert re.search(r"<title>About — ResearchMap</title>", about.read_text())
