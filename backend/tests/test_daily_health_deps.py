"""The daily health workflow installs only what .github/workflows/daily-health.yml
lists (Playwright). tools/grow/health.py and tools/qa/smoke.py must run with
exactly that: no pytest, numpy, pydantic... (smoke.py once imported a test
module, and daily health failed with ModuleNotFoundError: pytest)."""
from __future__ import annotations

import importlib.metadata as md
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WF = REPO / ".github" / "workflows" / "daily-health.yml"


def _installed_by_workflow() -> set[str]:
    """Top-level module names of the packages the workflow pip-installs, and
    their dependencies (recursively)."""
    pkgs = []
    for line in WF.read_text().splitlines():
        m = re.search(r"pip install (.+)$", line)
        if m:
            pkgs += [re.split(r"[=<>\[ ]", a)[0] for a in m.group(1).split() if not a.startswith("-")]
    assert pkgs, "no pip install line found in daily-health.yml"
    seen, todo, mods = set(), list(pkgs), set()
    while todo:
        p = todo.pop().lower()
        if p in seen:
            continue
        seen.add(p)
        try:
            dist = md.distribution(p)
        except md.PackageNotFoundError:
            mods.add(p.replace("-", "_"))
            continue
        top = dist.read_text("top_level.txt")
        mods |= set(top.split()) if top else {p.replace("-", "_")}
        for r in dist.requires or []:
            if "extra ==" not in r:
                todo.append(re.split(r"[=<>!~;\[ (]", r)[0])
    return mods


_PROBE = r'''
import importlib.abc, importlib.util, json, sys
from pathlib import Path
REPO = Path(sys.argv[1]); ALLOWED = set(json.loads(sys.argv[2]))
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        top = name.split(".")[0]
        if top in sys.stdlib_module_names or top in ALLOWED or top in sys.builtin_module_names:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                origin = spec.origin or (list(spec.submodule_search_locations or [""])[0])
                if origin and str(Path(origin).resolve()).startswith(str(REPO)) and ".venv" not in origin:
                    return None          # the repo's own code
                raise ModuleNotFoundError(f"not installed by daily-health.yml: {name}")
        return None
sys.meta_path.insert(0, Block())
sys.path[:0] = [str(REPO), str(REPO / "tools" / "grow"), str(REPO / "tools" / "qa")]
import health                                  # tools/grow/health.py
spec = importlib.util.spec_from_file_location("smoke", REPO / "tools" / "qa" / "smoke.py")
smoke = importlib.util.module_from_spec(spec); spec.loader.exec_module(smoke)
libs = json.loads((REPO / "frontend/public/data/libraries.json").read_text())["libraries"]
print(json.dumps({l["slug"]: smoke._phrase(l["slug"]) for l in libs}))
'''


def test_health_and_smoke_import_with_only_the_daily_workflows_packages():
    allowed = _installed_by_workflow()
    assert "playwright" in allowed
    r = subprocess.run([sys.executable, "-c", _PROBE, str(REPO), json.dumps(sorted(allowed))],
                       capture_output=True, text=True, cwd=REPO, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    phrases = json.loads(r.stdout.strip().splitlines()[-1])
    assert phrases and all(phrases.values()), phrases


def test_the_probe_really_blocks_test_only_packages():
    """Guard against a probe that allows everything: importing pytest under
    the same rules must fail."""
    allowed = _installed_by_workflow()
    assert "pytest" not in allowed and "numpy" not in allowed
    probe = _PROBE.split("sys.path[:0]")[0] + "import pytest\n"
    r = subprocess.run([sys.executable, "-c", probe, str(REPO), json.dumps(sorted(allowed))],
                       capture_output=True, text=True, cwd=REPO, timeout=120)
    assert r.returncode != 0 and "not installed by daily-health.yml: pytest" in r.stderr
