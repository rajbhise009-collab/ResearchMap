"""The rules for queued (new) libraries in the weekly run.

Run #8 (manual, cap ₹30, build_queued=false) printed "queued builds skipped"
and then "build nudge-effectiveness: built". Both were right: the Nudges
build was STARTED by the scheduled run an hour earlier (money rule; ₹54.81
projected) and run #8 only FINISHED it — collecting batches already paid
for, then its follow-on checks (₹6.87, inside run #8's cap). These tests pin
the rules so neither can be bypassed:

  - a queued build starts at most once per run, only if the money rule
    allows it, never on a manual run with build_queued=false, never while an
    earlier failed run is unresolved or its self-recovery failed;
  - finishing a build during such a run collects only (no paid follow-on);
  - a manual run's cap is in force before any queued library is finished;
  - a queued build starts only after its free dry run passes every gate.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def _rw():
    spec = importlib.util.spec_from_file_location("run_weekly", REPO / "tools" / "grow" / "run_weekly.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


OK = dict(weekly_inr=14.87, hold=False, recovery_failed=False, building=False, build_queued=True,
          started_this_run=0)


@pytest.mark.parametrize("change,why", [
    ({"started_this_run": 1}, "one queued library per run"),
    ({"hold": True}, "unresolved"),
    ({"recovery_failed": True}, "could not be republished"),
    ({"build_queued": False}, "build_queued=false"),
    ({"weekly_inr": 0.0}, "no money"),
    ({"building": True}, "already being built"),
])
def test_queued_start_refused(change, why):
    allowed, reason = _rw().queued_start_decision(**{**OK, **change})
    assert not allowed and why in reason


def test_queued_start_allowed_only_when_every_rule_holds():
    allowed, reason = _rw().queued_start_decision(**OK)
    assert allowed and "money rule" in reason


def test_manual_run_defaults_never_build_a_queued_library(monkeypatch):
    rw = _rw()
    monkeypatch.setenv("GROW_EVENT", "workflow_dispatch")
    monkeypatch.delenv("GROW_BUILD_QUEUED", raising=False)
    monkeypatch.setenv("GROW_RUN_BUDGET_INR", "30")
    manual, cap, build_queued = rw.run_controls()
    assert manual and cap == 30.0 and build_queued is False
    allowed, _ = rw.queued_start_decision(**{**OK, "build_queued": build_queued})
    assert not allowed


def test_finish_without_paid_followon_only_collects(monkeypatch, tmp_path):
    """No disagreement classification, embedding or matching runs; the
    library stays 'building' for a later run."""
    from backend.app.corpus import multi_domain_extract as X
    from backend.app.corpus import multi_domain_reason as R
    from backend.app.grow import queued
    state = tmp_path / "batch.json"
    state.write_text("{}")
    monkeypatch.setattr(X, "_batch_state_path", lambda key: state)
    monkeypatch.setattr(X, "batch_collect", lambda key, client: {"status": "collected", "n": 3})
    called = []
    monkeypatch.setattr(R, "load_extractions", lambda slug: called.append("load") or [])
    monkeypatch.setattr(R, "classify_pairs_batch", lambda *a, **k: called.append("classify"))
    statuses = []
    monkeypatch.setattr(queued.registry, "set_status", lambda slug, st: statuses.append(st))
    class _Cl:
        batch = embed = None
    r = queued.finish({"slug": "growth-mindset", "domain_key": "growth_mindset"}, cl=_Cl(),
                      paid_followon=False, why_not="test")
    assert r["status"].startswith("collected; follow-on checks wait"), r
    assert not called and not statuses and not state.exists()


def test_manual_cap_is_in_force_before_any_queued_library_is_finished():
    """RUN_CAP_LEDGER_INR (the manual run's cap) is set before the first
    paid step, so finishing a queued library is covered by it."""
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    main = src[src.index("def main() -> int:"):src.index("def gates_only_rows(")]
    assert main.index('os.environ["RUN_CAP_LEDGER_INR"]') < main.index("queued.finish(")
    assert main.index('os.environ["RUN_CAP_LEDGER_INR"]') < main.index("core.collect(")


def test_queued_start_comes_after_its_free_dry_run():
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    main = src[src.index("def main() -> int:"):src.index("def gates_only_rows(")]
    block = main[main.index("queued_start_decision("):]
    assert block.index("dry_gate(") < block.index("queued.start(")
    assert re.search(r"if not dg\[\"ok\"\]:.*?continue", block, re.S)        # a failed dry run spends nothing


@pytest.mark.parametrize("manual,build_queued,no_new_paid,allowed", [
    (True, False, False, False),     # run #8's case: collect only, never finish
    (True, True, False, True),
    (False, True, False, True),      # scheduled runs: the money rule (the ledger cap) governs
    (False, True, True, False),      # an unresolved failed run: no new paid work
    (True, True, True, False),
])
def test_finishing_a_queued_library_pays_only_when_allowed(manual, build_queued, no_new_paid, allowed):
    ok, why = _rw().queued_finish_followon(manual=manual, build_queued=build_queued, no_new_paid=no_new_paid)
    assert ok is allowed and (ok or why)


def test_main_passes_the_finish_rule_to_queued_finish():
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    main = src[src.index("def main() -> int:"):src.index("def gates_only_rows(")]
    call = main[main.index("queued_finish_followon("):main.index("queued.finish(") + 200]
    assert "paid_followon=fo_ok" in call and "build_queued=build_queued" in call


def test_dry_run_worktree_gets_every_installed_package_the_gates_need():
    """A fresh worktree has no node_modules: without them the dry run's site
    build or its smoke check's axe-core is missing and every queued library
    would be refused for an environment reason, not a real one."""
    rw = _rw()
    assert set(rw.DRY_GATE_LINKS) >= {"frontend/node_modules", "tools/qa/node_modules"}
    smoke = (REPO / "tools" / "qa" / "smoke.py").read_text()
    assert '"tools" / "qa" / "node_modules" / "axe-core"' in smoke         # where smoke looks without AXE_PATH
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    body = src[src.index("def dry_gate(slug"):src.index("def dry_gate_build(")]
    assert "for rel in DRY_GATE_LINKS" in body and body.index("DRY_GATE_LINKS") < body.index("--dry-gate-build")


def test_self_recovery_runs_before_preflight():
    """A failed run's paid data is on main but its site was not regenerated:
    main's full tests can fail until it is. Recovery (regenerate + every gate)
    must therefore come before preflight, or a preflight stop would block
    every later run and the loop could never heal. Preflight is skipped only
    when recovery just passed every gate on this tree."""
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    main = src[src.index("def main() -> int:"):src.index("def gates_only_rows(")]
    assert main.index("recover_on_main(date)") < main.index("preflight_checks()") < main.index("core.collect(")
    skip = main[main.index("if recovered:"):main.index("preflight_checks()")]
    assert "covered by the self-recovery gates" in skip and "else:" in skip
    gates_src = src[src.index("def gates(*"):src.index("def ", src.index("def gates(*") + 10)]
    for step in ('"typecheck"', '"full tests"', "production build"):
        assert step in gates_src                       # recovery's gates cover all of preflight


def test_commit_author_defaults_to_the_bot_and_follows_the_repo_variables(monkeypatch):
    """Vercel's Hobby plan deploys a PRIVATE repo's commits only when the
    author email is verified on the owner's GitHub account, so the weekly
    run's author is configurable (GROW_GIT_NAME / GROW_GIT_EMAIL)."""
    rw = _rw()
    monkeypatch.delenv("GROW_GIT_NAME", raising=False)
    monkeypatch.delenv("GROW_GIT_EMAIL", raising=False)
    assert rw._identity() == ["-c", "user.name=researchmap-bot", "-c",
                              "user.email=researchmap-bot@users.noreply.github.com"]
    monkeypatch.setenv("GROW_GIT_NAME", "Owner")
    monkeypatch.setenv("GROW_GIT_EMAIL", "1+owner@users.noreply.github.com")
    assert rw._identity() == ["-c", "user.name=Owner", "-c", "user.email=1+owner@users.noreply.github.com"]
    monkeypatch.setenv("GROW_GIT_EMAIL", "  ")                        # an empty variable keeps the bot
    assert rw._identity()[-1] == "user.email=researchmap-bot@users.noreply.github.com"
    for wf in ("weekly-grow.yml", "keepalive.yml"):
        src = (REPO / ".github" / "workflows" / wf).read_text()
        assert "GROW_GIT_EMAIL: ${{ vars.GROW_GIT_EMAIL }}" in src, wf
