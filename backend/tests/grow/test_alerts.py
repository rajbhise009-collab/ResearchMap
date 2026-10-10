"""ONE Issue per title: Daily health closes it on a passing day and never
opens a new one each failing day; the weekly failure step reports what the
run could not, and never overwrites the run's own report."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "grow"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / "grow" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_daily_health_one_issue_closed_on_pass_never_duplicated(monkeypatch, tmp_path):
    monkeypatch.setenv("GROW_ISSUE_DIR", str(tmp_path))
    h = _load("health")
    state = {"ok": False}
    monkeypatch.setattr(h, "run", lambda cmd: (state["ok"], "output"))
    assert h.main() == 1 and h.main() == 1                       # two failing days
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    it = json.loads(files[0].read_text())
    assert it["state"] == "open" and it["updates"] == 2 and it["title"] == h.TITLE
    state["ok"] = True
    assert h.main() == 0                                          # a passing day closes it
    assert json.loads(files[0].read_text())["state"] == "closed"
    assert h.main() == 0                                          # still passing: nothing to do
    state["ok"] = False
    assert h.main() == 1                                          # fails again: the SAME Issue reopens
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    it = json.loads(files[0].read_text())
    assert it["state"] == "open" and it["reopened"] == 1


def test_failure_step_reports_an_unreported_failure_once(monkeypatch, tmp_path):
    monkeypatch.setenv("GROW_ISSUE_DIR", str(tmp_path / "issues"))
    monkeypatch.setenv("GROW_ISSUE_MARKER", str(tmp_path / "marker"))
    monkeypatch.setenv("GROW_STEPS", json.dumps({"install": {"outcome": "failure"}, "grow": {"outcome": "skipped"}}))
    log = tmp_path / "install.log"
    log.write_text("\n".join(f"line {i}" for i in range(100)) + "\nERROR: pip failed\n")
    f = _load("on_failure")
    monkeypatch.setattr(sys, "argv", ["on_failure.py", str(log), str(tmp_path / "grow.log")])
    assert f.main() == 0
    files = list((tmp_path / "issues").glob("*.json"))
    assert len(files) == 1
    body = json.loads(files[0].read_text())["body"]
    assert "`install`" in body and "ERROR: pip failed" in body and "line 39" not in body and "line 41" in body
    assert "Nothing was spent" in body


def test_failure_step_never_overwrites_the_runs_own_report(monkeypatch, tmp_path):
    monkeypatch.setenv("GROW_ISSUE_DIR", str(tmp_path / "issues"))
    (tmp_path / "marker").write_text("Weekly grow — 2026-10-12")
    monkeypatch.setenv("GROW_ISSUE_MARKER", str(tmp_path / "marker"))
    monkeypatch.setenv("GROW_STEPS", json.dumps({"grow": {"outcome": "failure"}}))
    f = _load("on_failure")
    monkeypatch.setattr(sys, "argv", ["on_failure.py", "x", "y"])
    assert f.main() == 0
    assert not (tmp_path / "issues").exists()
