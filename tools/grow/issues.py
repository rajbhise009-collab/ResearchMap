"""Open, update or close ONE GitHub Issue by exact title, via the gh CLI.
GROW_ISSUE_DIR (tests) writes issues as files instead of calling GitHub."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _dir() -> Path | None:
    d = os.environ.get("GROW_ISSUE_DIR")
    return Path(d) if d else None


def _fname(title: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in title).strip("-")[:90] + ".json"


def _gh(*args: str, stdin: str | None = None) -> str:
    r = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {args[0]} {args[1] if len(args) > 1 else ''} failed: {r.stderr.strip()[:200]}")
    return r.stdout


def _find(title: str, state: str = "open") -> int | None:
    out = _gh("issue", "list", "--state", state, "--search", f'"{title}" in:title',
              "--json", "number,title", "--limit", "50")
    for it in json.loads(out or "[]"):
        if it["title"] == title:
            return it["number"]
    return None


def upsert(title: str, body: str, labels: list[str]) -> str:
    d = _dir()
    if d:
        d.mkdir(parents=True, exist_ok=True)
        p = d / _fname(title)
        prev = json.loads(p.read_text()) if p.exists() else {"updates": 0, "reopened": 0}
        p.write_text(json.dumps({"title": title, "body": body, "labels": labels, "state": "open",
                                 "updates": prev["updates"] + 1,
                                 "reopened": prev.get("reopened", 0) + (prev.get("state") == "closed")},
                                indent=1))
        return str(p)
    for lab in labels:   # create missing labels quietly
        subprocess.run(["gh", "label", "create", lab, "--force"], capture_output=True, text=True)
    n = _find(title)
    if n is None:
        # ONE Issue per title, ever: a closed one is reopened, not duplicated
        n = _find(title, state="closed")
        if n is not None:
            _gh("issue", "reopen", str(n))
    if n is None:
        return _gh("issue", "create", "--title", title, "--body-file", "-",
                   *sum((["--label", lab] for lab in labels), []), stdin=body).strip()
    _gh("issue", "edit", str(n), "--body-file", "-", *sum((["--add-label", lab] for lab in labels), []),
        stdin=body)
    return f"#{n} (updated)"


def close(title: str, comment: str) -> str | None:
    d = _dir()
    if d:
        p = d / _fname(title)
        if not p.exists():
            return None
        it = json.loads(p.read_text())
        if it["state"] == "closed":
            return None
        it.update(state="closed", closing_comment=comment)
        p.write_text(json.dumps(it, indent=1))
        return str(p)
    n = _find(title)
    if n is None:
        return None
    _gh("issue", "close", str(n), "--comment", comment)
    return f"#{n} (closed)"
