"""Build a queued library from the weekly workflow, two-phase, no human step.

  week N    start():  open full text for its prepared papers (free), project
                      the extraction at the batch rate, and — only if the
                      money rule says it is affordable (projection x1.5 plus
                      four weeks of growth fits what remains) — submit ONE
                      extraction batch. Registry status: queued -> building.
  week N+1  finish(): collect it (billed once), then every check the other
                      libraries have: claim embeddings, the disagreement check
                      (batch), future-work matcher, method-transfer
                      confirmation, cites-both counts. Registry: built.
                      New disagreements are unaudited: shown as "Flagged by
                      the system, not yet checked", never counted.

A batch that has not finished keeps its saved state and is resumed the next
week; nothing is paid twice. Preparation (snowball, rubric, dedupe, blind
audit) was done when the domain was queued: data/domains/<slug>/.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from backend.app.api import registry
from backend.app.config import REPO_ROOT
from backend.app.grow.core import FOLLOWON_WAIT_S, Clients, with_retry


def _key(lib: dict) -> str:
    return lib["domain_key"]


def building() -> list[dict]:
    return [l for l in registry.load() if l["status"] == "building"]


def open_fulltext(lib: dict, cl: Clients) -> dict:
    """Free. Fills input_source for prepared entries that do not have it, and
    re-fetches full text that an earlier preparation found but that is not
    in this checkout's cache (full text is never committed)."""
    from backend.app.corpus import records
    from backend.app.corpus.multi_domain import DOMAINS, _prelabel_path
    cfg = DOMAINS[_key(lib)]
    p = _prelabel_path(cfg)
    pre = json.loads(p.read_text())
    recs = {r.get("id", "").rsplit("/", 1)[-1]: r for r in records.load(cfg.slug)["records"]}
    n_ft = 0
    from backend.app.ingestion.fulltext import load_cached_fulltext
    for e in pre["entries"]:
        if e.get("input_source") == "abstract_only":
            continue
        if e.get("input_source") == "fulltext" and (load_cached_fulltext(f"openalex:{e['wid']}")
                                                     or load_cached_fulltext(e["wid"])):
            n_ft += 1
            continue
        # not looked for yet, or found once but not in this checkout's cache
        # (full text is never committed): fetch it again
        try:
            src = cl.fulltext(e, recs.get(e["wid"], {}))
        except Exception:  # noqa: BLE001
            src = None
        e["input_source"] = "fulltext" if src else "abstract_only"
        e["fulltext_source"] = src
        e["abstract_only"] = not src
        n_ft += bool(src)
    p.write_text(json.dumps(pre))
    return {"slug": cfg.slug, "papers": len(pre["entries"]), "full_text": n_ft}


def apply_core_scope(lib: dict) -> dict:
    """Free, idempotent. A queued library is built only from prepared papers
    that meet its core scope (backend/app/grow/scope.py). The others move to
    "scope_excluded" with the reason (kept on file, never deleted), so they
    are neither extracted nor paid for. Run before the projection."""
    from backend.app.corpus.multi_domain import DOMAINS, _prelabel_path
    from backend.app.grow.scope import core_scope
    cfg = DOMAINS[_key(lib)]
    p = _prelabel_path(cfg)
    pre = json.loads(p.read_text())
    keep, out = [], pre.setdefault("scope_excluded", [])
    for e in pre["entries"]:
        ok, why = core_scope(cfg.slug, e.get("title") or "", e.get("abstract"))
        if ok:
            keep.append(e)
        else:
            out.append({"wid": e["wid"], "title": e.get("title"), "reason": why,
                        "rule": "backend/app/grow/scope.py", "entry": e})
    moved = len(pre["entries"]) - len(keep)
    pre["entries"] = keep
    pre["n_kept"] = len(keep)
    p.write_text(json.dumps(pre))
    return {"slug": cfg.slug, "kept": len(keep), "excluded_now": moved, "excluded_total": len(out)}


# --- pace: how often a new library may be started -------------------------------------

GROWTH_CFG = REPO_ROOT / "config" / "growth.json"
BUILDS_LOG = REPO_ROOT / "data" / "grow" / "queued_builds.json"
DEFAULT_MAX_PER_MONTH = 1
DEFAULT_MIN_WEEKLY_RESERVE_INR = 15.0
PAD = 1.5                    # the money rule's padding on a projection


def pace_config(path: Path | None = None) -> dict:
    """max_queued_builds_per_month (default 1) and min_weekly_growth_reserve_inr
    (default 15) from config/growth.json."""
    p = path or GROWTH_CFG
    c = json.loads(p.read_text()) if p.exists() else {}
    return {"max_per_month": int(c.get("max_queued_builds_per_month", DEFAULT_MAX_PER_MONTH)),
            "min_weekly_reserve_inr": float(c.get("min_weekly_growth_reserve_inr", DEFAULT_MIN_WEEKLY_RESERVE_INR))}


def builds_log(path: Path | None = None) -> list[dict]:
    p = path or BUILDS_LOG
    return json.loads(p.read_text()).get("started", []) if p.exists() else []


def record_start(slug: str, date: str, source: str, path: Path | None = None) -> None:
    p = path or BUILDS_LOG
    d = json.loads(p.read_text()) if p.exists() else {"started": []}
    d.setdefault("started", []).append({"slug": slug, "date": date, "source": source})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")


def pace_check(*, proj_inr: float, available_inr: float, growth_committed_inr: float, weeks_after: int,
               ref: dt.date, cfg: dict | None = None, log: list[dict] | None = None) -> dict:
    """May a queued library be started now, at this pace? (After the money
    rule says it is affordable.) Two limits, both from config/growth.json:

      - at most max_per_month queued builds STARTED in ref's calendar month;
      - the money left after it (available - this week's growth commitments
        - the padded projection) must still fund min_weekly_reserve_inr of
        growth in each of the weeks_after remaining weeks: a queued build
        never cuts into that reserve.

    Returns {ok, reason, this_month, left_after_inr, reserve_needed_inr,
    weekly_growth_after_inr}."""
    cfg = cfg or pace_config()
    log = builds_log() if log is None else log
    month = ref.strftime("%Y-%m")
    this_month = [e for e in log if str(e.get("date", "")).startswith(month)]
    left = available_inr - growth_committed_inr - proj_inr * PAD
    need = cfg["min_weekly_reserve_inr"] * max(0, weeks_after)
    out = {"this_month": [e["slug"] for e in this_month], "left_after_inr": round(left, 2),
           "reserve_needed_inr": round(need, 2),
           "weekly_growth_after_inr": round(left / weeks_after, 2) if weeks_after > 0 else None}
    if len(this_month) >= cfg["max_per_month"]:
        return {**out, "ok": False, "blocked_by": "month",
                "reason": f"{len(this_month)} queued build(s) already started in {month} "
                                              f"({', '.join(out['this_month'])}); the limit is {cfg['max_per_month']} "
                                              "per month (config/growth.json max_queued_builds_per_month)"}
    if left + 1e-9 < need:
        return {**out, "ok": False, "blocked_by": "reserve",
                "reason": f"it would leave ₹{left:.2f} after this week, less than the "
                                              f"₹{cfg['min_weekly_reserve_inr']:.0f}/week growth reserve for the "
                                              f"{weeks_after} remaining weeks (₹{need:.2f}; config/growth.json "
                                              "min_weekly_growth_reserve_inr)"}
    return {**out, "ok": True, "blocked_by": None,
            "reason": "within the monthly limit and the weekly growth reserve"}


def projection_inr(lib: dict) -> float:
    from backend.app.corpus import multi_domain_extract as X
    return float(X.dry_run(_key(lib))["proj_cost_inr"]) / 2      # batch rate


def start(lib: dict, cl: Clients) -> dict:
    from backend.app.corpus import multi_domain_extract as X
    r = with_retry(lambda: X.batch_submit(_key(lib), client=cl.batch))
    registry.set_status(lib["slug"], "building")
    return r


def finish(lib: dict, cl: Clients, *, mock: bool = False, paid_followon: bool = True,
           why_not: str = "") -> dict:
    """Collect the library's extraction batch (already paid for when it was
    submitted), then its follow-on checks (paid: disagreement classification,
    embeddings, future-work matching, method-lead confirmation). With
    paid_followon=False only the collection runs; the library stays
    'building' and its follow-on checks run in a later run."""
    from backend.app.corpus import multi_domain_extract as X
    from backend.app.corpus import multi_domain_reason as R
    from backend.app.corpus.multi_domain_reason_incremental import write_coverage
    from backend.app.reasoning import run_library_scorers as S
    from backend.app.reasoning.library_corpus import embed_future_work
    key, slug = _key(lib), lib["slug"]
    out: dict = {"slug": slug}
    if X._batch_state_path(key).exists():
        r = with_retry(lambda: X.batch_collect(key, client=cl.batch))
        out["extract"] = {k: v for k, v in r.items() if k != "hard_fails"}
        if r["status"] == "pending":
            return {**out, "status": "pending"}
        if r["status"] == "failed":
            X._batch_state_path(key).unlink()
            registry.set_status(slug, "queued")
            return {**out, "status": "failed: back in the queue"}
        X._batch_state_path(key).unlink()
    if not paid_followon:
        return {**out, "status": f"collected; follow-on checks wait ({why_not or 'no paid work this run'})"}
    exts = R.load_extractions(slug)
    pairs = R.compute_shortlist(exts, use_real_embeddings=True, slug=slug, embed_client=cl.embed)
    try:
        res = R.classify_pairs_batch(slug, exts, pairs, client=cl.batch, wait_timeout_s=FOLLOWON_WAIT_S)
        out["disagree"] = {"n": res["n_todo"], "stats": res["stats"]}
    except S.BatchPending as e:
        return {**out, "status": f"pending: {e}"}
    write_coverage(slug, exts, pairs, threshold=R.LIBRARY_THRESHOLD, max_per_claim=R.LIBRARY_MAX_PER_CLAIM,
                   note="built by the weekly workflow (backend/app/grow/queued.py)")
    if embed_future_work(slug, dry_run=True)["to_embed"]:
        embed_future_work(slug, dry_run=False, client=cl.embed)
    for name, fn in (("fw_match", S.fwmatch), ("confirm", S.confirm)):
        try:
            out[name] = {k: v for k, v in fn(slug, dry_run=False, client=cl.batch,
                                             wait_timeout_s=FOLLOWON_WAIT_S).items()
                         if not isinstance(v, dict)}
        except S.BatchPending as e:
            return {**out, "status": f"pending: {e}"}
    if not mock:
        from backend.app.api.cites_both import compute_cites_both_for_domain
        try:
            out["cites_both"] = with_retry(lambda: compute_cites_both_for_domain(slug)).get("n_queried")
        except Exception as e:  # noqa: BLE001
            out["cites_both"] = f"skipped: {type(e).__name__}"      # free; retried next export
    registry.set_status(slug, "built")
    out["status"] = "built"
    out["finished_at"] = time.strftime("%Y-%m-%d")
    return out
