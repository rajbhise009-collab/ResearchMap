"""Incremental contradiction pass: classify ONLY pairs not yet paid for.

Builds the shortlist on the current extraction set (embeddings cached per
claim, so only new claims hit the API), classifies unseen pairs via
classify_pairs (which saves each verdict as it returns and skips anything
already classified), and writes `reasoning/coverage.json` — the record of
what the disagreement check has actually covered. The snapshot export
reads coverage.json to state that coverage plainly on the site.

Optional `--priority-papers`: pairs touching those paper ids are classified
first (used for the ML-fairness impossibility-paper re-check).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.app.corpus.multi_domain_reason import (  # noqa: E402
    DOMAINS, LAST_EMBED_STATS, _reason_dir, classify_pairs, compute_shortlist,
    load_classified_keys, load_extractions,
)


def coverage_path(slug: str) -> Path:
    return _reason_dir(slug) / "coverage.json"


def write_coverage(slug: str, exts, pairs, *, note: str = "",
                   threshold: float | None = None,
                   max_per_claim: int | None = None) -> dict:
    """Record shortlist vs classified counts for the CURRENT extraction set."""
    done = load_classified_keys(slug)
    keys = {(p.from_claim_id, p.to_claim_id) for p in pairs}
    classified = len(keys & done)
    paper_ids = sorted(e.paper_id for e in exts)
    claim_paper = {c.id: e.paper_id for e in exts for c in (e.claims or [])}
    pending = sorted({claim_paper[k[i]] for k in keys - done for i in (0, 1)
                      if k[i] in claim_paper})
    cov = {
        "date": time.strftime("%Y-%m-%d"),
        "n_papers_in_check": len(paper_ids),
        "paper_ids": paper_ids,
        "shortlist_pairs": len(keys),
        "classified_pairs": classified,
        "unclassified_pairs": len(keys) - classified,
        "papers_with_pending_pairs": len(pending),
        "pending_paper_ids": pending,
        "complete": classified == len(keys),
        "shortlist_settings": {"threshold": threshold,
                               "max_per_claim": max_per_claim},
        "note": note,
    }
    p = coverage_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cov, indent=2))
    return cov


# Shortlist settings: shared with multi_domain_reason (single source).
from backend.app.corpus.multi_domain_reason import (  # noqa: E402
    LIBRARY_MAX_PER_CLAIM,
    LIBRARY_THRESHOLD,
)


def run(slug: str, *, threshold: float = LIBRARY_THRESHOLD,
        max_per_claim: int = LIBRARY_MAX_PER_CLAIM,
        max_inr: float | None = None, projected_inr_per_call: float | None = None,
        priority_papers: set[str] | None = None, dry_run: bool = False) -> dict:
    slug = DOMAINS[slug].slug
    exts = load_extractions(slug)
    pairs = compute_shortlist(exts, threshold=threshold,
                              max_per_claim=max_per_claim,
                              use_real_embeddings=True, slug=slug)
    embed_stats = dict(LAST_EMBED_STATS)
    done = load_classified_keys(slug)
    unseen = [p for p in pairs if (p.from_claim_id, p.to_claim_id) not in done]
    if priority_papers:
        claim_paper = {c.id: e.paper_id for e in exts for c in (e.claims or [])}
        def touches(p):
            return (claim_paper.get(p.from_claim_id) in priority_papers
                    or claim_paper.get(p.to_claim_id) in priority_papers)
        unseen.sort(key=lambda p: (0 if touches(p) else 1))
    summary = {"slug": slug, "n_extractions": len(exts),
               "shortlist_pairs": len(pairs), "unseen_pairs": len(unseen),
               "embeddings": embed_stats}
    if dry_run:
        summary["coverage"] = write_coverage(slug, exts, pairs, threshold=threshold,
                                             max_per_claim=max_per_claim)
        return summary
    res = classify_pairs(slug, exts, unseen, max_inr=max_inr,
                         projected_inr_per_call=projected_inr_per_call)
    summary["classify"] = res
    summary["coverage"] = write_coverage(slug, exts, pairs, threshold=threshold,
                                         max_per_claim=max_per_claim)
    return summary


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--slug", required=True)
    p.add_argument("--threshold", type=float, default=LIBRARY_THRESHOLD)
    p.add_argument("--max-per-claim", type=int, default=LIBRARY_MAX_PER_CLAIM)
    p.add_argument("--max-inr", type=float)
    p.add_argument("--projected-inr-per-call", type=float)
    p.add_argument("--priority-papers", nargs="*")
    p.add_argument("--dry-run", action="store_true",
                   help="shortlist + coverage only; no classifier calls")
    a = p.parse_args()
    r = run(a.slug, threshold=a.threshold, max_per_claim=a.max_per_claim,
            max_inr=a.max_inr, projected_inr_per_call=a.projected_inr_per_call,
            priority_papers=set(a.priority_papers) if a.priority_papers else None,
            dry_run=a.dry_run)
    r.get("coverage", {}).pop("paper_ids", None)
    r.get("coverage", {}).pop("pending_paper_ids", None)
    print(json.dumps(r, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
