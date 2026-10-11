"""ci.yml: tests only — no secrets, read-only, pinned actions, never
pull_request_target; runs the ledger check, the build before the tests, both
test modes and the Playwright smoke."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_ci_is_safe_and_complete():
    text = WF.read_text()
    d = yaml.safe_load(text)
    on = d.get("on", d.get(True))
    assert "pull_request_target" not in on and set(on) <= {"push", "pull_request", "workflow_dispatch"}
    assert d["permissions"] == {"contents": "read"}
    assert "secrets." not in text
    for uses in re.findall(r"uses:\s*(\S+)", text):
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uses), uses
    steps = [s.get("name", "") for s in d["jobs"]["test"]["steps"]]
    for need in ("Ledger is append-only", "Typecheck", "Production build", "Full tests, normal and runner mode",
                 "Playwright smoke on the build"):
        assert any(n.startswith(need) for n in steps), need
    build = next(i for i, n in enumerate(steps) if n.startswith("Production build"))
    assert build < steps.index("Full tests, normal and runner mode")      # safety tests read the build
