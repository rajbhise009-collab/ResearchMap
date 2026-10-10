"""A failed run's paid data is never stranded on its grow/<date> branch, and
the zero-spend republish mode publishes it only when every gate passes.
All git work here happens in a throwaway repository, never the real one."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def _rw():
    spec = importlib.util.spec_from_file_location("rw_republish", REPO / "tools" / "grow" / "run_weekly.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """origin (bare) + a clone with main; data/spend_ledger.json and a
    pending file; returns (rw bound to the clone, clone path)."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    for k, v in (("user.name", "t"), ("user.email", "t@example.invalid")):
        _git(work, "config", k, v)
    (work / "data" / "grow").mkdir(parents=True)
    (work / "data" / "spend_ledger.json").write_text('{"cumulative_inr": 1.0}')
    (work / "data" / "pending.json").write_text('{"batch": "a"}')
    (work / "site.txt").write_text("site v1")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base")
    _git(work, "push", "-q", "origin", "HEAD:main")
    rw = _rw()
    monkeypatch.setattr(rw, "ROOT", work)
    return rw, work


def _branch(work, name, files):
    _git(work, "checkout", "-q", "-b", name)
    for f, txt in files.items():
        (work / f).write_text(txt)
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", name)
    _git(work, "push", "-q", "origin", name)
    _git(work, "checkout", "-q", "main")


def test_branch_whose_data_is_on_main(world):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"site.txt": "site v2"})            # site only
    assert rw.branch_data_state("grow/2026-10-10")[0] == "on_main"


def test_branch_with_data_only_on_it_is_recoverable(world):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"data/pending.json": '{"batch": "b"}'})
    state, files = rw.branch_data_state("grow/2026-10-10")
    assert state == "recoverable" and files == ["data/pending.json"]


def test_branch_and_main_both_changed_the_same_data_is_stranded(world):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"data/pending.json": '{"batch": "b"}'})
    (work / "data" / "pending.json").write_text('{"batch": "c"}')
    _git(work, "commit", "-qam", "main moved")
    assert rw.branch_data_state("grow/2026-10-10")[0] == "stranded"


def _patch_publish(rw, monkeypatch, gates_ok=True):
    calls = {}
    monkeypatch.setattr(rw, "regenerate", lambda: (rw.ROOT / "site.txt").write_text("site regenerated"))
    monkeypatch.setattr(rw, "items_snapshot", lambda: {})
    monkeypatch.setattr(rw, "changelog", lambda d, lines: calls.setdefault("changelog", lines))
    monkeypatch.setattr(rw, "fingerprint", lambda *a, **k: None)
    monkeypatch.setattr(rw, "ledger_inr", lambda: (1.0, 0.0))
    monkeypatch.setattr(rw, "gates", lambda **k: [{"gate": "full tests", "ok": gates_ok, "tail": "x",
                                                   "failed": [] if gates_ok else ["FAILED t"]}])
    monkeypatch.setattr(rw, "publish_main", lambda d: calls.setdefault("published", "abc1234def"))
    monkeypatch.setattr(rw, "_reset_rest", lambda: calls.setdefault("reset", True))
    monkeypatch.setattr(rw.issues, "upsert", lambda t, b, l: calls.setdefault("issue", (t, b, l)))
    monkeypatch.setattr(rw.issues, "close", lambda t, c: calls.setdefault("closed", t))
    return calls


def test_republish_publishes_only_when_every_gate_passes(world, monkeypatch):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"site.txt": "site v2"})
    calls = _patch_publish(rw, monkeypatch, gates_ok=True)
    led = (work / "data" / "spend_ledger.json").read_bytes()
    assert rw.republish("grow/2026-10-10", "2026-10-11") == 0
    assert calls["published"] and calls["closed"] == "Weekly grow — 2026-10-10"
    reg = json.loads((work / "data" / "grow" / "resolved_branches.json").read_text())
    assert "grow/2026-10-10" in reg["resolved"]
    assert (work / "data" / "spend_ledger.json").read_bytes() == led                # nothing spent
    assert _git(work, "ls-remote", "--heads", "origin", "grow/2026-10-10")         # branch kept


def test_republish_does_not_publish_when_a_gate_fails(world, monkeypatch):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"site.txt": "site v2"})
    calls = _patch_publish(rw, monkeypatch, gates_ok=False)
    assert rw.republish("grow/2026-10-10", "2026-10-11") == 1
    assert "published" not in calls and calls["reset"] and "needs-action" in calls["issue"][2]


def test_republish_refuses_stranded_data_and_non_grow_branches(world, monkeypatch):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"data/pending.json": '{"batch": "b"}'})
    (work / "data" / "pending.json").write_text('{"batch": "c"}')
    _git(work, "commit", "-qam", "main moved")
    calls = _patch_publish(rw, monkeypatch)
    assert rw.republish("grow/2026-10-10", "2026-10-11") == 2 and "published" not in calls
    assert rw.republish("main", "2026-10-11") == 2


def test_republish_brings_recoverable_data_to_main(world, monkeypatch):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"data/pending.json": '{"batch": "b"}', "site.txt": "site v2"})
    _patch_publish(rw, monkeypatch, gates_ok=True)
    assert rw.republish("grow/2026-10-10", "2026-10-11") == 0
    assert json.loads((work / "data" / "pending.json").read_text()) == {"batch": "b"}


def test_a_branch_whose_data_is_on_main_does_not_hold_the_next_run(world, monkeypatch):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"site.txt": "site v2"})
    rw._ON_MAIN_BRANCHES.clear()
    assert rw.guards() is None and rw._ON_MAIN_BRANCHES == ["grow/2026-10-10"]


def test_a_branch_with_conflicting_data_holds_new_spending(world, monkeypatch):
    rw, work = world
    _branch(work, "grow/2026-10-10", {"data/pending.json": '{"batch": "b"}'})
    (work / "data" / "pending.json").write_text('{"batch": "c"}')
    _git(work, "commit", "-qam", "main moved")
    hold = rw.guards()
    assert hold and "grow/2026-10-10" in hold


def test_workflow_republish_input_gets_no_api_keys():
    import yaml
    text = (REPO / ".github" / "workflows" / "weekly-grow.yml").read_text()
    d = yaml.safe_load(text)
    assert "republish_branch" in d[True]["workflow_dispatch"]["inputs"]
    assert text.count("!inputs.republish_branch && secrets.") == 2
