#!/usr/bin/env python3
"""CI / pre-push: the spend ledger stayed append-only across a range of commits.

  python tools/ci/check_ledger.py <base-sha> <head-sha>
  python tools/ci/check_ledger.py --worktree        (HEAD vs the working tree)

Every commit in base..head that touched data/spend_ledger.json is compared
with the version before it (backend/app/extraction/ledger_rules.py): old
entries kept exactly and in order, new ones only appended, the total equal
to the sum. A missing or all-zero base (new branch) checks the head alone.
Exit 1 with the offending commit on any violation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.extraction.ledger_rules import append_only_violation  # noqa: E402

LEDGER = "data/spend_ledger.json"


def _git(*a: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=check)


def at(rev: str) -> dict | None:
    r = _git("show", f"{rev}:{LEDGER}")
    return json.loads(r.stdout) if r.returncode == 0 else None


def check_range(base: str | None, head: str) -> list[str]:
    errors = []
    if not base or set(base) == {"0"} or _git("cat-file", "-e", f"{base}^{{commit}}").returncode:
        new = at(head)
        why = append_only_violation(None, new) if new else None
        return [f"{head[:7]}: {why}"] if why else []
    revs = _git("rev-list", "--reverse", "--first-parent", f"{base}..{head}", "--", LEDGER).stdout.split()
    prev_rev, prev = base, at(base)
    for rev in revs:
        cur = at(rev)
        if cur is None:
            errors.append(f"{rev[:7]}: {LEDGER} was deleted")
            continue
        why = append_only_violation(prev, cur)
        if why:
            errors.append(f"{rev[:7]} (vs {prev_rev[:7]}): {why}")
        prev_rev, prev = rev, cur
    return errors


def main(argv: list[str]) -> int:
    if argv[1:2] == ["--worktree"]:
        p = ROOT / LEDGER
        why = append_only_violation(at("HEAD"), json.loads(p.read_text())) if p.exists() else "ledger missing"
        errors = [f"working tree: {why}"] if why else []
    elif len(argv) == 3:
        errors = check_range(argv[1], argv[2])
    else:
        print(__doc__)
        return 2
    if errors:
        print("LEDGER NOT APPEND-ONLY:\n  " + "\n  ".join(errors))
        return 1
    print("ledger append-only: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
