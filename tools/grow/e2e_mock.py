"""End-to-end test of both workflows' logic, offline, with no paid calls.

  .venv/bin/python tools/grow/e2e_mock.py [--quick]

Builds a throwaway clone of the committed HEAD whose `origin` is a local
bare repository (stands in for GitHub), runs tools/grow/run_weekly.py with
mocked OpenAlex and Gemini (GROW_MOCK=1) and the clone's own copy of the
ledger (a temporary ledger: the real one is never touched), Issues written
to files (GROW_ISSUE_DIR), and the live check pointed at a local server of
the clone's build. Scenarios:

  1  week 1: nothing pending → submit a batch per library → gates → main
  2  week 2: collect (papers added, billed at batch rate) → follow-on checks
     (new disagreement flagged "not yet checked") → gates → main
  3  missing secrets (no mock): clean stop, nothing pushed, Issue says what to do
  4  OpenAlex down after last week's batch was collected: stop, work + spend
     record pushed to grow/<date>, main untouched
  5  next run while grow/<date> is unmerged: refuses to spend, Issue says why
  6  a publish gate fails (a broken test is committed): nothing to main,
     branch grow/<date>, Issue carries the gate output
  7  daily health: site down → Issue opened; site up → Issue closed

--quick skips the gates in scenarios 1, 2 (honoured only with GROW_MOCK=1).
Writes a JSON report to ~/ResearchMap-private/launch-qa/grow-e2e.json.
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
         if k not in ("OPENALEX_API_KEY", "GEMINI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN")}
    e.update(GROW_MOCK="1", GROW_MOCK_STATE=str(MOCKST), GROW_ISSUE_DIR=str(ISSUES), GROW_DATE=date,
             GROW_LIVE_WAIT_S="0", NEXT_PUBLIC_SITE_URL=SITE, WEEKLY_BUDGET_INR="25",
             GROW_VERCEL_HOST="",
             PYTHONHASHSEED="0")
    e.update(extra)
    return {k: v for k, v in e.items() if v is not None}


def run_weekly(date, **extra):
    r = subprocess.run([PY, "tools/grow/run_weekly.py"], cwd=WORK, capture_output=True, text=True,
                       env=env(date, **extra), timeout=7200)
    (OUT / f"run-{date}.log").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr)
    return r


def issue(date):
    p = ISSUES / f"Weekly-grow---{date}.json"
    return json.loads(p.read_text()) if p.exists() else None


def ledger():
    return json.loads((WORK / "data" / "spend_ledger.json").read_text())


def ledger_inr():
    return round(ledger()["cumulative_inr"], 4)


def papers(slug):
    return len(json.loads((WORK / "data" / "domains" / slug / "prelabelled.json").read_text())["entries"])


def setup():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    sh(["git", "clone", "-q", "--bare", str(ROOT), str(REMOTE)], cwd=OUT)
    sh(["git", "clone", "-q", str(REMOTE), str(WORK)], cwd=OUT)
    for rel in ("frontend/node_modules", "tools/qa/node_modules"):
        (WORK / rel).symlink_to(ROOT / rel)
    # node_modules symlinks must not make the checkout dirty
    with open(WORK / ".git" / "info" / "exclude", "a") as f:
        f.write("frontend/node_modules\ntools/qa/node_modules\n")


def write_marker(results: list[dict]) -> None:
    """Public copy may describe weekly growth only after a full pass
    (backend/tests/api/test_hardening.py checks this marker)."""
    head = git("rev-parse", "HEAD", cwd=ROOT)
    m = ROOT / "docs" / "releases" / "growth-e2e-passed.json"
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps({
        "what": "tools/grow/e2e_mock.py full run (every publish gate), mocked OpenAlex and Gemini, "
                "temporary ledger, local stand-in for GitHub",
        "date": time.strftime("%Y-%m-%d"), "tested_commit": head, "full": True,
        "passed": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results),
        "scenarios": sorted({str(r["scenario"]) for r in results}),
    }, indent=1) + "\n")


def main() -> int:
    setup()
    srv = subprocess.Popen([PY, "tools/qa/serve.py", PORT], cwd=WORK,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    real_ledger_before = (ROOT / "data" / "spend_ledger.json").read_bytes()
    try:
        gates = {"GROW_GATES": "skip"} if QUICK else {}
        if QUICK:   # the live check needs a built site to look at
            sh(["npm", "run", "build"], cwd=WORK / "frontend", env={**os.environ, "NEXT_PUBLIC_SITE_URL": SITE})
        # 1 ---------------------------------------------------------------
        d1 = "2026-10-12"
        m0 = remote_head()
        r = run_weekly(d1, **gates)
        it = issue(d1)
        pend = {s: (WORK / "data" / "domains" / s / "grow" / "pending.json").exists()
                for s in ("diet-and-mortality", "ml-fairness")}
        check(1, r.returncode == 0, "week 1 exits 0", r.stdout[-600:])
        check(1, remote_head() != m0 and remote_head() == git("rev-parse", "HEAD"),
              "main advanced on the remote (ls-remote == local HEAD)")
        check(1, all(pend.values()), "a batch is pending for each library", pend)
        check(1, it and it["state"] == "open" and "published to main" in it["body"], "one Issue, status published")
        check(1, (WORK / "docs" / "releases" / f"{d1}.json").exists(), "release fingerprint written")
        fpp = WORK / "docs" / "releases" / f"{d1}.json"
        fp = json.loads(fpp.read_text()) if fpp.exists() else {"gates": None}
        check(1, fp["gates"] and all(g["ok"] for g in fp["gates"]), "fingerprint records every gate passing",
              [g for g in fp["gates"] or [] if not g["ok"]])
        if r.returncode != 0:
            raise SystemExit("week 1 failed; see " + str(OUT / f"run-{d1}.log"))
        # 2 ---------------------------------------------------------------
        d2 = "2026-10-19"
        before = {s: papers(s) for s in ("diet-and-mortality", "ml-fairness")}
        submitted = {s: len(json.loads((WORK / "data/domains" / s / "grow/pending.json").read_text())["entries"])
                     for s in before}
        l_before = ledger_inr()
        r = run_weekly(d2, **gates)
        it = issue(d2)
        after = {s: papers(s) for s in ("diet-and-mortality", "ml-fairness")}
        check(2, r.returncode == 0, "week 2 exits 0", r.stdout[-800:])
        check(2, all(after[s] > before[s] for s in after), "papers added to both libraries", (before, after))
        check(2, all(after[s] - before[s] == submitted[s] for s in after),
              "every submitted paper that extracted cleanly was added, nothing else", (before, after, submitted))
        w1 = issue(d1)["body"]
        check(2, all(k in w1 for k in ("duplicate among candidates", "already in library", "rubric: off-domain")),
              "week 1 dropped the planted duplicates and the off-topic record")
        batch_rows = [e for e in ledger()["entries"] if e["stage"].startswith("grow_extract_") and e.get("batch")]
        check(2, batch_rows and ledger_inr() > l_before, "last week's batch billed to the ledger at the batch rate",
              len(batch_rows))
        facts = {l["slug"]: l for l in json.loads((WORK / "frontend/public/data/site-facts.json").read_text())["libraries"]}
        check(2, all(facts[s]["papers"] == after[s] for s in after), "site facts show the new paper counts")
        opps = json.loads((WORK / "frontend/public/data/library/diet-and-mortality/opportunities.json").read_text())["items"]
        flagged = [o for o in opps if o.get("verdict") == "unaudited"]
        check(2, flagged, "a new disagreement is shown as flagged, not yet checked", len(flagged))
        check(2, all(o["consumer"].get("verdict_label") == "Flagged by the system, not yet checked" for o in flagged),
              "flagged label is exact")
        check(2, facts["diet-and-mortality"]["results_total"] == sum(
            1 for o in opps if o.get("verdict") in (None, "genuine")), "flagged pairs do not count in results")
        sh_ = [o for o in opps if o.get("scorer") == "structural_holes"]
        check(2, all(o.get("confirm_status") for o in sh_), "every shown method-transfer lead went through confirmation")
        check(2, it and "Flagged disagreements awaiting your audit" in it["body"] and "- [ ]" in it["body"],
              "Issue lists flagged pairs with an audit checklist")
        check(2, "papers added" in (WORK / "docs" / "CHANGELOG.md").read_text(), "changelog entry written")
        # 3 ---------------------------------------------------------------
        d3 = "2026-10-20"
        m = remote_head()
        r = run_weekly(d3, GROW_MOCK=None, OPENALEX_API_KEY=FAKE_SECRET, GEMINI_API_KEY=None)
        it = issue(d3)
        check(3, r.returncode == 2, "missing secret → clean stop (exit 2)", r.stdout[-400:])
        check(3, remote_head() == m and not git("status", "--porcelain"), "nothing pushed, nothing changed")
        check(3, it and "GEMINI_API_KEY" in it["body"] and "Settings" in it["body"], "Issue says which secret to add")
        check(3, FAKE_SECRET not in (it or {}).get("body", "") and FAKE_SECRET not in r.stdout + r.stderr,
              "the secret that WAS set appears nowhere in the Issue or log")
        # 4 ---------------------------------------------------------------
        d4 = "2026-10-26"
        m = remote_head()
        l_before = ledger_inr()
        r = run_weekly(d4, GROW_MOCK_FAIL="openalex", GROW_GATES="skip")
        it = issue(d4)
        check(4, r.returncode == 2, "OpenAlex down → clean stop (exit 2)", r.stdout[-400:])
        check(4, remote_head() == m, "main untouched on the remote")
        check(4, remote_head(f"grow/{d4}") is not None, f"work pushed to grow/{d4}")
        br_ledger = json.loads(sh(["git", "show", f"grow/{d4}:data/spend_ledger.json"], cwd=REMOTE).stdout)
        check(4, br_ledger["cumulative_inr"] > l_before,
              "the spend recorded before the stop is preserved on the branch")
        check(4, it and "OpenAlex" in it["body"] and "needs-action" in it["labels"], "Issue explains the stop")
        # 5 ---------------------------------------------------------------
        d5 = "2026-11-02"
        git("checkout", "-q", "main")
        git("reset", "-q", "--hard", "origin/main")
        l_before = ledger_inr()
        mock_jobs = len(list(MOCKST.glob("*.json")))
        r = run_weekly(d5, GROW_GATES="skip")
        it = issue(d5)
        check(5, r.returncode == 2 and "unmerged growth branch" in r.stdout, "refuses to run with grow/* unmerged")
        check(5, ledger_inr() == l_before and len(list(MOCKST.glob("*.json"))) == mock_jobs,
              "nothing spent, nothing submitted")
        check(5, it and f"grow/{d4}" in it["body"], "Issue names the branch to merge or delete")
        # 6 ---------------------------------------------------------------
        git("merge", "-q", "--no-edit", f"origin/grow/{d4}")
        git("push", "-q", "origin", "main")
        git("push", "-q", "origin", "--delete", f"grow/{d4}")
        (WORK / "backend/tests/test_e2e_broken.py").write_text("def test_broken():\n    assert False\n")
        git("add", "-A")
        git("-c", "user.name=e2e", "-c", "user.email=e2e@example.invalid", "commit", "-q", "-m", "e2e: broken test")
        git("push", "-q", "origin", "main")
        m = remote_head()
        d6 = "2026-11-09"
        r = run_weekly(d6)
        it = issue(d6)
        check(6, r.returncode == 1, "a failing gate → exit 1", r.stdout[-400:])
        check(6, remote_head() == m, "nothing committed to main")
        check(6, remote_head(f"grow/{d6}") is not None, f"work pushed to grow/{d6}")
        check(6, it and "❌ full tests" in it["body"] and "test_broken" in it["body"],
              "Issue shows which gate failed, with its output")
        # 7 ---------------------------------------------------------------
        e = env("x", NEXT_PUBLIC_SITE_URL="http://127.0.0.1:9")
        r = subprocess.run([PY, "tools/grow/health.py"], cwd=WORK, capture_output=True, text=True, env=e)
        hp = ISSUES / "Daily-health-check-failing.json"
        check(7, r.returncode == 1 and hp.exists() and json.loads(hp.read_text())["state"] == "open",
              "site down → health Issue opened", r.stdout[-300:])
        git("checkout", "-q", "main")
        sh(["npm", "run", "build"], cwd=WORK / "frontend", env={**os.environ, "NEXT_PUBLIC_SITE_URL": SITE})
        r = subprocess.run([PY, "tools/grow/health.py"], cwd=WORK, capture_output=True, text=True, env=env("x"))
        check(7, r.returncode == 0 and json.loads(hp.read_text())["state"] == "closed",
              "site up → health Issue closed", r.stdout[-600:])
        # global -----------------------------------------------------------
        check("all", (ROOT / "data" / "spend_ledger.json").read_bytes() == real_ledger_before,
              "the real ledger was never touched")
        allbodies = "".join(p.read_text() for p in ISSUES.glob("*.json"))
        check("all", FAKE_SECRET not in allbodies, "no secret in any Issue")
    finally:
        srv.terminate()
    rep = Path.home() / "ResearchMap-private" / "launch-qa" / "grow-e2e.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps({"dir": str(OUT), "quick": QUICK, "results": R}, indent=1))
    n_fail = sum(not x["ok"] for x in R)
    print(f"\ne2e: PASS={len(R) - n_fail} FAIL={n_fail} (logs in {OUT})")
    if not QUICK and n_fail == 0:
        write_marker(R)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
