"""Weekly growth: budget, redaction, candidate selection, workflow hygiene.
Offline; nothing here writes to data/ (the full flow is exercised by
tools/grow/e2e_mock.py in a throwaway clone)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import re
from pathlib import Path

import pytest
import yaml

from backend.app.grow import core

REPO = Path(__file__).resolve().parents[3]
WF = REPO / ".github" / "workflows"


def _load_run_weekly():
    spec = importlib.util.spec_from_file_location("run_weekly", REPO / "tools" / "grow" / "run_weekly.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_budget_counts_padded_commitments():
    b = core.Budget(25.0)
    assert b.fits(25.0) and not b.fits(25.01)
    b.commit("x", 10.0, 1.5)
    assert b.committed == 15.0 and b.remaining == 10.0
    assert not b.fits(10.5)


def test_redact_masks_secret_values_and_key_params(monkeypatch):
    rw = _load_run_weekly()
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFAKEFAKEFAKE1234")
    out = rw.redact("GET https://api.openalex.org/works?filter=x&api_key=abc123 failed; key AIzaFAKEFAKEFAKE1234")
    assert "abc123" not in out and "AIzaFAKEFAKEFAKE1234" not in out


def test_selection_drops_planted_duplicates_and_off_topic(monkeypatch):
    monkeypatch.setenv("GROW_DATE", "2026-10-12")
    from backend.app.grow.mocks import MockOpenAlex
    oa = MockOpenAlex()
    errs: list[str] = []
    ref = dt.date(2026, 10, 12)
    cands = core.find_candidates("diet-and-mortality", oa, ref=ref, errors=errs)
    recs = core.fetch_records(oa, [c["wid"] for c in cands])
    chosen, drops = core.select("diet-and-mortality", cands, recs, ref=ref)
    titles = [e["title"] for e, _r in chosen]
    assert not errs
    assert drops.get("already in library (id/DOI/title)", 0) >= 1     # DOI or title duplicate
    assert drops.get("duplicate among candidates", 0) == 1             # the twin
    assert drops.get("rubric: off-domain", 0) >= 1                     # the off-topic record
    assert not any("DOI duplicate" in t for t in titles)
    assert sum("twin candidate" in t for t in titles) <= 1
    assert all(e["added_by"] == "weekly-grow" and e["found_via"] in core.REASON_RANK for e, _ in chosen)


def test_llm_calibration_is_never_grown():
    assert "llm-calibration" not in core.grow_slugs()
    assert {"diet-and-mortality", "ml-fairness"} <= set(core.grow_slugs())


def test_zero_budget_submits_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("GROW_DATE", "2026-10-12")
    from backend.app.grow.mocks import mock_clients
    monkeypatch.setenv("GROW_MOCK_STATE", str(tmp_path))
    # independent of any batch a real weekly run left pending
    monkeypatch.setattr(core, "pending_path", lambda slug: tmp_path / f"{slug}-pending.json")
    cl = mock_clients()
    errs: list[str] = []
    prep = core.prepare("ml-fairness", cl, ref=dt.date(2026, 10, 12), errors=errs)
    picked = core.allocate({"ml-fairness": prep}, core.Budget(0.0), {"ml-fairness": 99})
    r = core.submit("ml-fairness", cl, core.Budget(0.0), picked["ml-fairness"], ref=dt.date(2026, 10, 12))
    assert r["submitted"] == 0 and r["projected_inr"] == 0
    if prep["items"]:
        assert prep["dropped"].get("over weekly budget", 0) == len(prep["items"])
    assert not core.pending_path("ml-fairness").exists()


# ---- workflow hygiene -----------------------------------------------------

def _wf(name):
    d = yaml.safe_load((WF / name).read_text())
    return d, d.get("on", d.get(True))


def test_only_the_two_new_workflows_run_on_a_schedule():
    names = {p.name for p in WF.glob("*.yml")}
    assert "weekly-refresh.yml" not in names
    assert {"weekly-grow.yml", "daily-health.yml"} <= names


def test_triggers_permissions_pins_and_secret_scope():
    for name, perms in (("weekly-grow.yml", {"contents": "write", "issues": "write"}),
                        ("daily-health.yml", {"contents": "read", "issues": "write"})):
        d, on = _wf(name)
        assert set(on) == {"schedule", "workflow_dispatch"}, name       # never pull_request
        assert d["permissions"] == perms, name
        text = (WF / name).read_text()
        for uses in re.findall(r"uses:\s*(\S+)", text):
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uses), uses
        for job in d["jobs"].values():
            for step in job["steps"]:
                blob = yaml.safe_dump(step)
                if "secrets." in blob:
                    assert step.get("name") == "Grow, gate, publish", (name, step.get("name"))
                assert "echo $" not in blob or "GITHUB_ENV" in blob
    d, on = _wf("weekly-grow.yml")
    assert not re.fullmatch(r"0 .*", on["schedule"][0]["cron"])      # off the hour


def test_round_robin_allocation_favours_open_candidates_then_low_coverage():
    def items(n, inr=1.0):
        return [{"entry": {"wid": f"W{i}"}, "inr": inr} for i in range(n)]
    prep = {"a": {"items": items(5), "dropped": {}}, "b": {"items": items(2), "dropped": {}},
            "c": {"items": items(5), "dropped": {}}}
    # budget 6.0 padded x1.5 => 4 papers; a and c tie on candidates, c has fewer papers
    picked = core.allocate(prep, core.Budget(6.0), {"a": 200, "b": 50, "c": 100})
    assert [len(picked[s]) for s in ("c", "a", "b")] == [2, 1, 1]
    assert prep["a"]["dropped"]["over weekly budget"] == 4


def test_transient_errors_retry_then_succeed():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("OpenAlex HTTP 503 on /works")
        return "ok"
    assert core.with_retry(flaky, base_s=0) == "ok" and calls["n"] == 3
    with pytest.raises(ValueError):
        core.with_retry(lambda: (_ for _ in ()).throw(ValueError("bad input")), base_s=0)


def test_manual_run_inputs_and_controls(monkeypatch):
    _d, on = _wf("weekly-grow.yml")
    inp = on["workflow_dispatch"]["inputs"]
    assert inp["run_budget_inr"]["default"] == "25"
    assert inp["build_queued"]["type"] == "boolean" and inp["build_queued"]["default"] is False
    rw = _load_run_weekly()
    monkeypatch.setenv("GROW_EVENT", "schedule")
    assert rw.run_controls() == (False, None, True)                  # scheduled: money rule, queued allowed
    monkeypatch.setenv("GROW_EVENT", "workflow_dispatch")
    monkeypatch.delenv("GROW_RUN_BUDGET_INR", raising=False)
    monkeypatch.delenv("GROW_BUILD_QUEUED", raising=False)
    assert rw.run_controls() == (True, 25.0, False)                  # manual defaults
    monkeypatch.setenv("GROW_RUN_BUDGET_INR", "40")
    monkeypatch.setenv("GROW_BUILD_QUEUED", "true")
    assert rw.run_controls() == (True, 40.0, True)


def test_preflight_failure_spends_nothing_and_names_the_failing_tests(monkeypatch):
    """B: if the fresh checkout fails its tests, no client is built, nothing
    is collected or submitted, and the Issue names the failing tests."""
    rw = _load_run_weekly()
    monkeypatch.setattr(rw, "guards", lambda: None)
    monkeypatch.setattr(rw, "paused", lambda: False)
    monkeypatch.delenv("GROW_GATES_ONLY", raising=False)
    monkeypatch.setattr(rw, "preflight_checks", lambda: [
        {"gate": "preflight: typecheck", "ok": True, "tail": "", "failed": []},
        {"gate": "preflight: full tests", "ok": False, "tail": "x\nFAILED backend/tests/a.py::test_b - boom",
         "failed": ["FAILED backend/tests/a.py::test_b"]}])
    posted = {}
    monkeypatch.setattr(rw.issues, "upsert", lambda title, body, labels: posted.update(body=body, labels=labels))
    import backend.app.grow.clients as C
    monkeypatch.setattr(C, "make_clients", lambda: (_ for _ in ()).throw(AssertionError("clients built")))
    import backend.app.grow.core as core_mod
    for fn in ("collect", "submit", "prepare", "followon"):
        monkeypatch.setattr(core_mod, fn, lambda *a, **k: (_ for _ in ()).throw(AssertionError(f"{fn} called")))
    assert rw.main() == 3
    assert "test_b" in posted["body"] and "nothing spent" in posted["body"] and "needs-action" in posted["labels"]


def test_rerun_with_pending_batches_collects_and_never_resubmits(monkeypatch, tmp_path):
    """D.3: while a library has a pending batch, prepare() returns nothing to
    submit for it, and its pending papers are never candidates again."""
    import json as _json
    pend = tmp_path / "ml-fairness-pending.json"
    pend.write_text(_json.dumps({"entries": [{"wid": "W1"}], "batch_id": "b"}))
    monkeypatch.setattr(core, "pending_path", lambda slug: pend if slug == "ml-fairness" else tmp_path / "none.json")
    monkeypatch.setenv("GROW_DATE", "2026-10-12")
    from backend.app.grow.mocks import mock_clients
    monkeypatch.setenv("GROW_MOCK_STATE", str(tmp_path / "state"))
    cl = mock_clients()
    r = core.prepare("ml-fairness", cl, ref=dt.date(2026, 10, 12), errors=[])
    assert r["items"] == [] and "not collected" in r["note"]
    # and a library without a pending batch still gets candidates, none of them pending papers
    r2 = core.prepare("diet-and-mortality", cl, ref=dt.date(2026, 10, 12), errors=[])
    assert all(it["entry"]["wid"] != "W1" for it in r2["items"])


def test_pending_commitments_count_once(monkeypatch, tmp_path):
    """D.4: submitted-not-billed batches reduce available money and the
    weekly budget, and are excluded once billed (ledger_recorded)."""
    from backend.app.extraction import money
    d = tmp_path / "data" / "domains" / "x" / "grow"
    d.mkdir(parents=True)
    (d / "pending.json").write_text('{"projected_inr": 10.0, "ledger_recorded": false, "entries": [1, 2]}')
    monkeypatch.setattr(money, "_REPO_ROOT", tmp_path)
    assert money.pending_inr() == 10.0
    (d / "pending.json").write_text('{"projected_inr": 10.0, "ledger_recorded": true}')
    assert money.pending_inr() == 0.0


def test_gates_only_spends_nothing_and_publishes_nothing(monkeypatch, capsys):
    """F: gates_only runs preflight and every gate, reports pass/fail per
    gate, and never builds a client, collects, submits, publishes or files
    an Issue — even while growth is paused."""
    rw = _load_run_weekly()
    monkeypatch.setenv("GROW_GATES_ONLY", "true")
    monkeypatch.setattr(rw, "paused", lambda: True)
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called"))  # noqa: E731
    for name in ("guards", "publish_bookkeeping", "publish_branch", "regenerate", "_reset_rest"):
        if hasattr(rw, name):
            monkeypatch.setattr(rw, name, boom if name != "_reset_rest" else (lambda: None))
    monkeypatch.setattr(rw.issues, "upsert", boom)
    import backend.app.grow.clients as C
    import backend.app.grow.core as core_mod
    monkeypatch.setattr(C, "make_clients", boom)
    for fn in ("collect", "submit", "prepare", "followon"):
        monkeypatch.setattr(core_mod, fn, boom)
    ok = {"ok": True, "tail": "", "failed": []}
    monkeypatch.setattr(rw, "preflight_checks", lambda: [dict(ok, gate="preflight: full tests")])
    monkeypatch.setattr(rw, "gates", lambda **k: [dict(ok, gate="docs check"),
                                                  {"gate": "smoke", "ok": False, "tail": "boom",
                                                   "failed": ["[FAIL] smoke x"]}])
    assert rw.main() == 1
    out = capsys.readouterr().out
    assert "| docs check | PASS |" in out and "| smoke | FAIL |" in out and "GATE FAILURES" in out


def _gates_only_run(monkeypatch, tmp_path, pre, res):
    """Run gates_only with fake gate results; return (exit code, job summary)."""
    rw = _load_run_weekly()
    monkeypatch.setenv("GROW_GATES_ONLY", "true")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(rw, "_reset_rest", lambda: None)
    monkeypatch.setattr(rw, "preflight_checks", lambda: pre)
    monkeypatch.setattr(rw, "gates", lambda **k: res)
    rc = rw.main()
    return rc, summary.read_text()


def _row(name, ok, note=None):
    r = {"gate": name, "ok": ok, "tail": "" if ok else "boom", "failed": [] if ok else [f"[FAIL] {name}"]}
    if note:
        r["note"] = note
    return r


_PRE = [_row("preflight: typecheck", True), _row("preflight: production build", True),
        _row("preflight: full tests", True)]
_RESTATED = [_row(n, True, note="passed in preflight") for n in ("typecheck", "production build", "full tests")]
_LATER = ["docs check", "consistency script", "banned-phrase tests", "search regression suite",
          "hardening tests", "browser hunt", "smoke checks on the build"]


def test_gates_only_exits_nonzero_if_any_row_fails(monkeypatch, tmp_path):
    """Every row in the table counts: one failing gate anywhere -> exit 1,
    and that FAIL is in the one table the run writes."""
    for bad in range(len(_LATER)):
        res = _RESTATED + [_row(n, i != bad) for i, n in enumerate(_LATER)]
        (tmp_path / str(bad)).mkdir()
        rc, summ = _gates_only_run(monkeypatch, tmp_path / str(bad), _PRE, res)
        assert rc == 1, _LATER[bad]
        assert f"| {_LATER[bad]} | FAIL |" in summ and "1 FAILED" in summ
    # a failing preflight row also fails the run (later gates not run)
    (tmp_path / "pre").mkdir()
    rc, summ = _gates_only_run(monkeypatch, tmp_path / "pre",
                               [_row("preflight: typecheck", True), _row("preflight: full tests", False)], None)
    assert rc == 1 and "| preflight: full tests | FAIL |" in summ


def test_gates_only_writes_one_table_with_every_gate_once(monkeypatch, tmp_path):
    """All pass -> exit 0, and the job summary is ONE table: 3 preflight
    rows + 7 later gates, each exactly once."""
    rc, summ = _gates_only_run(monkeypatch, tmp_path, _PRE, _RESTATED + [_row(n, True) for n in _LATER])
    assert rc == 0
    assert summ.count("| gate | result |") == 1 and summ.count("## Weekly grow") == 1
    rows = [ln for ln in summ.splitlines() if ln.startswith("| ") and not ln.startswith("| gate")]
    assert len(rows) == 10 and all(ln.endswith("| PASS |") for ln in rows)
    assert len({ln.split("|")[1] for ln in rows}) == 10       # no gate listed twice


def test_tests_never_see_the_workflow_output_files():
    """The fixture in conftest strips GITHUB_STEP_SUMMARY & co, so no test
    can write into a live job's summary (the cause of a fake 'smoke: FAIL'
    row in gates_only run #3)."""
    import os
    for k in ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_PATH", "GITHUB_STATE"):
        assert k not in os.environ, k
