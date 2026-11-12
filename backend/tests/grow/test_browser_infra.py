"""The test browser comes without apt, is retried, and its failure is labelled
as infrastructure, never as the site being down (daily health #36: apt's
mirrors were unreachable, `playwright install --with-deps` failed, and the
live check never ran)."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
WF = REPO / ".github" / "workflows"
sys.path.insert(0, str(REPO / "tools" / "grow"))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ib():
    return _load(REPO / "tools" / "ci" / "install_browser.py", "install_browser")


class FakeRun:
    """Scripted results per command kind: launch / install / deps."""

    def __init__(self, **script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[tuple[str, int]] = []

    def __call__(self, cmd, timeout):
        kind = ("deps" if "install-deps" in cmd else "install" if "install" in cmd else "launch")
        self.calls.append((kind, timeout))
        res = self.script[kind].pop(0)
        return (res, "ok") if isinstance(res, bool) else res

    def kinds(self):
        return [k for k, _ in self.calls]


# ---- tools/ci/install_browser.py -------------------------------------------

def test_a_cached_browser_that_launches_is_used_without_any_download():
    ib, run, sleeps = _ib(), FakeRun(launch=[True]), []
    assert ib.install(run=run, sleep=sleeps.append)[0] is True
    assert run.kinds() == ["launch"] and sleeps == []


def test_chromium_only_retried_three_times_with_backoff_and_a_timeout():
    ib, sleeps = _ib(), []
    run = FakeRun(launch=[False, True], install=[(False, "DNS failure"), (False, "timed out after 240s"), True])
    ok, why = ib.install(run=run, sleep=sleeps.append)
    assert ok and run.kinds() == ["launch", "install", "install", "install", "launch"]
    assert sleeps == list(ib.BACKOFF_S) and sleeps[0] < sleeps[1]          # backoff grows
    assert all(t == ib.INSTALL_TIMEOUT_S for k, t in run.calls if k == "install")
    assert ib.ATTEMPTS == 3 and ib.INSTALL_TIMEOUT_S > 0
    assert run.calls[1] == ("install", ib.INSTALL_TIMEOUT_S)


def test_system_dependencies_only_when_the_installed_browser_will_not_launch():
    ib = _ib()
    run = FakeRun(launch=[False, True], install=[True])
    assert ib.install(run=run, sleep=lambda s: None)[0] and "deps" not in run.kinds()
    run = FakeRun(launch=[False, False, True], install=[True], deps=[(False, "mirror down"), True])
    ok, why = ib.install(run=run, sleep=lambda s: None)
    assert ok and run.kinds() == ["launch", "install", "launch", "deps", "deps", "launch"]
    assert "system dependencies" in why


def test_every_failure_path_reports_not_ok_and_never_raises():
    ib = _ib()
    run = FakeRun(launch=[False], install=[False, False, False])
    ok, why = ib.install(run=run, sleep=lambda s: None)
    assert not ok and "3 times" in why and run.kinds().count("install") == 3
    run = FakeRun(launch=[False, False], install=[True], deps=[False, False, False])
    assert ib.install(run=run, sleep=lambda s: None)[0] is False
    run = FakeRun(launch=[False, False, False], install=[True], deps=[True])
    assert ib.install(run=run, sleep=lambda s: None)[0] is False


def test_a_hung_command_is_a_failure_not_a_hang():
    ib = _ib()
    ok, out = ib._run([sys.executable, "-c", "import time; time.sleep(5)"], 1)
    assert not ok and "timed out" in out
    ok, out = ib._run(["/nonexistent/binary"], 5)
    assert not ok


def test_main_writes_the_step_output_and_exits_zero_even_on_failure(monkeypatch, tmp_path, capsys):
    ib = _ib()
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(ib, "install", lambda: (False, "Chromium download failed 3 times: DNS"))
    assert ib.main() == 0
    assert out.read_text() == "ok=false\n"
    printed = capsys.readouterr().out
    assert "::error title=Infrastructure::infrastructure: could not install test browser" in printed
    assert "not a site failure" in printed
    monkeypatch.setattr(ib, "install", lambda: (True, "a cached browser launches"))
    out.write_text("")
    assert ib.main() == 0 and out.read_text() == "ok=true\n"


# ---- the workflows ---------------------------------------------------------

def _wf(name):
    d = yaml.safe_load((WF / name).read_text())
    return d, d.get("on", d.get(True))


def _steps(d, job):
    return d["jobs"][job]["steps"]


def _browser_setup_ok(name, d, job):
    runs = " ".join(s.get("run", "") for j in d["jobs"].values() for s in j["steps"])
    assert "--with-deps" not in runs and not re.search(r"\bapt(-get)?\b", runs), name   # no apt
    version = d["env"]["PLAYWRIGHT_VERSION"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    steps = _steps(d, job)
    names = [s.get("name", "") for s in steps]
    pip = next(s for s in steps if "pip install" in s.get("run", ""))
    assert "playwright==${{ env.PLAYWRIGHT_VERSION }}" in pip["run"], name     # one version, two uses
    cache = next(s for s in steps if s.get("uses", "").startswith("actions/cache@")
                 and s["with"]["path"] == "~/.cache/ms-playwright")
    assert cache["with"]["key"] == "ms-playwright-${{ runner.os }}-${{ env.PLAYWRIGHT_VERSION }}"
    br = next(s for s in steps if s.get("id") == "browser")
    assert "tools/ci/install_browser.py" in br["run"]
    assert br["continue-on-error"] is True and br["timeout-minutes"] > 0
    i_cache, i_br = steps.index(cache), steps.index(br)
    drop = next(s for s in steps if "rm -rf ~/.cache/ms-playwright" in s.get("run", ""))
    assert i_cache < i_br < steps.index(drop) and drop["if"] == "steps.browser.outputs.ok != 'true'"
    return steps, names, steps.index(br)


def test_daily_health_installs_chromium_only_and_always_runs_the_live_check():
    d, on = _wf("daily-health.yml")
    steps, _names, i_br = _browser_setup_ok("daily-health.yml", d, "health")
    check = next(s for s in steps if s.get("id") == "check")
    assert steps.index(check) > i_br and "if" not in check          # runs after a failed browser install
    assert check["env"]["HEALTH_BROWSER_OK"] == "${{ steps.browser.outputs.ok }}"
    assert "tools/grow/health.py" in check["run"]


def test_daily_health_retry_slot_runs_only_after_an_infrastructure_failure():
    d, on = _wf("daily-health.yml")
    crons = [c["cron"] for c in on["schedule"]]
    assert crons == ["41 6 * * *", "41 12 * * *"]
    slot = d["jobs"]["slot"]
    marker = next(s for s in slot["steps"] if s.get("id") == "marker")
    assert marker["if"] == "github.event.schedule == '41 12 * * *'"
    assert marker["with"]["lookup-only"] is True
    assert marker["with"]["key"] == "health-infra-${{ steps.today.outputs.date }}"
    health = d["jobs"]["health"]
    assert health["needs"] == "slot" and health["if"] == "needs.slot.outputs.run == 'true'"
    check = next(s for s in health["steps"] if s.get("id") == "check")
    assert check["env"]["HEALTH_RETRY"] == "${{ needs.slot.outputs.retry }}"
    mark = d["jobs"]["mark"]
    assert mark["if"] == "needs.health.result == 'success' && needs.health.outputs.infra == 'true'"
    save = next(s for s in mark["steps"] if s.get("uses", "").startswith("actions/cache@"))
    assert save["with"]["key"] == "health-infra-${{ needs.slot.outputs.today }}"
    assert save["with"]["path"] == marker["with"]["path"]               # the same cache entry
    decide = next(s for s in slot["steps"] if s.get("id") == "decide")["run"]
    assert "run=false" in decide and "run=true\\nretry=true" in decide


def test_weekly_grow_installs_chromium_only_and_still_runs_on_a_failed_install():
    d, _on = _wf("weekly-grow.yml")
    steps, names, i_br = _browser_setup_ok("weekly-grow.yml", d, "grow")
    grow = steps[names.index("Grow, gate, publish")]
    assert names.index("Grow, gate, publish") > i_br
    assert grow["env"]["GROW_BROWSER_OK"] == "${{ steps.browser.outputs.ok }}"
    # the browser step's log goes where the failure report looks for it
    br = steps[i_br]
    assert '| tee -a "$RUNNER_TEMP/install.log"' in br["run"] and br["shell"] == "bash"
    src = (REPO / "tools" / "grow" / "on_failure.py").read_text()
    assert 'f in ("install", "browser")' in src


# ---- tools/grow/health.py ----------------------------------------------------

def _health(monkeypatch, tmp_path, *, live_ok=True, smoke_ok=True):
    monkeypatch.setenv("GROW_ISSUE_DIR", str(tmp_path / "issues"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    h = _load(REPO / "tools" / "grow" / "health.py", "health")
    ran = []

    def run(cmd):
        name = "smoke" if "smoke.py" in " ".join(cmd) else "live"
        ran.append(name)
        return (live_ok if name == "live" else smoke_ok), f"{name} output"
    monkeypatch.setattr(h, "run", run)
    return h, ran


def _issue(tmp_path, title):
    p = tmp_path / "issues" / ("".join(ch if ch.isalnum() else "-" for ch in title).strip("-")[:90] + ".json")
    return json.loads(p.read_text()) if p.exists() else None


def test_no_browser_site_up_first_attempt_no_issue_and_a_retry_marker(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HEALTH_BROWSER_OK", "false")
    monkeypatch.delenv("HEALTH_RETRY", raising=False)
    h, ran = _health(monkeypatch, tmp_path)
    assert h.main() == 0 and ran == ["live"]                       # the live check still ran
    assert (tmp_path / "out").read_text() == "infra=true\n"
    assert _issue(tmp_path, h.TITLE) is None and _issue(tmp_path, h.INFRA_TITLE) is None
    out = capsys.readouterr().out
    assert "infrastructure: could not install test browser" in out and "::warning" in out


def test_an_empty_browser_output_counts_as_no_browser(monkeypatch, tmp_path):
    """The install step crashed or timed out: its output is empty."""
    monkeypatch.setenv("HEALTH_BROWSER_OK", "")
    h, ran = _health(monkeypatch, tmp_path)
    assert h.main() == 0 and ran == ["live"]


def test_no_browser_again_on_the_retry_opens_an_infrastructure_issue_not_a_site_issue(monkeypatch, tmp_path):
    monkeypatch.setenv("HEALTH_BROWSER_OK", "false")
    monkeypatch.setenv("HEALTH_RETRY", "true")
    h, _ran = _health(monkeypatch, tmp_path)
    assert h.main() == 1
    it = _issue(tmp_path, h.INFRA_TITLE)
    assert it["state"] == "open" and "infrastructure" in it["labels"] and "needs-action" not in it["labels"]
    assert it["body"].startswith("**infrastructure: could not install test browser** — this is not the site")
    assert _issue(tmp_path, h.TITLE) is None
    assert not (tmp_path / "out").exists()                          # no further retry marker
    # the next day the browser installs and everything passes: it closes
    monkeypatch.setenv("HEALTH_BROWSER_OK", "true")
    monkeypatch.delenv("HEALTH_RETRY")
    h, ran = _health(monkeypatch, tmp_path)
    assert h.main() == 0 and ran == ["live", "smoke"]
    assert _issue(tmp_path, h.INFRA_TITLE)["state"] == "closed"


def test_site_down_without_a_browser_is_still_a_site_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("HEALTH_BROWSER_OK", "false")
    monkeypatch.delenv("HEALTH_RETRY", raising=False)
    h, _ran = _health(monkeypatch, tmp_path, live_ok=False)
    assert h.main() == 1
    it = _issue(tmp_path, h.TITLE)
    assert it["state"] == "open" and it["body"].startswith("**site check failed**")
    assert "smoke checks: not run" in it["body"] and _issue(tmp_path, h.INFRA_TITLE) is None
    assert not (tmp_path / "out").exists()


def test_smoke_failure_with_a_working_browser_is_a_site_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("HEALTH_BROWSER_OK", "true")
    h, ran = _health(monkeypatch, tmp_path, smoke_ok=False)
    assert h.main() == 1 and ran == ["live", "smoke"]
    assert _issue(tmp_path, h.TITLE)["body"].startswith("**site check failed**")


# ---- tools/grow/run_weekly.py ------------------------------------------------

def _rw():
    return _load(REPO / "tools" / "grow" / "run_weekly.py", "run_weekly_browser")


def test_weekly_browser_gates_fail_as_infrastructure_without_a_browser(monkeypatch):
    rw = _rw()
    monkeypatch.setattr(rw, "MOCK", False)
    monkeypatch.setattr(rw, "sh", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    served = []
    monkeypatch.setattr(rw, "_serve", lambda fn: served.append(1))
    monkeypatch.setenv("GROW_BROWSER_OK", "false")
    res = rw.gates()
    infra = [g for g in res if g.get("infra")]
    assert [g["gate"] for g in infra] == ["browser hunt (Part 3)", "smoke checks on the build"]
    assert all(not g["ok"] and "infrastructure: could not install test browser" in g["tail"] for g in infra)
    assert served == [] and rw.infra_only(res)
    assert "FAIL (infrastructure)" in rw.gates_only_summary("d", res)
    monkeypatch.setenv("GROW_BROWSER_OK", "true")
    monkeypatch.setattr(rw, "_serve", lambda fn: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    assert all(g["ok"] for g in rw.gates()) and not rw.infra_only(rw.gates())


def test_infra_only_needs_every_failure_to_be_infrastructure():
    rw = _rw()
    smoke = {"gate": "smoke checks on the build", "ok": False, "infra": True}
    assert rw.infra_only([smoke, {"gate": "full tests", "ok": True}])
    assert not rw.infra_only([smoke, {"gate": "full tests", "ok": False}])
    assert not rw.infra_only([]) and not rw.infra_only(None)


def test_browser_defaults_to_available_and_empty_means_missing(monkeypatch):
    rw = _rw()
    monkeypatch.delenv("GROW_BROWSER_OK", raising=False)
    assert rw.browser_ok()
    for v in ("", "false"):
        monkeypatch.setenv("GROW_BROWSER_OK", v)
        assert not rw.browser_ok()


def test_weekly_without_a_browser_collects_paid_work_and_starts_nothing_new():
    """Source pins: no browser -> the existing no-new-paid path (collect,
    start nothing), no queued start, and the Issue's status says
    infrastructure. The full flow runs in tools/grow/e2e_mock.py (scenario 18)."""
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    main = src[src.index("def main() -> int:"):src.index("def gates_only_rows(")]
    assert "infra = None if browser_ok() else BROWSER_HOLD" in main
    assert "no_new_paid = bool(hold or infra)" in main
    assert main.index("infra = None if browser_ok()") < main.index("core.collect(")
    assert 'allowed, why = False, f"{INFRA_BROWSER} (no new paid work)"' in main
    assert main.count("if infra_only(") == 2              # recovery failed, publish gates failed
    regen = src[src.index("def regenerate()"):src.index("def _serve(")]
    assert "not browser_ok()" in regen                     # share images need the browser too


def test_the_installer_needs_only_the_standard_library():
    """It runs before anything but Playwright is installed (daily health)."""
    import ast
    tree = ast.parse((REPO / "tools" / "ci" / "install_browser.py").read_text())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods and mods <= set(sys.stdlib_module_names) | {"__future__"}, mods
