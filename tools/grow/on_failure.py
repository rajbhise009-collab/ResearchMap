"""The weekly workflow's last step on failure or cancellation (called by
.github/workflows/weekly-grow.yml). Spends nothing and changes no file.

If the run already wrote its own Issue (GROW_ISSUE_MARKER exists) — a gate
or preflight failure, a clean stop — that report stands and nothing is done.
Otherwise (install failed, crash, timeout, cancellation) it opens or updates
the run's ONE Issue ("Weekly grow — <date>") with the failing step names and
the last 60 lines of output, and says whether anything could have been spent.

  python tools/grow/on_failure.py <install.log> <grow.log>
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import issues  # noqa: E402
from run_weekly import redact  # noqa: E402

TAIL = 60


def tail(path: str, n: int = TAIL) -> str:
    p = Path(path)
    if not p.exists():
        return "(no output was captured)"
    return "\n".join(p.read_text(errors="replace").splitlines()[-n:])


def body(steps: dict, logs: list[str], run_url: str) -> tuple[str, list[str]]:
    failed = [k for k, v in steps.items() if v.get("outcome") in ("failure", "cancelled")]
    grow_ran = steps.get("grow", {}).get("outcome") not in (None, "skipped")
    money = ("Nothing was spent: the run stopped before the growth step started."
             if not grow_ran else
             "The growth step had started. Anything it paid for was pushed to main right after each paid "
             "step (checkpoints), so the next run collects it and pays nothing twice. The site was not changed "
             "unless every publish gate had passed.")
    L = ["**Status:** the weekly run failed and could not report for itself", "",
         f"- failing step(s): {', '.join(f'`{f}`' for f in failed) or '(cancelled or timed out)'}",
         f"- run: {run_url}", f"- {money}", "",
         "## What to do", "",
         "Open the run link above for the full log. Most failures are transient (a runner or network "
         "problem): run **Weekly grow** again from the Actions tab with **gates_only** ticked first (zero "
         "spend) to confirm the checks pass. The next scheduled run also retries on its own.", ""]
    for f in failed:
        log = logs[0] if f == "install" else logs[1]
        L += [f"## `{f}`: last {TAIL} lines", "", "```", redact(tail(log)), "```", ""]
    return "\n".join(L), failed


def main() -> int:
    marker = os.environ.get("GROW_ISSUE_MARKER")
    if marker and Path(marker).exists():
        print(f"the run already reported in its Issue ({Path(marker).read_text()}); nothing to add")
        return 0
    steps = json.loads(os.environ.get("GROW_STEPS") or "{}")
    text, failed = body(steps, sys.argv[1:3] + [""] * (2 - len(sys.argv[1:3])), os.environ.get("GROW_RUN_URL", ""))
    title = f"Weekly grow — {dt.datetime.now(dt.timezone.utc).date().isoformat()}"
    print(f"issue: {issues.upsert(title, text, ['weekly-grow', 'needs-action'])}")
    print(f"failing steps: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
