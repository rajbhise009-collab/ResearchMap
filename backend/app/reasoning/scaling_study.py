"""Yield-vs-corpus-size scaling study. FREE — no extraction, no API calls.

Subsamples the clean 113-paper corpus at N in {40,60,80,100,113}, with 5
stratified random draws per N (full-text/abstract ratio held constant),
re-runs all scorers on each sub-corpus, and reports mean±spread of each
yield metric. Contradiction *candidate pairs* come from the free cosine
shortlist (scales pairwise); *confirmed* contradictions come from the
cached regime-aware verdicts.

Writes docs/findings/corpus-scaling-study.md.
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.reasoning import scorers as S  # noqa: E402
from backend.app.reasoning.corpus_view import ReasoningCorpus, load_reasoning_corpus  # noqa: E402
from backend.app.relationships.corpus_loader import LoadedCorpus  # noqa: E402
from backend.app.relationships.shortlist import shortlist_pairs  # noqa: E402

NS = [40, 60, 80, 100, 113]
DRAWS = 5
DOC = REPO_ROOT / "data" / "reasoning" / "scaling_curves.md"


def _src(fwid: str) -> str:
    parts = fwid.split(":")
    return ":".join(parts[:2]) if len(parts) >= 2 else fwid


def subset(rc: ReasoningCorpus, keep: set[str]) -> ReasoningCorpus:
    cidx = [i for i, cid in enumerate(rc.claim_ids) if rc.claim_paper.get(cid) in keep]
    cids = [rc.claim_ids[i] for i in cidx]
    cvecs = rc.claim_vectors[cidx] if cidx else np.zeros((0, rc.claim_vectors.shape[1] if rc.claim_vectors.ndim == 2 else 1), np.float32)
    claim_paper = {cid: rc.claim_paper[cid] for cid in cids}
    fw_keep = [i for i, fid in enumerate(rc.fw_ids) if _src(fid) in keep]
    fw_ids = [rc.fw_ids[i] for i in fw_keep]
    fw_vecs = rc.fw_vectors[fw_keep] if (rc.fw_vectors is not None and fw_keep) else None
    loaded = LoadedCorpus(
        papers={p: rc._loaded.papers[p] for p in keep if p in rc._loaded.papers},
        extractions={p: rc._loaded.extractions[p] for p in keep if p in rc._loaded.extractions},
        claim_paper=claim_paper, claim_source={})
    return ReasoningCorpus(
        papers={p: rc.papers[p] for p in keep},
        own_limitations=[(l, pid) for l, pid in rc.own_limitations if pid in keep],
        future_work=[(f, m) for f, m in rc.future_work if m.paper_id in keep],
        addressals=[a for a in rc.addressals if a.from_paper_id in keep and a.to_paper_id in keep],
        contradictions=[r for r in rc.contradictions if r.from_paper_id in keep and r.to_paper_id in keep],
        citation_edges={(a, b) for a, b in rc.citation_edges if a in keep and b in keep},
        claim_ids=cids, claim_vectors=cvecs,
        paper_vectors={p: rc.paper_vectors[p] for p in keep if p in rc.paper_vectors},
        fw_ids=fw_ids, fw_vectors=fw_vecs, claim_paper=claim_paper, _loaded=loaded)


def _candidate_pairs(sub: ReasoningCorpus) -> int:
    s = get_settings()
    if len(sub.claim_ids) < 2:
        return 0
    return len(shortlist_pairs(sub.claim_ids, sub.claim_vectors, sub.claim_paper,
                               threshold=s.rel_similarity_threshold,
                               max_per_claim=s.rel_max_candidates_per_claim,
                               cross_paper_only=s.rel_cross_paper_only))


def _orphan_split(sub: ReasoningCorpus) -> Counter:
    s = get_settings()
    labels = defaultdict(set)
    for a in sub.addressals:
        labels[a.future_work_id].add(a.label)
    fw_index = {fid: i for i, fid in enumerate(sub.fw_ids)}
    paper_year = {p: m.year for p, m in sub.papers.items()}
    claim_year = np.array([paper_year.get(sub.claim_paper.get(c)) or -1 for c in sub.claim_ids])
    dist = Counter()
    for fw, meta in sub.future_work:
        lab = labels.get(fw.id, set())
        if "addressed" in lab:
            dist["addressed"] += 1; continue
        if "partial" in lab:
            dist["partial"] += 1; continue
        if fw.id not in fw_index or meta.year is None or sub.fw_vectors is None or len(sub.claim_ids) == 0:
            dist["indeterminate"] += 1; continue
        sims = sub.claim_vectors @ sub.fw_vectors[fw_index[fw.id]]
        later = claim_year > meta.year
        near = 0
        if later.any():
            idx = np.where(later)[0]
            near = len({sub.claim_paper.get(sub.claim_ids[int(k)])
                        for k in idx if sims[k] >= s.rel_futurework_topical_threshold})
        dist["unaddressed" if near >= s.rel_futurework_min_near_later else "indeterminate"] += 1
    return dist


def _metrics(sub: ReasoningCorpus) -> dict:
    orph = _orphan_split(sub)
    return {
        "persistent": len(S.score_persistent_limitations(sub)),
        "contra_candidates": _candidate_pairs(sub),
        "contra_confirmed": len(S.score_unresolved_contradictions(sub)),
        "orphan_unaddressed": len(S.score_orphaned_future_work(sub)),
        "orphan_addressed": orph["addressed"],
        "orphan_partial": orph["partial"],
        "orphan_indeterminate": orph["indeterminate_small_corpus"] + orph["indeterminate"],
        "structural_holes": len(S.score_structural_holes(sub)),
    }


def run() -> dict:
    rc = load_reasoning_corpus()
    ids = sorted(rc.papers)
    ft = [p for p in ids if rc.papers[p].input_source == "fulltext"]
    ab = [p for p in ids if rc.papers[p].input_source != "fulltext"]
    ft_ratio = len(ft) / len(ids)

    results: dict[int, list[dict]] = {}
    for N in NS:
        draws = 1 if N >= len(ids) else DRAWS
        n_ft = min(len(ft), round(N * ft_ratio))
        n_ab = N - n_ft
        per_draw = []
        for d in range(draws):
            rng = np.random.default_rng(1000 * N + d)
            if N >= len(ids):
                keep = set(ids)
            else:
                keep = set(rng.choice(ft, n_ft, replace=False).tolist()
                           + rng.choice(ab, min(n_ab, len(ab)), replace=False).tolist())
            per_draw.append(_metrics(subset(rc, keep)))
        results[N] = per_draw
    return results


def _agg(vals):
    m = st.mean(vals)
    sd = st.pstdev(vals) if len(vals) > 1 else 0.0
    return m, sd


def main() -> int:
    results = run()
    metrics = ["persistent", "contra_candidates", "contra_confirmed",
               "orphan_unaddressed", "orphan_addressed", "orphan_indeterminate",
               "structural_holes"]
    table = {N: {mtr: _agg([d[mtr] for d in draws]) for mtr in metrics}
             for N, draws in results.items()}

    L = ["# Corpus-scaling study — yield vs. N (2026-07-29)", "",
         "Free study: the clean 113-paper corpus subsampled at N∈{40,60,80,"
         "100,113}, 5 stratified draws per N (full-text ratio held at "
         f"{load_reasoning_corpus().__class__ and round(sum(1 for p in load_reasoning_corpus().papers.values() if p.input_source=='fulltext')/113,2)}), "
         "scorers re-run on each. No new extraction or API calls: contradiction "
         "*candidates* from the free cosine shortlist; *confirmed* from cached "
         "regime-aware verdicts.", "",
         "## Method", "",
         "- Stratified subsample (fixed full-text:abstract ratio), 5 draws/N "
         "(1 at N=113, the full set). Mean ± population SD reported.",
         "- Each draw builds a filtered `ReasoningCorpus` (papers, claims, "
         "embeddings, limitations, addressals, contradictions, citation edges, "
         "future-work vectors) and runs every scorer.", "",
         "## Curves (mean ± SD across draws)", "",
         "| N | persist | contra cand | contra conf | orphan unaddr | orphan addr | orphan indet | struct holes |",
         "|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for N in NS:
        t = table[N]
        def c(m):
            mm, sd = t[m]
            return f"{mm:.1f}±{sd:.1f}"
        L.append(f"| {N} | {c('persistent')} | {c('contra_candidates')} | "
                 f"{c('contra_confirmed')} | {c('orphan_unaddressed')} | "
                 f"{c('orphan_addressed')} | {c('orphan_indeterminate')} | "
                 f"{c('structural_holes')} |")
    L.append("")

    # curve-shape diagnostics: growth exponent p where metric ~ N^p (log-log slope)
    L.append("## Curve shape (log-log slope p, metric ∝ N^p)")
    L.append("")
    L.append("p≈0 flat · p≈1 linear · p>1 super-linear (pairwise signal). "
             "Fit on the mean at N=40 vs 113.")
    L.append("")
    L.append("| metric | mean@40 | mean@113 | slope p |")
    L.append("|:--|--:|--:|--:|")
    import math
    for m in metrics:
        y0, y1 = table[40][m][0], table[113][m][0]
        p = (math.log(max(y1, 1e-9)) - math.log(max(y0, 1e-9))) / (math.log(113) - math.log(40))
        L.append(f"| {m} | {y0:.1f} | {y1:.1f} | {p:.2f} |")
    L.append("")

    DOC.write_text("\n".join(L))
    print(json.dumps({N: {m: round(table[N][m][0], 2) for m in metrics} for N in NS}, indent=2))
    print(f"\nwrote {DOC.relative_to(REPO_ROOT)} (partial — extrapolation/cost appended next)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
