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

_upsert = issues.upsert


def _upsert_marked(title: str, body: str, labels: list[str]) -> str:
    """Every Issue this run writes also drops a marker, so the workflow's
    failure step knows the run reported for itself (and never overwrites
    that report)."""
    out = _upsert(title, body, labels)
    m = os.environ.get("GROW_ISSUE_MARKER")
    if m:
        Path(m).write_text(title)
    return out


issues.upsert = _upsert_marked

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


SECRET_ENV = ("GEMINI_API_KEY", "OPENALEX_API_KEY", "ANTHROPIC_API_KEY", "SEMANTIC_SCHOLAR_API_KEY",
              "GH_TOKEN", "GITHUB_TOKEN")


def _in_tests() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _no_git_writes_in_tests(what: str) -> None:
    """Commits, pushes, checkouts and cleans never run inside a test process:
    there ROOT is the developer's working tree (a test once reached the
    error path and reset it). Tests patch these functions instead."""
    if _in_tests():
        raise RuntimeError(f"run_weekly.{what}: refusing to write to git inside pytest")


def sh(cmd: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int | None = None,
       env: dict | None = None, no_secrets: bool = False) -> subprocess.CompletedProcess:
    """no_secrets: the child gets no credentials and no run controls (tests,
    builds and gates never need them)."""
    full = {**os.environ, **(env or {})}
    if no_secrets:
        for k in (*SECRET_ENV, "GROW_EVENT", "GROW_RUN_BUDGET_INR", "GROW_BUILD_QUEUED", "GROW_GATES_ONLY",
                  "GROW_REPUBLISH"):
            full.pop(k, None)
    r = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout, env=full)
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
    resolved = _resolved_branches()
    names = []
    for ln in heads.splitlines():
        sha, ref = ln.split()
        name = ref.split("refs/heads/", 1)[-1]
        merged = sh(["git", "merge-base", "--is-ancestor", sha, "HEAD"], check=False).returncode == 0
        if name in resolved or merged:
            continue
        state, files = branch_data_state(name)
        if state == "recoverable":
            # paid data only on that branch, and main has not touched those
            # files since: bring it to main now (nothing paid is stranded)
            git("checkout", f"origin/{name}", "--", *files)
            publish_bookkeeping(_today(), f"weekly grow: data recovered from {name}", keep_rest=True)
            state = "on_main"
        if state == "on_main":
            # its paid data is on main; its site files are regenerated by
            # this run (and recorded as resolved when this run publishes)
            _ON_MAIN_BRANCHES.append(name)
            continue
        names.append(name)
    if names:
        return (f"an earlier run's branch {', '.join(names)} holds paid data that conflicts with main: "
                "collecting what was already paid for, starting nothing new until the owner resolves it "
                "(see docs/OPERATIONS.md)")
    return None


_ON_MAIN_BRANCHES: list[str] = []


def _today() -> str:
    return os.environ.get("GROW_DATE") or dt.datetime.now(dt.timezone.utc).date().isoformat()


def branch_data_state(name: str) -> tuple[str, list[str]]:
    """Where a failed run's paid data is. Returns (state, files):
      on_main      every data/ change on the branch is already on main
      recoverable  some is only on the branch, and main has not changed those
                   files since the branch forked: safe to bring over
      stranded     both changed the same files: needs the owner"""
    sh(["git", "fetch", "-q", "origin", f"+refs/heads/{name}:refs/remotes/origin/{name}"], check=False)
    ref = f"origin/{name}"
    base = git("merge-base", "HEAD", ref)
    changed = [f for f in git("diff", "--name-only", base, ref, "--", "data").splitlines() if f]
    if not changed:
        return "on_main", []
    differ = [f for f in git("diff", "--name-only", ref, "HEAD", "--", *changed).splitlines() if f]
    if not differ:
        return "on_main", []
    main_touched = [f for f in git("diff", "--name-only", base, "HEAD", "--", *differ).splitlines() if f]
    return ("recoverable", differ) if not main_touched else ("stranded", differ)


def _record_resolved(names: list[str], reason: str) -> None:
    if not names:
        return
    p = ROOT / "data" / "grow" / "resolved_branches.json"
    reg = json.loads(p.read_text()) if p.exists() else {"resolved": {}}
    for n in names:
        reg.setdefault("resolved", {}).setdefault(n, {"date": _today(), "reason": reason})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(reg, indent=1) + "\n")


def _resolved_branches() -> set[str]:
    """grow/<date> branches the owner (or a later fix) has dealt with without
    merging; listed in data/grow/resolved_branches.json with a reason.
    Branches are never deleted by the workflow."""
    p = ROOT / "data" / "grow" / "resolved_branches.json"
    return set(json.loads(p.read_text()).get("resolved", {})) if p.exists() else set()


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


def _gate_result(name: str, r) -> dict:
    """ok, the failing test/check names, and the last 60 lines of output."""
    if r.returncode == 0:
        return {"gate": name, "ok": True, "tail": "", "failed": []}
    out = redact((r.stdout or "") + (r.stderr or ""))
    failed = [ln.split(" - ")[0].strip() for ln in out.splitlines()
              if ln.startswith(("FAILED ", "ERROR ")) or ln.startswith("[FAIL]")]
    return {"gate": name, "ok": False, "failed": failed[:40],
            "tail": "\n".join(out.strip().splitlines()[-60:])}


def failure_block(gate_res: list[dict]) -> str:
    """One clearly marked block: every failed gate, its failing tests and
    the last 60 lines of its output. Printed last and copied into the Issue."""
    bad = [g for g in gate_res if not g["ok"]]
    if not bad:
        return ""
    L = ["", "=" * 25 + " GATE FAILURES " + "=" * 25]
    for g in bad:
        L += [f"--- {g['gate']} ---", "failing: " + (", ".join(g.get("failed") or []) or "(see output)"),
              "last 60 lines:", g.get("tail") or "(no output)", ""]
    L.append("=" * 65)
    return "\n".join(L)


def preflight_checks() -> list[dict]:
    """Before ANY paid step, on the fresh checkout: typecheck, the
    production build (the rendered-output and safety tests need it) and the
    full test suite. Nothing is spent unless all three pass."""
    if MOCK and os.environ.get("GROW_GATES") == "skip":
        return [{"gate": "(preflight skipped: mock run)", "ok": True, "tail": "", "failed": []}]
    res = []
    for name, cmd, cwd in (("preflight: typecheck", ["npm", "run", "typecheck"], FE),
                           ("preflight: production build", ["npm", "run", "build"], FE),
                           ("preflight: full tests", [PY, "-m", "pytest", "backend/tests", "-q"], ROOT)):
        r = sh(cmd, cwd=cwd, check=False, timeout=3600, no_secrets=True)
        res.append(_gate_result(name, r))
        say(f"{'PASS' if r.returncode == 0 else 'FAIL'}: {name}")
        if r.returncode != 0:
            break
    return res


def gates(*, after_preflight: bool = False) -> list[dict]:
    """after_preflight: typecheck, build and full tests just passed on this
    same tree (gates_only mode, nothing regenerated in between), so they are
    not repeated."""
    if MOCK and os.environ.get("GROW_FAIL_GATE"):            # offline e2e only: a gate that fails
        name = os.environ["GROW_FAIL_GATE"]
        say(f"gate FAIL: {name} (forced: mock run, GROW_FAIL_GATE)")
        return [{"gate": name, "ok": False, "failed": [f"FAILED {name} (forced by the mocked e2e)"],
                 "tail": f"{name}: forced failure for the mocked end-to-end test"}]
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
    if after_preflight:
        steps = steps[3:]
        res = [{"gate": n, "ok": True, "tail": "", "failed": [], "note": "passed in preflight"}
               for n in ("typecheck", "production build (+ consistency before and after)", "full tests")]
    for name, cmd, cwd in steps:
        r = sh(cmd, cwd=cwd, check=False, timeout=3600, no_secrets=True)
        res.append(_gate_result(name, r))
        say(f"gate {'PASS' if r.returncode == 0 else 'FAIL'}: {name}")
    built = next(g["ok"] for g in res if g["gate"].startswith("production build"))
    for name, script, extra in (("browser hunt (Part 3)", "tools/qa/hunt.py", []),
                                ("smoke checks on the build", "tools/qa/smoke.py", ["--engines=chromium"])):
        if not built:
            res.append({"gate": name, "ok": False, "tail": "not run: the build failed"})
            continue
        r = _serve(lambda base: sh([PY, script, *extra] + ([base] if "smoke" in script else []),
                                   check=False, timeout=3600, env={"HUNT_BASE": base}, no_secrets=True))
        res.append(_gate_result(name, r))
        say(f"gate {'PASS' if r.returncode == 0 else 'FAIL'}: {name}")
    return res


def fingerprint(date: str, gate_res: list[dict] | None, ledger: tuple[float, float],
                diff: dict | None = None) -> Path:
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
        # the permanent record of every result that left, with its reason
        "results_changed": {slug: {k: d[k] for k in ("shown_before", "shown_after", "removed_shown",
                                                     "removed_not_shown", "verdict_changed")}
                            for slug, d in (diff or {}).items()} or None,
    }, indent=1) + "\n")
    return p


def changelog(date: str, lines: list[str]) -> None:
    p = ROOT / "docs" / "CHANGELOG.md"
    head = "# Changelog\n\nOne entry per weekly growth run (newest first).\n"
    old = p.read_text() if p.exists() else head
    body = old[len(head):] if old.startswith(head) else old
    p.write_text(head + f"\n## {date}\n\n" + "\n".join(f"- {l}" for l in lines) + "\n" + body)


SHOWN = (None, "genuine")       # verdicts a reader sees as a result
UNEXPLAINED = "UNEXPLAINED"


def _fw_addressal(slug: str, fw_id: str) -> dict | None:
    """The recorded verdict that a later paper addresses this future-work
    item (addressed or partial), if any."""
    p = ROOT / "data" / "domains" / slug / "reasoning" / "fw_addressals.jsonl"
    if not p.exists():
        return None
    hit = None
    for ln in p.read_text().splitlines():
        if ln.strip():
            r = json.loads(ln)
            if r.get("future_work_id") == fw_id and r.get("label") in ("addressed", "partial"):
                hit = r
    return hit


def _removed_papers(slug: str) -> dict[str, dict]:
    """Papers taken out of a library by an owner decision (prelabelled.json
    "removed"), by wid."""
    p = ROOT / "data" / "domains" / slug / "prelabelled.json"
    if not p.exists():
        return {}
    return {r["wid"]: r for r in json.loads(p.read_text()).get("removed", [])}


_ORPHAN_RULES: dict[str, dict] = {}


def _orphan_rules(slug: str) -> dict:
    """The open-question rule's verdict for every future-work item in the
    library as it is NOW (backend/app/reasoning/scorers.orphan_evaluation)."""
    if slug not in _ORPHAN_RULES:
        try:
            from backend.app.reasoning.library_corpus import load_library_corpus
            from backend.app.reasoning.scorers import orphan_evaluation
            _ORPHAN_RULES[slug] = orphan_evaluation(load_library_corpus(slug))
        except Exception:  # noqa: BLE001  (no corpus: no rule can explain it)
            _ORPHAN_RULES[slug] = {}
    return _ORPHAN_RULES[slug]


def removal_reason(slug: str, item_slug: str) -> str:
    """Why a result left the library, from the recorded data and the rule
    that applies. UNEXPLAINED when no rule accounts for it."""
    for wid, r in _removed_papers(slug).items():
        if f"-{wid.lower()}" in item_slug:
            return (f"its paper {wid} was removed from the library ({r.get('decided_on')}, owner-approved): "
                    f"{r.get('reason')}")
    m = re.search(r"-orphan-(openalex)-(w\d+)-(f\d+)$", item_slug)
    if m:
        fw = f"{m.group(1)}:{m.group(2).upper()}:{m.group(3)}"
        r = _fw_addressal(slug, fw)
        if r:
            return (f"open question answered: the later paper {r['to_paper_id'].split(':')[-1]} was judged to "
                    f"address it ({r['label']}); an open question a later paper addresses is no longer open "
                    "(docs/opportunity-criteria.md)")
        ev = _orphan_rules(slug).get(fw)
        if ev and not ev["shown"] and ev["rule"] == "too few later near papers":
            from backend.app.config import get_settings
            gone = [w for w in _removed_papers(slug)]
            return (f"no longer meets the open-question rule: {ev['near_later']} later topically near papers that "
                    f"do not address it, minimum {get_settings().rel_futurework_min_near_later}"
                    + (f" (papers removed from the library: {', '.join(gone)})" if gone else ""))
        if ev and not ev["shown"] and ev["rule"] == "not open long enough":
            return f"no longer meets the open-question rule: open {ev['age']} years, minimum 2"
        return UNEXPLAINED
    if re.search(r"-hole-w\d+-w\d+$", item_slug):
        return ("method-transfer candidates are recomputed every run from the library's paper clusters; "
                "with the library's current papers this pair is no longer a candidate")
    return UNEXPLAINED


def diff_items(before, after) -> dict:
    """Per library: what appeared and what left, with a reason for every
    item that left. Counts add up: shown_before + new_results (+ new flagged
    shown later) - removed_shown + promoted - demoted = shown_after."""
    _ORPHAN_RULES.clear()      # the rules are read from the library as it is now
    out = {}
    for slug in after:
        b, a = before.get(slug, {}), after[slug]
        new = [s for s in a if s not in b]
        gone = [s for s in b if s not in a]
        out[slug] = {
            "shown_before": sum(1 for s in b if b[s]["verdict"] in SHOWN),
            "shown_after": sum(1 for s in a if a[s]["verdict"] in SHOWN),
            "new_results": [a[s]["headline"] for s in new if a[s]["verdict"] in SHOWN],
            "new_flagged": [(s, a[s]["headline"]) for s in new if a[s]["verdict"] == "unaudited"],
            "new_set_aside": [a[s]["headline"] for s in new if a[s]["verdict"] not in (*SHOWN, "unaudited")],
            "removed_shown": [{"id": s, "headline": b[s]["headline"], "reason": removal_reason(slug, s)}
                              for s in gone if b[s]["verdict"] in SHOWN],
            "removed_not_shown": [{"id": s, "headline": b[s]["headline"], "was": b[s]["verdict"],
                                   "reason": removal_reason(slug, s)} for s in gone if b[s]["verdict"] not in SHOWN],
            "verdict_changed": [{"id": s, "from": b[s]["verdict"], "to": a[s]["verdict"]}
                                for s in a if s in b and a[s]["verdict"] != b[s]["verdict"]],
        }
        # back-compat key: every removed id (shown or not)
        out[slug]["removed"] = [r["headline"] for r in out[slug]["removed_shown"] + out[slug]["removed_not_shown"]]
    return out


def diff_lines(diff: dict) -> list[str]:
    """Changelog/Issue lines: shown counts before -> after, and every item
    that left with its reason."""
    L = []
    for slug, d in diff.items():
        if slug == "llm-calibration" and not (d["new_results"] or d["removed"]):
            continue
        L.append(f"{slug}: results shown {d['shown_before']} -> {d['shown_after']} "
                 f"(+{len(d['new_results'])} new, -{len(d['removed_shown'])} no longer shown); "
                 f"{len(d['new_flagged'])} flagged disagreements (not yet checked)"
                 + (f"; {len(d['removed_not_shown'])} set-aside item(s) dropped (never shown)"
                    if d["removed_not_shown"] else ""))
        for r in d["removed_shown"]:
            L.append(f"  - no longer shown: {r['id']} — {r['reason']}")
        for r in d["removed_not_shown"]:
            L.append(f"  - dropped (was {r['was']}, never shown): {r['id']} — {r['reason']}")
    return L


def unexplained(diff: dict) -> list[str]:
    return [r["id"] for d in (diff or {}).values() for r in d.get("removed_shown", []) + d.get("removed_not_shown", [])
            if r["reason"] == UNEXPLAINED]


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
    owed = [(r["slug"], r["followon_owed"]) for r in p1 if r.get("followon_owed")]
    for r in p1:
        if r.get("status") == "collected":
            L.append(f"- {r['slug']}: {len(r['added'])} added"
                     + (f", {len(r['failed'])} failed extraction" if r["failed"] else ""))
            L += [f"  - {t}" for t in r.get("added_titles", [])]
        else:
            L.append(f"- {r['slug']}: {r.get('status', 'not reached')}")
    if not p1:
        L.append("- none")
    if owed:
        L += ["", "Follow-on checks carried over to next run (budget); that library goes first next week:", ""]
        L += [f"- {slug}: {', '.join(steps)}" for slug, steps in owed]
    excl = [(r["slug"], x) for r in p1 for x in r.get("scope_excluded", [])]
    if excl:
        L += ["", "## Scope exclusions (proposals; nothing deleted)", "",
              "Paid for and collected, but outside the library's core scope (backend/app/grow/scope.py), so "
              "**not published**. Kept on file under `scope_excluded` in the library's prelabelled.json. "
              "To publish one anyway, move its entry back into `entries` and commit.", ""]
        L += [f"- {slug}: {x['wid']} — {x.get('title') or ''} — {x['reason']}" for slug, x in excl]
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
                L.append(f"- {slug}: results shown {d['shown_before']} → {d['shown_after']}: "
                         f"{len(d['new_results'])} new, {len(d['removed_shown'])} no longer shown; "
                         f"{len(d['new_set_aside'])} new set aside; "
                         f"{len(d['removed_not_shown'])} set-aside item(s) dropped (never shown)")
                L += [f"  - new: {h}" for h in d["new_results"][:20]]
                L += [f"  - no longer shown: {r['headline']} (`{r['id']}`) — {r['reason']}" for r in d["removed_shown"]]
                L += [f"  - dropped, never shown: `{r['id']}` — {r['reason']}" for r in d["removed_not_shown"]]
        if unexplained(diff):
            L += ["", "**Results left without a recorded reason (needs your look):** "
                  + ", ".join(f"`{x}`" for x in unexplained(diff))]
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
            if not g["ok"]:
                L += ["", f"**{g['gate']}** failing: " + (", ".join(f"`{x}`" for x in g.get("failed") or []) or
                                                          "(see output)"),
                      "", f"<details><summary>{g['gate']}: last 60 lines</summary>", "", "```",
                      g.get("tail") or "", "```", "</details>"]
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
    if _in_tests() and any(os.environ.get(k) for k in SECRET_ENV):
        # a live run never starts inside a test process that holds credentials
        # (the suite strips them; this is the last line). Raised BEFORE the
        # try: no error path (bookkeeping commit, reset) may run either.
        raise RuntimeError("run_weekly.main(): refusing a live run inside pytest with credentials present")
    try:
        if (os.environ.get("GROW_GATES_ONLY", "").lower() == "true"
                and os.environ.get("GROW_EVENT", "workflow_dispatch") == "workflow_dispatch"):
            return gates_only(date)      # zero spend; works even while paused; manual runs only
        if (os.environ.get("GROW_REPUBLISH", "").strip()
                and os.environ.get("GROW_EVENT", "workflow_dispatch") == "workflow_dispatch"):
            return republish(os.environ["GROW_REPUBLISH"].strip(), date)   # zero spend; manual only
        hold = guards()
        if paused():
            body = issue_body(date, "paused — nothing collected, spent or published", p1=[], p2=[], diff=None,
                              spent=0.0, ledger=ledger_inr(), budget=budget, gate_res=None,
                              note="config/growth.json has paused: true. Set it to false to resume.")
            say(f"issue: {issues.upsert(title, body, ['weekly-grow'])}")
            return 0
        # PREFLIGHT: nothing is spent unless the fresh checkout passes
        pre = preflight_checks()
        if not all(g["ok"] for g in pre):
            block = failure_block(pre)
            body = issue_body(date, "preflight failed — nothing spent, nothing submitted", p1=[], p2=[],
                              diff=None, spent=0.0, ledger=ledger_inr(), budget=budget, gate_res=pre,
                              note="The full tests or typecheck failed on the fresh checkout BEFORE any paid "
                                   "step, so the run stopped. Fix the failing tests below and run again.")
            say(f"issue: {issues.upsert(title, body, ['weekly-grow', 'needs-action'])}")
            print(block, flush=True)
            return 3
        _reset_rest()          # the preflight build must not leave the tree dirty
        l0 = ledger_inr()
        manual, run_budget, build_queued = run_controls()
        if run_budget is not None:
            # Every paid call in this process is refused past this ledger
            # total. Collecting batches submitted by an EARLIER run records
            # money that run already committed, so that is added on top:
            # this run's cap is for this run's new spending only.
            pend0 = money.pending_inr()
            os.environ["RUN_CAP_LEDGER_INR"] = str(round(l0[0] + pend0 + run_budget, 6))
            say(f"manual run: total spend capped at ₹{run_budget:.2f}; queued builds "
                f"{'allowed' if build_queued else 'skipped'}")
        mstat = money.status(ref)
        weekly = mstat.get("weekly_budget_inr", 0.0)
        if run_budget is not None:
            weekly = min(weekly, run_budget)
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
        # Phase 1a: collect last week's growth batches (already paid for)
        collected: dict[str, dict] = {}
        for slug in core.grow_slugs():
            try:
                r = core.collect(slug, cl, ref=ref)
            except Exception as e:  # noqa: BLE001
                raise core.GrowStop(f"Gemini or data error while collecting {slug}: {type(e).__name__}: {e}",
                                    "Usually transient (retried with backoff already). Nothing is lost: the "
                                    "saved batch state and the ledger were committed, and next week's run "
                                    "resumes. To retry sooner, run “Weekly grow” from the Actions tab.") from None
            say(f"collect {slug}: {r['status']} added={len(r['added'])}")
            collected[slug] = r
        # Phase 1b: budget-gated follow-on checks, in the FAIR order (owed work
        # first, then the library served longest ago); skipped steps are owed
        for slug in core.fair_order(list(collected), "followon"):
            r = collected[slug]
            try:
                r["followon"] = core.followon(slug, cl, budget)
            except Exception as e:  # noqa: BLE001
                raise core.GrowStop(f"Gemini or data error in the follow-on checks for {slug}: "
                                    f"{type(e).__name__}: {e}",
                                    "Usually transient. Nothing is lost: saved batch states and the ledger were "
                                    "committed, and next week's run resumes.") from None
            say(f"follow-on {slug}: {json.dumps(r['followon'], default=str)[:400]}")
            owed = core.followon_owed(r["followon"])
            core.record_fairness(slug, "followon", served=not owed, ref=ref, owed=owed)
            if owed:
                r["followon_owed"] = owed
            if r["followon"].get("money_refused"):
                note = "Budget exhausted: " + BUDGET_EXHAUSTED_ACTION
                budget = core.Budget(0.0)          # nothing new for the rest of this run
        p1.extend(collected[s_] for s_ in collected)
        checkpoint(date, "collected and checked")
        # Libraries being built by the workflow: finish them (already paid for)
        for lib in queued.building():
            try:
                r = queued.finish(lib, cl, mock=cl.mock)
            except Exception as e:  # noqa: BLE001
                from backend.app.extraction.spend_gate import SpendGateRefused
                from backend.app.extraction.spend_ledger import SpendCapExceededError
                if isinstance(e, (SpendGateRefused, SpendCapExceededError)):
                    note = "Budget exhausted: " + BUDGET_EXHAUSTED_ACTION
                    budget = core.Budget(0.0)
                    r = {"status": "waiting for money (stays 'building'; resumes when money is available)"}
                else:
                    raise core.GrowStop(f"error while finishing the {lib['slug']} library: {type(e).__name__}: {e}",
                                        "Usually transient. The batch state was saved; next week's run resumes.") from None
            say(f"build {lib['slug']}: {r.get('status')}")
            builds.append({"slug": lib["slug"], "status": r.get("status"),
                           "detail": "new library published" if r.get("status") == "built" else None})
        if builds:
            checkpoint(date, "queued library steps")
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
            order = core.fair_order(list(prepared), "extraction", papers=papers,
                                    candidates={s_: len(prepared[s_]["items"]) for s_ in prepared})
            say("allocation order (fair): " + ", ".join(order))
            picked = core.allocate(prepared, budget, papers, order)
            for slug in order:
                pr = prepared[slug]
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
                # served: it got papers, or it had nothing to submit (not starved)
                core.record_fairness(slug, "extraction", ref=ref,
                                     served=bool(r.get("submitted")) or not pr["items"])
                say(f"submit {slug}: {r.get('submitted', 0)} papers, projected ₹{r.get('projected_inr', 0):.2f}")
                p2.append(r)
            checkpoint(date, "submitted")
        # A queued library, if the money rule says it is affordable (one at a time)
        if budget.weekly_inr > 0 and not queued.building() and build_queued:
            rem = money.status(ref)["remaining_inr"] - budget.committed
            for lib in registry_queued():
                queued.apply_core_scope(lib)          # free; only in-scope papers are built
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
                    checkpoint(date, f"queued {lib['slug']} submitted")
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
        try:
            mstat = money.status(ref)          # after this run's spending, not before
        except Exception:  # noqa: BLE001
            pass
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
              + diff_lines(diff)
              + [f"spend recorded ₹{l1[0] - l0[0]:.2f}; remaining ₹{mstat['remaining_inr']:.2f}"])
    fingerprint(date, None, l1, diff)
    gate_res = gates()
    fingerprint(date, gate_res, l1, diff)
    ok = all(g["ok"] for g in gate_res)
    live = None
    if ok:
        _record_resolved(_ON_MAIN_BRANCHES, f"its paid data was already on main; the site was republished by "
                                            f"the weekly run of {date} (branch kept, never deleted)")
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
    needs = not ok or (live is not None and not live[0]) or bool(note) or bool(unexplained(diff))
    labels = ["weekly-grow"] + (["needs-action"] if needs else [])
    say(f"issue: {issues.upsert(title, body, labels)}")
    block = failure_block(gate_res)
    if block:
        print(block, flush=True)       # last thing in the log
    return 0 if ok and (live is None or live[0]) else 1


def gates_only_rows(pre: list[dict], res: list[dict] | None) -> list[dict]:
    """The one list of rows a gates_only run reports AND is judged by:
    the preflight checks, then every later gate (rows that only restate a
    preflight pass are dropped, so each check appears once)."""
    return list(pre) + [g for g in (res or []) if not g.get("note")]


def gates_only_summary(date: str, rows: list[dict]) -> str:
    bad = sum(not g["ok"] for g in rows)
    return "\n".join([f"## Weekly grow — gates only ({date}): "
                      + ("all passed" if not bad else f"{bad} FAILED"), "",
                      "| gate | result |", "|:--|:--|",
                      *[f"| {g['gate']} | {'PASS' if g['ok'] else 'FAIL'} |" for g in rows], ""])


def gates_only(date: str) -> int:
    """Zero-spend proof run: no API call, no batch submit or collect, no
    publish, ledger untouched, no Issue. Preflight on the fresh checkout,
    then regenerate (free) and EVERY gate, on the runner. The job summary is
    written once, as one table of every row, and the exit code is non-zero
    if ANY row in that table failed."""
    say(f"GATES ONLY {date}: no API calls, nothing submitted, collected or published")
    led0 = (ROOT / "data" / "spend_ledger.json").read_bytes()
    pre = preflight_checks()
    res = None
    if all(g["ok"] for g in pre):
        # exactly what a run's gates face: the site regenerated from the
        # current data first (free), then EVERY gate (after a failed run the
        # data on main is ahead of the site until it is republished)
        _reset_rest()
        regenerate()
        res = gates()
    rows = gates_only_rows(pre, res)
    if (ROOT / "data" / "spend_ledger.json").read_bytes() != led0:   # must never happen
        rows.append({"gate": "ledger untouched", "ok": False, "failed": [],
                     "tail": "data/spend_ledger.json changed during a gates_only run"})
    summary = gates_only_summary(date, rows)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary + "\n")
    print(summary, flush=True)
    block = failure_block(rows)
    if block:
        print(block, flush=True)
    _reset_rest()
    return 0 if rows and all(g["ok"] for g in rows) else 1


def republish(branch: str, date: str) -> int:
    """Zero-spend republish of a failed run (manual only, no API keys, the
    ledger untouched). The branch's paid data must already be on main (or be
    brought over without conflict); the site is regenerated on current main
    (with any fixes since), every gate runs, and main is fast-forwarded only
    if all pass. The branch is recorded as resolved, never deleted."""
    title = f"Weekly grow — {branch.split('/', 1)[-1]}"
    say(f"REPUBLISH {branch}: no API calls, nothing submitted or collected")
    if not re.fullmatch(r"grow/\d{4}-\d{2}-\d{2}", branch):
        say(f"refused: {branch!r} is not a grow/<date> branch")
        return 2
    if git("status", "--porcelain"):
        say("refused: the checkout is not clean")
        return 2
    if not git("ls-remote", "--heads", "origin", branch):
        say(f"refused: no branch {branch} on origin")
        return 2
    led0 = (ROOT / "data" / "spend_ledger.json").read_bytes()
    state, files = branch_data_state(branch)
    say(f"{branch}: paid data {state}" + (f" ({len(files)} files)" if files else ""))
    if state == "stranded":
        body = (f"**Status:** republish of `{branch}` refused — nothing changed\n\nThe branch and main both "
                f"changed these data files since the branch was made, so they cannot be combined "
                f"automatically:\n\n" + "\n".join(f"- `{f}`" for f in files))
        say(f"issue: {issues.upsert(title, body, ['weekly-grow', 'needs-action'])}")
        return 2
    if state == "recoverable":
        git("checkout", f"origin/{branch}", "--", *files)
    before = items_snapshot()
    regenerate()
    diff = diff_items(before, items_snapshot())
    rec = f"docs/releases/{branch.split('/', 1)[-1]}.json"
    if not (ROOT / rec).exists():                    # the failed run's own record
        shown = sh(["git", "show", f"origin/{branch}:{rec}"], check=False)
        if shown.returncode == 0:
            (ROOT / rec).write_text(shown.stdout)
    changelog(f"{date} (republished {branch})", diff_lines(diff) or ["no change to the results"])
    gate_res = gates()
    led_ok = (ROOT / "data" / "spend_ledger.json").read_bytes() == led0
    if not led_ok:
        gate_res.append({"gate": "ledger untouched", "ok": False, "failed": [], "tail": "ledger changed"})
    ok = all(g["ok"] for g in gate_res)
    lines = [f"- {'✅' if g['ok'] else '❌'} {g['gate']}" for g in gate_res]
    if ok:
        _record_resolved([branch], f"republished to main on {date} by the zero-spend republish mode "
                                   "(every gate passed; branch kept, never deleted)")
        fingerprint(date, gate_res, ledger_inr(), diff)
        sha = publish_main(date)
        body = "\n".join([f"**Status:** republished from `{branch}` to main ({sha[:7]}); nothing spent", "",
                          "## Results", "", *[f"- {x}" for x in diff_lines(diff)], "", "## Gates", "", *lines])
        say(f"issue: {issues.upsert(title, body, ['weekly-grow'])}")
        issues.close(title, f"Republished to main in {sha[:7]}; every gate passed.")
        return 0
    block = failure_block(gate_res)
    body = "\n".join([f"**Status:** republish of `{branch}` failed a gate — main and the site unchanged; "
                      "nothing spent", "", *lines, "", "```", block[-6000:], "```"])
    say(f"issue: {issues.upsert(title, body, ['weekly-grow', 'needs-action'])}")
    print(block, flush=True)
    _reset_rest()
    return 1


def run_controls() -> tuple[bool, float | None, bool]:
    """(manual?, run budget or None, build queued libraries?). Manual runs
    (workflow_dispatch) use the inputs; scheduled runs keep the money rule
    and may build a queued library when it is affordable."""
    manual = os.environ.get("GROW_EVENT") == "workflow_dispatch"
    if not manual:
        return False, None, True
    raw = (os.environ.get("GROW_RUN_BUDGET_INR") or "25").strip()
    return True, max(0.0, float(raw)), os.environ.get("GROW_BUILD_QUEUED", "false").lower() == "true"


def dry_run() -> int:
    """Planned spend for a manual run with the defaults (or the GROW_* inputs),
    without spending anything: free OpenAlex queries and projections only.
    No Gemini call, no commit, no Issue."""
    from backend.app.corpus import multi_domain_reason as R
    from backend.app.extraction import money
    from backend.app.grow import core, queued
    from backend.app.grow.core import Clients
    from backend.app.reasoning import run_library_scorers as S
    os.environ.setdefault("GROW_EVENT", "workflow_dispatch")
    date = os.environ.get("GROW_DATE") or dt.datetime.now(dt.timezone.utc).date().isoformat()
    ref = dt.date.fromisoformat(date)
    _manual, run_budget, build_queued = run_controls()
    st = money.status(ref)
    weekly = min(st["weekly_budget_inr"], run_budget) if run_budget is not None else st["weekly_budget_inr"]
    if os.environ.get("WEEKLY_BUDGET_INR"):
        weekly = min(weekly, float(os.environ["WEEKLY_BUDGET_INR"]))

    class _NoPaid:
        def __getattr__(self, name):
            raise RuntimeError("dry run: no paid call")

    import httpx
    from backend.app.config import get_settings
    from backend.app.corpus.multi_domain import retrieve_fulltext_one
    from backend.app.refresh.weekly_candidates import LiveOpenAlexClient
    k = get_settings().openalex_api_key
    http = httpx.Client(timeout=25.0, follow_redirects=True, headers={"User-Agent": "ResearchMap/0.3 dry-run"})
    cl = Clients(openalex=LiveOpenAlexClient(k.get_secret_value() if hasattr(k, "get_secret_value") else k),
                 batch=_NoPaid(), embed=_NoPaid(), llm=_NoPaid(),
                 fulltext=lambda e, r: retrieve_fulltext_one(e, r, client=http))
    budget = core.Budget(weekly)
    print(f"DRY RUN {date} — nothing is spent")
    print(f"money: ceiling ₹{st['ceiling_inr']:.2f}, ledger ₹{st['ledger_inr']:.2f}, remaining "
          f"₹{st['remaining_inr']:.2f}, pending (submitted, not yet billed) ₹{st['pending_inr']:.2f}, "
          f"available ₹{st['available_inr']:.2f}, weeks left {st['weeks_left']}, "
          f"money-rule weekly ₹{st['weekly_budget_inr']:.2f}")
    for c in money.pending_commitments():
        print(f"  pending: {c['file']} — {c['papers']} papers, ₹{c['projected_inr']:.2f} (collected and billed "
              "once by the next live run; its library gets no new submission until then)")
    print(f"this run: cap ₹{run_budget if run_budget is not None else st['weekly_budget_inr']:.2f} "
          f"(run_budget_inr), weekly budget used ₹{weekly:.2f}, queued builds "
          f"{'allowed' if build_queued else 'SKIPPED (build_queued=false)'}")
    rows, followon_total, errs = [], 0.0, []
    for slug in core.grow_slugs():
        f = 0.0
        exts = R.load_extractions(slug)
        pairs = R.compute_shortlist(exts, use_real_embeddings=True, slug=slug, embed_client=_NoPaid())
        done = R.load_classified_keys(slug)
        unseen = sum(1 for p in pairs if (p.from_claim_id, p.to_claim_id) not in done)
        f += unseen * R.projected_inr_per_pair()
        f += S.fwmatch(slug, dry_run=True).get("projected_inr", 0.0)
        f += S.confirm(slug, dry_run=True).get("projected_inr", 0.0)
        followon_total += f
        rows.append([slug, f])
    prepared = {s: core.prepare(s, cl, ref=ref, errors=errs) for s in core.grow_slugs()}
    papers = {s: len(json.loads((ROOT / "data/domains" / s / "prelabelled.json").read_text())["entries"])
              for s in prepared}
    order = core.fair_order(list(prepared), "extraction", papers=papers,
                            candidates={s_: len(prepared[s_]["items"]) for s_ in prepared})
    print("allocation order (fair: served longest ago first): " + ", ".join(order))
    picked = core.allocate(prepared, budget, papers, order)
    print("\n| library | candidates | planned papers | follow-on checks ₹ | extraction ₹ (batch) | padded ×1.5 ₹ |")
    print("|:--|--:|--:|--:|--:|--:|")
    tot_x = 0.0
    for slug, f in rows:
        x = sum(it["inr"] for it in picked[slug])
        tot_x += x
        print(f"| {slug} | {len(prepared[slug]['items'])} | {len(picked[slug])} | {f:.2f} | {x:.2f} | {x * 1.5:.2f} |")
        for it in picked[slug]:
            e = it["entry"]
            print(f"|   {e['wid']} | {it['src']} ({e.get('fulltext_source') or 'no open full text'}) | | | "
                  f"{it['inr']:.2f} | |")
    q = registry_queued()[:1]
    if q:
        print(f"\nqueued library {q[0]['slug']}: extraction projected ₹{queued.projection_inr(q[0]):.2f} "
              f"— {'would be considered' if build_queued else 'skipped this run'}")
    planned = tot_x + followon_total
    cap = run_budget if run_budget is not None else None
    print(f"\nplanned spend: ₹{planned:.2f} (extraction ₹{tot_x:.2f} + follow-on ₹{followon_total:.2f})"
          + (f"; cap ₹{cap:.2f}" if cap is not None else ""))
    print(f"available money afterwards: ₹{st['available_inr'] - planned:.2f} (if every projection is spent; "
          f"pending ₹{st['pending_inr']:.2f} already counted)")
    print("note: a live run fetches open full text again; a paper whose PDF was unreachable here but "
          "reachable then costs about 3x more (abstract ~₹0.9, full text ~₹2.7).")
    if errs:
        print("OpenAlex notes:", "; ".join(errs[:5]))
    return 0


def registry_queued() -> list[dict]:
    from backend.app.api import registry
    return registry.queued()


def _identity() -> list[str]:
    return ["-c", "user.name=researchmap-bot", "-c", "user.email=researchmap-bot@users.noreply.github.com"]


def publish_main(date: str) -> str:
    _no_git_writes_in_tests("publish_main")
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


def checkpoint(date: str, what: str) -> None:
    """Right after a paid step: push data/ (ledger, batch states, pending
    files) to main BEFORE any long step (gates can take an hour). If the job
    is cancelled or times out afterwards, nothing paid for is lost and the
    next run collects it instead of paying again. The site is not touched."""
    publish_bookkeeping(date, f"weekly grow {date}: checkpoint ({what})", keep_rest=True)


def publish_bookkeeping(date: str, msg: str, *, keep_rest: bool = False) -> str | None:
    """Commit ONLY data/ (ledger, projections, batch states, extraction cache,
    verdict logs, corpus files) to main and push, so paid work is never lost
    and the next run resumes. The public site (frontend/, docs/) is not
    touched. Unless keep_rest, the rest of the working tree is then reset."""
    _no_git_writes_in_tests("publish_bookkeeping")
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
    _no_git_writes_in_tests("_reset_rest")
    git("checkout", "--", ".")
    sh(["git", "clean", "-fdq", "--", "frontend/public", "docs"], check=False)


def publish_branch(date: str, msg: str) -> str:
    _no_git_writes_in_tests("publish_branch")
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
    raise SystemExit(dry_run() if "--dry-run" in sys.argv else main())
