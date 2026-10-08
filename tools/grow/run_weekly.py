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

def guards() -> str | None:
    """Clean checkout and (mock) local remote are required. An unmerged
    grow/* branch (a failed publish gate) does not stop the run: it only
    suppresses NEW spending until the owner merges or deletes it. Returns
    that reason, or None."""
    from backend.app.grow.core import GrowStop
    if git("status", "--porcelain"):
        raise GrowStop("the checkout is not clean", "Re-run the workflow; if it repeats, look at the run log.")
    url = git("remote", "get-url", "origin")
    if MOCK and not (url.startswith("/") or url.startswith("file:")):
        raise GrowStop("mock run against a real remote", "Mock runs may only push to a local test remote.")
    heads = git("ls-remote", "--heads", "origin", "grow/*")
    if heads:
        names = [ln.split("refs/heads/", 1)[-1] for ln in heads.splitlines()]
        return (f"an earlier run's publish gates failed (branch {', '.join(names)}): collecting what was "
                "already paid for, starting nothing new until that branch is merged into main or deleted")
    return None


def paused() -> bool:
    p = ROOT / "config" / "growth.json"
    return bool(json.loads(p.read_text()).get("paused")) if p.exists() else False


def libs_built() -> list[tuple[str, Path]]:
    m = json.loads((DATA / "libraries.json").read_text())["libraries"]
    return [(l["slug"], DATA if l["snapshot_path"] == "/data" else DATA / l["snapshot_path"].removeprefix("/data/"))
            for l in m]


def items_snapshot() -> dict[str, dict[str, dict]]:
    out = {}
    for slug, d in libs_built():
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
    # Build first: the rendered-output tests and the browser checks need it.
    steps = [
        ("typecheck", ["npm", "run", "typecheck"], FE),
        ("production build (+ consistency before and after)", ["npm", "run", "build"], FE),
        ("full tests", [PY, "-m", "pytest", "backend/tests", "-q"], ROOT),
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
    built = res[1]["ok"]
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
    for slug, d in libs_built():
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
               stop=None, live=None, money=None, builds=None, note=None) -> str:
    L = [f"**Status:** {status}", ""]
    if note:
        L += [f"> {note}", ""]
    if stop:
        L += ["## What stopped the run", "", stop[0], "", "## What you need to do", "", stop[1], ""]
    if money:
        L += ["## Money", "",
              f"- remaining: **₹{money['remaining_inr']:.2f}** of the ₹{money['ceiling_inr']:.0f} ceiling "
              f"(config/money.json; ledger ₹{money['ledger_inr']:.2f}"
              + (f", console figure ₹{money['console_spent_inr']} as of {money['console_spent_date']}"
                 if money.get("console_spent_inr") is not None else "") + ")",
              f"- weeks left in the growth horizon: {money.get('weeks_left')}; this week's budget: "
              f"₹{budget.weekly_inr:.2f}",
              f"- recorded this run: ₹{spent:.2f} (includes last week's batches at the batch rate)",
              f"- new commitments this run (padded projections): ₹{budget.committed:.2f}", ""]
    L += ["## Papers added this week", ""]
    for r in p1:
        if r.get("status") == "collected":
            L.append(f"- {r['slug']}: {len(r['added'])} added"
                     + (f", {len(r['failed'])} failed extraction" if r["failed"] else ""))
            L += [f"  - {t}" for t in r.get("added_titles", [])]
        else:
            L.append(f"- {r['slug']}: {r.get('status', 'not reached')}")
    if not p1:
        L.append("- none")
    if builds:
        L += ["", "## New libraries", ""] + [f"- {b['slug']}: {b.get('status')}" + (
            f" — {b['detail']}" if b.get("detail") else "") for b in builds]
    L += ["", "## Submitted for next week", ""]
    for r in p2:
        L.append(f"- {r['slug']}: {r.get('submitted', 0)} papers (projected ₹{r.get('projected_inr', 0):.2f}; "
                 f"{r.get('candidates', 0)} candidates, dropped: {json.dumps(r.get('dropped', {}))})"
                 + (f" — {r['note']}" if r.get("note") else ""))
    if not p2:
        L.append("- nothing")
    L += ["", f"Lifetime ledger: ₹{ledger[0]:.2f}.", ""]
    flagged = [(s_, h, slug) for slug, d in (diff or {}).items() for s_, h in d["new_flagged"]]
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
        for s_, h, slug in flagged:
            L.append(f"- [ ] **{slug}** — [{h}]({SITE}/gap/{s_}/)")
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
        L += [f"Nothing was published to the site. This run's work is on branch `{branch}`. Until it is merged "
              "into main or deleted, weekly runs collect what was already paid for but start nothing new "
              "(see docs/OPERATIONS.md, “A run failed”).", ""]
    if live is not None:
        L += ["## Live check after publishing", "", "```", live[1][-1500:], "```", ""]
        if not live[0]:
            L += ["**The live site failed its checks.** One-click rollback: Vercel dashboard → the project → "
                  "Deployments → the deployment before this one → ⋯ → **Promote to Production**. Nothing was "
                  "auto-reverted.", ""]
    L += ["<details><summary>Run log</summary>", "", "```", "\n".join(LOG[-80:]), "```", "</details>"]
    return redact("\n".join(L))


BUDGET_EXHAUSTED_ACTION = (
    "No new spending until there is money. The site stays as it is, and batches already submitted are still "
    "collected. To continue, either (a) open the Google Cloud console's billing page, read what has actually "
    "been spent, and enter it in config/money.json as console_spent_inr with today's date as "
    "console_spent_date (the ledger rounds projections up, so this usually frees some money), or (b) add money "
    "to the account and raise account_total_inr in config/money.json. Commit the change; the next weekly run "
    "picks it up.")


# ---------------------------------------------------------------------------

def main() -> int:
    from backend.app.extraction import money
    from backend.app.grow import core, queued
    from backend.app.grow.clients import make_clients
    date = os.environ.get("GROW_DATE") or dt.datetime.now(dt.timezone.utc).date().isoformat()
    ref = dt.date.fromisoformat(date)
    title = f"Weekly grow — {date}"
    p1: list[dict] = []
    p2: list[dict] = []
    builds: list[dict] = []
    diff = None
    l0 = (0.0, 0.0)
    budget = core.Budget(0.0)
    mstat: dict = {}
    note = None
    try:
        hold = guards()
        if paused():
            body = issue_body(date, "paused — nothing collected, spent or published", p1=[], p2=[], diff=None,
                              spent=0.0, ledger=ledger_inr(), budget=budget, gate_res=None,
                              note="config/growth.json has paused: true. Set it to false to resume.")
            say(f"issue: {issues.upsert(title, body, ['weekly-grow'])}")
            return 0
        l0 = ledger_inr()
        mstat = money.status(ref)
        weekly = mstat.get("weekly_budget_inr", 0.0)
        if os.environ.get("WEEKLY_BUDGET_INR"):        # optional owner override: can only lower it
            weekly = min(weekly, float(os.environ["WEEKLY_BUDGET_INR"]))
        exhausted = mstat["remaining_inr"] < 1.0
        if hold or exhausted:
            weekly = 0.0
            note = hold or "Budget exhausted: " + BUDGET_EXHAUSTED_ACTION
        budget = core.Budget(weekly)
        say(f"money: remaining ₹{mstat['remaining_inr']:.2f}, weeks left {mstat.get('weeks_left')}, "
            f"weekly budget ₹{weekly:.2f}")
        cl = make_clients()
        before = items_snapshot()
        # Phase 1: collect last week's growth batches + budget-gated follow-on checks
        for slug in core.grow_slugs():
            try:
                r = core.collect(slug, cl, ref=ref)
                say(f"collect {slug}: {r['status']} added={len(r['added'])}")
                r["followon"] = core.followon(slug, cl, budget)
                say(f"follow-on {slug}: {json.dumps(r['followon'], default=str)[:400]}")
                if r["followon"].get("money_refused"):
                    note = "Budget exhausted: " + BUDGET_EXHAUSTED_ACTION
                    budget = core.Budget(0.0)          # nothing new for the rest of this run
            except Exception as e:  # noqa: BLE001
                raise core.GrowStop(f"Gemini or data error while collecting {slug}: {type(e).__name__}: {e}",
                                    "Usually transient (retried with backoff already). Nothing is lost: the "
                                    "saved batch state and the ledger were committed, and next week's run "
                                    "resumes. To retry sooner, run “Weekly grow” from the Actions tab.") from None
            p1.append(r)
        # Libraries being built by the workflow: finish them (already paid for)
        for lib in queued.building():
            try:
                r = queued.finish(lib, cl, mock=cl.mock)
            except Exception as e:  # noqa: BLE001
                raise core.GrowStop(f"error while finishing the {lib['slug']} library: {type(e).__name__}: {e}",
                                    "Usually transient. The batch state was saved; next week's run resumes.") from None
            say(f"build {lib['slug']}: {r.get('status')}")
            builds.append({"slug": lib["slug"], "status": r.get("status"),
                           "detail": "new library published" if r.get("status") == "built" else None})
        regenerate()
        # Phase 2: new candidates for every growing library, budget shared round-robin
        prepared, errs = {}, []
        if budget.weekly_inr > 0:
            for slug in core.grow_slugs():
                prepared[slug] = core.prepare(slug, cl, ref=ref, errors=errs)
            if errs:
                raise core.GrowStop("OpenAlex errors (after retries): " + "; ".join(errs[:5]),
                                    "Check that the OPENALEX_API_KEY secret is valid and that api.openalex.org is "
                                    "up. Nothing is lost; next week's run tries again.")
            papers = {s_: len(json.loads((ROOT / "data/domains" / s_ / "prelabelled.json").read_text())["entries"])
                      for s_ in prepared}
            picked = core.allocate(prepared, budget, papers)
            for slug, pr in prepared.items():
                try:
                    r = core.submit(slug, cl, budget, picked[slug], ref=ref)
                except Exception as e:  # noqa: BLE001
                    from backend.app.extraction.spend_gate import SpendGateRefused
                    if isinstance(e, SpendGateRefused):
                        note = "Budget exhausted: " + BUDGET_EXHAUSTED_ACTION
                        r = {"slug": slug, "submitted": 0, "note": "refused by the money rule"}
                    else:
                        raise core.GrowStop(f"Gemini error while submitting {slug}: {type(e).__name__}: {e}",
                                            "Usually transient; next week's run tries again.") from None
                r.update(candidates=pr["candidates"], dropped=pr["dropped"], note=r.get("note") or pr.get("note"))
                say(f"submit {slug}: {r.get('submitted', 0)} papers, projected ₹{r.get('projected_inr', 0):.2f}")
                p2.append(r)
        # A queued library, if the money rule says it is affordable (one at a time)
        if budget.weekly_inr > 0 and not queued.building():
            rem = money.status(ref)["remaining_inr"] - budget.committed
            for lib in registry_queued():
                queued.open_fulltext(lib, cl)
                proj = queued.projection_inr(lib)
                if money.queued_affordable(proj, rem, budget.weekly_inr, money.load()):
                    try:
                        r = queued.start(lib, cl)
                    except Exception as e:  # noqa: BLE001
                        from backend.app.extraction.spend_gate import SpendGateRefused
                        if not isinstance(e, SpendGateRefused):
                            raise
                        builds.append({"slug": lib["slug"], "status": "waiting for money",
                                       "detail": "refused by the money rule"})
                        break
                    say(f"queued {lib['slug']}: submitted {r.get('submitted')} papers, projected ₹{proj:.2f}")
                    builds.append({"slug": lib["slug"], "status": "building (extraction submitted)",
                                   "detail": f"projected ₹{proj:.2f}; finishes next week"})
                else:
                    builds.append({"slug": lib["slug"], "status": "waiting for money",
                                   "detail": f"needs ₹{proj * 1.5 + 4 * budget.weekly_inr:.2f} "
                                             f"(projection x1.5 + 4 weeks of growth), ₹{rem:.2f} remains"})
                break
        diff = diff_items(before, items_snapshot())
    except Exception as exc:  # noqa: BLE001  (GrowStop or anything unexpected)
        stop = exc if isinstance(exc, core.GrowStop) else core.GrowStop(
            f"unexpected error: {type(exc).__name__}: {exc}",
            "Open this run's log in the Actions tab. The site was not changed; anything already paid for "
            "was committed as bookkeeping and the next run resumes.")
        say(f"STOP: {stop.what}")
        l1 = ledger_inr() if l0[1] else l0
        kept = publish_bookkeeping(date, f"weekly grow {date}: bookkeeping only ({stop.what[:50]})")
        body = issue_body(date, "stopped cleanly — the site was not changed", p1=p1, p2=p2, diff=diff,
                          spent=l1[0] - l0[0], ledger=l1, budget=budget, gate_res=None,
                          stop=(redact(stop.what), stop.action), money=mstat or None, builds=builds,
                          note=(f"Paid work committed to main as bookkeeping ({kept})." if kept else None))
        say(f"issue: {issues.upsert(title, body, ['weekly-grow', 'needs-action'])}")
        return 2

    l1 = ledger_inr()
    mstat = money.status(ref)
    added = {r["slug"]: len(r.get("added", [])) for r in p1}
    changelog(date, [f"{s_}: {n} papers added" for s_, n in added.items()]
              + [f"new library {b['slug']}: {b['status']}" for b in builds]
              + [f"{s_}: {len(d['new_results'])} new results, {len(d['new_flagged'])} flagged disagreements "
                 "(not yet checked)" for s_, d in diff.items() if s_ != "llm-calibration"]
              + [f"spend recorded ₹{l1[0] - l0[0]:.2f}; remaining ₹{mstat['remaining_inr']:.2f}"])
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
        r = sh([PY, "tools/live-check.py", SITE, "--vercel-host",
                os.environ.get("GROW_VERCEL_HOST", "researchmap-one.vercel.app")], check=False, timeout=600)
        live = (r.returncode == 0, redact(r.stdout + r.stderr))
        if not live[0]:
            status += " — LIVE CHECK FAILED"
        branch = None
    else:
        publish_bookkeeping(date, f"weekly grow {date}: bookkeeping only (publish gates failed)", keep_rest=True)
        branch = publish_branch(date, f"weekly grow {date}: publish gates failed")
        status = "publish gates failed — the site was not changed"
    if note and note.startswith("Budget exhausted"):
        status += " — BUDGET EXHAUSTED"
    body = issue_body(date, status, p1=p1, p2=p2, diff=diff, spent=l1[0] - l0[0], ledger=l1,
                      budget=budget, gate_res=gate_res, branch=branch, live=live, money=mstat,
                      builds=builds, note=note)
    needs = not ok or (live is not None and not live[0]) or bool(note)
    labels = ["weekly-grow"] + (["needs-action"] if needs else [])
    say(f"issue: {issues.upsert(title, body, labels)}")
    return 0 if ok and (live is None or live[0]) else 1


def registry_queued() -> list[dict]:
    from backend.app.api import registry
    return registry.queued()


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


BOOKKEEPING = ("data",)        # everything paid for or recorded; never the public site or docs


def publish_bookkeeping(date: str, msg: str, *, keep_rest: bool = False) -> str | None:
    """Commit ONLY data/ (ledger, projections, batch states, extraction cache,
    verdict logs, corpus files) to main and push, so paid work is never lost
    and the next run resumes. The public site (frontend/, docs/) is not
    touched. Unless keep_rest, the rest of the working tree is then reset."""
    git("add", "--", *BOOKKEEPING)
    if not git("diff", "--cached", "--name-only"):
        if not keep_rest:
            _reset_rest()
        return None
    git(*_identity(), "commit", "-q", "-m", msg)
    r = sh(["git", "push", "origin", "HEAD:main"], check=False)
    local = git("rev-parse", "HEAD")
    remote = git("ls-remote", "origin", "refs/heads/main").split()[0:1]
    ok = r.returncode == 0 and remote == [local]
    say(f"bookkeeping {'pushed' if ok else 'PUSH FAILED'} {local[:7]}")
    if not keep_rest:
        _reset_rest()
    return local[:7] if ok else None


def _reset_rest() -> None:
    git("checkout", "--", ".")
    sh(["git", "clean", "-fdq", "--", "frontend/public", "docs"], check=False)


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
