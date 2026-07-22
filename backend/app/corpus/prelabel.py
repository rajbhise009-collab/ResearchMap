"""Pre-label the 60-paper hand-review sample.

This script encodes one human reviewer's judgments (mine, per
`docs/labelling-rubric.md`) against the 60 abstracts in
`scratch/corpus_review.csv`. It is NOT an autonomous labeller; it is
a record of judgments made offline, kept in a script so they are
reproducible and reviewable.

Inputs:
  scratch/corpus_review.csv   (unlabelled 60-row CSV from build_review_artifact)

Outputs:
  scratch/corpus_review.csv   (rewritten with judgments merged in)
  scratch/corpus_review.md    (rewritten same content, per-paper section)
  scratch/audit_sample.md     (stratified 15-paper subsample for Raj to review)

Each of the 60 rows gets:
  on_domain          on-domain | borderline | off-domain
  has_limitation     yes | no | unknown (unknown when abstract is missing)
  limitation_scope   own | prior | both | none | unknown
                     — own: paper reports a limitation of its OWN work
                       (its method / findings / benchmark) OR a limitation
                       of the studied subject that the paper itself
                       investigates.
                     — prior: paper cites a limitation of PRIOR work as
                       motivation ("existing methods X"). Without the
                       specific prior work being cited in the abstract,
                       these are largely unattributable and cannot
                       independently feed the persistent-limitations
                       scorer.
                     — both: paper mentions both kinds.
                     — none: has_limitation=no.
                     — unknown: no abstract available.
  claim_hedged       firm | hedged | mixed | unknown
  has_future_work    explicit | implied | none | unknown
  compound_claims    yes | no | unknown
  notes              free-form; HARD flag when the judgment was genuinely close
  label_reasoning    one sentence: what the paper's contribution IS, and why
                     that puts it in the given bucket
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

CSV_IN = REPO_ROOT / "scratch" / "corpus_review.csv"
CSV_OUT = REPO_ROOT / "scratch" / "corpus_review.csv"
MD_OUT = REPO_ROOT / "scratch" / "corpus_review.md"
AUDIT_OUT = REPO_ROOT / "scratch" / "audit_sample.md"


# --- Judgments, keyed by paper number (1..60 in the shuffled sample) ---
#
# Field values (mapped to CSV column names below):
#   on   = on_domain     ("on-domain" / "borderline" / "off-domain")
#   lim  = has_limitation ("yes" / "no" / "unknown")
#   hedg = claim_hedged  ("firm" / "hedged" / "mixed" / "unknown")
#   fw   = has_future_work ("explicit" / "implied" / "none" / "unknown")
#   comp = compound_claims ("yes" / "no" / "unknown")
#   hard = True when the judgment was genuinely close (surfaced in audit)
#   why  = label_reasoning: one sentence naming the paper's contribution
#          AND why that puts it in the on-domain bucket

JUDGMENTS: dict[int, dict] = {
    # 01. LLMC quantization toolkit
    1: dict(on="off-domain", lim="no", hedg="firm", fw="none", comp="no", hard=False,
            why="Contribution is a quantization compression toolkit; 'calibration' here means the calibration dataset used in post-training quantization, not confidence calibration."),
    # 02. Rationalizing predictions by adversarial information calibration
    # (abstract recovered from Semantic Scholar; label updated to off-domain)
    2: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
            why="Contribution is an adversarial two-model framework for extracting rationales (subphrase-level feature selection) for classifier predictions; 'information calibration' is the method name but 'calibration' here means aligning information between two models, not confidence calibration."),
    # 03. L2CEval
    3: dict(on="borderline", lim="yes", hedg="mixed", fw="explicit", comp="yes", hard=False,
            why="Contribution is a benchmark for language-to-code generation across 7 tasks; confidence calibration is one substantive assessment among many, not the main object of study."),
    # 04. Hallucination as Geometric Overflow
    4: dict(on="on-domain", lim="no", hedg="firm", fw="implied", comp="yes", hard=False,
            why="Contribution is a formal framework distinguishing hallucination as boundary violation from probabilistic miscalibration; the primary object of study is hallucination and its taxonomy."),
    # 05. EGO-PLM via consistency calibration
    # (abstract recovered from Semantic Scholar; label updated to off-domain)
    5: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
            why="Contribution is EGO-PLM, a framework using PLMs as task-specific embedding generators via adversarial alignment of pre-defined and task-specific objectives; 'consistency calibration' is the alignment technique's name, not confidence calibration."),
    # 06. Gradient-based Language Model Pruner
    6: dict(on="off-domain", lim="no", hedg="firm", fw="none", comp="no", hard=False,
            why="Contribution is a gradient-based LLM pruning method; 'calibration samples' is jargon for the small dataset used to compute pruning statistics, not confidence calibration."),
    # 07. R-Tuning
    7: dict(on="on-domain", lim="no", hedg="firm", fw="implied", comp="no", hard=False,
            why="Contribution is refusal-aware instruction tuning that teaches an LLM when to abstain and improves calibration as a documented side effect — abstention IS the paper's main object."),
    # 08. Semantic Density UQ
    8: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
            why="Contribution is Semantic Density, a UQ method for LLMs in semantic space; uncertainty quantification for LLMs is the paper's headline claim."),
    # 09. MultiLLM-Chatbot RAG benchmarking
    9: dict(on="borderline", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
            why="Contribution is a scalable multi-domain LLM benchmarking framework; hallucination identification is one of four evaluation dimensions but the paper is a benchmarking / evaluation framework, not a hallucination-detection method paper."),
    # 10. Laplace-LoRA
    10: dict(on="on-domain", lim="no", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is Laplace-LoRA, a Bayesian LoRA that specifically targets improving calibration of fine-tuned LLMs — calibration is the named improvement axis."),
    # 11. UQ for In-Context Learning
    11: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is a UQ method for LLM in-context learning that separately estimates aleatoric and epistemic uncertainty; UQ for LLMs is the paper's whole object."),
    # 12. BIRD Bayesian inference framework
    12: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is a Bayesian inference framework aligning LLM abductions with a Bayesian network to produce more accurate probability estimates from LLMs — confidence / probability estimation IS the contribution."),
    # 13. Model Hemorrhage
    13: dict(on="off-domain", lim="no", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is a robustness analysis of LLMs under quantization/pruning/decoding changes; 'decoding calibration' is one mitigation strategy of three, not the paper's subject."),
    # 14. Chainpoll
    14: dict(on="on-domain", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is ChainPoll, a novel LLM hallucination detection method plus a RealHall benchmark — hallucination detection is the whole point."),
    # 15. BIG-Bench
    15: dict(on="borderline", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is BIG-Bench, a 204-task benchmark; calibration is measured but is one finding among many rather than the paper's headline object."),
    # 16. MergeQuant
    16: dict(on="off-domain", lim="no", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is a 4-bit static quantization framework; 'per-channel dynamic calibration' and 'static calibration' are quantization jargon for the reference dataset, not confidence calibration."),
    # 17. Chain of Natural Language Inference (CoNLI)
    17: dict(on="on-domain", lim="no", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is CoNLI, a hierarchical framework for detecting and mitigating ungrounded hallucinations — hallucination detection is the primary claim."),
    # 18. RAGTruth
    18: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is RAGTruth, a word-level hallucination corpus for RAG — the whole paper builds and validates a hallucination-detection resource."),
    # 19. Nearest Neighbor Calibration for in-context learning
    19: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is a novel calibration framework for in-context learning based on kNN over cached representations — the calibration method IS the paper."),
    # 20. Quantization trade-offs
    20: dict(on="off-domain", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is a comprehensive quantization evaluation across model scales; 'hallucination detection' appears as one downstream task the quantized models are evaluated on, not as the paper's subject."),
    # 21. Uncertainty-aware response length perception
    # (no abstract recoverable from Semantic Scholar or arXiv; EXCLUDED from
    # extraction corpus per recovery manifest)
    21: dict(on="borderline", lim="unknown", hedg="unknown", fw="unknown", comp="unknown", hard=True,
             why="No abstract available from OpenAlex, Semantic Scholar, or arXiv; excluded from the extraction corpus. Title alone is insufficient to place — uncertainty-aware modifier could apply to a UQ contribution or an application paper using UQ as a tool."),
    # 22. LLMs are not Fair Evaluators
    22: dict(on="borderline", lim="yes", hedg="firm", fw="implied", comp="yes", hard=True,
             why="Contribution is a three-part calibration framework fixing LLM-as-judge order bias — 'calibration' is central and the paper genuinely proposes calibration methods, but for evaluator bias rather than confidence calibration, which straddles the rubric."),
    # 23. Survey on Hallucination in LLMs (2024)
    23: dict(on="on-domain", lim="yes", hedg="firm", fw="explicit", comp="no", hard=False,
             why="Contribution is a comprehensive survey of LLM hallucination taxonomy, detection methods, and mitigation strategies — hallucination in LLMs is the paper's entire scope."),
    # 24. BAF-FedLLM student action modeling
    24: dict(on="off-domain", lim="no", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is a federated LLM framework for privacy-preserving student action prediction; expected calibration error is reported as a headline metric of improvement but the paper is about federated learning for education, not calibration."),
    # 25. MCQ Reasoning Makes LLMs More Self-Confident
    25: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is an empirical analysis showing CoT prompting systematically degrades LLM confidence calibration on MCQs — calibration is the entire subject."),
    # 26. Depth Avoidance
    26: dict(on="off-domain", lim="no", hedg="hedged", fw="explicit", comp="yes", hard=False,
             why="Contribution is a behavioral hypothesis about safety-tuned LLMs defaulting to shallow responses; the paper explicitly cites 'Victor Calibration' as related work but does not itself study confidence calibration."),
    # 27. Pearl personalized writing assistant
    27: dict(on="borderline", lim="yes", hedg="firm", fw="implied", comp="yes", hard=True,
             why="Contribution is Pearl, a personalization framework whose novelty is a 'generation-calibrated' retriever — calibration is core to the method name but the paper's subject is personalization of LLM writing assistants, not confidence calibration."),
    # 28. HalluciNot
    28: dict(on="on-domain", lim="no", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is HDM-2, a hallucination detection model for enterprise LLM deployments — hallucination detection is the entire point."),
    # 29. MEDAI-LLM-SUMM
    29: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is a reporting checklist for medical text summarization studies using LLMs; hallucination assessment is one of many items on the checklist but the paper is about reporting standards, not hallucination detection."),
    # 30. Survey on UQ of LLMs
    30: dict(on="on-domain", lim="yes", hedg="firm", fw="explicit", comp="no", hard=False,
             why="Contribution is a comprehensive survey of uncertainty quantification methods for LLMs — UQ is the entire scope."),
    # 31. SliM-LLM salience-driven quantization
    31: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is SliM-LLM, a mixed-precision quantization framework; 'Salience-Weighted Quantizer Calibration' is one of two proposed components, and 'calibration' here means quantizer calibration jargon."),
    # 32. Zero-Resource Hallucination Prevention
    32: dict(on="on-domain", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is SELF-FAMILIARITY, a pre-detection self-evaluation technique for preventing hallucinations by having LLMs abstain on unfamiliar concepts — abstention-based hallucination prevention IS the paper."),
    # 33. Navigating the Grey Area
    33: dict(on="on-domain", lim="no", hedg="hedged", fw="implied", comp="yes", hard=False,
             why="Contribution is a study of how epistemic markers of certainty/uncertainty in prompts affect LM behaviour — expressions of uncertainty in language models are the paper's subject."),
    # 34. Context-faithful Prompting
    34: dict(on="borderline", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is prompting strategies for context faithfulness across two aspects — knowledge conflict AND prediction-with-abstention; abstention is genuinely 50% of the paper's scope but not the whole."),
    # 35. Non-Parametric UQ for Black-Box LLMs
    35: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is a non-parametric UQ method for black-box LLMs plus an agent design using the estimator — UQ is the first and primary contribution."),
    # 36. Hallucination detection framework for summarization
    36: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is a Q-S-E hallucination detection and mitigation framework for faithful text summarization — hallucination detection is the paper's named subject."),
    # 37. LM in the Loop / Snorkel
    37: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is applying LLMs as labeling functions in a weak supervision framework; 'abstentions' is one of the label options the model can emit, not the paper's subject."),
    # 38. LLMs are Overconfident (FermiEval)
    38: dict(on="on-domain", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is FermiEval, a benchmark for LLM confidence-interval calibration, plus conformal-prediction methods to fix overconfidence — the entire paper is confidence calibration for LLMs."),
    # 39. Statistical foundations
    39: dict(on="off-domain", lim="yes", hedg="hedged", fw="explicit", comp="yes", hard=False,
             why="Contribution is a position argument for why statistics should engage with LLM research; UQ is named as one of several application areas but the paper is not itself a UQ method paper."),
    # 40. Co-training prompt-based learning
    40: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is co-training for prompt-based learning; 'calibration model over prompt outputs' is one of two settings considered but the paper's subject is co-training, not calibration."),
    # 41. ASVD compression
    41: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is Activation-aware SVD for LLM compression; 'iterative calibration' is quantization-style calibration jargon for reducing decomposition error."),
    # 42. SAC3
    42: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is SAC3, a semantic-aware cross-check consistency method for hallucination detection in black-box LMs — hallucination detection is the paper's subject."),
    # 43. UQ via Convex Hull
    43: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is a geometric UQ method using convex hull of response embeddings — UQ for LLMs is the entire object."),
    # 44. Self-Evaluation Improves Selective Generation
    44: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is a self-evaluation method leveraging LLM token-level calibration to improve selective generation — selective generation/abstention IS the paper."),
    # 45. Pornographic text detection via KD
    45: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is CensorChat, a dataset and pipeline for detecting pornographic content in chat; 'GPT-4 for label calibration' is one pipeline step, not the paper's subject."),
    # 46. Predictability of LM Performance
    46: dict(on="borderline", lim="no", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is a performance-prediction study using DeBERTa 'assessors' to predict when generative LMs will succeed; assessors are compared to subjects on refinement AND calibration, so calibration is one of two prediction objects rather than the paper's subject."),
    # 47. Prompts and Response Uncertainty
    47: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is a prompt-response concept model explaining how prompt informativeness affects LLM response uncertainty — LLM uncertainty is the whole object."),
    # 48. Subjective UQ and Calibration in NLG
    48: dict(on="on-domain", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is a Bayesian-decision-theory framework for subjective UQ and calibration in natural language generation — UQ and calibration are jointly the subject."),
    # 49. Sirens' Whisper jailbreak
    49: dict(on="off-domain", lim="no", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is an inaudible near-ultrasonic audio jailbreak of speech-driven LLM assistants — a security attack paper, unrelated to calibration/uncertainty/hallucination as properties."),
    # 50. To Rely or Not to Rely
    50: dict(on="borderline", lim="yes", hedg="hedged", fw="explicit", comp="yes", hard=False,
             why="Contribution is a randomized HCI experiment evaluating reliance interventions for LLM decision support; poor user calibration is a headline finding but the paper's subject is reliance interventions, not confidence calibration."),
    # 51. Time-Aware LMs
    51: dict(on="off-domain", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is a technique for jointly modeling text with timestamp so LMs handle temporal facts; improved calibration on future predictions is one of several reported benefits, not the paper's subject."),
    # 52. TRoT / normal form (record mis-titled)
    52: dict(on="off-domain", lim="no", hedg="firm", fw="none", comp="yes", hard=False,
             why="Record is mis-titled 'Contrastive Decoding' but the abstract describes a categorical-theory unification of LLM inference methods; 'Conformal calibration snapshots' is one item in a reproducibility log, not the paper's subject."),
    # 53. Trustworthy Summarization via UQ
    # (abstract recovered from arXiv; label remains borderline)
    53: dict(on="borderline", lim="yes", hedg="firm", fw="none", comp="yes", hard=True,
             why="Contribution is a summarization LLM framework integrating Bayesian UQ and a risk-aware loss; UQ is substantively half the framework but the paper's headline object is trustworthy summarization, not UQ per se — a genuinely close borderline call."),
    # 54. Reinforced Calibration for political bias
    54: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is an RL framework for mitigating political bias in LM generation; 'reinforced calibration' is the method name but 'calibration' here means reward-weighted regeneration, not confidence calibration."),
    # 55. Survey on Hallucination in LLMs (2023 — same paper as #23)
    55: dict(on="on-domain", lim="yes", hedg="firm", fw="explicit", comp="no", hard=False,
             why="Contribution is a comprehensive survey of LLM hallucination taxonomy, detection methods, and mitigation strategies — this is the arXiv preprint version of paper #23."),
    # 56. SPV-MIA
    56: dict(on="off-domain", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is SPV-MIA, a membership inference attack against fine-tuned LLMs; 'self-prompt calibration' is the method name but the paper's subject is a privacy attack, not confidence calibration."),
    # 57. SLiC-HF
    57: dict(on="off-domain", lim="no", hedg="firm", fw="none", comp="no", hard=True,
             why="Contribution is SLiC-HF, a preference-learning alternative to RLHF using sequence likelihood calibration; 'calibration' is central to the method but for aligning sequence probabilities to preferences, not for confidence estimation — genuinely close call."),
    # 58. Decomposing Uncertainty via Input Clarification
    58: dict(on="on-domain", lim="yes", hedg="firm", fw="none", comp="no", hard=False,
             why="Contribution is an aleatoric/epistemic uncertainty decomposition framework for LLMs via input clarification ensembling — UQ for LLMs is the entire subject."),
    # 59. LLMs for Multi-Modal OOD
    59: dict(on="borderline", lim="yes", hedg="firm", fw="none", comp="yes", hard=False,
             why="Contribution is using LLMs' descriptive features to improve multi-modal OOD detection; 'consistency-based uncertainty calibration' is one of two proposed mechanisms, giving uncertainty calibration a substantive but not primary role."),
    # 60. Iterative Self-Questioning Supervision with Semantic Calibration
    60: dict(on="off-domain", lim="yes", hedg="firm", fw="implied", comp="yes", hard=False,
             why="Contribution is an iterative reasoning framework with four modules (questioning, reflection, semantic calibration, renewed reasoning); 'semantic calibration' is one module among four and 'calibration' here means semantic alignment, not confidence calibration."),
}

assert len(JUDGMENTS) == 60, f"expected 60 judgments, got {len(JUDGMENTS)}"


# --- Second-pass split: for every paper where has_limitation="yes",
# classify whether the limitation is of the paper's OWN work (or the
# subject it's investigating) versus PRIOR work cited as motivation.
# Only own-work + subject-finding limitations are usable evidence for
# the persistent-limitations scorer without full attribution to the
# specific prior paper being cited.
#
# Values:
#   own      — paper reports a limitation of its own method / findings,
#              OR reports a limitation of the studied subject as its own
#              empirical finding (e.g. "we find LLMs are miscalibrated").
#   prior    — paper cites a limitation of prior methods as motivation
#              ("existing X have Y problem, so we propose Z"). Usually
#              unattributable from abstract alone.
#   both     — both scopes present in the same abstract.
#   none     — has_limitation=no.
#   unknown  — no abstract available.

LIMITATION_SCOPE: dict[int, str] = {
    1:  "none",     # LLMC — no limitation stated
    2:  "prior",    # recovered; "one disadvantage of these works" — prior methods
    3:  "both",     # L2CEval — prior gap + own findings on LLM failures
    4:  "none",
    5:  "prior",    # recovered; "an inherent challenge of this approach" — prior
    6:  "none",
    7:  "none",
    8:  "prior",    # "existing UQ methods have fundamental limitations"
    9:  "prior",    # "challenges persist" — general/prior
    10: "none",
    11: "prior",    # "existing works overlook complex nature"
    12: "prior",    # "current LLMs are insufficient" — motivating
    13: "none",
    14: "prior",    # "many datasets not suitable for potent LLMs"
    15: "own",      # BIG-Bench's own finding: model perf/calibration poor
    16: "none",
    17: "none",
    18: "prior",    # "important to create benchmark datasets" — gap
    19: "prior",    # "susceptible to prompt choice" — motivating LM state
    20: "prior",    # "most prior work has been limited"
    21: "unknown",
    22: "own",      # "we uncover a systematic bias" — own finding
    23: "own",      # survey's own analysis of subject limitations
    24: "none",
    25: "own",      # own finding: "LLMs systematically more confident when wrong"
    26: "none",
    27: "prior",    # "barrier is lack of personalization" — motivating gap
    28: "none",
    29: "prior",    # "existing standards inadequate"
    30: "own",      # survey's own analysis of methods reviewed
    31: "prior",    # "compromises model performance" — prior methods
    32: "prior",    # "existing techniques suffer from interpretability"
    33: "none",
    34: "own",      # own finding about subject: LLMs overlook context
    35: "prior",    # "existing approaches limited"
    36: "prior",    # "existing methods exhibit limitations"
    37: "prior",    # "labeled training data limited" — general condition
    38: "own",      # own finding: "systematically overconfident"
    39: "own",      # own analysis: "black-box nature" — subject property
    40: "prior",    # "prompting is often brittle"
    41: "prior",    # "distribution variance in LLM activations"
    42: "prior",    # "existing approaches cannot detect"
    43: "prior",    # "traditional methods face challenges"
    44: "prior",    # "recent research demonstrated limitations" of prior
    45: "prior",    # "detecting pornographic language rarely studied"
    46: "none",
    47: "prior",    # "reliability...not well-established"
    48: "prior",    # "task-specific uncertainties difficult to define"
    49: "none",
    50: "both",     # "interventions lack rigorous evaluation" + own findings
    51: "both",     # "can limit utility" + own findings on LM problems
    52: "none",
    53: "both",     # recovered; "avoid overconfident predictions" (own) + prior gap
    54: "prior",    # "can be politically biased" — motivating subject prop
    55: "own",      # survey duplicate of #23
    56: "prior",    # "reasons lead to high false-positive rates" of prior MIAs
    57: "none",
    58: "prior",    # "remains an important open research question"
    59: "own",      # own analysis of LLM hallucination damage in OOD
    60: "prior",    # "LLMs often exhibit inconsistency, semantic drift"
}
assert len(LIMITATION_SCOPE) == 60
# Cross-check: papers marked own/prior/both here must have has_limitation=yes
# in JUDGMENTS; papers marked none/unknown must NOT.
for _n, _scope in LIMITATION_SCOPE.items():
    _lim = JUDGMENTS[_n]["lim"]
    if _scope == "none":
        assert _lim == "no", f"row {_n}: scope=none but lim={_lim!r}"
    elif _scope == "unknown":
        assert _lim == "unknown", f"row {_n}: scope=unknown but lim={_lim!r}"
    else:  # own / prior / both
        assert _lim == "yes", f"row {_n}: scope={_scope} but lim={_lim!r}"


def load_rows() -> list[dict]:
    with CSV_IN.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge(rows: list[dict]) -> list[dict]:
    """Write the judgment fields into each row. Preserves row order."""
    out = []
    for i, row in enumerate(rows, 1):
        j = JUDGMENTS[i]
        row["on_domain"] = j["on"]
        row["has_limitation"] = j["lim"]
        row["limitation_scope"] = LIMITATION_SCOPE[i]
        row["claim_hedged"] = j["hedg"]
        row["has_future_work"] = j["fw"]
        row["compound_claims"] = j["comp"]
        notes = "HARD" if j["hard"] else ""
        row["notes"] = notes
        row["label_reasoning"] = j["why"]
        out.append(row)
    return out


def write_csv(rows: list[dict]) -> None:
    # Canonical column order — puts limitation_scope next to
    # has_limitation and keeps label_reasoning at the end.
    fieldnames = [
        "openalex_id", "title", "venue", "year", "abstract_full",
        "on_domain",
        "has_limitation", "limitation_scope",
        "claim_hedged", "has_future_work", "compound_claims",
        "notes", "label_reasoning",
    ]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_md(rows: list[dict]) -> None:
    lines: list[str] = []
    lines.append("# Corpus review — pre-labelled")
    lines.append("")
    lines.append("Same 60-paper deterministic sample; each row now carries a pre-label + reasoning per `docs/labelling-rubric.md`. The reviewer's job is to spot-check and correct, not re-label from scratch.")
    lines.append("")
    lines.append("---")
    lines.append("")
    for i, r in enumerate(rows, 1):
        lines.append(f"## {i:02d}. {r['title']}")
        lines.append("")
        lines.append(f"- **openalex_id:** [{r['openalex_id']}]({r['openalex_id']})")
        lines.append(f"- **venue:** {r['venue']}")
        lines.append(f"- **year:** {r['year']}")
        lines.append("")
        lines.append("**Abstract**")
        lines.append("")
        lines.append(r["abstract_full"] or "_(no abstract in response)_")
        lines.append("")
        lines.append("**Pre-labels**")
        lines.append("")
        lines.append(f"- **on_domain:** {r['on_domain']}")
        lines.append(f"- **label_reasoning:** {r['label_reasoning']}")
        lines.append(f"- **has_limitation:** {r['has_limitation']} (scope: {r['limitation_scope']})")
        lines.append(f"- **claim_hedged:** {r['claim_hedged']}")
        lines.append(f"- **has_future_work:** {r['has_future_work']}")
        lines.append(f"- **compound_claims:** {r['compound_claims']}")
        if r["notes"]:
            lines.append(f"- **notes:** {r['notes']}")
        lines.append("")
        lines.append("---")
        lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def write_audit(rows: list[dict]) -> None:
    """Stratified 5 + 5 + 5 audit sample plus a hard-case addendum.

    The picks favor the closer-to-boundary papers within each bucket
    since easy hits are less informative to spot-check."""
    picks = {
        "on-domain":   [4, 7, 8, 33, 38],   # varied topics: hallucination, abstention, UQ, epistemic markers, calibration
        "borderline":  [3, 22, 27, 34, 50], # 22, 27 are HARD; 34 is 50/50 abstention; 50 is HCI
        "off-domain":  [1, 6, 29, 54, 57],  # PTQ toolkit, pruning, medical checklist, bias, HARD SLiC-HF
    }
    by_num = {i + 1: r for i, r in enumerate(rows)}

    lines: list[str] = []
    lines.append("# Audit sample — 15 stratified pre-labels")
    lines.append("")
    lines.append("Five papers each from my on-domain / borderline / off-domain buckets, plus a hard-case addendum. Read the pre-label + reasoning, then write **agree** or **disagree** on the blank line. If disagree, one word of what you'd change is enough — the full reasoning is in `scratch/corpus_review.md`.")
    lines.append("")
    lines.append("Rubric reminder: `docs/labelling-rubric.md`. Discriminator is contribution, not vocabulary.")
    lines.append("")
    for bucket in ("on-domain", "borderline", "off-domain"):
        lines.append(f"## {bucket}")
        lines.append("")
        for n in picks[bucket]:
            r = by_num[n]
            lines.append(f"### {n:02d}. {r['title']}")
            lines.append("")
            lines.append(f"- **openalex_id:** [{r['openalex_id']}]({r['openalex_id']})")
            lines.append(f"- **venue:** {r['venue']} ({r['year']})")
            lines.append(f"- **my label:** **{r['on_domain']}**")
            lines.append(f"- **my reasoning:** {r['label_reasoning']}")
            if r["notes"]:
                lines.append(f"- **flag:** {r['notes']}")
            lines.append("")
            lines.append("**Abstract**")
            lines.append("")
            lines.append(r["abstract_full"] or "_(no abstract in response)_")
            lines.append("")
            lines.append("- **agree/disagree:**")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Hard-case addendum
    hard_nums = sorted(n for n, j in JUDGMENTS.items() if j["hard"])
    picks_flat = {n for ns in picks.values() for n in ns}
    hard_extra = [n for n in hard_nums if n not in picks_flat]
    if hard_extra:
        lines.append("## Hard cases I flagged (not already in the stratified sample)")
        lines.append("")
        lines.append("These are the calls I found genuinely close. They're more informative to spot-check than easy ones.")
        lines.append("")
        for n in hard_extra:
            r = by_num[n]
            lines.append(f"### {n:02d}. {r['title']}")
            lines.append("")
            lines.append(f"- **openalex_id:** [{r['openalex_id']}]({r['openalex_id']})")
            lines.append(f"- **venue:** {r['venue']} ({r['year']})")
            lines.append(f"- **my label:** **{r['on_domain']}**")
            lines.append(f"- **my reasoning:** {r['label_reasoning']}")
            lines.append("")
            lines.append("**Abstract**")
            lines.append("")
            lines.append(r["abstract_full"] or "_(no abstract in response)_")
            lines.append("")
            lines.append("- **agree/disagree:**")
            lines.append("")
            lines.append("---")
            lines.append("")

    AUDIT_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    rows = load_rows()
    if len(rows) != 60:
        print(f"expected 60 rows, got {len(rows)}", file=sys.stderr)
        return 1
    labelled = merge(rows)
    write_csv(labelled)
    write_md(labelled)
    write_audit(labelled)

    # Report summary distribution.
    from collections import Counter
    labels = Counter(r["on_domain"] for r in labelled)
    scopes = Counter(r["limitation_scope"] for r in labelled)
    hard = sum(1 for j in JUDGMENTS.values() if j["hard"])
    print(f"Wrote {CSV_OUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {MD_OUT.relative_to(REPO_ROOT)}")
    print(f"Wrote {AUDIT_OUT.relative_to(REPO_ROOT)}")
    print()
    print("=== Label distribution (n=60) ===")
    for k in ("on-domain", "borderline", "off-domain"):
        c = labels.get(k, 0)
        print(f"  {k:12s}: {c:2d} ({100*c/60:.1f}%)")
    print(f"  hard cases : {hard:2d}")
    print()
    print("=== Limitation scope (n=60) ===")
    for k in ("own", "prior", "both", "none", "unknown"):
        c = scopes.get(k, 0)
        print(f"  {k:8s}: {c:2d} ({100*c/60:.1f}%)")
    # Own-work + subject-finding limitations are the usable evidence
    # for the persistent-limitations scorer without further attribution.
    usable = scopes.get("own", 0) + scopes.get("both", 0)
    print()
    print(f"  usable for persistent-limitations scorer "
          f"(own + both): {usable}/60 = {100*usable/60:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
