"""Contradiction RECALL probe (measurement, task 1).

148 supports vs 2 contradicts could be classifier bias, not a corpus
property. This authors an explicit labelled probe — real corpus claims
(claim A) paired with hand-written claim B that is a planted
contradiction, a genuine support, or an unrelated control — and runs the
EXISTING classifier (same prompt, same batch path) over it. Reports
recall on planted contradictions and false-positive rate on controls.

No new prompt here — this measures the current one. Cheap (~26 pairs).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.extraction.batch_client import GeminiBatchClient  # noqa: E402
from backend.app.relationships import contradiction as C  # noqa: E402

# (claim_a from corpus, claim_b authored, gold label). claim_a texts are
# real corpus claims; claim_b is authored to create the labelled pair.
PROBE: list[tuple[str, str, str]] = [
    # --- planted CONTRADICTIONS (flip direction / magnitude / negate) ---
    ("GPT-4 achieves 98% accuracy in Experiment 1A when selecting human-preferred scope readings.",
     "GPT-4 achieves only about 62% accuracy in Experiment 1A when selecting human-preferred scope readings.",
     "contradicts"),
    ("Larger LLMs exhibit lower memorization ratios than smaller LLMs on filtered evaluation sets in knowledge conflict scenarios.",
     "Larger LLMs exhibit higher memorization ratios than smaller LLMs on filtered evaluation sets in knowledge conflict scenarios.",
     "contradicts"),
    ("The RE2 model achieves an accuracy of 89.2% on the Quora Question Pairs test set.",
     "The RE2 model reaches only 71.0% accuracy on the Quora Question Pairs test set.",
     "contradicts"),
    ("MT-DNN achieves an accuracy of 91.6% on the SNLI dataset.",
     "MT-DNN fails to exceed 85% accuracy on the SNLI dataset.",
     "contradicts"),
    ("Large language models are systematically more confident when providing reasoning before answering multiple-choice questions.",
     "Large language models are systematically less confident when reasoning precedes their multiple-choice answers.",
     "contradicts"),
    ("GPT-4 achieves significantly higher pair-wise consistency when provided with five WEP choices compared to three WEP choices.",
     "GPT-4 shows no significant difference in pair-wise consistency between five and three WEP choices.",
     "contradicts"),
    ("Training BERT on MultiNLI and then fine-tuning on the BoolQ dataset achieves 80.43% test accuracy.",
     "Fine-tuning BERT from MultiNLI on BoolQ yields at most 68% test accuracy.",
     "contradicts"),
    ("Technical fine-tuning and reinforcement learning from human feedback prioritize rhetoric and sycophancy over factual accuracy.",
     "Reinforcement learning from human feedback improves factual accuracy and reduces sycophancy in language models.",
     "contradicts"),
    ("MM-PEAR-CoT achieves a 1.7% improvement in binary classification accuracy on the CMU-MOSEI dataset.",
     "MM-PEAR-CoT degrades binary classification accuracy on the CMU-MOSEI dataset.",
     "contradicts"),
    ("Task Routing Layers allow a multi-task network to scale up to 312 tasks simultaneously.",
     "Task Routing Layers fail to scale a multi-task network beyond a few dozen simultaneous tasks.",
     "contradicts"),
    # --- genuine SUPPORTS (restate / corroborate) ---
    ("Larger LLMs exhibit lower memorization ratios than smaller LLMs on filtered evaluation sets in knowledge conflict scenarios.",
     "Memorization decreases as model scale increases under knowledge-conflict evaluation.",
     "supports"),
    ("MT-DNN achieves an accuracy of 91.6% on the SNLI dataset.",
     "MT-DNN attains roughly 91-92% accuracy on the SNLI natural language inference benchmark.",
     "supports"),
    ("Large language models are systematically more confident when providing reasoning before answering multiple-choice questions.",
     "Producing a rationale before answering increases LLMs' stated confidence on multiple-choice questions.",
     "supports"),
    ("Technical fine-tuning and reinforcement learning from human feedback prioritize rhetoric and sycophancy over factual accuracy.",
     "RLHF-tuned models tend to favor persuasive, sycophantic responses at the expense of factuality.",
     "supports"),
    ("The RE2 model achieves an accuracy of 89.2% on the Quora Question Pairs test set.",
     "RE2 reaches about 89% accuracy on the QQP paraphrase-identification benchmark.",
     "supports"),
    ("GPT-4 achieves significantly higher pair-wise consistency when provided with five WEP choices compared to three WEP choices.",
     "Offering five WEP options improves GPT-4's pairwise consistency relative to three options.",
     "supports"),
    ("Training BERT on MultiNLI and then fine-tuning on the BoolQ dataset achieves 80.43% test accuracy.",
     "A MultiNLI-pretrained BERT fine-tuned on BoolQ reaches roughly 80% test accuracy.",
     "supports"),
    # --- UNRELATED controls (shared domain vocab, different construct) ---
    ("MT-DNN achieves an accuracy of 91.6% on the SNLI dataset.",
     "Conformal prediction provides distribution-free coverage guarantees for set-valued classifiers.",
     "none"),
    ("Large language models are systematically more confident when providing reasoning before answering multiple-choice questions.",
     "Retrieval-augmented generation reduces hallucination in clinical note generation.",
     "none"),
    ("The RE2 model achieves an accuracy of 89.2% on the Quora Question Pairs test set.",
     "Temperature scaling is a widely used post-hoc calibration method for neural networks.",
     "none"),
    ("Task Routing Layers allow a multi-task network to scale up to 312 tasks simultaneously.",
     "Semantic entropy estimates predictive uncertainty over clusters of meaning-equivalent generations.",
     "none"),
    ("MM-PEAR-CoT achieves a 1.7% improvement in binary classification accuracy on the CMU-MOSEI dataset.",
     "Larger language models memorize less training data under knowledge-conflict conditions.",
     "none"),
    ("Technical fine-tuning and reinforcement learning from human feedback prioritize rhetoric and sycophancy over factual accuracy.",
     "Split-conformal inference yields plug-in set-valued classifiers with finite-sample validity.",
     "none"),
    ("Training BERT on MultiNLI and then fine-tuning on the BoolQ dataset achieves 80.43% test accuracy.",
     "GPT-4 selects human-preferred scope readings with near-ceiling accuracy.",
     "none"),
]

OUT = REPO_ROOT / "data" / "relationships" / "recall_probe_results.json"


def main() -> int:
    if not get_settings().can_use_gemini:
        print("GEMINI_API_KEY unset.", file=sys.stderr)
        return 2
    reqs = {
        str(i): C.build_pair_prompt(text_a=a, text_b=b, paper_a="P_A", paper_b="P_B")
        for i, (a, b, _gold) in enumerate(PROBE)
    }
    client = GeminiBatchClient(model_name=get_settings().gemini_model)
    bid = client.submit(reqs, display_name="researchmap-recall-probe")
    print(f"[probe] submitted {len(reqs)} pairs id={bid}", flush=True)
    job = client.wait(bid, poll_interval_s=20)
    if not job.succeeded:
        print(f"[probe] batch failed: {job.state}", file=sys.stderr)
        return 1
    results = client.results(job)

    rows = []
    for i, (a, b, gold) in enumerate(PROBE):
        v = C.parse_verdict(results.get(str(i), ""))
        pred = v.relationship if v else "MALFORMED"
        rows.append({"gold": gold, "pred": pred, "a": a, "b": b})

    def rate(gold, pred):
        sub = [r for r in rows if r["gold"] == gold]
        hit = sum(1 for r in sub if r["pred"] == pred)
        return hit, len(sub)

    c_hit, c_tot = rate("contradicts", "contradicts")
    s_hit, s_tot = rate("supports", "supports")
    n_hit, n_tot = rate("none", "none")
    # False positives = a control (support or unrelated) called 'contradicts'.
    fp = sum(1 for r in rows if r["gold"] in ("supports", "none")
             and r["pred"] == "contradicts")
    controls = s_tot + n_tot

    summary = {
        "contradiction_recall": f"{c_hit}/{c_tot}",
        "contradiction_recall_pct": round(100 * c_hit / c_tot, 1) if c_tot else 0,
        "support_accuracy": f"{s_hit}/{s_tot}",
        "unrelated_accuracy": f"{n_hit}/{n_tot}",
        "false_positive_contradictions": f"{fp}/{controls}",
        "false_positive_rate_pct": round(100 * fp / controls, 1) if controls else 0,
        "rows": rows,
    }
    OUT.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    print("\nMissed planted contradictions:")
    for r in rows:
        if r["gold"] == "contradicts" and r["pred"] != "contradicts":
            print(f"  pred={r['pred']}: {r['b'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
