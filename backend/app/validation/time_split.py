"""Retrospective time-split test (Phase 6 pilot) — free, deterministic.

  python -m backend.app.validation.time_split --slug ml-fairness --year 2018 --k 2

Implements the matching rule in docs/opportunity-criteria.md
("Matching rule for retrospective validation") for the open-question
(orphaned future-work) scorer, using only cached data (no API call):

 1. Freeze: the library restricted to papers with year <= Y — their claims,
    future-work items, citation edges, and only those future-work matcher
    verdicts whose later paper is also <= Y. The unchanged Phase-4 scorer
    ranks the open questions it finds in that frozen corpus.
 2. Evidence R: the library's papers with year in [Y+1, Y+k].
 3. Match (no language model): opportunity O is addressed when some claim in
    R has cosine >= tau with O's future-work text AND that claim has no
    pre-freeze claim with cosine >= tau (it was new, so O was open at Y).
 4. tau is calibrated at the OPPORTUNITY level against a within-field
    negative set: for each O, the best cosine over a random draw (size of R's
    claim set) of claims from papers OLDER than O's source paper, which
    cannot address a direction not yet written; tau = the 95th percentile.
    Novelty uses a separate near-duplicate threshold: the 99th percentile of
    cosine between claims of different pre-freeze papers.
 5. Metric: precision@K of the engine's ranking, against (a) the pool's base
    rate (what a random ordering of the same candidates gets; one-sided
    hypergeometric p-value) and (b) a no-future-information baseline: newest
    source paper first. Citation counts are NOT used (today's counts leak
    the future).

Limits (also in the findings doc): R is the library's own later papers, a
sample chosen by a snowball, not the field's output; the future-work matcher's
verdicts for the frozen corpus are the subset of the full-corpus run (its
shortlist was drawn with all papers present); embeddings are the same model
for both sides; small n.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, replace

import numpy as np

from backend.app.config import REPO_ROOT

OUT = REPO_ROOT / "data" / "validation"
SEED = 20261009


@dataclass
class Result:
    slug: str
    year: int
    k: int
    n_frozen_papers: int
    n_r_papers: int
    n_r_claims: int
    tau: float
    pool: int
    base_rate: float
    ranked: list[dict]
    precision: dict
    recency_precision: dict
    p_values: dict


def _frozen(rc, year: int):
    keep = {pid for pid, p in rc.papers.items() if p.year is not None and p.year <= year}
    cidx = [i for i, c in enumerate(rc.claim_ids) if rc.claim_paper.get(c) in keep]
    fw_keep = {fw.id for fw, m in rc._loaded.future_work() if m.paper_id in keep}
    fidx = [i for i, f in enumerate(rc.fw_ids) if f in fw_keep]
    return replace(
        rc,
        papers={pid: rc.papers[pid] for pid in keep},
        own_limitations=[(l, p) for l, p in rc.own_limitations if p in keep],
        future_work=[(fw, m) for fw, m in rc._loaded.future_work() if m.paper_id in keep],
        addressals=[a for a in rc.addressals if a.from_paper_id in keep and a.to_paper_id in keep],
        contradictions=[],
        citation_edges={(a, b) for a, b in rc.citation_edges if a in keep and b in keep},
        claim_ids=[rc.claim_ids[i] for i in cidx],
        claim_vectors=rc.claim_vectors[cidx],
        paper_vectors={p: v for p, v in rc.paper_vectors.items() if p in keep},
        fw_ids=[rc.fw_ids[i] for i in fidx],
        fw_vectors=rc.fw_vectors[fidx] if len(fidx) else rc.fw_vectors[:0],
    )


def _negatives(slug: str) -> np.ndarray:
    """Claim vectors from every OTHER built multi-domain library."""
    from backend.app.api import registry
    from backend.app.reasoning.library_corpus import claim_vectors, load_loaded_corpus
    out = []
    for lib in registry.built():
        s = lib["slug"]
        if s in (slug, "llm-calibration"):
            continue
        _ids, v = claim_vectors(s, load_loaded_corpus(s))
        out.append(v)
    return np.vstack(out)


def _hypergeom_sf(k: int, N: int, K: int, n: int) -> float:
    """P(X >= k) drawing n of N items, K of them successes."""
    tot = math.comb(N, n)
    return sum(math.comb(K, i) * math.comb(N - K, n - i) for i in range(k, min(K, n) + 1)) / tot


def run(slug: str, year: int, k: int = 2, ks=(5, 10, 20)) -> Result:
    from backend.app.reasoning.library_corpus import load_library_corpus
    from backend.app.reasoning.scorers import score_orphaned_future_work
    rc = load_library_corpus(slug)
    # every future-work item in the frozen corpus needs a vector
    fz = _frozen(rc, year)
    opps = sorted(score_orphaned_future_work(fz), key=lambda o: (-o.score, o.id))
    yr = {pid: p.year for pid, p in rc.papers.items()}
    r_papers = {pid for pid, y in yr.items() if y is not None and year < y <= year + k}
    r_idx = [i for i, c in enumerate(rc.claim_ids) if rc.claim_paper.get(c) in r_papers]
    pre_idx = [i for i, c in enumerate(rc.claim_ids) if yr.get(rc.claim_paper.get(c)) is not None
               and yr[rc.claim_paper[c]] <= year]
    R = rc.claim_vectors[r_idx]
    PRE = rc.claim_vectors[pre_idx]
    fwv = {f: rc.fw_vectors[i] for i, f in enumerate(rc.fw_ids)}
    # tau at the OPPORTUNITY level, within the same field: negatives are
    # claims from papers OLDER than O's source paper (they cannot address a
    # direction not yet written). Unrelated-field negatives (first pilot)
    # gave tau below the field's ordinary topical similarity; see findings.
    rng = np.random.default_rng(SEED)
    cyear = np.array([yr.get(rc.claim_paper.get(c)) or 0 for c in rc.claim_ids])
    best = []
    size = max(1, len(r_idx))
    for o in opps:
        v = fwv[o.evidence_trail[0]]
        src_year = yr.get(o.supporting_paper_ids[0]) or 0
        older = np.where((cyear > 0) & (cyear < src_year))[0]
        if len(older) == 0:
            continue
        for _rep in range(20):
            draw = rc.claim_vectors[rng.choice(older, size=size, replace=len(older) < size)]
            best.append(float((draw @ v).max()))
    tau = float(np.percentile(best, 95)) if best else 1.0
    # novelty: an R claim counts only if no pre-freeze claim is a near-duplicate
    # of it (99th percentile of cross-paper claim similarity before the freeze)
    pre_paper = np.array([rc.claim_paper[rc.claim_ids[i]] for i in pre_idx])
    S = PRE @ PRE.T if len(PRE) else np.zeros((0, 0))
    cross = S[pre_paper[:, None] != pre_paper[None, :]] if len(PRE) else np.zeros(1)
    tau_equiv = float(np.percentile(cross, 99))
    novel = (R @ PRE.T).max(axis=1) < tau_equiv if len(PRE) and len(R) else np.ones(len(R), bool)
    ranked = []
    for rank, o in enumerate(opps, 1):
        v = fwv[o.evidence_trail[0]]
        sims = R @ v if len(R) else np.zeros(0)
        hit = bool(((sims >= tau) & novel).any()) if len(sims) else False
        src = o.supporting_paper_ids[0]
        ranked.append({"rank": rank, "opportunity": o.id, "score": round(o.score, 4),
                       "source": src, "source_year": yr.get(src),
                       "best_r_cosine": round(float(sims.max()), 4) if len(sims) else None,
                       "addressed_later": hit})
    N = len(ranked)
    hits = sum(r["addressed_later"] for r in ranked)
    base = hits / N if N else 0.0
    prec, prec_rec, pv = {}, {}, {}
    by_recent = sorted(ranked, key=lambda r: (-(r["source_year"] or 0), r["opportunity"]))
    for K in ks:
        if K > N:
            continue
        h = sum(r["addressed_later"] for r in ranked[:K])
        prec[K] = round(h / K, 3)
        prec_rec[K] = round(sum(r["addressed_later"] for r in by_recent[:K]) / K, 3)
        pv[K] = round(_hypergeom_sf(h, N, hits, K), 4)
    res = Result(slug, year, k, len(fz.papers), len(r_papers), len(r_idx), round(tau, 4), N,
                 round(base, 3), ranked, prec, prec_rec, pv)
    res.tau_equiv = round(tau_equiv, 4)
    res.novel_r_claims = int(novel.sum())
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--k", type=int, default=2)
    a = ap.parse_args()
    r = run(a.slug, a.year, a.k)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"time_split_{a.slug}_{a.year}_k{a.k}.json").write_text(json.dumps(r.__dict__, indent=1, default=str))
    print(json.dumps({k: v for k, v in r.__dict__.items() if k != "ranked"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
