"""Daily health check (called by .github/workflows/daily-health.yml).

Runs tools/live-check.py and the quick production smoke checks against
NEXT_PUBLIC_SITE_URL (fallback https://researchmap-one.vercel.app). On
failure it opens or updates ONE Issue ("Daily health check failing"); when
the checks pass again it closes that Issue. Exit 1 on failure.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "grow"))
import issues  # noqa: E402
from run_weekly import redact  # noqa: E402

TITLE = "Daily health check failing"
SITE = (os.environ.get("NEXT_PUBLIC_SITE_URL") or "https://researchmap-one.vercel.app").rstrip("/")


def run(cmd: list[str]) -> tuple[bool, str]:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    return r.returncode == 0, redact((r.stdout + r.stderr).strip())


def main() -> int:
    checks = [("live check", [sys.executable, "tools/live-check.py", SITE]),
              ("smoke checks", [sys.executable, "tools/qa/smoke.py", SITE, "--quick"])]
    res = [(name, *run(cmd)) for name, cmd in checks]
    for name, ok, out in res:
        print(f"{'PASS' if ok else 'FAIL'}: {name}\n{out[-3000:]}\n", flush=True)
    if all(ok for _, ok, _ in res):
        closed = issues.close(TITLE, f"All checks pass again on {SITE}. Closing.")
        print(f"issue: {closed or 'none open'}")
        return 0
    body = [f"The daily checks against {SITE} failed.", "",
            "If the site is down or broken: Vercel dashboard → the project → Deployments → the last good "
            "deployment → ⋯ → **Promote to Production** (one click; nothing is reverted automatically). "
            "This Issue closes itself on the first day the checks pass again.", ""]
    for name, ok, out in res:
        body += [f"## {'✅' if ok else '❌'} {name}", "", "```", out[-2500:], "```", ""]
    print(f"issue: {issues.upsert(TITLE, redact(chr(10).join(body)), ['health', 'needs-action'])}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
