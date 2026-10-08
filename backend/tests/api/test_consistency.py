"""Every count and title agrees across the site's surfaces
(frontend/scripts/consistency.mjs). Data checks always; built-output checks
(sitemap, page titles, /method) when frontend/out exists."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FE = Path(__file__).resolve().parents[3] / "frontend"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def _run(*args):
    return subprocess.run([NODE, str(FE / "scripts" / "consistency.mjs"), *args],
                          capture_output=True, text=True)


def test_data_surfaces_agree():
    r = _run()
    assert r.returncode == 0, r.stderr + r.stdout


@pytest.mark.skipif(not (FE / "out" / "sitemap.xml").exists(), reason="frontend not built")
def test_built_surfaces_agree():
    r = _run("--built")
    assert r.returncode == 0, r.stderr + r.stdout
