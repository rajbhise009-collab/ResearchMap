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
    assert {"weekly-grow.yml", "daily-health.yml", "keepalive.yml"} <= names


def test_triggers_permissions_pins_and_secret_scope():
    for name, perms in (("weekly-grow.yml", {"contents": "write", "issues": "write"}),
                        ("daily-health.yml", {"contents": "read", "issues": "write"}),
                        ("keepalive.yml", {"contents": "write"})):
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
    monkeypatch.setenv("GROW_EVENT", "workflow_dispatch")
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
    monkeypatch.setenv("GROW_EVENT", "workflow_dispatch")
    # any fall-through to the live path must fail loudly, never run
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("live path reached"))  # noqa: E731
    import backend.app.grow.clients as C
    import backend.app.grow.core as core_mod
    monkeypatch.setattr(C, "make_clients", boom)
    for fn in ("collect", "submit", "prepare", "followon"):
        monkeypatch.setattr(core_mod, fn, boom)
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


def _snap(**items):
    return {k.replace("_", "-"): {"headline": f"h {k}", "verdict": v, "kind": "x"} for k, v in items.items()}


def test_every_removed_result_has_a_reason_and_counts_add_up(monkeypatch, tmp_path):
    """A result never disappears silently: each one that leaves carries the
    rule that removed it; shown counts before/after match the arithmetic;
    set-aside items that drop are not reported as 'no longer shown'."""
    rw = _load_run_weekly()
    monkeypatch.setattr(rw, "ROOT", tmp_path)
    d = tmp_path / "data" / "domains" / "lib" / "reasoning"
    d.mkdir(parents=True)
    (d / "fw_addressals.jsonl").write_text(
        '{"future_work_id": "openalex:W1:f1", "to_paper_id": "openalex:W9", "label": "partial"}\n'
        '{"future_work_id": "openalex:W2:f1", "to_paper_id": "openalex:W9", "label": "not_addressed"}\n')
    before = {"lib": {"opp-lib-orphan-openalex-w1-f1": {"headline": "answered", "verdict": None, "kind": "o"},
                      "opp-lib-orphan-openalex-w3-f1": {"headline": "kept", "verdict": None, "kind": "o"},
                      "opp-lib-hole-w4-w5": {"headline": "hole", "verdict": "set_aside", "kind": "m"}}}
    after = {"lib": {"opp-lib-orphan-openalex-w3-f1": {"headline": "kept", "verdict": None, "kind": "o"},
                     "opp-lib-orphan-openalex-w6-f2": {"headline": "new", "verdict": None, "kind": "o"}}}
    x = rw.diff_items(before, after)["lib"]
    assert (x["shown_before"], x["shown_after"]) == (2, 2)
    assert x["shown_before"] + len(x["new_results"]) - len(x["removed_shown"]) == x["shown_after"]
    assert [r["id"] for r in x["removed_shown"]] == ["opp-lib-orphan-openalex-w1-f1"]
    assert "W9" in x["removed_shown"][0]["reason"] and "partial" in x["removed_shown"][0]["reason"]
    assert [r["id"] for r in x["removed_not_shown"]] == ["opp-lib-hole-w4-w5"]
    assert "clusters" in x["removed_not_shown"][0]["reason"]
    lines = "\n".join(rw.diff_lines({"lib": x}))
    assert "results shown 2 -> 2 (+1 new, -1 no longer shown)" in lines
    assert "never shown" in lines and rw.unexplained({"lib": x}) == []


def test_a_result_leaving_without_a_recorded_reason_is_flagged(monkeypatch, tmp_path):
    """An open question whose removal no addressal explains (and any kind no
    rule covers) is UNEXPLAINED: listed in the Issue and marks needs-action."""
    rw = _load_run_weekly()
    monkeypatch.setattr(rw, "ROOT", tmp_path)
    before = {"lib": {"opp-lib-orphan-openalex-w1-f1": {"headline": "a", "verdict": None, "kind": "o"},
                      "opp-contra-lib-01-x-y": {"headline": "b", "verdict": "genuine", "kind": "d"}}}
    diff = rw.diff_items(before, {"lib": {}})
    assert sorted(rw.unexplained(diff)) == ["opp-contra-lib-01-x-y", "opp-lib-orphan-openalex-w1-f1"]
    body = rw.issue_body("2026-10-12", "published", p1=[], p2=[], diff=diff, spent=0.0, ledger=(0.0, 0.0),
                         budget=rw_budget(), gate_res=None)
    assert "without a recorded reason" in body and "opp-lib-orphan-openalex-w1-f1" in body


def test_run5_accounting_replays_with_a_reason_for_every_change():
    """Replays weekly-grow run #5 (954ce65 -> 9fa4dc9) from git: Diet 12 -> 11
    (one open question answered by W7220864522), ML fairness 55 -> 60 (+5,
    two set-aside method transfers dropped, never shown), Social media
    32 -> 32 (one set-aside method transfer dropped, never shown)."""
    import json as _json
    import subprocess as _sp
    rw = _load_run_weekly()
    if _sp.run(["git", "cat-file", "-e", "9fa4dc9^{commit}"], cwd=rw.ROOT, capture_output=True).returncode:
        pytest.skip("history not available in this checkout (shallow clone)")

    def snap(rev):
        out = {}
        for slug in ("diet-and-mortality", "ml-fairness", "social-media-teen-mental-health"):
            raw = _sp.run(["git", "show", f"{rev}:frontend/public/data/library/{slug}/opportunities.json"],
                          cwd=rw.ROOT, capture_output=True, text=True).stdout
            out[slug] = {i["slug"]: {"headline": i["consumer"]["headline"], "verdict": i.get("verdict"),
                                     "kind": i["consumer"]["kind_id"]} for i in _json.loads(raw)["items"]}
        return out
    d = rw.diff_items(snap("954ce65"), snap("9fa4dc9"))
    got = {s: (x["shown_before"], len(x["new_results"]), len(x["removed_shown"]), len(x["removed_not_shown"]),
               x["shown_after"]) for s, x in d.items()}
    assert got == {"diet-and-mortality": (12, 0, 1, 0, 11), "ml-fairness": (55, 5, 0, 2, 60),
                   "social-media-teen-mental-health": (32, 0, 0, 1, 32)}
    assert rw.unexplained(d) == []
    assert "W7220864522" in d["diet-and-mortality"]["removed_shown"][0]["reason"]


def rw_budget():
    from backend.app.grow.core import Budget
    return Budget(0.0)


def test_scheduled_runs_use_the_money_rule_and_ignore_manual_inputs(monkeypatch):
    """A scheduled run (event=schedule, no inputs) is never manual: no run
    cap, queued builds left to the money rule, and gates_only ignored even if
    the variables were somehow set."""
    rw = _load_run_weekly()
    monkeypatch.setenv("GROW_EVENT", "schedule")
    monkeypatch.setenv("GROW_RUN_BUDGET_INR", "5")
    monkeypatch.setenv("GROW_BUILD_QUEUED", "false")
    assert rw.run_controls() == (False, None, True)
    d, on = _wf("weekly-grow.yml")
    assert on["schedule"][0]["cron"] == "23 5 * * 1"
    assert d["concurrency"] == {"group": "weekly-grow", "cancel-in-progress": False}
    _d2, _on2 = _wf("keepalive.yml")
    assert _d2["concurrency"]["group"] == "weekly-grow" and _d2["concurrency"]["cancel-in-progress"] is False
    text = (WF / "weekly-grow.yml").read_text()
    assert "if: failure() || cancelled()" in text and "on_failure.py" in text
    src = (Path(rw.__file__)).read_text()
    assert 'os.environ.get("GROW_EVENT", "workflow_dispatch") == "workflow_dispatch"' in src


def test_keepalive_acts_only_after_40_quiet_days():
    import importlib.util
    spec = importlib.util.spec_from_file_location("keepalive", WF.parents[1] / "tools" / "grow" / "keepalive.py")
    k = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k)
    assert k.QUIET_DAYS <= 45
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    assert k.quiet_days(now) >= 0


def test_tests_never_see_a_scheduled_runs_controls_or_credentials():
    """Inside the suite, the scheduled run's controls and credentials are
    gone (conftest), so a test can never inherit a scheduled run's live path."""
    import os
    for k in ("GROW_EVENT", "GROW_GATES_ONLY", "GEMINI_API_KEY", "OPENALEX_API_KEY", "GH_TOKEN"):
        assert k not in os.environ, k


def test_gate_subprocesses_get_no_credentials(monkeypatch):
    rw = _load_run_weekly()
    monkeypatch.setenv("GEMINI_API_KEY", "x-test")
    monkeypatch.setenv("GROW_EVENT", "schedule")
    import sys as _sys
    r = rw.sh([_sys.executable, "-c", "import os; print(os.environ.get('GEMINI_API_KEY'), os.environ.get('GROW_EVENT'))"],
              no_secrets=True)
    assert r.stdout.strip() == "None None"


def test_live_run_refused_inside_pytest_when_credentials_are_present(monkeypatch):
    """Raised before anything runs: no client, no bookkeeping, no reset."""
    rw = _load_run_weekly()
    monkeypatch.setenv("GEMINI_API_KEY", "x-test")
    with pytest.raises(RuntimeError, match="refusing a live run inside pytest"):
        rw.main()


def test_no_git_writes_inside_pytest():
    rw = _load_run_weekly()
    for fn, args in ((rw.publish_main, ("2026-10-12",)), (rw.publish_bookkeeping, ("2026-10-12", "m")),
                     (rw.publish_branch, ("2026-10-12", "m")), (rw._reset_rest, ())):
        with pytest.raises(RuntimeError, match="refusing to write to git inside pytest"):
            fn(*args)
