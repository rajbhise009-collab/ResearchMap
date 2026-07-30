"""The five reasoning-engine scorers. DETERMINISTIC PYTHON ONLY — no LLM
anywhere in this module. Each is a pure function
`(ReasoningCorpus) -> list[Opportunity]`; each Opportunity carries
`component_scores` (the named numeric contributions), a deterministic
`explanation` built from the evidence trail, and full provenance.

Traceability to docs/opportunity-criteria.md is stated per scorer. Where a
scoring factor is NOT in that document, it is flagged in the code comment
and the review output — not silently invented.

Scores map raw signals to [0,1] via `saturating(n,k)=n/(n+k)` (count=k gives
0.5) or explicit clamps; weights come from config, chosen with reasoning in
docs/reasoning-engine.md.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from backend.app.config import get_settings
from backend.app.models import GapType, Opportunity
from backend.app.reasoning.corpus_view import ReasoningCorpus
from backend.app.reasoning.fidelity import effective_count
from backend.app.reasoning.independence import independent_set

# Generic methodological categories that fail the actionability "named
# object of study" bar (opportunity-criteria.md actionable #1). Flagged, not
# dropped — the reviewer decides.
GENERIC_CATEGORIES = {
    "computational-cost", "high-computational-cost", "computational-efficiency",
    "inference-latency", "small-sample-size", "sample-representativeness",
    "lack-of-empirical-validation", "evaluation-scope", "task-scope-limitation",
    "limited-dataset-scope", "domain-generality", "scalability",
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _saturating(n: float, k: float) -> float:
    return n / (n + k) if (n + k) > 0 else 0.0


def _cos(a, b) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _titles(corpus, pids):
    return [(p, corpus.papers[p].title) for p in pids if p in corpus.papers]


# Sub-construct keywords for the same-construct gate (gated categories only).
# A limitation "computationally expensive" can mean any of these distinct
# bottlenecks; only same-sub-construct limitations may cluster together.
_SUBCONSTRUCT = [
    ("inference", ("inference", "latency", "forward pass", "at test", "test-time",
                   "test time", "deployment", "per input", "per-input", "real-time",
                   "real time", "serving")),
    ("training", ("training", "train ", "fine-tun", "finetun", "epoch", "gradient step",
                  "backprop", "pre-training", "pretrain")),
    ("sampling", ("sampl", "multiple response", "multiple generation", "monte carlo",
                  "ensemble", "multiple forward", "multiple model", "multiple queries",
                  "multiple network")),
    ("evaluation", ("evaluat", "benchmark", "test set", "annotation")),
    ("memory", ("memory", "gpu", "vram", "parameter count", "model size", "storage")),
]


def _cost_subconstruct(text: str) -> str:
    t = (text or "").lower()
    for name, kws in _SUBCONSTRUCT:
        if any(k in t for k in kws):
            return name
    return "general"


# --- 1. Persistent limitations -----------------------------------------
# Traceability: opportunity-criteria.md criterion 1 (>=3 independent
# papers), failure modes (own-work via source_scope=this_work; independence
# collapses first-author dups). gap_type UNADDRESSED_LIMITATION.
# FLAG: "methodological diversity" and "time span" as score boosters are
# NOT in opportunity-criteria.md — they are design choices (config-weighted),
# marked here and in the review. "Absence of resolution" is asserted but NOT
# computable: no limitation-resolution relation exists in Phase 3, so it is
# assumed, not verified (flagged).

def score_persistent_limitations(corpus: ReasoningCorpus) -> list[Opportunity]:
    s = get_settings()
    gated = set(s.reason_gated_categories)
    # Group by category — but for GATED (overloaded) categories, split by
    # sub-construct so different bottlenecks don't count as one limitation.
    lim_by_cat: dict[str, list] = defaultdict(list)
    papers_by_cat: dict[str, set] = defaultdict(set)
    for lim, pid in corpus.own_limitations:
        cat = lim.normalized_category
        key = f"{cat}::{_cost_subconstruct(lim.text)}" if cat in gated else cat
        lim_by_cat[key].append((lim, pid))
        papers_by_cat[key].add(pid)

    out: list[Opportunity] = []
    for cat, pids in papers_by_cat.items():
        indep = independent_set(pids, corpus.papers)
        n = len(indep)
        if n < s.reason_min_independent_papers:
            continue
        eff_corr = effective_count(indep, corpus.papers, corrected=True)
        eff_raw = float(n)
        count_corr = _saturating(eff_corr, k=3.0)
        count_raw = _saturating(eff_raw, k=3.0)
        # methodological diversity (NOT in criteria doc — flagged)
        methods = set()
        for p in indep:
            for m in corpus._loaded.extractions[p].methodologies:
                methods.add(m.name.strip().lower())
        diversity = _saturating(len(methods), k=3.0)
        years = [corpus.papers[p].year for p in indep if corpus.papers[p].year]
        span = (max(years) - min(years)) if len(years) >= 2 else 0
        timespan = _clamp01(span / 5.0)
        blend = (s.reason_persist_w_count * count_corr
                 + s.reason_persist_w_diversity * diversity
                 + s.reason_persist_w_timespan * timespan)
        blend_raw = (s.reason_persist_w_count * count_raw
                     + s.reason_persist_w_diversity * diversity
                     + s.reason_persist_w_timespan * timespan)
        n_ft = sum(1 for p in indep if corpus.papers[p].input_source == "fulltext")
        n_ab = n - n_ft
        frac_ft = n_ft / n
        conf = _clamp01(0.30 + 0.08 * (n - s.reason_min_independent_papers) + 0.25 * frac_ft)
        generic = cat.split("::")[0] in GENERIC_CATEGORIES

        lim_ids = [l.id for l, p in lim_by_cat[cat] if p in indep]
        trail = list(indep) + lim_ids
        sample = [l.text for l, p in lim_by_cat[cat] if p in indep][:3]
        titles = _titles(corpus, indep)
        expl = (
            f"{n} independent papers ({min(years) if years else '?'}–{max(years) if years else '?'}) "
            f"report an own-work limitation normalized to '{cat}'. "
            f"Mixed-fidelity: {n_ft} full-text, {n_ab} abstract-only; score corrected "
            f"for the ~11x full-text detection bias = {blend:.3f} vs uncorrected {blend_raw:.3f}. "
            f"Methodological diversity: {len(methods)} distinct methods (NOTE: diversity/time-span "
            f"weighting extends beyond opportunity-criteria.md). Resolution is ASSUMED absent — "
            f"no limitation-resolution relation exists in Phase 3, so 'unresolved' is unverified. "
            + ("CAVEAT: '" + cat + "' is a generic methodological category; it may fail the "
               "actionability 'named object of study' bar. " if generic else "")
            + "Example limitation statements: " + " | ".join(t[:110] for t in sample)
            + ". Papers: " + "; ".join(f"{p}" for p, _t in titles) + "."
        )
        out.append(Opportunity(
            id=f"opp:persist:{cat}",
            gap_type=GapType.UNADDRESSED_LIMITATION,
            title=f"Recurring unresolved limitation '{cat}' across {n} independent papers",
            score=_clamp01(blend),
            component_scores={
                "count_corrected": round(count_corr, 4), "count_raw": round(count_raw, 4),
                "diversity": round(diversity, 4), "timespan": round(timespan, 4),
                "score_corrected": round(blend, 4), "score_uncorrected": round(blend_raw, 4),
                "n_independent": float(n), "effective_count_corrected": round(eff_corr, 3),
                "n_fulltext": float(n_ft), "n_abstract": float(n_ab),
                "generic_category": 1.0 if generic else 0.0,
            },
            explanation=expl,
            supporting_paper_ids=list(indep),
            confidence=conf,
            evidence_trail=trail,
        ))
    return out


# --- 2. Unresolved contradictions --------------------------------------
# Traceability: opportunity-criteria.md non-triviality #2 (two papers,
# incompatible findings on the same construct, named claim IDs; non-trivial
# when neither cites/acknowledges the other). gap_type
# UNRESOLVED_CONTRADICTION. Expect ~2 corpus-wide — reported honestly.

def score_unresolved_contradictions(corpus: ReasoningCorpus) -> list[Opportunity]:
    ctext = {c.id: c.text for pid, ext in corpus._loaded.extractions.items() for c in ext.claims}
    out: list[Opportunity] = []
    for rel in corpus.contradictions:
        a, b = rel.from_paper_id, rel.to_paper_id
        cites = (a, b) in corpus.citation_edges or (b, a) in corpus.citation_edges
        non_trivial = not cites          # neither acknowledges the other
        sim = rel.similarity or 0.0
        both_ft = all(corpus.papers.get(p) and corpus.papers[p].input_source == "fulltext"
                      for p in (a, b))
        # score: the contradiction's semantic tightness + a non-triviality
        # boost when the two papers don't cite each other.
        score = _clamp01(0.5 * sim + (0.4 if non_trivial else 0.0) + (0.1 if both_ft else 0.0))
        conf = _clamp01(0.35 + 0.4 * sim + (0.15 if both_ft else 0.0))
        ta = ctext.get(rel.from_claim_id, "")
        tb = ctext.get(rel.to_claim_id, "")
        expl = (
            f"Papers {a} and {b} make incompatible claims on the same construct, and "
            f"{'NEITHER cites the other (non-trivial)' if non_trivial else 'one cites the other (the link is already made — likely trivial)'}. "
            f"Claim A: \"{ta[:140]}\". Claim B: \"{tb[:140]}\". "
            f"Detector note: {rel.evidence_note or '—'}. "
            f"Fidelity: both full-text={both_ft}. Similarity={sim:.3f}."
        )
        out.append(Opportunity(
            id=f"opp:contra:{rel.id}",
            gap_type=GapType.UNRESOLVED_CONTRADICTION,
            title=f"Unresolved contradiction between {a.split(':')[-1]} and {b.split(':')[-1]}",
            score=score,
            component_scores={
                "similarity": round(sim, 4), "non_trivial_no_cross_citation": 1.0 if non_trivial else 0.0,
                "both_fulltext": 1.0 if both_ft else 0.0, "score": round(score, 4),
            },
            explanation=expl,
            supporting_paper_ids=[a, b],
            contradiction_ids=[rel.id],
            confidence=conf,
            evidence_trail=[rel.id, rel.from_claim_id, rel.to_claim_id],
        ))
    return out


# --- 3. Orphaned future-work -------------------------------------------
# Traceability: opportunity-criteria.md non-triviality #3 (future-work
# unfollowed >= N years). Uses the two-stage matcher; `indeterminate` items
# are UNSCOREABLE and excluded. Every opportunity carries the corpus-relative
# caveat. gap_type UNFOLLOWED_FUTURE_WORK.

def score_orphaned_future_work(corpus: ReasoningCorpus) -> list[Opportunity]:
    s = get_settings()
    cutoff = max((p.year for p in corpus.papers.values() if p.year), default=None)
    labels_by_fw: dict[str, set] = defaultdict(set)
    notaddr_ids: dict[str, list] = defaultdict(list)
    for a in corpus.addressals:
        labels_by_fw[a.future_work_id].add(a.label)
        if a.label == "not_addressed":
            notaddr_ids[a.future_work_id].append(a.to_paper_id)

    # near-later count per fw (guard) — reuse embeddings
    fw_index = {fid: i for i, fid in enumerate(corpus.fw_ids)}
    claim_year = np.array([corpus.papers.get(corpus.claim_paper.get(c)).year
                           if corpus.papers.get(corpus.claim_paper.get(c)) and
                           corpus.papers[corpus.claim_paper[c]].year else -1
                           for c in corpus.claim_ids])
    out: list[Opportunity] = []
    for fw, meta in corpus.future_work:
        src = meta.paper_id
        labels = labels_by_fw.get(fw.id, set())
        if "addressed" in labels or "partial" in labels:
            continue  # engaged — not orphaned
        meta_year = corpus.papers[src].year if src in corpus.papers else None
        if meta_year is None or fw.id not in fw_index:
            continue
        # near-later count
        i = fw_index[fw.id]
        sims = corpus.claim_vectors @ corpus.fw_vectors[i]
        later = claim_year > meta_year
        near_pids = set()
        if later.any():
            idx = np.where(later)[0]
            near_pids = {corpus.claim_paper.get(corpus.claim_ids[int(k)])
                        for k in idx if sims[k] >= s.rel_futurework_topical_threshold}
        near = len(near_pids)
        if near < s.rel_futurework_min_near_later:
            continue  # INDETERMINATE — unscoreable, excluded (mandatory)
        age = (cutoff - meta_year) if cutoff else 0
        if age < s.reason_orphan_min_years:
            continue  # trivial: not unfollowed long enough (criteria #3)
        near_score = _saturating(near, k=8.0)
        age_score = _clamp01(age / 6.0)
        score = _clamp01(0.6 * near_score + 0.4 * age_score)
        # Corpus-relative uncertainty + noisy two-stage matcher -> capped conf.
        conf = _clamp01(0.25 + 0.2 * near_score + 0.15 * age_score)
        support = [src] + [p for p in notaddr_ids.get(fw.id, []) if p][:4]
        support = list(dict.fromkeys(support)) or [src]
        expl = (
            f"Future-work item from {src} ({meta_year}) is unaddressed by any later corpus paper "
            f"through {cutoff} ({age} yrs). {near} later topically-near papers exist and none "
            f"addresses it (two-stage matcher). Item: \"{fw.text[:150]}\". "
            f"CORPUS-RELATIVE CAVEAT: 'orphaned' means unaddressed WITHIN this {len(corpus.papers)}-paper corpus, "
            f"not the field; the two-stage matcher's precision is limited (P≈0.64) and the corpus "
            f"is a sample, so this is a weak, corpus-relative signal — not evidence the field ignored it."
        )
        out.append(Opportunity(
            id=f"opp:orphan:{fw.id}",
            gap_type=GapType.UNFOLLOWED_FUTURE_WORK,
            title=f"Orphaned future-work direction from {src.split(':')[-1]} ({meta_year})",
            score=score,
            component_scores={
                "near_later": float(near), "near_score": round(near_score, 4),
                "years_unfollowed": float(age), "age_score": round(age_score, 4),
                "score": round(score, 4),
            },
            explanation=expl,
            supporting_paper_ids=support,
            confidence=conf,
            evidence_trail=[fw.id] + notaddr_ids.get(fw.id, [])[:4],
        ))
    return out


# --- 4. Structural holes -----------------------------------------------
# Traceability: opportunity-criteria.md non-triviality #4 (method transfer
# across a citation-graph boundary the graph does not cross) + the
# structural-hole failure-mode note. gap_type METHOD_TRANSFER.
# SEMANTIC (2026-07-30): replaced the token-overlap proxy with claim-
# embedding cosine — token overlap cannot express "addresses" (same reason
# raw cosine failed for future-work). A method-type CLAIM in cluster A is
# matched, by cosine, against the CLAIMS of cluster-B papers that carry an
# own-work limitation (the open-problem gate). Limitations are not
# separately embedded — embedding them would be a paid API call this task
# forbids — so B's open-problem area is represented by that paper's claim
# embeddings, with the limitation TEXT carried in the evidence trail. This
# is a semantic SHORTLIST, not an LLM-confirmed "addresses" verdict (that
# would need an API call); output is a lead, flagged as such.

def _kmeans(mat: np.ndarray, k: int, iters: int = 25, seed: int = 7):
    rng = np.random.default_rng(seed)
    centers = mat[rng.choice(len(mat), size=min(k, len(mat)), replace=False)]
    labels = np.zeros(len(mat), dtype=int)
    for _ in range(iters):
        d = ((mat[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        new = d.argmin(1)
        if (new == labels).all():
            break
        labels = new
        for c in range(len(centers)):
            pts = mat[labels == c]
            if len(pts):
                centers[c] = pts.mean(0)
    return labels


def score_structural_holes(corpus: ReasoningCorpus,
                            n_clusters: int | None = None,
                            top: int | None = 12) -> list[Opportunity]:
    s = get_settings()
    ncl = n_clusters or s.reason_n_clusters
    pids = sorted(corpus.paper_vectors)   # deterministic order -> stable clustering
    if len(pids) < ncl:
        return []
    mat = np.stack([corpus.paper_vectors[p] for p in pids])
    labels = _kmeans(mat, ncl)
    cluster = {p: int(labels[i]) for i, p in enumerate(pids)}
    members: dict[int, set] = defaultdict(set)
    for p, c in cluster.items():
        members[c].add(p)
    cross = Counter()
    for (frm, to) in corpus.citation_edges:
        if frm in cluster and to in cluster and cluster[frm] != cluster[to]:
            cross[(cluster[frm], cluster[to])] += 1
            cross[(cluster[to], cluster[frm])] += 1
    methods_in: dict[int, set] = defaultdict(set)
    for p, c in cluster.items():
        for m in corpus._loaded.extractions[p].methodologies:
            methods_in[c].add(m.name.strip().lower())

    # claim embeddings: id -> unit vector (cosine = dot)
    cvec = {cid: corpus.claim_vectors[i] for i, cid in enumerate(corpus.claim_ids)}
    method_claims: dict[str, list] = {}     # a_pid -> [(claim_id, vec)]
    paper_claims: dict[str, list] = defaultdict(list)  # pid -> [(claim_id, vec)]
    for pid, ext in corpus._loaded.extractions.items():
        for c in ext.claims:
            if c.id in cvec:
                paper_claims[pid].append((c.id, cvec[c.id]))
                if c.type == "method":
                    method_claims.setdefault(pid, []).append((c.id, cvec[c.id]))
    lims_by_paper: dict[str, list] = defaultdict(list)
    for lim, pid in corpus.own_limitations:
        lims_by_paper[pid].append(lim)

    thr = s.reason_method_addresses_threshold
    out: list[Opportunity] = []
    seen: set = set()
    for A in range(ncl):
        for B in range(ncl):
            if A == B or cross[(A, B)] > s.reason_weak_bridge_max_edges:
                continue
            b_lim_papers = [p for p in members[B] if p in lims_by_paper and p in paper_claims]
            if not b_lim_papers:
                continue
            for a_pid in members[A]:
                if a_pid not in method_claims:
                    continue
                a_methods = [m.name.strip() for m in corpus._loaded.extractions[a_pid].methodologies
                             if m.name.strip().lower() not in methods_in[B]]
                if not a_methods:
                    continue  # A's methods are all already present in B
                for _cid_m, v_m in method_claims[a_pid]:
                    best = None
                    for b_pid in b_lim_papers:
                        for cid_b, v_b in paper_claims[b_pid]:
                            sim = float(np.dot(v_m, v_b))
                            if sim >= thr and (best is None or sim > best[0]):
                                best = (sim, b_pid, cid_b)
                    if best is None:
                        continue
                    sim, b_pid, _cid_b = best
                    key = (a_pid, b_pid)
                    if key in seen:
                        continue
                    seen.add(key)
                    b_lim = lims_by_paper[b_pid][0]
                    method_name = a_methods[0]
                    score = _clamp01(0.6 * sim + 0.2 * (1.0 - _saturating(cross[(A, B)], 2.0))
                                     + 0.2 * _saturating(len(a_methods), 3.0))
                    out.append(Opportunity(
                        id=f"opp:hole:{a_pid.split(':')[-1]}->{b_pid.split(':')[-1]}",
                        gap_type=GapType.METHOD_TRANSFER,
                        title=f"Method transfer: '{method_name}' ({a_pid.split(':')[-1]}, cluster {A}) "
                              f"may address an open limitation in {b_pid.split(':')[-1]} (cluster {B})",
                        score=score,
                        component_scores={
                            "semantic_similarity": round(sim, 4),
                            "cross_citations_AB": float(cross[(A, B)]),
                            "a_methods_absent_in_B": float(len(a_methods)),
                            "score": round(score, 4),
                        },
                        explanation=(
                            f"Paper {a_pid} (cluster {A}) has a method-type claim semantically close "
                            f"(cosine {sim:.3f}) to the work of {b_pid} (cluster {B}), which reports an own-work "
                            f"limitation — yet the two clusters are weakly citation-bridged ({cross[(A, B)]} edges) "
                            f"and {a_pid}'s method(s) are absent from cluster {B}. Method(s): {', '.join(a_methods[:3])}. "
                            f"B's limitation: \"{b_lim.text[:140]}\". SEMANTIC SHORTLIST (claim-embedding cosine), "
                            f"NOT an LLM-confirmed 'addresses' verdict — a lead to check, not a finding."
                        ),
                        supporting_paper_ids=[a_pid, b_pid],
                        confidence=_clamp01(0.15 + 0.3 * (sim - thr) / max(1e-6, 1 - thr)),
                        evidence_trail=[a_pid, b_pid, b_lim.id],
                    ))
    out.sort(key=lambda o: o.score, reverse=True)
    return out[:top] if top else out


# --- 5. Disjoint bridging (Swanson ABC) — GATED OFF --------------------
# Traceability: only referenced obliquely in opportunity-criteria.md
# (small-corpus "disjoint-bridging scorers" note) — there is NO dedicated
# criterion for it, so it is FLAGGED as under-specified and OFF by default:
# classic Swanson ABC is mostly noise until validated against the
# retrospective test. Implemented minimally so it can be turned on later.

def score_disjoint_bridging(corpus: ReasoningCorpus) -> list[Opportunity]:
    s = get_settings()
    if not s.reason_enable_disjoint_bridging:
        return []
    pids = [p for p in corpus.paper_vectors]
    V = {p: corpus.paper_vectors[p] for p in pids}
    out: list[Opportunity] = []
    # A-B strong, B-C strong, A-C weak, no A-C citation: B bridges A and C.
    for a in pids:
        for c in pids:
            if a >= c:
                continue
            if _cos(V[a], V[c]) >= 0.6:  # A and C already close -> not disjoint
                continue
            if (a, c) in corpus.citation_edges or (c, a) in corpus.citation_edges:
                continue
            bridges = [b for b in pids if b not in (a, c)
                       and _cos(V[a], V[b]) >= 0.72 and _cos(V[c], V[b]) >= 0.72]
            if not bridges:
                continue
            b = max(bridges, key=lambda x: _cos(V[a], V[x]) + _cos(V[c], V[x]))
            score = _clamp01(0.5 * (_cos(V[a], V[b]) + _cos(V[c], V[b])) - 0.2)
            out.append(Opportunity(
                id=f"opp:bridge:{a}:{c}",
                gap_type=GapType.METHOD_TRANSFER,
                title=f"Disjoint bridge {a.split(':')[-1]}–[{b.split(':')[-1]}]–{c.split(':')[-1]}",
                score=score,
                component_scores={"ab": round(_cos(V[a], V[b]), 3), "cb": round(_cos(V[c], V[b]), 3),
                                  "ac": round(_cos(V[a], V[c]), 3), "score": round(score, 4)},
                explanation=(f"Papers {a} and {c} are topically distant and do not cite each other, "
                             f"but both are close to {b} — a possible Swanson ABC bridge. EXPERIMENTAL: "
                             f"disjoint bridging is mostly noise until validated; OFF by default."),
                supporting_paper_ids=[a, b, c],
                confidence=0.15,
                evidence_trail=[a, b, c],
            ))
    out.sort(key=lambda o: o.score, reverse=True)
    return out[:5]


SCORERS = {
    "persistent_limitations": score_persistent_limitations,
    "unresolved_contradictions": score_unresolved_contradictions,
    "orphaned_future_work": score_orphaned_future_work,
    "structural_holes": score_structural_holes,
    "disjoint_bridging": score_disjoint_bridging,
}

__all__ = ["SCORERS"] + [f"score_{k}" for k in SCORERS]
