#!/usr/bin/env python3
"""PreToolUse guard for ~/ResearchMap-private (wired in .claude/settings.local.json,
which is personal and not committed).

Existing files there are frozen; NEW files may be created. Denies an Edit /
Write / MultiEdit / NotebookEdit of a file that already exists there, and a
Bash command that writes, moves or deletes an existing path there.
Standard library only; `decide(event, home)` is importable for tests.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

WRITE_OPS = re.compile(r"(?:^|[\s;&|(])(?:rm|mv|cp|tee|truncate|dd|touch|chmod)\s|sed\s+(?:-\S*\s+)*-i|"
                       r"(?<![<>&0-9])>{1,2}\s*(?!/dev/null)[^\s&]|open\([^)]*['\"][wa]|write_text|write_bytes")


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _unquoted(cmd: str, home: str) -> str:
    """Drop quoted text the shell would not turn into a real path there: a
    commit message or an echo that merely MENTIONS ~/ResearchMap-private is
    not a write to it. Single quotes never expand; double quotes are kept
    only if they hold $HOME or the absolute home path (`~` is not expanded
    inside quotes)."""
    cmd = re.sub(r"'[^']*'", "''", cmd)
    return re.sub(r'"((?:[^"\\]|\\.)*)"',
                  lambda m: m.group(0) if ("$HOME" in m.group(1) or home in m.group(1)) else '""', cmd)


def decide(event: dict, home: str | None = None) -> dict | None:
    home = home or os.path.expanduser("~")
    private = Path(home) / "ResearchMap-private"
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        raw = ti.get("file_path") or ti.get("notebook_path") or ""
        p = Path(os.path.expanduser(raw))
        try:
            p.resolve().relative_to(private.resolve())
        except (ValueError, OSError):
            return None
        if p.exists():
            return _deny(f"{p}: existing files in ~/ResearchMap-private are frozen (new files are allowed).")
        return None
    if tool == "Bash":
        cmd = _unquoted(ti.get("command") or "", home)
        if not WRITE_OPS.search(cmd):
            return None
        for tok in re.findall(r"(?:~|\$HOME|" + re.escape(home) + r")/ResearchMap-private[^\s'\";|&)]*", cmd):
            path = Path(tok.replace("$HOME", home).replace("~", home, 1))
            if path.exists() and (path.is_file() or any(path.iterdir())):
                return _deny(f"{tok}: existing files in ~/ResearchMap-private are frozen (new files are allowed).")
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    out = decide(event)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
