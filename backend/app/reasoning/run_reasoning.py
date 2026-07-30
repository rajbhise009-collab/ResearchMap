"""Run all five scorers over the real corpus, rank, validate, and write
scratch/opportunities_review.md. Deterministic end-to-end — no LLM.

Ranking key: score × confidence (trust-weighted expected value). A raw
`score` can be high while `confidence` is low (e.g. corpus-relative
orphans); ranking by the product surfaces trustworthy opportunities first
and is documented in docs/reasoning-engine.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

from backend.app.models import Opportunity  # noqa: E402
from backend.app.reasoning.corpus_view import load_reasoning_corpus  # noqa: E402
from backend.app.reasoning import scorers as S  # noqa: E402

REVIEW = REPO_ROOT / "scratch" / "opportunities_review.md"
OPPS_OUT = REPO_ROOT / "data" / "reasoning" / "opportunities.jsonl"


def _validate(o: Opportunity, scorer: str) -> None:
    """opportunity-criteria.md criteria 2 & 3 as a runtime check."""
    assert o.supporting_paper_ids, f"{o.id}: empty supporting_paper_ids"
    assert o.evidence_trail, f"{o.id}: empty evidence_trail"
    assert o.component_scores, f"{o.id}: empty component_scores (criterion 3)"


def _is_weak(scorer: str, o: Opportunity) -> str | None:
    if scorer == "structural_holes":
        return "coarse token-overlap proxy (no semantic match); noise-level lead"
    if scorer == "orphaned_future_work" and o.confidence < 0.58:
        return "corpus-relative orphan; low confidence, noisy two-stage matcher"
    if o.component_scores.get("generic_category") == 1.0:
        return "generic methodological category — likely fails the actionability bar"
    if o.gap_type == "unresolved_contradiction" and o.component_scores.get("similarity", 1) < 0.6:
        return "low-similarity contradiction; may be a weak/terminology-adjacent pair"
    return None


def main() -> int:
    corpus = load_reasoning_corpus()
    tagged: list[tuple[str, Opportunity]] = []
    per_scorer: dict[str, int] = {}
    for name, fn in S.SCORERS.items():
        opps = fn(corpus)
        per_scorer[name] = len(opps)
        for o in opps:
            _validate(o, name)
            tagged.append((name, o))

    tagged.sort(key=lambda t: -(t[1].score * t[1].confidence))
    OPPS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with OPPS_OUT.open("w") as fh:
        for name, o in tagged:
            fh.write(json.dumps({"scorer": name, **o.model_dump()}) + "\n")

    title = {p: corpus.papers[p].title for p in corpus.papers}
    L: list[str] = []
    L.append("# Reasoning-engine opportunities — review\n")
    L.append("Deterministic Python only (no LLM in scoring). Ranked by "
             "**score × confidence** (trust-weighted). Every scorer traces to "
             "docs/opportunity-criteria.md; deviations are flagged in-line and "
             "in docs/reasoning-engine.md.\n")
    L.append("## Scorer yield\n")
    for name, n in per_scorer.items():
        L.append(f"- **{name}**: {n} opportunities")
    L.append("")
    L.append(f"Honest notes (corrected corpus, {len(corpus.papers)} papers after "
             f"dedup + relabel): **{per_scorer['persistent_limitations']}** "
             f"persistent-limitation cluster(s) survive the 3-paper floor + "
             f"same-construct gate; **{per_scorer['unresolved_contradictions']}** "
             f"contradictions (the earlier 2 were a duplicate + a regime "
             f"artifact — gone after dedup and regime-aware re-classification); "
             f"orphaned-future-work fires {per_scorer['orphaned_future_work']}x "
             f"but each is a weak, corpus-relative signal; structural holes "
             f"{per_scorer['structural_holes']}; disjoint bridging OFF.\n")

    # Mixed-fidelity: with vs without, for the count-based scorer.
    L.append("## Mixed-fidelity correction — with vs without\n")
    L.append("Persistent-limitations scores, corrected (abstract-only papers "
             "up-weighted 3x) vs uncorrected. **The correction is a NO-OP on the "
             "current qualifying set — every category that reaches the 3-paper "
             "floor is 100% full-text (n abstract = 0).** That is not the "
             "correction failing; it is the mixed-fidelity bias made visible: "
             "abstract-only papers yield so few own-work limitations (15 of 254) "
             "that NO limitation category reaches the 3-paper floor with any "
             "abstract support. The 3x up-weight would change scores/order only "
             "once abstract papers contribute to a qualifying category. The "
             "machinery is in place and applied; here it has nothing to correct. "
             "(The correction is applied to this count-based scorer; it is not "
             "mechanically applied to the orphan scorer, whose signal is "
             "'no later paper addressed', not a paper count.)\n")
    L.append("| category | n indep | n full / abs | score corrected | score uncorrected |")
    L.append("|:--|--:|:--:|--:|--:|")
    for name, o in tagged:
        if name != "persistent_limitations":
            continue
        cs = o.component_scores
        cat = o.id.split(":")[-1]
        L.append(f"| {cat} | {int(cs['n_independent'])} | "
                 f"{int(cs['n_fulltext'])}/{int(cs['n_abstract'])} | "
                 f"{cs['score_corrected']:.3f} | {cs['score_uncorrected']:.3f} |")
    L.append("")

    L.append("## Top 15 opportunities\n")
    weak_count = 0
    for rank, (name, o) in enumerate(tagged[:15], 1):
        weak = _is_weak(name, o)
        if weak:
            weak_count += 1
        tag = f"  ⚠️ **WEAK/QUESTIONABLE** — {weak}" if weak else ""
        L.append(f"### {rank}. {o.title}{tag}")
        L.append(f"- **gap_type:** {o.gap_type} · **scorer:** {name}")
        L.append(f"- **score:** {o.score:.3f} · **confidence:** {o.confidence:.2f} "
                 f"· **trust (score×conf):** {o.score * o.confidence:.3f}")
        L.append(f"- **component_scores:** {json.dumps(o.component_scores)}")
        L.append(f"- **explanation:** {o.explanation}")
        L.append("- **supporting papers:**")
        for p in o.supporting_paper_ids[:6]:
            L.append(f"    - `{p}` — {title.get(p, '?')}")
        L.append("")

    L.append(f"\n_({weak_count} of the top 15 flagged weak/questionable.)_\n")

    # Dedicated section for structural-hole leads (new semantic matcher) —
    # they rank mid by trust so would be buried, but are the point of review.
    holes = [o for name, o in tagged if name == "structural_holes"]
    conf_path = REPO_ROOT / "data" / "reasoning" / "structural_hole_confirmations.json"
    conf = json.loads(conf_path.read_text()) if conf_path.exists() else {}
    if holes:
        n_sub = sum(1 for o in holes if conf.get(o.id, {}).get("verdict") == "substantive")
        L.append("\n## Structural-hole leads (semantic matcher → LLM-confirmed)\n")
        L.append("Semantic shortlist (cluster-A method-type claim near a cluster-B "
                 "paper with an open own-work limitation, weakly citation-bridged) → "
                 "LLM confirmation of whether A's method plausibly ADDRESSES B's "
                 "limitation and the direction is non-trivial. "
                 f"**{n_sub} of {len(holes)} survive as SUBSTANTIVE**; the rest are "
                 "`trivial` (larger-eval / apply-to-dataset) or `not_addressing` "
                 "(topical adjacency). Confirmation is classification only — no scoring.\n")
        order = {"substantive": 0, "trivial": 1, "not_addressing": 2, "malformed": 3}
        holes_sorted = sorted(holes, key=lambda o: order.get(conf.get(o.id, {}).get("verdict", "z"), 4))
        for o in holes_sorted:
            v = conf.get(o.id, {})
            verdict = v.get("verdict", "unconfirmed")
            badge = {"substantive": "✅ SUBSTANTIVE", "trivial": "⚠️ TRIVIAL",
                     "not_addressing": "❌ NOT ADDRESSING"}.get(verdict, verdict.upper())
            L.append(f"### [{badge}] {o.title}")
            L.append(f"- **cosine:** {o.component_scores['semantic_similarity']:.3f} "
                     f"· LLM verdict: **{verdict}** — {v.get('reason', '(not confirmed)')}")
            L.append(f"- {o.explanation}")
            L.append("- **papers:**")
            for p in o.supporting_paper_ids:
                L.append(f"    - `{p}` — {title.get(p, '?')}")
            L.append("")

    REVIEW.write_text("\n".join(L))
    print(f"scorer yield: {per_scorer}")
    print(f"total opportunities: {len(tagged)}; wrote {REVIEW.relative_to(REPO_ROOT)} "
          f"({weak_count}/15 flagged weak)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
