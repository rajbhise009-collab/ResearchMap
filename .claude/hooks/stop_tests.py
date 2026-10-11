#!/usr/bin/env python3
"""Stop hook (.claude/settings.json): before Claude finishes a turn, run the
test suites that cover what changed, chosen from `git diff --name-only HEAD`
plus untracked files.

- Nothing relevant changed, or the same change already passed: exit at once.
- A suite fails: return decision "block" with the failing tests and the tail
  of the output, so the turn continues and the failure gets fixed.
- `stop_hook_active` (already continuing because of this hook): never block
  twice in a row; the failure is reported, not looped on.

Standard library only. `suites_for(paths)` is importable for tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
PY = str(ROOT / ".venv" / "bin" / "python")
CACHE = ROOT / ".git" / "claude-stop-hook-passed"

SEARCH = ["backend/tests/api/test_search.py", "backend/tests/api/test_search_typing.py",
          "backend/tests/api/test_search_per_library.py", "backend/tests/api/test_search_parity.py",
          "backend/tests/api/test_search_autogen.py", "backend/tests/api/test_search_growth.py",
          "backend/tests/api/test_cross_library_collisions.py", "backend/tests/api/test_safety_queries.py"]

# (path prefix, suites) — first match per path wins; order matters
RULES: list[tuple[str, list[str]]] = [
    ("backend/app/api/search_index.py", SEARCH),
    ("backend/app/api/search_phrases.py", SEARCH),
    ("frontend/lib/search.ts", SEARCH + ["@tsc"]),
    ("backend/tests/conftest.py", ["backend/tests"]),
    ("backend/app/grow/", ["backend/tests/grow", "backend/tests/test_daily_health_deps.py"]),
    ("tools/grow/", ["backend/tests/grow", "backend/tests/test_daily_health_deps.py"]),
    (".github/workflows/", ["backend/tests/grow", "backend/tests/test_ci_workflow.py"]),
    ("tools/qa/", ["backend/tests/test_daily_health_deps.py"]),
    ("tools/ci/", ["backend/tests/extraction/test_ledger_append_only.py"]),
    (".claude/hooks/", ["backend/tests/test_claude_hooks.py"]),
    (".githooks/", ["backend/tests/test_claude_hooks.py"]),
    ("backend/app/reasoning/", ["backend/tests/reasoning", "backend/tests/ranking"]),
    ("backend/app/ranking/", ["backend/tests/ranking"]),
    ("backend/app/relationships/", ["backend/tests/relationships"]),
    ("backend/app/extraction/", ["backend/tests/extraction"]),
    ("backend/app/validation/", ["backend/tests/validation"]),
    ("backend/app/corpus/", ["backend/tests/corpus"]),
    ("backend/app/ingestion/", ["backend/tests/ingestion"]),
    ("backend/app/api/", ["backend/tests/api"]),
    ("backend/app/", ["backend/tests"]),
    ("frontend/", ["@tsc"]),
]


def suites_for(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if p.startswith("backend/tests/") and p.endswith(".py"):
            picked = [p]
        else:
            picked = next((s for prefix, s in RULES if p.startswith(prefix)), [])
            if p.startswith("frontend/") and not (p.endswith((".ts", ".tsx")) and "/public/" not in p):
                picked = [s for s in picked if s != "@tsc"]
        for s in picked:
            if s not in out:
                out.append(s)
    # a selected folder covers every test file inside it
    dirs = [s for s in out if not s.startswith("@") and not s.endswith(".py")]
    out = [s for s in out if not any(s != d and s.startswith(d + "/") for d in dirs)]
    return [s for s in out if s.startswith("@") or (ROOT / s).exists()]


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout


def changed_paths() -> list[str]:
    tracked = _git("diff", "--name-only", "HEAD").splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({p for p in tracked + untracked if p})


def fingerprint(paths: list[str]) -> str:
    h = hashlib.sha256(_git("diff", "HEAD").encode())
    for p in paths:
        f = ROOT / p
        if f.is_file() and p in _git("ls-files", "--others", "--exclude-standard"):
            h.update(p.encode() + f.read_bytes())
    return h.hexdigest()


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        event = {}
    paths = changed_paths()
    suites = suites_for(paths)
    if not suites:
        return 0
    fp = fingerprint(paths)
    if CACHE.exists() and CACHE.read_text().strip() == fp:
        return 0                                          # this exact change already passed
    failures = []
    py_suites = [s for s in suites if not s.startswith("@")]
    if py_suites:
        r = subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *py_suites],
                           cwd=ROOT, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-40:])
            failures.append(f"pytest {' '.join(py_suites)}\n{tail}")
    if "@tsc" in suites:
        r = subprocess.run(["npx", "tsc", "--noEmit"], cwd=ROOT / "frontend", capture_output=True, text=True,
                           timeout=600)
        if r.returncode != 0:
            failures.append("frontend typecheck\n" + "\n".join((r.stdout + r.stderr).strip().splitlines()[-30:]))
    if not failures:
        CACHE.write_text(fp)
        return 0
    if event.get("stop_hook_active"):
        print("Stop-hook tests still failing (not blocking twice):\n" + "\n\n".join(failures), file=sys.stderr)
        return 0
    print(json.dumps({"decision": "block", "reason":
        "Tests covering your uncommitted changes fail. Fix them (never by weakening or deleting a test) "
        "before finishing:\n\n" + "\n\n".join(failures)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
