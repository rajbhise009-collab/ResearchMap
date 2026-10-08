"""Build a prepared library end to end (paid), resumable stage by stage.

  python -m backend.app.corpus.build_library --domain nudges --plan
  python -m backend.app.corpus.build_library --domain nudges --run-budget 160 [--stages ...]

Stages, each idempotent (saved batch state; nothing is paid twice):
  extract     batch extraction of every uncached paper (projection x1.5)
  claims      claim embeddings (about ₹0.5 per 100 claims; ledgered by the client)
  disagree    disagreement check on every shortlisted pair, BATCH mode (x2)
  fw-embed    future-work embeddings
  fw-match    two-stage future-work matcher, batch (x2)
  confirm     method-transfer lead confirmation, batch (x2)
  cites-both  free OpenAlex counts for every flagged pair (cards + timelines)

Two gates before every paid stage: the money rule (SpendLedger, enforced at
call time) and this run's allocation: spend recorded since the run started
plus the stage's padded projection must fit --run-budget. A stage that does
not fit is skipped and reported, never forced.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from backend.app.corpus import multi_domain_reason as R
from backend.app.extraction.spend_ledger import SpendLedger

STAGES = ("extract", "claims", "disagree", "fw-embed", "fw-match", "confirm", "cites-both")
EXTRACT_MULT, CLASSIFY_MULT = 1.5, 2.0


class RunBudget:
    def __init__(self, inr: float, start_ledger_inr: float | None = None):
        """`start_ledger_inr`: the ledger total when the RUN began (a run may
        span several processes); default = now."""
        self.inr = inr
        self.start = (start_ledger_inr if start_ledger_inr is not None
                      else SpendLedger.load().snapshot()["cumulative_inr"])

    def spent(self) -> float:
        return SpendLedger.load().snapshot()["cumulative_inr"] - self.start

    def fits(self, padded: float) -> bool:
        return self.spent() + padded <= self.inr + 1e-9


def _projections(key: str) -> dict:
    """Free projections for every stage (no API calls; mock embeddings for
    the pair-count estimate, which over-projects)."""
    from backend.app.corpus import multi_domain_extract as X
    from backend.app.corpus.multi_domain import DOMAINS
    slug = DOMAINS[key].slug
    out = {"slug": slug}
    try:
        out["extract"] = X.dry_run(key)
    except Exception as e:  # noqa: BLE001
        out["extract"] = {"error": f"{type(e).__name__}: {e}"}
    exts = R.load_extractions(slug)
    out["n_extracted"] = len(exts)
    if exts:
        pairs = R.compute_shortlist(exts, use_real_embeddings=False)
        out["disagree_pairs_estimate_mock"] = len(pairs)
        out["disagree_projected_inr_batch"] = round(len(pairs) * R.projected_inr_per_pair() / 2, 2)
    return out


def run(key: str, budget: RunBudget, stages: tuple[str, ...], *, wait_s: float = 6 * 3600) -> dict:
    from backend.app.corpus import multi_domain_extract as X
    from backend.app.corpus.multi_domain import DOMAINS
    from backend.app.reasoning import run_library_scorers as S
    slug = DOMAINS[key].slug
    log: dict = {"slug": slug, "stages": {}}

    def note(stage, **kw):
        log["stages"][stage] = {**kw, "run_spent_inr": round(budget.spent(), 2)}
        print(stage, json.dumps(log["stages"][stage], default=str)[:600], flush=True)

    if "extract" in stages:
        st_path = X._batch_state_path(key)
        if not st_path.exists():
            d = X.dry_run(key)
            proj = float(d["proj_cost_inr"]) / 2          # dry_run projects the sync rate; batch is half
            if not budget.fits(proj * EXTRACT_MULT):
                note("extract", skipped=f"run budget: projection ₹{proj:.2f} x1.5 does not fit")
                return log
            note("extract-submit", **X.batch_submit(key))
        while True:
            r = X.batch_collect(key)
            if r["status"] != "pending":
                break
            time.sleep(60)
        note("extract", **{k: v for k, v in r.items() if k != "hard_fails"},
             hard_fails=len(r.get("hard_fails", [])))
        if r["status"] == "collected":
            X._batch_state_path(key).unlink(missing_ok=True)
    exts = R.load_extractions(slug)
    if "claims" in stages or "disagree" in stages:
        pairs = R.compute_shortlist(exts, use_real_embeddings=True, slug=slug)
        note("claims", embedded=dict(R.LAST_EMBED_STATS), shortlist=len(pairs))
    if "disagree" in stages:
        done = R.load_classified_keys(slug)
        todo = [p for p in pairs if (p.from_claim_id, p.to_claim_id) not in done]
        proj = len(todo) * R.projected_inr_per_pair() / 2
        if todo and not S._state(slug, "contradiction").exists() and not budget.fits(proj * CLASSIFY_MULT):
            note("disagree", skipped=f"run budget: {len(todo)} pairs, projection ₹{proj:.2f} x2 does not fit")
        else:
            res = R.classify_pairs_batch(slug, exts, todo, wait_timeout_s=wait_s)
            note("disagree", n_todo=res["n_todo"], stats=res["stats"], money=res.get("money"),
                 files=res["file_counts"])
        from backend.app.corpus.multi_domain_reason_incremental import write_coverage
        write_coverage(slug, exts, pairs, threshold=R.LIBRARY_THRESHOLD, max_per_claim=R.LIBRARY_MAX_PER_CLAIM,
                       note="built by backend/app/corpus/build_library.py")
    if "fw-embed" in stages:
        from backend.app.reasoning.library_corpus import embed_future_work
        d = embed_future_work(slug, dry_run=True)
        if d["to_embed"] and budget.fits(d["projected_inr"] * EXTRACT_MULT):
            note("fw-embed", **embed_future_work(slug, dry_run=False))
        else:
            note("fw-embed", **d)
    for stage, fn in (("fw-match", S.fwmatch), ("confirm", S.confirm)):
        if stage not in stages:
            continue
        d = fn(slug, dry_run=True)
        n = d.get("to_classify", d.get("to_confirm", 0))
        state = S._state(slug, "fw_match" if stage == "fw-match" else "hole_confirm").exists()
        if n and not state and not budget.fits(d["projected_inr"] * CLASSIFY_MULT):
            note(stage, skipped=f"run budget: projection ₹{d['projected_inr']:.2f} x2 does not fit", **d)
            continue
        note(stage, **(fn(slug, dry_run=False, wait_timeout_s=wait_s) if n or state else d))
    if "cites-both" in stages:
        from backend.app.api.cites_both import compute_cites_both_for_domain
        note("cites-both", **{k: v for k, v in compute_cites_both_for_domain(slug).items()
                              if not isinstance(v, (list, dict))})
    return log


def main() -> int:
    from backend.app.corpus.multi_domain import DOMAINS
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", choices=sorted(DOMAINS), required=True)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--run-budget", type=float, default=0.0)
    ap.add_argument("--run-start-ledger", type=float, default=None,
                    help="ledger INR when the run began (allocation spans processes)")
    ap.add_argument("--stages", nargs="*", default=list(STAGES))
    a = ap.parse_args()
    if a.plan:
        print(json.dumps(_projections(a.domain), indent=1, default=str))
        return 0
    log = run(a.domain, RunBudget(a.run_budget, a.run_start_ledger), tuple(a.stages))
    print(json.dumps(log, indent=1, default=str)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
