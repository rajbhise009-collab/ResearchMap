"""End-to-end test of both workflows' logic, offline, with no paid calls.

  .venv/bin/python tools/grow/e2e_mock.py [--quick]

A throwaway clone of the committed HEAD whose `origin` is a local bare
repository (stands in for GitHub); tools/grow/run_weekly.py with mocked
OpenAlex and Gemini (GROW_MOCK=1); the clone's own copy of the ledger and a
temporary money config (MONEY_CONFIG_PATH: ₹600 remaining); Issues written to
files (GROW_ISSUE_DIR); the live check against a local server of the clone's
build. Scenarios:

  1  week 1: submit across every growing library (round-robin budget) and
     start building the first affordable queued library
  2  week 2: collect papers, finish the queued library (a new library on a
     five-plus-library site), every publish gate, publish
  3  missing secret: clean stop, nothing pushed, Issue names the secret
  4  OpenAlex down after collecting: bookkeeping-only commit to main (paid
     work kept, site files untouched), no blocking branch
  5  next week: runs normally (not blocked)
  6  budget exhausted mid-run: collecting uses up the money; submission is
     refused; Issue says what to do (console_spent_inr / account_total_inr)
  7  a failing test: PREFLIGHT stops the run before any spend (exit 3), the
     Issue names the test, one marked failure block ends the log
  8  an unmerged grow/* branch holds back new spending; once recorded in
     data/grow/resolved_branches.json the run proceeds (branch kept)
  9  pause (config/growth.json) then resume
 10  daily health: site down -> Issue opened; site up -> Issue closed
 11  rotation week: a library never served (and owed its follow-on checks)
     goes first in both phases and gets papers
 12  scope exclusion: a paid-for paper outside the core scope is collected,
     kept on file, not published, listed in the Issue; the run is not blocked
 13  a publish gate fails after regeneration: site unchanged, paid work on
     main, grow/<date> branch, one marked failure block, Issue names the gate
 14  zero-spend REPUBLISH of that branch (manual, no keys): regenerated on
     main, gates pass, main fast-forwarded, ledger untouched, branch kept and
     recorded as resolved, the run's Issue closed

--quick skips the publish gates except in scenario 7 (honoured only with
GROW_MOCK=1). Every run takes the SCHEDULED path (event=schedule, empty
inputs). Writes <E2E_DIR>/grow-e2e.json and, on a full pass,
docs/releases/growth-e2e-passed.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
QUICK = "--quick" in sys.argv
OUT = Path(os.environ.get("E2E_DIR") or (Path("/private/tmp") / f"grow-e2e-{int(time.time())}"))
WORK, REMOTE, ISSUES, MOCKST = OUT / "work", OUT / "remote.git", OUT / "issues", OUT / "mockstate"
MONEY = OUT / "money.json"
PORT = "8797"
SITE = f"http://127.0.0.1:{PORT}"
FAKE_SECRET = "oa-FAKE-SECRET-value-123456"
R: list[dict] = []


def check(scn, ok, label, detail=""):
    R.append({"scenario": scn, "ok": bool(ok), "label": label, "detail": str(detail)[:400]})
    print(f"[{'PASS' if ok else 'FAIL'}] {scn}: {label}" + (f" — {detail}" if detail and not ok else ""), flush=True)


def sh(cmd, cwd=WORK, env=None, check_=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if check_ and r.returncode != 0:
        raise RuntimeError(f"{cmd}: {r.stderr[-800:]}")
    return r


def git(*a, cwd=WORK):
    return sh(["git", *a], cwd=cwd).stdout.strip()


def remote_head(ref="main"):
    out = git("ls-remote", str(REMOTE), f"refs/heads/{ref}")
    return out.split()[0] if out else None


def env(date, **extra):
    e = {k: v for k, v in os.environ.items()
         if k not in ("OPENALEX_API_KEY", "GEMINI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN", "WEEKLY_BUDGET_INR")}
    # the SCHEDULED path, as the workflow runs it: event=schedule and empty inputs
    e.update(GROW_EVENT="schedule", GROW_RUN_BUDGET_INR="", GROW_BUILD_QUEUED="", GROW_GATES_ONLY="")
    e.update(GROW_MOCK="1", GROW_MOCK_STATE=str(MOCKST), GROW_ISSUE_DIR=str(ISSUES), GROW_DATE=date,
             GROW_LIVE_WAIT_S="0", NEXT_PUBLIC_SITE_URL=SITE, MONEY_CONFIG_PATH=str(MONEY),
             GROW_VERCEL_HOST="", GROW_RETRY_BASE_S="0", PYTHONHASHSEED="0")
    if QUICK:
        e["GROW_GATES"] = "skip"
    e.update(extra)
    return {k: v for k, v in e.items() if v is not None}


def run_weekly(date, **extra):
    r = subprocess.run([PY, "tools/grow/run_weekly.py"], cwd=WORK, capture_output=True, text=True,
                       env=env(date, **extra), timeout=7200)
    (OUT / f"run-{date}.log").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr)
    return r


def issue(date):
    p = ISSUES / f"Weekly-grow---{date}.json"
    return json.loads(p.read_text()) if p.exists() else {"body": "", "labels": [], "state": "missing"}


def ledger_inr():
    return round(json.loads((WORK / "data" / "spend_ledger.json").read_text())["cumulative_inr"], 4)


def papers(slug):
    return len(json.loads((WORK / "data" / "domains" / slug / "prelabelled.json").read_text())["entries"])


def registry():
    return {l["slug"]: l for l in json.loads((WORK / "data" / "library_registry.json").read_text())["libraries"]}


def site_libs():
    return [l["slug"] for l in json.loads((WORK / "frontend/public/data/libraries.json").read_text())["libraries"]]


def public_tree_sha(ref):
    return git("rev-parse", f"{ref}:frontend/public", cwd=REMOTE)


def setup():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    sh(["git", "clone", "-q", "--bare", str(ROOT), str(REMOTE)], cwd=OUT)
    sh(["git", "clone", "-q", str(REMOTE), str(WORK)], cwd=OUT)
    for rel in ("frontend/node_modules", "tools/qa/node_modules"):
        (WORK / rel).symlink_to(ROOT / rel)
    with open(WORK / ".git" / "info" / "exclude", "a") as f:
        f.write("frontend/node_modules\ntools/qa/node_modules\n")
    # The clone carries the REAL pending batches (submitted by a live run and
    # billed when a live run collects them). The mocked Gemini cannot know
    # those batch ids, so the mock world starts with none. Only this scratch
    # clone and its stand-in remote change; the real files are untouched.
    real_pending = sorted(str(p.relative_to(WORK)) for p in (WORK / "data" / "domains").glob("*/grow/pending.json"))
    if real_pending:
        git("rm", "-q", *real_pending)
        git("-c", "user.name=e2e", "-c", "user.email=e2e@example.invalid", "commit", "-q", "-m",
            "e2e: start the mock world with no real pending batches")
        git("push", "-q", "origin", "HEAD:main")
    _set_money(650)


def _set_money(headroom):
    led = json.loads((WORK / "data" / "spend_ledger.json").read_text())["cumulative_inr"]
    MONEY.write_text(json.dumps({"account_total_inr": round(led + headroom, 2), "safety_buffer_inr": 50,
                                 "console_spent_inr": None, "console_spent_date": None,
                                 "growth_horizon_weeks": 12, "growth_horizon_start": "2026-10-12",
                                 "weekly_budget_max_inr": 60, "queued_domain_reserve_weeks": 4}))


def commit_push(msg, files):
    git("add", *files)
    git("-c", "user.name=e2e", "-c", "user.email=e2e@example.invalid", "commit", "-q", "-m", msg)
    git("push", "-q", "origin", "HEAD:main")


def sync_main():
    git("checkout", "-q", "main")
    git("fetch", "-q", "origin")
    git("reset", "-q", "--hard", "origin/main")


def write_marker(results):
    head = git("rev-parse", "HEAD", cwd=ROOT)
    m = ROOT / "docs" / "releases" / "growth-e2e-passed.json"
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps({
        "what": "tools/grow/e2e_mock.py full run (every publish gate in scenarios 1, 2 and 7), mocked OpenAlex "
                "and Gemini, temporary ledger and money config, local stand-in for GitHub",
        "date": time.strftime("%Y-%m-%d"), "tested_commit": head, "full": True,
        "passed": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results),
        "scenarios": sorted({str(r["scenario"]) for r in results}),
    }, indent=1) + "\n")


def main() -> int:
    setup()
    srv = subprocess.Popen([PY, "tools/qa/serve.py", PORT], cwd=WORK,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    real_ledger_before = (ROOT / "data" / "spend_ledger.json").read_bytes()
    reg0 = registry()
    growing = [s for s, l in reg0.items() if l["status"] == "built" and not l["frozen"]]
    queued0 = [s for s, l in reg0.items() if l["status"] == "queued"]
    full = {"GROW_GATES": None}
    try:
        if QUICK:   # the live check needs a built site to look at
            sh(["npm", "run", "build"], cwd=WORK / "frontend", env={**os.environ, "NEXT_PUBLIC_SITE_URL": SITE})
        # 1 ---------------------------------------------------------------
        d = "2026-10-12"
        m0 = remote_head()
        r = run_weekly(d, **({} if QUICK else full))
        it = issue(d)
        pend = {s: (WORK / "data/domains" / s / "grow/pending.json").exists() for s in growing}
        check(1, r.returncode == 0, "week 1 exits 0", r.stdout[-600:])
        check(1, remote_head() != m0 and remote_head() == git("rev-parse", "HEAD"), "main advanced (ls-remote == HEAD)")
        check(1, sum(pend.values()) >= 2, "batches pending across the growing libraries (round-robin)", pend)
        building = [s for s, l in registry().items() if l["status"] == "building"]
        check(1, building == queued0[:1], "the first queued library started building", building)
        check(1, it["body"].startswith("**Status:** published to main") and "## Money" in it["body"]
              and "weeks left" in it["body"], "one Issue: published, with money and weeks left")
        fp = json.loads((WORK / "docs/releases" / f"{d}.json").read_text())
        check(1, fp["gates"] and all(g["ok"] for g in fp["gates"]), "every publish gate passed",
              [g for g in fp["gates"] or [] if not g["ok"]])
        if r.returncode != 0:
            raise SystemExit("week 1 failed; see " + str(OUT / f"run-{d}.log"))
        # 2 ---------------------------------------------------------------
        d = "2026-10-19"
        before = {s: papers(s) for s in growing}
        submitted = {s: (len(json.loads((WORK / "data/domains" / s / "grow/pending.json").read_text())["entries"])
                         if pend[s] else 0) for s in growing}
        l_before = ledger_inr()
        r = run_weekly(d, **({} if QUICK else full))
        it = issue(d)
        after = {s: papers(s) for s in growing}
        new_lib = queued0[0]
        check(2, r.returncode == 0, "week 2 exits 0", r.stdout[-800:])
        check(2, all(after[s] - before[s] == submitted[s] for s in growing),
              "every submitted paper that extracted cleanly was added", (before, after, submitted))
        check(2, ledger_inr() > l_before, "last week's batches billed to the ledger")
        check(2, registry()[new_lib]["status"] == "built" and new_lib in site_libs(),
              f"queued library {new_lib} built and on the site", site_libs())
        check(2, len(site_libs()) >= 5, f"a {len(site_libs())}-library site built" + ("" if QUICK else
              " and passed every gate"), site_libs())
        if not QUICK:
            fp = json.loads((WORK / "docs/releases" / f"{d}.json").read_text())
            check(2, fp["gates"] and all(g["ok"] for g in fp["gates"]), "every publish gate passed",
                  [g for g in fp["gates"] or [] if not g["ok"]])
        facts = {l["slug"]: l for l in
                 json.loads((WORK / "frontend/public/data/site-facts.json").read_text())["libraries"]}
        opps = json.loads((WORK / f"frontend/public/data/library/{new_lib}/opportunities.json").read_text())["items"]
        flagged = [o for o in opps if o.get("verdict") == "unaudited"]
        check(2, all(o["consumer"].get("verdict_label") == "Flagged by the system, not yet checked" for o in flagged)
              and facts[new_lib]["results_total"] == sum(1 for o in opps if o.get("verdict") in (None, "genuine")),
              "new library: flagged pairs labelled 'not yet checked' and never counted", len(flagged))
        check(2, all(o.get("confirm_status") for o in opps if o.get("scorer") == "structural_holes"),
              "new library: every shown method-transfer lead went through confirmation")
        check(2, "## New libraries" in it["body"] and new_lib in it["body"], "Issue reports the new library")
        # 3 ---------------------------------------------------------------
        d = "2026-10-20"
        m = remote_head()
        r = run_weekly(d, GROW_MOCK=None, OPENALEX_API_KEY=FAKE_SECRET, GEMINI_API_KEY=None)
        it = issue(d)
        check(3, r.returncode == 2 and remote_head() == m and not git("status", "--porcelain"),
              "missing secret: clean stop, nothing pushed or changed", r.stdout[-300:])
        check(3, "GEMINI_API_KEY" in it["body"], "Issue names the secret to add")
        check(3, FAKE_SECRET not in it["body"] + r.stdout + r.stderr, "the set secret appears nowhere")
        # 4 ---------------------------------------------------------------
        d = "2026-10-26"
        pub_before = public_tree_sha("main")
        l_before = ledger_inr()
        r = run_weekly(d, GROW_MOCK_FAIL="openalex", GROW_GATES="skip")
        it = issue(d)
        led_main = json.loads(sh(["git", "show", "main:data/spend_ledger.json"], cwd=REMOTE).stdout)["cumulative_inr"]
        check(4, r.returncode == 2, "OpenAlex down -> clean stop (exit 2)", r.stdout[-300:])
        check(4, led_main > l_before, "the spend recorded before the stop is on main (bookkeeping commit)")
        check(4, public_tree_sha("main") == pub_before, "site files on main unchanged")
        check(4, not git("ls-remote", "--heads", str(REMOTE), "grow/*"), "no blocking branch")
        check(4, "OpenAlex" in it["body"] and "next week" in it["body"], "Issue explains and says it retries")
        # 5 ---------------------------------------------------------------
        sync_main()
        d = "2026-11-02"
        r = run_weekly(d, GROW_GATES="skip")
        check(5, r.returncode == 0 and issue(d)["body"].startswith("**Status:** published"),
              "next week runs normally (not blocked)", r.stdout[-300:])
        # 6 ---------------------------------------------------------------
        d = "2026-11-09"
        r = run_weekly(d, GROW_GATES="skip", GROW_MOCK_USAGE_MULT="600")
        it = issue(d)
        check(6, "BUDGET EXHAUSTED" in it["body"].splitlines()[0] if it["body"] else False,
              "collecting used up the money: status says BUDGET EXHAUSTED", it["body"][:200])
        check(6, "console_spent_inr" in it["body"] and "account_total_inr" in it["body"],
              "Issue says exactly what the owner can do")
        check(6, all(not (WORK / "data/domains" / s / "grow/pending.json").exists() for s in growing),
              "nothing new submitted after exhaustion")
        _set_money(650)          # restore money for the remaining scenarios
        # 7 ---------------------------------------------------------------
        sync_main()
        (WORK / "backend/tests/test_e2e_broken.py").write_text("def test_broken():\n    assert False\n")
        commit_push("e2e: broken test", ["backend/tests/test_e2e_broken.py"])
        d = "2026-11-16"
        pub_before, m = public_tree_sha("main"), remote_head()
        l_before, jobs0 = ledger_inr(), len(list(MOCKST.glob("*.json")))
        r = run_weekly(d, GROW_GATES=None)
        it = issue(d)
        check(7, r.returncode == 3, "a failing test is caught by PREFLIGHT -> exit 3", r.stdout[-300:])
        check(7, remote_head() == m and public_tree_sha("main") == pub_before, "nothing pushed, site unchanged")
        check(7, ledger_inr() == l_before and len(list(MOCKST.glob("*.json"))) == jobs0,
              "nothing spent, collected or submitted")
        check(7, "test_broken" in it["body"] and "nothing spent" in it["body"], "Issue names the failing test")
        check(7, "GATE FAILURES" in r.stdout and "test_broken" in r.stdout.split("GATE FAILURES")[-1],
              "one marked failure block at the end of the log")
        # 8 ---------------------------------------------------------------
        sync_main()
        (WORK / "backend/tests/test_e2e_broken.py").unlink()
        commit_push("e2e: fix test", ["-A", "backend/tests"])
        # an unmerged grow/* branch holds back new spending ...
        git("checkout", "-q", "-b", "grow/2026-11-20")
        (WORK / "docs" / "e2e-branch-note.md").write_text("unmerged work\n")
        commit_push_branch = ["docs/e2e-branch-note.md"]
        git("add", *commit_push_branch)
        git("-c", "user.name=e2e", "-c", "user.email=e2e@example.invalid", "commit", "-q", "-m", "unmerged")
        git("push", "-q", "origin", "grow/2026-11-20")
        sync_main()
        d = "2026-11-23"
        jobs0 = len(list(MOCKST.glob("*.json")))
        r = run_weekly(d, GROW_GATES="skip")
        it = issue(d)
        check(8, r.returncode == 0 and "starting nothing new" in it["body"],
              "with an unmerged grow/* branch: runs, collects, starts nothing new", r.stdout[-300:])
        check(8, len(list(MOCKST.glob("*.json"))) == jobs0, "no new batch submitted")
        # ... until it is recorded as resolved (branches are never deleted)
        sync_main()
        rb = WORK / "data" / "grow" / "resolved_branches.json"
        reg = json.loads(rb.read_text()) if rb.exists() else {"resolved": {}}
        reg["resolved"]["grow/2026-11-20"] = {"date": "2026-11-23", "reason": "e2e"}
        rb.parent.mkdir(parents=True, exist_ok=True)
        rb.write_text(json.dumps(reg, indent=1))
        commit_push("resolve grow/2026-11-20", [str(rb.relative_to(WORK))])
        d = "2026-11-24"
        r = run_weekly(d, GROW_GATES="skip")
        check(8, r.returncode == 0 and "starting nothing new" not in issue(d)["body"]
              and remote_head("grow/2026-11-20") is not None,
              "recorded as resolved: runs normally again; the branch still exists")
        # 9 ---------------------------------------------------------------
        sync_main()
        g = json.loads((WORK / "config/growth.json").read_text())
        g["paused"] = True
        (WORK / "config/growth.json").write_text(json.dumps(g, indent=1))
        commit_push("pause growth", ["config/growth.json"])
        d = "2026-11-30"
        m, l_before = remote_head(), ledger_inr()
        r = run_weekly(d, GROW_GATES="skip")
        check(9, r.returncode == 0 and remote_head() == m and ledger_inr() == l_before
              and issue(d)["body"].startswith("**Status:** paused"), "paused: nothing collected, spent or pushed")
        g["paused"] = False
        (WORK / "config/growth.json").write_text(json.dumps(g, indent=1))
        commit_push("resume growth", ["config/growth.json"])
        d = "2026-12-07"
        r = run_weekly(d, GROW_GATES="skip")
        check(9, r.returncode == 0 and issue(d)["body"].startswith("**Status:** published"), "resumed",
              r.stdout[-300:])
        # 11 rotation -----------------------------------------------------
        sync_main()
        last = "social-media-teen-mental-health"
        fair_p = WORK / "data" / "grow" / "fairness.json"
        fair = {s: {"extraction_served": "2026-12-07", "followon_served": "2026-12-07", "followon_owed": []}
                for s in growing if s != last}
        fair[last] = {"followon_owed": ["fw_match"]}            # never served for papers; owed its checks
        fair_p.parent.mkdir(parents=True, exist_ok=True)
        fair_p.write_text(json.dumps(fair, indent=1))
        commit_push("e2e: social media starved so far", [str(fair_p.relative_to(WORK))])
        d = "2026-12-14"
        r = run_weekly(d, GROW_GATES="skip")
        order = next((ln.split(":", 1)[1].strip().split(", ") for ln in r.stdout.splitlines()
                      if ln.strip().startswith("allocation order (fair)") or "allocation order (fair):" in ln), [])
        fo = [ln.split("follow-on ", 1)[1].split(":")[0] for ln in r.stdout.splitlines() if "follow-on " in ln
              and ":" in ln.split("follow-on ", 1)[1]]
        sub = json.loads((WORK / "data/domains" / last / "grow/pending.json").read_text())["entries"] \
            if (WORK / "data/domains" / last / "grow/pending.json").exists() else []
        check(11, r.returncode == 0, "rotation week exits 0", r.stdout[-300:])
        check(11, order[:1] == [last], "the never-served library goes first in allocation", order)
        check(11, fo[:1] == [last], "the library owed follow-on checks goes first in the follow-on phase", fo)
        check(11, len(sub) >= 1, "and it gets papers this week", len(sub))
        f_after = json.loads(fair_p.read_text())
        check(11, f_after[last].get("extraction_served") == d, "fairness record updated (served this week)", f_after)
        # 12 scope exclusion -------------------------------------------------
        sync_main()
        diet = "diet-and-mortality"
        pp = WORK / "data/domains" / diet / "grow/pending.json"
        excl_wid = None
        if pp.exists():
            st = json.loads(pp.read_text())
            st["entries"][0]["title"] = "Dietary fibre and the composition of the gut microbiota"
            st["entries"][0]["abstract"] = "We measured fibre intake and microbial diversity in 200 adults."
            excl_wid = st["entries"][0]["wid"]
            pp.write_text(json.dumps(st))
            commit_push("e2e: a pending paper submitted before the scope rule", [str(pp.relative_to(WORK))])
        d = "2026-12-21"
        r = run_weekly(d, GROW_GATES="skip")
        it = issue(d)
        pre = json.loads((WORK / "data/domains" / diet / "prelabelled.json").read_text())
        check(12, excl_wid is not None, "a diet batch was pending to collect", excl_wid)
        check(12, r.returncode == 0, "a scope exclusion never blocks the run", r.stdout[-300:])
        check(12, excl_wid not in {e["wid"] for e in pre["entries"]}
              and excl_wid in {x["wid"] for x in pre.get("scope_excluded", [])},
              "collected, kept on file under scope_excluded, not in the library")
        check(12, "## Scope exclusions" in it["body"] and str(excl_wid) in it["body"],
              "listed as a proposal under 'Scope exclusions' in the Issue")
        check(12, not (WORK / f"frontend/public/data/library/{diet}/paper/{excl_wid}.json").exists(),
              "not published")
        # 13 gate failure after regeneration -----------------------------------
        sync_main()
        d = "2026-12-28"
        pub_before, l_before = public_tree_sha("main"), ledger_inr()
        r = run_weekly(d, GROW_GATES=None, GROW_FAIL_GATE="search regression suite")
        it = issue(d)
        led_main = json.loads(sh(["git", "show", "main:data/spend_ledger.json"], cwd=REMOTE).stdout)["cumulative_inr"]
        check(13, r.returncode == 1, "a failed publish gate -> exit 1", r.stdout[-300:])
        check(13, public_tree_sha("main") == pub_before, "site files on main unchanged")
        check(13, led_main >= l_before and remote_head(f"grow/{d}") is not None,
              "paid work on main (checkpoints/bookkeeping) and the run's grow/<date> branch pushed")
        check(13, "GATE FAILURES" in r.stdout and "search regression suite" in r.stdout.split("GATE FAILURES")[-1],
              "one marked failure block at the end of the log")
        check(13, "search regression suite" in it["body"] and "needs-action" in it["labels"],
              "the Issue names the failing gate and needs action")
        # 14 republish -------------------------------------------------------
        sync_main()
        failed = f"grow/{d}"
        pub_before, m, l_before = public_tree_sha("main"), remote_head(), ledger_inr()
        jobs0 = len(list(MOCKST.glob("*.json")))
        r = run_weekly("2026-12-29", GROW_EVENT="workflow_dispatch", GROW_REPUBLISH=failed, GROW_GATES="skip")
        sync_main()
        resolved = json.loads((WORK / "data/grow/resolved_branches.json").read_text())["resolved"]
        it = issue(d)
        check(14, r.returncode == 0 and "REPUBLISH" in r.stdout, "republish exits 0", r.stdout[-400:])
        check(14, remote_head() != m and public_tree_sha("main") != pub_before, "main fast-forwarded, site updated")
        check(14, ledger_inr() == l_before and len(list(MOCKST.glob("*.json"))) == jobs0,
              "nothing spent, submitted or collected")
        check(14, failed in resolved and remote_head(failed) is not None, "branch recorded as resolved and kept")
        check(14, it.get("state") == "closed", "the failed run's Issue is closed", it.get("state"))
        # 10 --------------------------------------------------------------
        e = env("x", NEXT_PUBLIC_SITE_URL="http://127.0.0.1:9")
        r = subprocess.run([PY, "tools/grow/health.py"], cwd=WORK, capture_output=True, text=True, env=e)
        hp = ISSUES / "Daily-health-check-failing.json"
        check(10, r.returncode == 1 and json.loads(hp.read_text())["state"] == "open", "site down -> Issue opened")
        sync_main()
        sh(["npm", "run", "build"], cwd=WORK / "frontend", env={**os.environ, "NEXT_PUBLIC_SITE_URL": SITE})
        r = subprocess.run([PY, "tools/grow/health.py"], cwd=WORK, capture_output=True, text=True, env=env("x"))
        check(10, r.returncode == 0 and json.loads(hp.read_text())["state"] == "closed", "site up -> Issue closed",
              r.stdout[-600:])
        # all -------------------------------------------------------------
        check("all", (ROOT / "data" / "spend_ledger.json").read_bytes() == real_ledger_before,
              "the real ledger was never touched")
        check("all", FAKE_SECRET not in "".join(p.read_text() for p in ISSUES.glob("*.json")),
              "no secret in any Issue")
    finally:
        srv.terminate()
    rep = OUT / "grow-e2e.json"          # never ~/ResearchMap-private (left untouched)
    rep.write_text(json.dumps({"dir": str(OUT), "quick": QUICK, "results": R}, indent=1))
    n_fail = sum(not x["ok"] for x in R)
    print(f"\ne2e: PASS={len(R) - n_fail} FAIL={n_fail} (logs in {OUT})")
    if not QUICK and n_fail == 0:
        write_marker(R)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
