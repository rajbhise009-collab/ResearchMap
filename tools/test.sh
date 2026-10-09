#!/usr/bin/env bash
# The normal test command:  tools/test.sh   (or: make test)
#
#  1. the full suite in this checkout;
#  2. RUNNER MODE: the same suite the way the weekly workflow's runner sees
#     it — a fresh clone of HEAD plus your uncommitted changes (fresh file
#     order, no local caches, no ~/ResearchMap-private), CI=1, TZ=UTC, the
#     regenerate step first (dirty tree with new snapshots), then the
#     production build and the full tests. With CI=1 the safety tests may
#     not skip (backend/tests/conftest.py).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
echo "== 1/2 full tests (this checkout)"
"$PY" -m pytest "$ROOT/backend/tests" -q -p no:cacheprovider

TMP="$(mktemp -d "${TMPDIR:-/tmp}/rm-runner.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
echo "== 2/2 runner mode in $TMP"
git clone -q "$ROOT" "$TMP/repo"
( cd "$ROOT" && git diff HEAD --binary ) | ( cd "$TMP/repo" && git apply --allow-empty --whitespace=nowarn - )
# untracked (not ignored) files too, portably
( cd "$ROOT" && git ls-files -o --exclude-standard -z ) | "$PY" -c '
import shutil, sys, pathlib
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
for rel in filter(None, sys.stdin.buffer.read().decode().split("\0")):
    (dst / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / rel, dst / rel)
print("copied untracked:", sys.stdin is not None)' "$ROOT" "$TMP/repo"
test -f "$TMP/repo/tools/test.sh" || { echo "runner mode: untracked files not copied"; exit 1; }
ln -s "$ROOT/frontend/node_modules" "$TMP/repo/frontend/node_modules"
mkdir -p "$TMP/home"
cd "$TMP/repo"
export CI=1 TZ=UTC HOME="$TMP/home"
"$PY" -m backend.app.api.multi_library_export > "$TMP/regen.log" 2>&1
"$PY" -m backend.app.corpus.doc_numbers >> "$TMP/regen.log" 2>&1
"$PY" -m backend.app.api.multi_library_export >> "$TMP/regen.log" 2>&1
( cd frontend && npm run build > "$TMP/build.log" 2>&1 ) || { tail -30 "$TMP/build.log"; echo "runner mode: BUILD FAILED"; exit 1; }
# like the runner, a live job-summary file exists; the tests must not write it
export GITHUB_STEP_SUMMARY="$TMP/job-summary.md"
"$PY" -m pytest backend/tests -q -p no:cacheprovider
if [ -s "$GITHUB_STEP_SUMMARY" ]; then
  echo "runner mode: the tests wrote into the job summary:"; cat "$GITHUB_STEP_SUMMARY"; exit 1
fi
echo "== runner mode: OK"
