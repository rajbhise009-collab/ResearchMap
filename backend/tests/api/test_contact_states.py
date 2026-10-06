"""/contact wording for every site.config.json state, and the launch-check
contact gate. Runs the real frontend/lib/contact.ts through Node's built-in
TypeScript stripping (Node >= 22.6), so no frontend test runner is needed."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FE = REPO / "frontend"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

REPO_URL = "https://github.com/example/project"


def _content(cfg: dict) -> dict:
    script = (f"import {{ contactContent }} from {json.dumps((FE / 'lib' / 'contact.ts').as_uri())};"
              f"console.log(JSON.stringify(contactContent({json.dumps(cfg)})));")
    out = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings",
                          "--input-type=module", "-e", script],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _text(c: dict) -> str:
    return c["none"] or " ".join(f"{l['lead']} {l['label']}" for l in c["lines"])


def test_email_and_public_repo():
    c = _content({"contactEmail": "a@example.org", "repoUrl": REPO_URL, "repoIsPublic": True})
    assert [l["lead"] for l in c["lines"]] == ["Email:", "You can also open an issue on GitHub:"]
    assert c["lines"][0]["href"] == "mailto:a@example.org"
    assert c["lines"][1]["href"] == REPO_URL + "/issues" and c["none"] is None


def test_email_only():
    for public, url in [(False, REPO_URL), (True, "")]:
        c = _content({"contactEmail": "a@example.org", "repoUrl": url, "repoIsPublic": public})
        assert [l["lead"] for l in c["lines"]] == ["Email:"]


def test_public_repo_only_has_no_dangling_or():
    c = _content({"contactEmail": "", "repoUrl": REPO_URL, "repoIsPublic": True})
    assert [l["lead"] for l in c["lines"]] == ["Open an issue on GitHub:"]
    assert not _text(c).lower().startswith("or ")
    assert "also" not in _text(c).lower()


def test_neither_is_one_honest_line():
    c = _content({"contactEmail": "  ", "repoUrl": REPO_URL, "repoIsPublic": False})
    assert c["lines"] == []
    assert c["none"] == "There is no way to contact the project through this site yet."


def test_no_address_is_invented():
    c = _content({"contactEmail": "", "repoUrl": "", "repoIsPublic": False})
    assert "@" not in json.dumps(c) and "http" not in json.dumps(c)


@pytest.mark.skipif(not (FE / "out" / "index.html").exists(), reason="frontend not built")
@pytest.mark.parametrize("cfg,ok", [
    ({"contactEmail": "", "repoIsPublic": False}, False),
    ({"contactEmail": "", "repoIsPublic": True}, True),
    ({"contactEmail": "a@example.org", "repoIsPublic": False}, True),
])
def test_launch_check_contact_gate(tmp_path, cfg, ok):
    p = tmp_path / "site.config.json"
    p.write_text(json.dumps({"siteName": "X", "authorName": "", "affiliation": "",
                             "repoUrl": REPO_URL, **cfg}))
    out = subprocess.run([NODE, str(FE / "scripts" / "launch-check.mjs")],
                         capture_output=True, text=True, env={"SITE_CONFIG": str(p), "PATH": ""})
    line = next(l for l in out.stdout.splitlines() if "contact route configured" in l)
    assert line.startswith("PASS" if ok else "FAIL"), line
