"""Embedding shortlist — the combinatorial-budget guard.

~1,000 claims is ~500k naive pairs; all-pairs LLM comparison is
forbidden. Instead, embeddings cheaply pre-select the few pairs worth a
pairwise LLM call: only pairs with cosine similarity >= threshold, and
only the top-`max_per_claim` neighbours of each claim, become candidates.
Both knobs are config-driven (`REL_SIMILARITY_THRESHOLD`,
`REL_MAX_CANDIDATES_PER_CLAIM`) and documented in
docs/relationship-layer.md.

This is pure deterministic math (numpy cosine) — no LLM, no scoring
judgement. It decides *which pairs to look at*, not what they mean.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidatePair:
    from_claim_id: str
    to_claim_id: str
    similarity: float


def shortlist_pairs(
    claim_ids: list[str],
    vectors,                      # np.ndarray[n, dim], L2-normalized
    claim_paper: dict[str, str],
    *,
    threshold: float,
    max_per_claim: int,
    cross_paper_only: bool = True,
) -> list[CandidatePair]:
    """Return candidate pairs (canonical id order) above `threshold`,
    keeping at most `max_per_claim` neighbours per claim. A pair survives
    if it is a top-`max_per_claim` neighbour of EITHER endpoint."""
    import numpy as np

    n = len(claim_ids)
    if n < 2:
        return []
    v = np.asarray(vectors, dtype=np.float32)
    sims = v @ v.T                       # cosine (vectors are unit-norm)
    np.fill_diagonal(sims, -1.0)         # never pair a claim with itself

    if cross_paper_only:
        papers = [claim_paper.get(cid) for cid in claim_ids]
        same = np.array([[papers[i] == papers[j] for j in range(n)]
                         for i in range(n)])
        sims[same] = -1.0

    pairs: dict[tuple[str, str], float] = {}
    for i in range(n):
        row = sims[i]
        # indices above threshold, then top-k by similarity
        cand = np.where(row >= threshold)[0]
        if cand.size == 0:
            continue
        topk = cand[np.argsort(row[cand])[::-1][:max_per_claim]]
        for j in topk:
            a, b = claim_ids[i], claim_ids[int(j)]
            key = (a, b) if a < b else (b, a)
            # Clamp: float32 cosine of near-identical unit vectors can
            # exceed 1.0 by ~1e-7, tripping the [-1,1] schema bound.
            sim = float(min(1.0, max(-1.0, row[int(j)])))
            pairs[key] = max(pairs.get(key, -1.0), sim)

    out = [CandidatePair(a, b, s) for (a, b), s in pairs.items()]
    out.sort(key=lambda p: p.similarity, reverse=True)
    return out


__all__ = ["CandidatePair", "shortlist_pairs"]
