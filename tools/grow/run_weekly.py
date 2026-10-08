"""Weekly growth run (called by .github/workflows/weekly-grow.yml).

  python tools/grow/run_weekly.py

Order: guards → Phase 1 collect + follow-on checks → regenerate site data →
Phase 2 submit → release fingerprint + changelog → publish gates →
  all pass: commit to main, push (fast-forward), live check after a wait
  any fail: commit to branch grow/<date>, push it, publish nothing to main
→ ONE Issue per run ("Weekly grow — <date>"), opened or updated.

Clean stops (missing secret, lifetime ceiling, model unavailable, OpenAlex
or Gemini errors, an unmerged grow/* branch): nothing reaches main. If the
run had already changed bookkeeping (ledger, batch state), that work goes to
grow/<date> so no recorded spend is ever lost, and later runs refuse to
spend until that branch is merged or deleted.

Environment: WEEKLY_BUDGET_INR (default 25), NEXT_PUBLIC_SITE_URL (default
https://researchmap-one.vercel.app), GROW_DATE (override, tests),
GROW_LIVE_WAIT_S (default 300), GROW_MOCK=1 (offline test: mocked clients;
refuses any remote that is not a local path), GROW_ISSUE_DIR (tests).
Secrets OPENALEX_API_KEY / GEMINI_API_KEY are read from the environment and
never printed; every message is passed through `redact`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "grow"))

import issues  # noqa: E402

PY = sys.executable
FE = ROOT / "frontend"
DATA = FE / "public" / "data"
SITE = (os.environ.get("NEXT_PUBLIC_SITE_URL") or "https://researchmap-one.vercel.app").rstrip("/")
MOCK = os.environ.get("GROW_MOCK") == "1"
LOG: list[str] = []


def redact(text: str) -> str:
    text = str(text)
    for k in ("OPENALEX_API_KEY", "GEMINI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(k)
        if v and len(v) > 4:
            text = text.replace(v, "***")
    return re.sub(r"(?i)\b(api_key|key|token)=[^&\s'\"]+", r"\1=***", text)


def say(msg: str) -> None:
    msg = redact(msg)
    LOG.append(msg)
    print(msg, flush=True)


def sh(cmd: list[str], *, cwd: Path = ROOT, check: bool = True, timeout: int | None = None,
       env: dict | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **(env or {})})
    if check and r.returncode != 0:
        raise RuntimeError(redact(f"{' '.join(cmd[:4])} exited {r.returncode}: "
                                  f"{(r.stderr or r.stdout).strip()[-600:]}"))
    return r


def git(*a: str, check: bool = True) -> str:
    return sh(["git", *a], check=check).stdout.strip()


# ---------------------------------------------------------------------------

def guards() -> None:
    from backend.app.grow.core import GrowStop
    if git("status", "--porcelain"):
        raise GrowStop("the checkout is not clean", "Re-run the workflow; if it repeats, look at the run log.")
    url = git("remote", "get-url", "origin")
    if MOCK and not (url.startswith("/") or url.startswith("file:")):
        raise GrowStop("mock run against a real remote", "Mock runs may only push to a local test remote.")
    heads = git("ls-remote", "--heads", "origin", "grow/*")
    if heads:
        names = [ln.split("refs/heads/", 1)[-1] for ln in heads.splitlines()]
        raise GrowStop(
            f"unmerged growth branch(es): {', '.join(names)}",
            "A previous run's work (including its spend record) is on the branch(es) above and not "
            "on main. Read that run's Issue, then either merge the branch into main or delete it "
            "(only if its Issue says nothing was spent). Growth stays paused until then.")


def items_snapshot() -> dict[str, dict[str, dict]]:
    out = {}
    for slug, d in (("llm-calibration", DATA), ("diet-and-mortality", DATA / "library" / "diet-and-mortality"),
                    ("ml-fairness", DATA / "library" / "ml-fairness")):
        items = json.loads((d / "opportunities.json").read_text())["items"]
        out[slug] = {it["slug"]: {"headline": it["consumer"]["headline"], "verdict": it.get("verdict"),
                                  "kind": it["consumer"]["kind_id"]} for it in items}
    return out


def ledger_inr() -> tuple[float, float]:
    from backend.app.extraction.spend_ledger import SpendLedger
    s = SpendLedger.load().snapshot()
    return s["cumulative_inr"], s["cap_inr"]


def regenerate() -> None:
    say("regenerate: snapshots, docs numbers, share images")
    sh([PY, "-m", "backend.app.api.multi_library_export"])
    sh([PY, "-m", "backend.app.corpus.doc_numbers"])
    sh([PY, "-m", "backend.app.api.multi_library_export"])       # findings.json picks up the docs
    # Share images only when what they show changed (PNG bytes churn otherwise).
    facts = {l["slug"]: l for l in json.loads((DATA / "site-facts.json").read_text())["libraries"]}
    mp = FE / "public" / "og" / "manifest.json"
    og = json.loads(mp.read_text()) if mp.exists() else {}
    stale = (og.get("total_papers") != sum(l["papers"] for l in facts.values())
             or any((og.get("libraries") or {}).get(s, {}).get(k) != f[k]
                    for s, f in facts.items() for k in ("papers", "claims_read", "built")))
    if stale:
        sh([PY, "tools/og/make_og_images.py"])


def _serve(fn):
    port = "8799"
    srv = subprocess.Popen([PY, "tools/qa/serve.py", port], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        return fn(f"http://127.0.0.1:{port}")
    finally:
        srv.terminate()


def gates() -> list[dict]:
    if MOCK and os.environ.get("GROW_GATES") == "skip":      # offline e2e only
        say("gates skipped (mock run, GROW_GATES=skip)")
        return [{"gate": "(skipped: mock run)", "ok": True, "tail": ""}]
    t = "backend/tests/api/"
    steps = [
        ("full tests", [PY, "-m", "pytest", "backend/tests", "-q"], ROOT),
        ("typecheck", ["npm", "run", "typecheck"], FE),
        ("production build (+ consistency before and after)", ["npm", "run", "build"], FE),
        ("docs check", [PY, "-m", "backend.app.corpus.doc_numbers", "--check"], ROOT),
        ("consistency script", ["node", "scripts/consistency.mjs", "--built"], FE),
        ("banned-phrase tests", [PY, "-m", "pytest", "-q", t + "test_rendered_output.py", t + "test_language.py",
                                 t + "test_public_claims.py", t + "test_contradiction_titles.py"], ROOT),
        ("search regression suite", [PY, "-m", "pytest", "-q", t + "test_search.py", t + "test_search_parity.py",
                                     t + "test_search_per_library.py", t + "test_search_typing.py",
                                     t + "test_cross_library_collisions.py"], ROOT),
        ("hardening tests (Part 3)", [PY, "-m", "pytest", "-q", t + "test_hardening.py"], ROOT),
    ]
    res = []
    for name, cmd, cwd in steps:
        r = sh(cmd, cwd=cwd, check=False, timeout=3600)
        res.append({"gate": name, "ok": r.returncode == 0,
                    "tail": "" if r.returncode == 0 else redact((r.stdout + r.stderr).strip()[-800:])})
        say(f"gate {'PASS' if r.returncode == 0 else 'FAIL'}: {name}")
    built = all(g["ok"] for g in res[:3])
    for name, script, extra in (("browser hunt (Part 3)", "tools/qa/hunt.py", []),
                                ("smoke checks on the build", "tools/qa/smoke.py", ["--engines=chromium"])):
        if not built:
            res.append({"gate": name, "ok": False, "tail": "not run: the build failed"})
            continue
        r = _serve(lambda base: sh([PY, script, *extra] + ([base] if "smoke" in script else []),
                                   check=False, timeout=3600, env={"HUNT_BASE": base}))
        res.append({"gate": name, "ok": r.returncode == 0,
                    "tail": "" if r.returncode == 0 else redact(r.stdout.strip()[-800:])})
        say(f"gate {'PASS' if r.returncode == 0 else 'FAIL'}: {name}")
    return res


def fingerprint(date: str, gate_res: list[dict] | None, ledger: tuple[float, float]) -> Path:
    facts = {l["slug"]: l for l in json.loads((DATA / "site-facts.json").read_text())["libraries"]}
    libs = {}
    for slug, d in (("llm-calibration", DATA), ("diet-and-mortality", DATA / "library" / "diet-and-mortality"),
                    ("ml-fairness", DATA / "library" / "ml-fairness")):
        raw = (d / "opportunities.json").read_bytes()
        items = json.loads(raw)["items"]
        libs[slug] = {"papers": facts[slug]["papers"], "results": facts[slug]["results_total"],
                      "set_aside": facts[slug]["set_aside_total"],
                      "flagged_not_checked": sum(1 for i in items if i.get("verdict") == "unaudited"),
                      "opportunities_sha256": hashlib.sha256(raw).hexdigest()}
    p = ROOT / "docs" / "releases" / f"{date}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "date": date, "parent_commit": git("rev-parse", "HEAD"), "libraries": libs,
        "ledger_inr": round(ledger[0], 4), "ledger_cap_inr": ledger[1],
        "gates": [{"gate": g["gate"], "ok": g["ok"]} for g in gate_res] if gate_res else None,
    }, indent=1) + "\n")
    return p


def changelog(date: str, lines: list[str]) -> None:
    p = ROOT / "docs" / "CHANGELOG.md"
    head = "# Changelog\n\nOne entry per weekly growth run (newest first).\n"
    old = p.read_text() if p.exists() else head
    body = old[len(head):] if old.startswith(head) else old
    p.write_text(head + f"\n## {date}\n\n" + "\n".join(f"- {l}" for l in lines) + "\n" + body)


def diff_items(before, after) -> dict:
    out = {}
    for slug in after:
        b, a = before.get(slug, {}), after[slug]
        new = [s for s in a if s not in b]
        out[slug] = {
            "new_results": [a[s]["headline"] for s in new if a[s]["verdict"] in (None, "genuine")],
            "new_flagged": [(s, a[s]["headline"]) for s in new if a[s]["verdict"] == "unaudited"],
            "new_set_aside": [a[s]["headline"] for s in new if a[s]["verdict"] not in (None, "genuine", "unaudited")],
            "removed": [b[s]["headline"] for s in b if s not in a],
        }
    return out


def issue_body(date, status, *, p1, p2, diff, spent, ledger, budget, gate_res, branch=None,
               stop=None, live=None) -> str:
    L = [f"**Status:** {status}", ""]
    if stop:
        L += ["## What stopped the run", "", stop[0], "", "## What you need to do", "", stop[1], ""]
    L += ["## Papers added this week", ""]
    for r in p1:
        if r.get("status") == "collected":
            L.append(f"- {r['slug']}: {len(r['added'])} added"
                     + (f", {len(r['failed'])} failed extraction" if r["failed"] else ""))
            L += [f"  - {t}" for t in r.get("added_titles", [])]
        else:
            L.append(f"- {r['slug']}: {r.get('status', 'not reached')}")
    L += ["", "## Submitted for next week", ""]
    for r in p2:
        L.append(f"- {r['slug']}: {r.get('submitted', 0)} papers (projected ₹{r.get('projected_inr', 0):.2f}; "
                 f"{r.get('candidates', 0)} candidates, dropped: {json.dumps(r.get('dropped', {}))})"
                 + (f" — {r['note']}" if r.get("note") else ""))
    L += ["", "## Spend", "",
          f"- recorded this run: ₹{spent:.2f} (includes last week's batch at the batch rate)",
          f"- new commitments this run (projections, padded): ₹{budget.committed:.2f} of the ₹{budget.weekly_inr:.0f} weekly budget",
          f"- lifetime ledger: ₹{ledger[0]:.2f} of ₹{ledger[1]:.0f}", ""]
    flagged = [(s, h, slug) for slug, d in (diff or {}).items() for s, h in d["new_flagged"]]
    if diff:
        L += ["## New on the site", ""]
        for slug, d in diff.items():
            if d["new_results"] or d["new_set_aside"] or d["removed"]:
                L.append(f"- {slug}: {len(d['new_results'])} new results, {len(d['new_set_aside'])} set aside, "
                         f"{len(d['removed'])} no longer shown")
                L += [f"  - {h}" for h in d["new_results"][:20]]
        if not any(d["new_results"] or d["new_set_aside"] or d["removed"] for d in diff.values()):
            L.append("- nothing new")
        L.append("")
    L += ["## Flagged disagreements awaiting your audit", ""]
    if flagged:
        L += ["These show on the site as “Flagged by the system, not yet checked” and do not count in any "
              "headline. For each one:", ""]
        for s, h, slug in flagged:
            L.append(f"- [ ] **{slug}** — [{h}]({SITE}/gap/{s}/)")
        L += ["", "Audit checklist per pair: open the card; read both abstracts (linked on the card); decide "
              "`genuine` (same question, comparable populations, opposite findings), `artifact` (they measure "
              "different things) or `duplicate`; add the verdict with a one-line reason to "
              "`data/domains/<library>/reasoning/contradiction_audit.json` (see docs/OPERATIONS.md); commit.", ""]
    else:
        L += ["- none this week", ""]
    if gate_res:
        L += ["## Publish gates", ""] + [f"- {'✅' if g['ok'] else '❌'} {g['gate']}" for g in gate_res]
        for g in gate_res:
            if not g["ok"] and g["tail"]:
                L += ["", f"<details><summary>{g['gate']} output</summary>", "", "```", g["tail"], "```", "</details>"]
        L.append("")
    if branch:
        L += [f"Nothing was published. This run's work is on branch `{branch}`. Growth is paused until it is "
              "merged into main or deleted (see docs/OPERATIONS.md, “A run failed”).", ""]
    if live is not None:
        L += ["## Live check after publishing", "", "```", live[1][-1500:], "```", ""]
        if not live[0]:
            L += ["**The live site failed its checks.** One-click rollback: Vercel dashboard → the project → "
                  "Deployments → the deployment before this one → ⋯ → **Promote to Production**. Nothing was "
                  "auto-reverted.", ""]
    L += ["<details><summary>Run log</summary>", "", "```", "\n".join(LOG[-80:]), "```", "</details>"]
    return redact("\n".join(L))


# ---------------------------------------------------------------------------

def main() -> int:
    from backend.app.grow import core
    from backend.app.grow.clients import make_clients
    date = os.environ.get("GROW_DATE") or dt.datetime.now(dt.timezone.utc).date().isoformat()
    ref = dt.date.fromisoformat(date)
    title = f"Weekly grow — {date}"
    budget = core.Budget(float(os.environ.get("WEEKLY_BUDGET_INR", "25")))
    p1: list[dict] = []
    p2: list[dict] = []
    diff = None
    l0 = (0.0, 0.0)
    try:
        guards()
        l0 = ledger_inr()
        if l0[0] >= l0[1]:
            raise core.GrowStop(f"lifetime ledger ceiling reached (₹{l0[0]:.2f} of ₹{l0[1]:.0f})",
                                "Growth is paused: the ledger has no headroom. It resumes only if you "
                                "raise the ledger ceiling yourself (docs/OPERATIONS.md).")
        cl = make_clients()
        before = items_snapshot()
        for slug in core.GROW_SLUGS:
            try:
                r = core.collect(slug, cl, ref=ref)
                say(f"collect {slug}: {r['status']} added={len(r['added'])}")
                r["followon"] = core.followon(slug, cl, budget)
                say(f"follow-on {slug}: {json.dumps(r['followon'], default=str)[:400]}")
            except core.GrowStop:
                raise
            except Exception as e:  # noqa: BLE001
                raise core.GrowStop(f"Gemini or data error while collecting {slug}: {type(e).__name__}: {e}",
                                    "Usually transient (Gemini outage or quota). Re-run “Weekly grow” from the "
                                    "Actions tab later; the saved batch state means nothing is paid twice.") from None
            p1.append(r)
        regenerate()
        for slug in core.GROW_SLUGS:
            errs: list[str] = []
            try:
                r = core.submit(slug, cl, budget, ref=ref, errors=errs)
            except Exception as e:  # noqa: BLE001
                from backend.app.extraction.spend_gate import SpendGateRefused
                if isinstance(e, SpendGateRefused):
                    raise core.GrowStop(f"lifetime ledger ceiling would be exceeded: {e}",
                                        "Growth is paused: next week's batch does not fit the ledger's headroom. "
                                        "It resumes only if you raise the ledger ceiling yourself.") from None
                raise core.GrowStop(f"Gemini error while submitting {slug}: {type(e).__name__}: {e}",
                                    "Usually transient. Re-run “Weekly grow” from the Actions tab later.") from None
            if errs:
                raise core.GrowStop("OpenAlex errors: " + "; ".join(errs[:5]),
                                    "Check that the OPENALEX_API_KEY secret is valid and that api.openalex.org "
                                    "is up, then re-run “Weekly grow” from the Actions tab.")
            say(f"submit {slug}: {r.get('submitted', 0)} papers, projected ₹{r.get('projected_inr', 0):.2f}")
            p2.append(r)
        diff = diff_items(before, items_snapshot())
    except core.GrowStop as stop:
        say(f"STOP: {stop.what}")
        l1 = ledger_inr() if l0[1] else l0
        branch = None
        if git("status", "--porcelain"):
            branch = publish_branch(date, f"weekly grow {date}: stopped ({stop.what[:60]})")
        body = issue_body(date, f"stopped cleanly — nothing published to main", p1=p1, p2=p2, diff=diff,
                          spent=l1[0] - l0[0], ledger=l1, budget=budget, gate_res=None, branch=branch,
                          stop=(redact(stop.what), stop.action))
        say(f"issue: {issues.upsert(title, body, ['weekly-grow', 'needs-action'])}")
        return 2

    l1 = ledger_inr()
    added = {r["slug"]: len(r.get("added", [])) for r in p1}
    changelog(date, [f"{s}: {n} papers added" for s, n in added.items()]
              + [f"{s}: {len(d['new_results'])} new results, {len(d['new_flagged'])} flagged disagreements "
                 "(not yet checked)" for s, d in diff.items() if s in core.GROW_SLUGS]
              + [f"spend recorded ₹{l1[0] - l0[0]:.2f}; lifetime ₹{l1[0]:.2f} of ₹{l1[1]:.0f}"])
    fingerprint(date, None, l1)
    gate_res = gates()
    fingerprint(date, gate_res, l1)
    ok = all(g["ok"] for g in gate_res)
    live = None
    if ok:
        sha = publish_main(date)
        status = f"published to main ({sha[:7]})"
        wait = int(os.environ.get("GROW_LIVE_WAIT_S", "300"))
        say(f"waiting {wait}s for the deployment")
        time.sleep(wait)
        r = sh([PY, "tools/live-check.py", SITE], check=False, timeout=600)
        live = (r.returncode == 0, redact(r.stdout + r.stderr))
        if not live[0]:
            status += " — LIVE CHECK FAILED"
        branch = None
    else:
        branch = publish_branch(date, f"weekly grow {date}: publish gates failed")
        status = "publish gates failed — nothing published to main"
    body = issue_body(date, status, p1=p1, p2=p2, diff=diff, spent=l1[0] - l0[0], ledger=l1,
                      budget=budget, gate_res=gate_res, branch=branch, live=live)
    labels = ["weekly-grow"] + ([] if ok and (live is None or live[0]) else ["needs-action"])
    say(f"issue: {issues.upsert(title, body, labels)}")
    return 0 if ok and (live is None or live[0]) else 1


def _identity() -> list[str]:
    return ["-c", "user.name=researchmap-bot", "-c", "user.email=researchmap-bot@users.noreply.github.com"]


def publish_main(date: str) -> str:
    git("add", "-A")
    git(*_identity(), "commit", "-q", "-m", f"weekly grow {date}\n\nAutomated by .github/workflows/weekly-grow.yml; "
        f"see docs/releases/{date}.json and docs/CHANGELOG.md.")
    r = sh(["git", "push", "origin", "HEAD:main"], check=False)
    local = git("rev-parse", "HEAD")
    remote = git("ls-remote", "origin", "refs/heads/main").split()[0:1]
    if r.returncode != 0 or remote != [local]:
        raise RuntimeError(f"push to main failed (exit {r.returncode}); remote main is {remote}")
    say(f"pushed main {local[:7]} (ls-remote agrees)")
    return local


def publish_branch(date: str, msg: str) -> str:
    branch = f"grow/{date}"
    git("checkout", "-q", "-B", branch)
    git("add", "-A")
    git(*_identity(), "commit", "-q", "-m", msg)
    r = sh(["git", "push", "origin", f"{branch}:{branch}"], check=False)
    local = git("rev-parse", "HEAD")
    remote = git("ls-remote", "origin", f"refs/heads/{branch}").split()[0:1]
    if r.returncode != 0 or remote != [local]:
        say(f"WARNING: push of {branch} failed (exit {r.returncode}); work exists only in this runner")
    else:
        say(f"pushed {branch} {local[:7]} (ls-remote agrees)")
    return branch


if __name__ == "__main__":
    raise SystemExit(main())
