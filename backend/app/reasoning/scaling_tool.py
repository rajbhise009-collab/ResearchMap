"""Reusable corpus-scaling tool. Free — no API calls, no extraction.

Answers, for ANY `ReasoningCorpus`: at what N does each scorer become
viable, and what would that cost?

## Design

Takes a corpus, a list of Ns to sample, a per-scorer configuration
(including its parameters), and returns a structured `ScalingReport`
with:

  * per-N per-scorer yield distribution (mean, SD, all draws)
  * a log-log slope estimate per curve
  * detected BOUNDED-YIELD parameters — the mistake we made in the
    hand-run study, when `structural_holes(n_clusters=8)` capped
    output at k(k-1)/2 = 28 regardless of N. The tool checks every
    scorer's parameters against a schema of "bounded-yield" flags
    and either:
      - scales the parameter with N (if given a scale function), or
      - marks the curve `unreliable` with a machine-readable reason
    Both live in the ScalingReport, not just in the finding docs.
  * an extrapolation with FRAGILITY caveats attached to each row —
    "extrapolated from 5 points; power-law shape assumed", "all-zeros
    bounds a rate rather than proving absence"
  * a cost estimate using corrected thinking-token pricing

Runs on ANY corpus that satisfies the `ReasoningCorpus` shape (papers,
claims, embeddings, addressals, contradictions, citation edges) — the
hand-labelled 113-paper corpus is the reference; any hypothetical
future corpus can be plugged into the same code.

## What this tool refuses to do

Silently extrapolate from all-zero curves. A rate observed as 0/M
bounds the true rate at ~1/M (Wilson upper), not "the true rate is
zero." The report's `viable_N` for such a scorer will be a *lower
bound* with an explicit `interpretation: bound_only` marker.

Silently assume the input curve is a power law. If the log-log fit
residuals are large, the curve carries a `fit_confidence: low` marker
alongside the slope.
"""

from __future__ import annotations

import math
import statistics as st
from collections.abc import Callable
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

from backend.app.reasoning.corpus_view import ReasoningCorpus


# --------------------------------------------------------------------------
# Scorer contract
# --------------------------------------------------------------------------

@dataclass
class ScorerSpec:
    """One scorer as the tool sees it.

    - `name`: report label, e.g. "structural_holes".
    - `fn(corpus, **kwargs) -> list`: any callable returning a list of
      opportunities. Length is the yield.
    - `params`: kwargs to pass. Any value that varies with N should be
      declared via `scale_with_n` below rather than baked in here.
    - `scale_with_n`: mapping from param name to a function `N -> value`.
      Only the scaled params get overridden per subsample; everything
      else in `params` is passed through unchanged.
    - `bounded_yield`: a dict from param name to a *ceiling function*.
      Given the current param value, returns the maximum yield the
      scorer could produce with that param — used to detect the
      fixed-k artifact. Example: for `structural_holes(n_clusters=k,
      top=T)`, ceiling(k, T) = min(k*(k-1)//2, T or ∞).
      When ceiling <= current mean yield, the tool marks the curve
      `unreliable` unless the param scales with N.
    """
    name: str
    fn: Callable[..., list]
    params: dict[str, Any] = field(default_factory=dict)
    scale_with_n: dict[str, Callable[[int], Any]] = field(default_factory=dict)
    bounded_yield: Callable[[dict[str, Any]], int | None] | None = None


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------

def stratified_draw(paper_ids: list[str], is_ft: dict[str, bool],
                    N: int, seed: int) -> set[str]:
    """Fixed-ratio stratified sample: keep the full-text:abstract ratio
    of the source corpus stable across N so that a "yield goes down at
    small N" isn't confounded by "we happened to sample fewer full-text
    papers."

    If N >= len(paper_ids), returns the full set — one canonical draw."""
    if N >= len(paper_ids):
        return set(paper_ids)
    ft = [p for p in paper_ids if is_ft.get(p)]
    ab = [p for p in paper_ids if not is_ft.get(p)]
    ratio = len(ft) / len(paper_ids) if paper_ids else 0.0
    n_ft = min(len(ft), round(N * ratio))
    n_ab = min(len(ab), N - n_ft)
    rng = np.random.default_rng(seed)
    return set(rng.choice(ft, n_ft, replace=False).tolist()
               + rng.choice(ab, n_ab, replace=False).tolist())


# --------------------------------------------------------------------------
# Curve fitting + fragility flags
# --------------------------------------------------------------------------

@dataclass
class CurvePoint:
    N: int
    values: list[float]

    @property
    def mean(self) -> float:
        return st.mean(self.values) if self.values else 0.0

    @property
    def sd(self) -> float:
        return st.pstdev(self.values) if len(self.values) > 1 else 0.0

    @property
    def is_zero(self) -> bool:
        return all(v == 0 for v in self.values)


@dataclass
class Curve:
    scorer: str
    points: list[CurvePoint]
    # Set to a machine-readable reason if the tool detects a param that
    # bounds yield by construction. Empty list = no such issue detected.
    caveats: list[str] = field(default_factory=list)
    # log-log slope (metric ~ N^p). None when fit isn't meaningful.
    slope: float | None = None
    fit_confidence: str = "unknown"  # "high"|"medium"|"low"|"unmeasurable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scorer": self.scorer,
            "points": [{"N": p.N, "mean": round(p.mean, 4),
                        "sd": round(p.sd, 4), "draws": len(p.values)}
                       for p in self.points],
            "slope_p": None if self.slope is None else round(self.slope, 3),
            "fit_confidence": self.fit_confidence,
            "caveats": list(self.caveats),
        }


def _fit_slope(points: list[CurvePoint]) -> tuple[float | None, str]:
    """Log-log slope (metric ~ N^p) using linear regression on the
    non-zero mean values. Returns (slope, confidence).

    Confidence bands:
      unmeasurable — every mean is zero (rate is bounded, not measured)
      low          — 2 non-zero points, or R² < 0.5
      medium       — 3-4 non-zero points and R² >= 0.5
      high         — 5+ non-zero points and R² >= 0.9
    """
    xs, ys = [], []
    for pt in points:
        if pt.mean > 0:
            xs.append(math.log(pt.N))
            ys.append(math.log(pt.mean))
    n = len(xs)
    if n == 0:
        return None, "unmeasurable"
    if n == 1:
        return None, "low"
    # simple least-squares fit
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return None, "low"
    slope = num / den
    intercept = mean_y - slope * mean_x
    # R²
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((ys[i] - (slope * xs[i] + intercept)) ** 2 for i in range(n))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    if n >= 5 and r2 >= 0.9: conf = "high"
    elif n >= 3 and r2 >= 0.5: conf = "medium"
    else: conf = "low"
    return slope, conf


# --------------------------------------------------------------------------
# The tool
# --------------------------------------------------------------------------

@dataclass
class ScalingReport:
    corpus_name: str
    corpus_size: int
    Ns: list[int]
    draws: int
    curves: list[Curve]
    # Cost projection at extrapolated Ns (extraction, contradiction
    # classification, embeddings). Each row carries its own fragility flags.
    cost_projection: list[dict[str, Any]]
    caveats: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_name": self.corpus_name,
            "corpus_size": self.corpus_size,
            "Ns": self.Ns,
            "draws_per_N": self.draws,
            "curves": [c.to_dict() for c in self.curves],
            "cost_projection": self.cost_projection,
            "report_caveats": list(self.caveats),
        }


# Corrected thinking-token pricing from docs/findings/corpus-scaling-study.md.
# Extraction cost is per paper by input source; contradiction is per pair.
COST_PER_FT_PAPER = 0.0336
COST_PER_ABSTRACT_PAPER = 0.0109
COST_PER_CONTRA_PAIR = 0.00199
COST_EMBED_PER_1M_TOKENS = 0.15


def project_cost(target_N: int, ft_ratio: float,
                 cand_ref_N: int, cand_ref_yield: float,
                 cand_slope: float) -> dict[str, Any]:
    """Cost to build+extract at target_N, using the corrected pricing.

    - extraction: per-paper mix by ft_ratio
    - contradiction: `pairs(N) = ref_yield * (N/ref_N)^slope` — extrapolates
      from the ACTUAL measured point at ref_N (the corpus's largest
      observed N), so the projection agrees with the measurement at ref_N
      rather than a naive `N^slope` that ignores intercept.
    - embeddings: negligible but included so the total is defensible
    """
    n_ft = round(target_N * ft_ratio)
    n_ab = target_N - n_ft
    ext = n_ft * COST_PER_FT_PAPER + n_ab * COST_PER_ABSTRACT_PAPER
    # Roughly 5000 tokens / paper for embedding (title + abstract chunks)
    embed = target_N * 5000 * COST_EMBED_PER_1M_TOKENS / 1_000_000
    # Extrapolate: pairs(N) = ref_yield * (N/ref_N)^slope.
    if cand_ref_yield > 0 and cand_ref_N > 0 and cand_slope > 0:
        pairs = int(round(cand_ref_yield * (target_N / cand_ref_N) ** cand_slope))
    else:
        pairs = 0
    contra = pairs * COST_PER_CONTRA_PAIR
    return {
        "target_N": target_N,
        "extraction_usd": round(ext, 3),
        "embeddings_usd": round(embed, 4),
        "estimated_contradiction_pairs": pairs,
        "contradiction_classification_usd": round(contra, 3),
        "total_usd": round(ext + embed + contra, 2),
        "caveat": (
            f"Contradiction cost extrapolated from the measured candidate "
            f"count at N={cand_ref_N} ({cand_ref_yield:.0f} pairs), scaled "
            f"as N^{cand_slope:.2f}. Extraction is per-paper mix. Ingestion "
            f"assumed free (OpenAlex under quota)."
        ),
    }


def run(
    corpus: ReasoningCorpus,
    *,
    corpus_name: str = "unnamed",
    Ns: list[int] | None = None,
    draws: int = 5,
    scorers: list[ScorerSpec] | None = None,
    subset_fn: Callable[[ReasoningCorpus, set[str]], ReasoningCorpus] | None = None,
    cost_target_Ns: list[int] | None = None,
) -> ScalingReport:
    """Run the scaling study on `corpus` and produce a `ScalingReport`.

    `subset_fn` builds a filtered corpus given the paper ids to keep.
    Injected rather than imported so the tool doesn't couple to
    `scaling_study.subset()`'s specific internals.
    """
    if subset_fn is None:
        # Local import to avoid a cycle at module load.
        from backend.app.reasoning.scaling_study import subset as _subset
        subset_fn = _subset
    if scorers is None:
        scorers = default_scorers()
    Ns = Ns or [40, 60, 80, 100, len(corpus.papers)]
    Ns = sorted(set(N for N in Ns if N <= len(corpus.papers)))
    if not Ns:
        raise ValueError("No valid N values (all exceed corpus size)")
    ids = sorted(corpus.papers)
    is_ft = {p: (m.input_source == "fulltext") for p, m in corpus.papers.items()}
    ft_ratio = sum(is_ft.values()) / len(ids)

    # -- run --
    per_scorer_points: dict[str, list[CurvePoint]] = {s.name: [] for s in scorers}
    param_history_by_scorer: dict[str, list[dict]] = {s.name: [] for s in scorers}
    for N in Ns:
        n_draws = 1 if N >= len(ids) else draws
        sub_corpora = []
        for d in range(n_draws):
            keep = stratified_draw(ids, is_ft, N, seed=1000 * N + d)
            sub_corpora.append(subset_fn(corpus, keep))
        for spec in scorers:
            call_params = dict(spec.params)
            for pname, pfn in spec.scale_with_n.items():
                call_params[pname] = pfn(N)
            values: list[float] = []
            for sub in sub_corpora:
                try:
                    result = spec.fn(sub, **call_params)
                except TypeError:
                    result = spec.fn(sub)
                values.append(len(result))
            per_scorer_points[spec.name].append(CurvePoint(N=N, values=values))
            # Keep params in their real types for bounded_yield to consume
            # (bounded_yield expects ints, not their str repr); the report
            # printer stringifies at emission time.
            param_history_by_scorer[spec.name].append(
                {"N": N, "params": dict(call_params)}
            )

    # -- assemble curves with fragility + bounded-yield caveats --
    curves: list[Curve] = []
    for spec in scorers:
        pts = per_scorer_points[spec.name]
        slope, conf = _fit_slope(pts)
        cav: list[str] = []
        # All-zero: bound the rate on the LARGEST N — that's the only
        # sample where zero is informative about the deployment-scale rate.
        # Use `1/N_max` as a per-*opportunity* upper bound (not per-draw),
        # since at N=largest we look for ONE contradiction across the whole
        # candidate space. That gives the reader something calibrated:
        # "we searched ~256 candidate pairs at N=113 and found zero, so
        # the true per-candidate rate is bounded ~<1/256 ≈ 0.4%."
        if all(pt.is_zero for pt in pts):
            # Prefer a companion "candidate-count" curve for the denominator.
            cand_points = [p for cs in per_scorer_points.get("contra_candidates", [])
                           for p in cs.values] if "contra_candidates" in per_scorer_points else []
            top_cand = per_scorer_points.get("contra_candidates", [None])[-1] if per_scorer_points.get("contra_candidates") else None
            if top_cand and top_cand.mean > 0:
                bound = 1.0 / (top_cand.mean + 1)
                cav.append(
                    f"all_zeros:bound_only — 0 confirmed across {top_cand.mean:.0f} "
                    f"candidate pairs at N={top_cand.N}; per-candidate rate bounded "
                    f"~<{bound:.2%}, not proven absent"
                )
            else:
                # Fall back to counting draws.
                total_draws = sum(len(pt.values) for pt in pts)
                if total_draws > 0:
                    cav.append(
                        f"all_zeros:bound_only — 0 across {total_draws} draws total; "
                        f"true rate bounded ~<{1.0/(total_draws+1):.2%} per draw, "
                        f"not proven absent"
                    )
        # Bounded-yield check: does the scorer's own parameterisation cap
        # the number it can produce, regardless of N?
        if spec.bounded_yield is not None:
            for h in param_history_by_scorer[spec.name]:
                cap = spec.bounded_yield(h["params"])
                if cap is None:
                    continue
                # This is the fixed-k lesson enforced. If the scorer's
                # own parameters cap it below the observed yield anywhere
                # in the sweep, the curve is unreliable unless a
                # scale_with_n is defined for a bounding parameter.
                observed_max = max(pt.mean for pt in pts) if pts else 0
                if observed_max >= cap - 1e-9 and not spec.scale_with_n:
                    cav.append(
                        f"parameter_bound:{h['params']}_caps_yield_at_{cap}"
                        f" — output cap hit at some N; curve is a fixed-parameter "
                        f"artifact, not a property of the data. Add a scale_with_n "
                        f"or interpret with caution."
                    )
                    break
        if spec.scale_with_n:
            cav.append(
                f"parameter_scaled_with_N:{sorted(spec.scale_with_n)} — "
                "curve reflects yield under scaled parameter(s), not "
                "yield under the deployment default. Both are legitimate; "
                "read the finding carefully."
            )
        curves.append(Curve(scorer=spec.name, points=pts, caveats=cav,
                            slope=slope, fit_confidence=conf))

    # -- cost projection --
    # Use the contradiction-candidate curve to extrapolate pair counts.
    # ref_N = the largest N we actually sampled; ref_yield = measured
    # candidate mean there. slope from the log-log fit. This anchors the
    # projection to the measurement, not to N^slope with an implicit
    # intercept of 1.
    cand_curve = next((c for c in curves if c.scorer == "contra_candidates"), None)
    cand_slope = cand_curve.slope if (cand_curve and cand_curve.slope) else 1.0
    if cand_curve:
        cand_ref_N = cand_curve.points[-1].N
        cand_ref_yield = cand_curve.points[-1].mean
    else:
        cand_ref_N = len(corpus.papers)
        cand_ref_yield = 0.0
    cost_target_Ns = cost_target_Ns or [200, 300, 500, 800]
    cost = [project_cost(tN, ft_ratio, cand_ref_N, cand_ref_yield, cand_slope)
            for tN in cost_target_Ns]

    report_caveats = [
        f"Extrapolations sit on {len(Ns)} data points; power-law shape "
        "assumed, not established.",
        f"Subsamples are internal to the source corpus ({corpus_name}); "
        "cross-domain generalisation is not tested.",
        "Flat/zero curves bound absence — they cannot prove it.",
    ]

    return ScalingReport(
        corpus_name=corpus_name,
        corpus_size=len(corpus.papers),
        Ns=Ns,
        draws=draws,
        curves=curves,
        cost_projection=cost,
        caveats=report_caveats,
    )


# --------------------------------------------------------------------------
# Default scorer set for our own reasoning engine
# --------------------------------------------------------------------------

def default_scorers() -> list[ScorerSpec]:
    """The five scorers, wired with the bounded-yield ceilings we know about.

    Notably: `structural_holes` gets both a `scale_with_n` for n_clusters
    (round(sqrt(N))) AND a bounded_yield ceiling. The tool will report:

      * with the default deployment `top=12` cap, yield IS bounded — but
        the curve is legitimate because clusters scale with N.
      * without scaling clusters (fixed k=8, uncapped) the ceiling would
        fire and the curve would be marked unreliable. That is exactly
        the mistake documented in the scaling-study finding.
    """
    from backend.app.reasoning import scorers as S
    from backend.app.reasoning.scaling_study import _candidate_pairs

    def _sh_ceiling(params: dict[str, Any]) -> int | None:
        # k(k-1)/2 pairwise cap, optionally further capped by `top`.
        k = params.get("n_clusters")
        try:
            k = int(k) if k is not None else None
        except (TypeError, ValueError):
            k = None
        if k is None:
            return None
        pair_cap = k * (k - 1) // 2
        top = params.get("top")
        try:
            top = int(top) if top is not None and top != "None" else None
        except (TypeError, ValueError):
            top = None
        return min(pair_cap, top) if top is not None else pair_cap

    return [
        ScorerSpec(
            name="persistent_limitations",
            fn=lambda c, **_: S.score_persistent_limitations(c),
        ),
        ScorerSpec(
            name="contra_confirmed",
            fn=lambda c, **_: S.score_unresolved_contradictions(c),
        ),
        ScorerSpec(
            name="contra_candidates",
            fn=lambda c, **_: [None] * _candidate_pairs(c),  # ← returns list of len == candidate count
        ),
        ScorerSpec(
            name="orphaned_future_work",
            fn=lambda c, **_: S.score_orphaned_future_work(c),
        ),
        ScorerSpec(
            name="structural_holes",
            fn=lambda c, **kw: S.score_structural_holes(c, **kw),
            params={"top": None},  # uncapped so we measure the actual curve shape
            scale_with_n={"n_clusters": lambda N: max(2, round(math.sqrt(N)))},
            bounded_yield=_sh_ceiling,
        ),
    ]
