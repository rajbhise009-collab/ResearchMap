"""The spend ledger is append-only, in code (SpendLedger) and in CI
(tools/ci/check_ledger.py)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.extraction.ledger_rules import LedgerAppendOnlyError, append_only_violation

REPO = Path(__file__).resolve().parents[3]
from backend.app.extraction.spend_ledger import FX_USD_TO_INR  # noqa: E402

# built like real entries: cost_inr = cost_usd x the ledger's exchange rate
E1 = {"ts": 1, "stage": "s", "cost_usd": 0.01, "cost_inr": 0.01 * FX_USD_TO_INR}
E2 = {"ts": 2, "stage": "s", "cost_usd": 0.02, "cost_inr": 0.02 * FX_USD_TO_INR}


def _led(*entries):
    return {"cumulative_inr": sum(e["cost_inr"] for e in entries), "entries": list(entries)}


def test_rule():
    assert append_only_violation(_led(E1), _led(E1, E2)) is None
    assert append_only_violation(None, _led(E1)) is None
    assert "shrank" in append_only_violation(_led(E1, E2), _led(E1))
    assert "changed" in append_only_violation(_led(E1, E2), _led(dict(E1, cost_inr=0.5), E2))
    assert "changed" in append_only_violation(_led(E1, E2), _led(E2, E1))
    bad = _led(E1, E2)
    bad["cumulative_inr"] = 99.0
    assert "sum of entries" in append_only_violation(_led(E1), bad)


def test_spend_ledger_refuses_to_rewrite_history(tmp_path):
    from backend.app.extraction.spend_ledger import SpendLedger
    p = tmp_path / "ledger.json"
    led = SpendLedger(path=p)
    state = led._read()
    state.entries.append(dict(E1))
    led._write(state)                                   # appending is fine
    state = led._read()
    state.entries[0]["cost_inr"] = 0.0                  # editing a recorded entry is not
    with pytest.raises(LedgerAppendOnlyError):
        led._write(state)
    state = led._read()
    state.entries.clear()                               # nor is dropping entries
    with pytest.raises(LedgerAppendOnlyError):
        led._write(state)
    assert json.loads(p.read_text())["entries"][0] == E1


def test_ci_check_passes_on_the_whole_real_history():
    roots = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=REPO,
                           capture_output=True, text=True).stdout.split()
    if not roots:
        pytest.skip("no git history in this checkout (shallow clone)")
    r = subprocess.run([sys.executable, "tools/ci/check_ledger.py", roots[-1], "HEAD"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ci_check_catches_a_rewritten_entry(tmp_path):
    """A throwaway repo whose second commit edits a recorded entry."""
    w = tmp_path / "w"
    (w / "data").mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", *a], cwd=w, capture_output=True, text=True, check=True).stdout.strip()
    run("init", "-q", "-b", "main")
    run("config", "user.name", "t")
    run("config", "user.email", "t@example.invalid")
    led = w / "data" / "spend_ledger.json"
    led.write_text(json.dumps(_led(E1)))
    run("add", "-A")
    run("commit", "-qm", "one")
    base = run("rev-parse", "HEAD")
    led.write_text(json.dumps(_led(dict(E1, cost_inr=0.0))))
    run("commit", "-qam", "rewrite")
    tools = w / "tools" / "ci"
    tools.mkdir(parents=True)
    (tools / "check_ledger.py").write_text((REPO / "tools" / "ci" / "check_ledger.py").read_text().replace(
        "sys.path.insert(0, str(ROOT))", f"sys.path.insert(0, {str(REPO)!r})"))
    r = subprocess.run([sys.executable, str(tools / "check_ledger.py"), base, "HEAD"], cwd=w,
                       capture_output=True, text=True)
    assert r.returncode == 1 and "NOT APPEND-ONLY" in r.stdout
