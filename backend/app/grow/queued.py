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

import json
import time

from backend.app.api import registry
from backend.app.grow.core import FOLLOWON_WAIT_S, Clients, with_retry


def _key(lib: dict) -> str:
    return lib["domain_key"]


def building() -> list[dict]:
    return [l for l in registry.load() if l["status"] == "building"]


def open_fulltext(lib: dict, cl: Clients) -> dict:
    """Free. Fills input_source for prepared entries that do not have it."""
    from backend.app.corpus import records
    from backend.app.corpus.multi_domain import DOMAINS, _prelabel_path
    cfg = DOMAINS[_key(lib)]
    p = _prelabel_path(cfg)
    pre = json.loads(p.read_text())
    recs = {r.get("id", "").rsplit("/", 1)[-1]: r for r in records.load(cfg.slug)["records"]}
    n_ft = 0
    for e in pre["entries"]:
        if "input_source" in e:
            n_ft += e["input_source"] == "fulltext"
            continue
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


def projection_inr(lib: dict) -> float:
    from backend.app.corpus import multi_domain_extract as X
    return float(X.dry_run(_key(lib))["proj_cost_inr"]) / 2      # batch rate


def start(lib: dict, cl: Clients) -> dict:
    from backend.app.corpus import multi_domain_extract as X
    r = with_retry(lambda: X.batch_submit(_key(lib), client=cl.batch))
    registry.set_status(lib["slug"], "building")
    return r


def finish(lib: dict, cl: Clients, *, mock: bool = False) -> dict:
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
