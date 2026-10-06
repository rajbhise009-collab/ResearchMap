"""Every occurrence of "definitional" on the public findings pages sits in a
section whose text includes "hypothes" or "not established". Checked on the
shipped findings.json files and on the built /findings/* pages. The word is
allowed; presenting it outside a hypothesis-labelled section is not."""

from __future__ import annotations

import html as htmlmod
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PUBLIC = REPO / "frontend" / "public" / "data"
OUT = REPO / "frontend" / "out" / "findings"
LABELS = ("hypothes", "not established")


def _check(sections: list[str], where: str) -> int:
    n = 0
    for sec in sections:
        low = sec.lower()
        if "definitional" in low:
            n += low.count("definitional")
            assert any(l in low for l in LABELS), f"{where}: unlabelled 'definitional' in {sec[:160]!r}"
    return n


def test_shipped_findings_json():
    total = 0
    for f in sorted(PUBLIC.rglob("findings.json")):
        for item in json.loads(f.read_text())["items"]:
            sections = re.split(r"^#{1,6} ", item["markdown"], flags=re.M)
            total += _check(sections, f"{f.relative_to(REPO)}:{item['slug']}")
    assert total > 0, "expected the word to be present (it stays, labelled)"


@pytest.mark.skipif(not OUT.exists(), reason="frontend not built")
def test_built_findings_pages():
    total = 0
    for page in sorted(OUT.glob("*/index.html")):
        raw = page.read_text()
        body = raw[raw.find('<article class="md"'):]
        body = body[:body.find("</article>")]
        parts = re.split(r"<h[1-6][^>]*>", body)
        text = [htmlmod.unescape(re.sub(r"<[^>]+>", " ", p)) for p in parts]
        total += _check(text, str(page.relative_to(REPO)))
    assert total > 0
