"""Install the test browser (Chromium) for the daily health and weekly grow
workflows, without depending on apt.

  python tools/ci/install_browser.py

The runner image already has Chromium's system libraries, so this installs
only the browser (`playwright install chromium`, no --with-deps): up to 3
attempts, each with a timeout, with backoff between them. A launch check
confirms it works; only if that check fails are the system dependencies
installed (`playwright install-deps chromium`, which uses apt), again with
retries. A browser restored from the cache (~/.cache/ms-playwright, keyed on
the Playwright version) that already launches is used as is.

Never fails its step: the result goes to $GITHUB_OUTPUT as ok=true|false, so
the checks that need no browser (the live check) still run. On failure it
prints one "infrastructure: could not install test browser" annotation.
Standard library only (daily health installs nothing but Playwright).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

INFRA = "infrastructure: could not install test browser"
ATTEMPTS = 3
BACKOFF_S = (15, 45)           # sleep after attempt 1, after attempt 2
INSTALL_TIMEOUT_S = 240
DEPS_TIMEOUT_S = 240
LAUNCH_TIMEOUT_S = 90       # worst case for everything: about 31 minutes

PW = [sys.executable, "-m", "playwright"]
LAUNCH = [sys.executable, "-c",
          "from playwright.sync_api import sync_playwright\n"
          "with sync_playwright() as p:\n"
          "    p.chromium.launch(headless=True).close()\n"]


def _run(cmd: list[str], timeout: int) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except OSError as e:
        return False, f"{type(e).__name__}: {e}"
    return r.returncode == 0, (r.stdout + r.stderr).strip()[-1500:]


def retry(what: str, cmd: list[str], timeout: int, *, run=_run, sleep=time.sleep) -> tuple[bool, str]:
    out = ""
    for attempt in range(1, ATTEMPTS + 1):
        ok, out = run(cmd, timeout)
        print(f"{what}: attempt {attempt}/{ATTEMPTS} {'ok' if ok else 'FAILED'}", flush=True)
        if ok:
            return True, out
        print(out, flush=True)
        if attempt < ATTEMPTS:
            sleep(BACKOFF_S[attempt - 1])
    return False, out


def install(*, run=_run, sleep=time.sleep) -> tuple[bool, str]:
    """(ok, why). Steps: a launch check (a cached browser is used as is);
    else install Chromium (retried); launch check; only if that fails,
    install the system dependencies (retried) and check once more."""
    if run(LAUNCH, LAUNCH_TIMEOUT_S)[0]:
        return True, "a cached browser launches"
    ok, out = retry("playwright install chromium", PW + ["install", "chromium"], INSTALL_TIMEOUT_S,
                    run=run, sleep=sleep)
    if not ok:
        return False, f"Chromium download failed {ATTEMPTS} times: {out[-300:]}"
    ok, out = run(LAUNCH, LAUNCH_TIMEOUT_S)
    if ok:
        return True, "installed Chromium; it launches"
    print(f"launch check failed, installing system dependencies:\n{out}", flush=True)
    ok, out = retry("playwright install-deps chromium", PW + ["install-deps", "chromium"], DEPS_TIMEOUT_S,
                    run=run, sleep=sleep)
    if not ok:
        return False, f"Chromium does not launch and its system dependencies failed to install: {out[-300:]}"
    ok, out = run(LAUNCH, LAUNCH_TIMEOUT_S)
    return (True, "installed Chromium and its system dependencies; it launches") if ok else \
        (False, f"Chromium does not launch even with its system dependencies: {out[-300:]}")


def main() -> int:
    ok, why = install()
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"ok={'true' if ok else 'false'}\n")
    if ok:
        print(f"test browser ready: {why}")
    else:
        why = " ".join(why.split())
        print(f"::error title=Infrastructure::{INFRA}: {why}. This is not a site failure; checks that need no browser still run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
