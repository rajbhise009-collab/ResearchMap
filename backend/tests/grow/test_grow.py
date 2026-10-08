"""Weekly growth: budget, redaction, candidate selection, workflow hygiene.
Offline; nothing here writes to data/ (the full flow is exercised by
tools/grow/e2e_mock.py in a throwaway clone)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import re
from pathlib import Path

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
    assert "llm-calibration" not in core.GROW_SLUGS


def test_zero_budget_submits_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("GROW_DATE", "2026-10-12")
    from backend.app.grow.mocks import mock_clients
    monkeypatch.setenv("GROW_MOCK_STATE", str(tmp_path))
    # independent of any batch a real weekly run left pending
    monkeypatch.setattr(core, "pending_path", lambda slug: tmp_path / f"{slug}-pending.json")
    cl = mock_clients()
    errs: list[str] = []
    r = core.submit("ml-fairness", cl, core.Budget(0.0), ref=dt.date(2026, 10, 12), errors=errs)
    assert r["submitted"] == 0 and r["projected_inr"] == 0
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
