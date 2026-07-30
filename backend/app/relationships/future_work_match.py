"""Future-work "addressed_by" matching.

For each FutureWork item, search the corpus for a LATER paper whose
claims are semantically close to the future-work statement; if one is
found above threshold, that paper `addressed` it. Deterministic
(embedding cosine + a year filter); no LLM, no scoring.

The small-corpus false-positive failure mode applies even at n=200
(docs/opportunity-criteria.md). Orphan-hood is CORPUS-RELATIVE: "no later
paper addressed this" is only informative if the corpus holds enough
later, TOPICALLY-NEAR papers that the addressing work would plausibly
have been seen. The criterion is therefore not "how many later papers
exist" (which counts unrelated work) but "how many later papers are on
this research thread" — later papers with a claim whose cosine to the
future-work item is >= `topical_threshold`. Only when at least
`min_near_later` such papers exist AND none matched is the item
`unaddressed`; otherwise it is `indeterminate_small_corpus`. This
replaces the earlier crude all-later-papers count that produced a
non-credible 91% orphan rate.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.relationships.corpus_loader import LoadedCorpus


@dataclass
class FutureWorkMatch:
    future_work_id: str
    paper_id: str
    source_year: int | None
    addressed_by: str | None
    best_similarity: float
    later_papers_in_corpus: int      # all later papers (context)
    near_later_papers: int           # later papers ON THIS THREAD (the criterion)
    status: str  # "addressed" | "unaddressed" | "indeterminate_small_corpus"


def match_future_work(
    corpus: LoadedCorpus,
    fw_ids: list[str],
    fw_vectors,                 # np.ndarray[m, dim] aligned to fw_ids
    claim_ids: list[str],
    claim_vectors,              # np.ndarray[n, dim]
    *,
    threshold: float,
    topical_threshold: float = 0.65,
    min_near_later: int = 5,
) -> list[FutureWorkMatch]:
    import numpy as np

    fw_lookup = {fw.id: (fw, meta) for fw, meta in corpus.future_work()}
    claim_paper = corpus.claim_paper
    paper_year = {pid: m.year for pid, m in corpus.papers.items()}
    cvec = np.asarray(claim_vectors, dtype=np.float32)
    claim_year = np.array(
        [paper_year.get(claim_paper.get(cid)) or -1 for cid in claim_ids]
    )
    claim_pid = [claim_paper.get(cid) for cid in claim_ids]

    out: list[FutureWorkMatch] = []
    for i, fw_id in enumerate(fw_ids):
        fw, meta = fw_lookup[fw_id]
        src_year = meta.year
        n_later = sum(1 for pid, y in paper_year.items()
                      if y is not None and src_year is not None and y > src_year
                      and pid != meta.paper_id)

        best_sim = -1.0
        best_pid = None
        near_later = 0
        if src_year is not None:
            sims = cvec @ np.asarray(fw_vectors[i], dtype=np.float32)
            later = claim_year > src_year
            if later.any():
                idx = np.where(later)[0]
                j = idx[int(np.argmax(sims[idx]))]
                best_sim = float(sims[j])
                best_pid = claim_pid[int(j)]
                # Later papers with >=1 claim topically near the FW item —
                # the "same research thread, came after" population.
                near_later = len({
                    claim_pid[k] for k in idx if sims[k] >= topical_threshold
                })

        if best_sim >= threshold and best_pid is not None:
            status, addressed_by = "addressed", best_pid
        elif near_later >= min_near_later:
            status, addressed_by = "unaddressed", None
        else:
            # Not enough later same-thread papers to have plausibly seen
            # the answer — refuse to call it orphaned.
            status, addressed_by = "indeterminate_small_corpus", None

        out.append(FutureWorkMatch(
            future_work_id=fw_id,
            paper_id=meta.paper_id,
            source_year=src_year,
            addressed_by=addressed_by,
            best_similarity=round(best_sim, 4) if best_sim >= 0 else 0.0,
            later_papers_in_corpus=n_later,
            near_later_papers=near_later,
            status=status,
        ))
    return out


__all__ = ["FutureWorkMatch", "match_future_work"]
