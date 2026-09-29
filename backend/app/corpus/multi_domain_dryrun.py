"""Combined multi-domain dry-run — extraction + contradiction pass.

Applies Raj's cut order until the projection fits ₹850:
  (a) skip structural-hole LLM confirmations  (deferred; not run at all)
  (b) tighten the per-claim contradiction candidate cap
  (c) reduce corpus size (dropping peripheral before core)

Never drops contradiction classification. Never touches the LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.corpus.multi_domain import DOMAINS, _prelabel_path  # noqa: E402
from backend.app.corpus.multi_domain_extract import dry_run as extract_dry_run  # noqa: E402
from backend.app.extraction.pricing import OUT_TOKENS_PAIR, cost  # noqa: E402
from backend.app.extraction.spend_ledger import CAP_INR, FX_USD_TO_INR  # noqa: E402


# Contradiction-pair projection. Based on LLM-cal library numbers
# (docs/relationship-layer.md): 1,022 claims -> 437 pairs at threshold
# 0.78, cap 10 — a candidate-per-claim rate of ~0.43.
CONTRADICTION_RATE_PER_CLAIM = 0.43
IN_TOKENS_PAIR = 300


def _claim_estimate(slug: str) -> int:
    """Estimate claim count from prelabelled entries — 8 per full-text
    paper, 4 per abstract-only, based on the observed LLM-cal average."""
    payload = json.loads(_prelabel_path(DOMAINS[slug]).read_text())
    entries = payload["entries"]
    full = sum(1 for e in entries if e.get("input_source") == "fulltext")
    abst = len(entries) - full
    return full * 8 + abst * 4


def contradiction_projection(slug: str, *,
                               per_claim_cap: int = 4,
                               corpus_size: int | None = None) -> dict:
    """Project contradiction-pass cost for a domain."""
    n_claims = _claim_estimate(slug)
    if corpus_size:
        payload = json.loads(_prelabel_path(DOMAINS[slug]).read_text())
        scale = min(1.0, corpus_size / max(1, len(payload["entries"])))
        n_claims = int(n_claims * scale)
    n_pairs = int(n_claims * CONTRADICTION_RATE_PER_CLAIM * (per_claim_cap / 4.0))
    proj_in = n_pairs * IN_TOKENS_PAIR
    proj_out = n_pairs * OUT_TOKENS_PAIR
    proj_usd = cost(proj_in, proj_out, batch=False)
    return {
        "slug": slug, "per_claim_cap": per_claim_cap,
        "corpus_size": corpus_size,
        "n_claims_est": n_claims, "n_pairs_est": n_pairs,
        "proj_cost_usd": proj_usd, "proj_cost_inr": proj_usd * FX_USD_TO_INR,
    }


def project(*, per_claim_cap: int = 4,
             corpus_size: int | None = None,
             skip_structural: bool = True) -> dict:
    """Project total spend under a set of cut parameters."""
    domains = list(DOMAINS)
    ex = {}
    total_usd = 0.0
    for d in domains:
        ex[d] = extract_dry_run(d)
        # If corpus_size was cut, scale extraction linearly (peripheral
        # papers cost the same as core per-paper).
        if corpus_size:
            scale = corpus_size / max(1, ex[d]["n_entries"])
            ex[d]["proj_cost_usd"] *= scale
            ex[d]["proj_cost_inr"] *= scale
            ex[d]["applied_corpus_cut"] = corpus_size
        total_usd += ex[d]["proj_cost_usd"]
    co = {d: contradiction_projection(d, per_claim_cap=per_claim_cap,
                                        corpus_size=corpus_size)
          for d in domains}
    for d in domains:
        total_usd += co[d]["proj_cost_usd"]
    struct_note = "SKIPPED per cut (a)" if skip_structural else "included"
    return {
        "fx_usd_to_inr": FX_USD_TO_INR, "cap_inr": CAP_INR,
        "cap_usd": CAP_INR / FX_USD_TO_INR,
        "cuts": {"skip_structural_confirm": skip_structural,
                  "per_claim_cap": per_claim_cap,
                  "corpus_size": corpus_size or "unchanged (100 per domain)"},
        "extract_per_domain": ex,
        "contradiction_per_domain": co,
        "structural_hole_confirm": struct_note,
        "total_projected_usd": total_usd,
        "total_projected_inr": total_usd * FX_USD_TO_INR,
        "headroom_inr": CAP_INR - (total_usd * FX_USD_TO_INR),
        "fits": (total_usd * FX_USD_TO_INR) <= CAP_INR,
    }


def apply_cuts_until_fits() -> dict:
    """Try progressively harsher cuts. Ordered per Raj's spec."""
    log = []
    # Step 0: no cuts (structural is already skipped by default here).
    proj = project(per_claim_cap=4, corpus_size=None, skip_structural=True)
    log.append({"cut": "baseline (structural skipped from the start per cut a)",
                 **proj})
    if proj["fits"]:
        return {"chosen": log[-1], "trace": log}
    # Cut (b): tighten per-claim cap 4 -> 3 -> 2
    for cap in (3, 2):
        proj = project(per_claim_cap=cap, corpus_size=None, skip_structural=True)
        log.append({"cut": f"per_claim_cap={cap}", **proj})
        if proj["fits"]:
            return {"chosen": log[-1], "trace": log}
    # Cut (c): reduce corpus (drop peripheral first, then trim core)
    # Peripheral is 100-core; if core is <100, target dropping to core-count
    # first; then further trim.
    for size in (80, 60):
        proj = project(per_claim_cap=2, corpus_size=size, skip_structural=True)
        log.append({"cut": f"corpus_size={size}", **proj})
        if proj["fits"]:
            return {"chosen": log[-1], "trace": log}
    return {"chosen": None, "trace": log, "reason": "still over cap after all cuts"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--auto-cut", action="store_true",
                   help="run the progressive-cut ladder and return the "
                        "first setting that fits")
    args = p.parse_args()
    if args.auto_cut:
        print(json.dumps(apply_cuts_until_fits(), indent=2))
    else:
        print(json.dumps(project(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
