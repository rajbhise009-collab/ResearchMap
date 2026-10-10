"""Keepalive for scheduled workflows (called by .github/workflows/keepalive.yml).

If main's last commit is at least QUIET_DAYS old, write data/keepalive.json
and push one commit to main (judged by exit code and ls-remote). Otherwise
do nothing. No secrets, no API calls, nothing spent, the site unchanged.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUIET_DAYS = 40          # GitHub disables schedules at 60; this weekly check acts by day 47


def git(*a: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=check)


def quiet_days(now: dt.datetime | None = None) -> float:
    ts = int(git("log", "-1", "--format=%ct").stdout.strip())
    now = now or dt.datetime.now(dt.timezone.utc)
    return (now.timestamp() - ts) / 86400


def main() -> int:
    days = quiet_days()
    print(f"main's last commit: {days:.1f} days ago (threshold {QUIET_DAYS})")
    if days < QUIET_DAYS:
        print("recent activity: nothing to do")
        return 0
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    p = ROOT / "data" / "keepalive.json"
    p.write_text(json.dumps({"date": today, "why": "keeps the scheduled workflows enabled (60-day rule); "
                             "written by .github/workflows/keepalive.yml"}, indent=1) + "\n")
    git("add", str(p))
    git("-c", "user.name=researchmap-bot", "-c", "user.email=researchmap-bot@users.noreply.github.com",
        "commit", "-q", "-m", f"keepalive {today}: no commit for {days:.0f} days")
    r = git("push", "origin", "HEAD:main", check=False)
    local = git("rev-parse", "HEAD").stdout.strip()
    remote = (git("ls-remote", "origin", "refs/heads/main").stdout.split() or [""])[0]
    ok = r.returncode == 0 and remote == local
    print(f"heartbeat {'pushed' if ok else 'PUSH FAILED'} {local[:7]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
