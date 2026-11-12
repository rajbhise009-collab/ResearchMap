"""Daily health check (called by .github/workflows/daily-health.yml).

Runs tools/live-check.py and the quick production smoke checks against the
configured site (frontend/site.config.json siteUrl; NEXT_PUBLIC_SITE_URL
overrides it). Two kinds of failure, never mixed up:

- **site check failed** (the live check, or the smoke checks with a working
  browser): opens or updates ONE Issue ("Daily health check failing"); it
  closes when the checks pass again. Exit 1.
- **infrastructure: could not install test browser** (HEALTH_BROWSER_OK is not
  "true"; set by tools/ci/install_browser.py): the live check still runs (it needs no
  browser) and decides whether the site is up; the smoke checks are not run
  and never count as the site being down. On the first attempt of the day:
  no Issue, exit 0 with a warning, and infra=true in $GITHUB_OUTPUT so the
  workflow's retry slot (later the same day) runs again. On that retry
  (HEALTH_RETRY=true) a repeat opens ONE Issue of its own, labelled
  infrastructure. Exit 1.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "grow"))
sys.path.insert(0, str(ROOT / "tools"))
import issues  # noqa: E402
from run_weekly import redact  # noqa: E402
from site_url import site_url, vercel_host  # noqa: E402

TITLE = "Daily health check failing"
INFRA_TITLE = "Daily health: could not install test browser"
INFRA = "infrastructure: could not install test browser"
SITE = site_url()


def run(cmd: list[str]) -> tuple[bool, str]:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    return r.returncode == 0, redact((r.stdout + r.stderr).strip())


def _output(key: str, value: str) -> None:
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"{key}={value}\n")


def main() -> int:
    browser_ok = os.environ.get("HEALTH_BROWSER_OK", "true").lower() == "true"   # empty: the step crashed
    retry = os.environ.get("HEALTH_RETRY", "").lower() == "true"
    checks = [("live check", [sys.executable, "tools/live-check.py", SITE, "--vercel-host", vercel_host()])]
    if browser_ok:
        checks.append(("smoke checks", [sys.executable, "tools/qa/smoke.py", SITE, "--quick"]))
    res = [(name, *run(cmd)) for name, cmd in checks]
    for name, ok, out in res:
        print(f"{'PASS' if ok else 'FAIL'}: {name}\n{out[-3000:]}\n", flush=True)
    if not browser_ok:
        print(f"NOT RUN: smoke checks — {INFRA} (not a site failure)\n", flush=True)
    if not all(ok for _, ok, _ in res):
        body = [f"**site check failed** — the daily checks against {SITE} failed.", "",
                "If the site is down or broken: Vercel dashboard → the project → Deployments → the last good "
                "deployment → ⋯ → **Promote to Production** (one click; nothing is reverted automatically). "
                "This Issue closes itself on the first day the checks pass again.", ""]
        for name, ok, out in res:
            body += [f"## {'✅' if ok else '❌'} {name}", "", "```", out[-2500:], "```", ""]
        if not browser_ok:
            body += ["## ⚠️ smoke checks: not run", "", f"{INFRA}, so only the live check ran.", ""]
        print(f"issue: {issues.upsert(TITLE, redact(chr(10).join(body)), ['health', 'needs-action'])}")
        return 1
    if browser_ok:
        closed = issues.close(TITLE, f"All checks pass again on {SITE}. Closing.")
        print(f"issue: {closed or 'none open'}")
        closed = issues.close(INFRA_TITLE, "The test browser installed and every check ran. Closing.")
        print(f"infrastructure issue: {closed or 'none open'}")
        return 0
    # the live check passed; only the browser is missing (infrastructure)
    if not retry:
        _output("infra", "true")
        print(f"::warning title=Infrastructure::{INFRA}. The live check passed, so the site is up; the smoke "
              "checks could not run. The retry slot later today runs every check again; an Issue opens only "
              "if that fails the same way.")
        return 0
    body = [f"**{INFRA}** — this is not the site being down.", "",
            f"The live check against {SITE} passed on both of today's attempts, but the test browser "
            "(Chromium, for the smoke checks) could not be installed either time, so the smoke checks did "
            "not run. Usually a runner or network problem (for example, the package mirrors or the "
            "browser download were unreachable). Open the run's log for the install step's output; run "
            "**Daily health** again from the Actions tab to retry. This Issue closes itself on the first "
            "run where the browser installs and every check passes.", "",
            "## ✅ live check", "", "```", res[0][2][-2500:], "```", ""]
    print(f"issue: {issues.upsert(INFRA_TITLE, redact(chr(10).join(body)), ['health', 'infrastructure'])}")
    print(f"::error title=Infrastructure::{INFRA} on the retry too (the live check passed; not a site failure)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
