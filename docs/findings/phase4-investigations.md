# Phase-4 investigations (2026-07-26) — read-only, no scoring changes

Diagnostics on the reasoning-engine output. No weights, prompts, or
Phase-5 work touched.

## 0. DEDUP REGRESSION (priority) — one survey counted twice; corpus is 198 not 200

`#1` and `#11` are the **same contradiction counted twice**. Both pair the
clinical paper `W4412853478` (claim c4, "temp=0 doesn't reduce
hallucination") against the SAME survey, which exists in the corpus as two
un-collapsed records:

- `W4388585881` — 2023 **arXiv preprint**, DOI `10.48550/arxiv.2311.05232`
- `W4404534210` — 2024 **ACM published**, DOI `10.1145/3703155`

Byte-identical normalized titles ("A Survey on Hallucination in Large
Language Models…"); the two "different" survey claims (c5, c6) are the same
sentence reworded. Both were hand-labelled core seeds; neither the hand
review nor the dedup caught the duplication.

**Which pass should have caught it:** pass **#4** (arXiv-DOI-aware: one
arXiv DOI + one non-arXiv DOI, same title, shared author → merge regardless
of year gap). Verified: `normalizer.deduplicate()` collapses the pair 2→1
when author data is present.

**Why it didn't fire:** the corpus was assembled by
`build_expanded_manifest.py`, whose dedup is a weaker 2-pass — `DOI`, then
`(normalize_title, YEAR)`. The DOIs differ (arxiv vs ACM) and the years
differ (2023 vs 2024), so both passes miss. The full ingestion
`deduplicate()` (which HAS pass #4) was never run on the assembled corpus,
and the manifest-built Papers carry no authors (pass #4 needs a shared
author). The `(title, YEAR)` key literally reintroduces the preprint-vs-
published failure mode its own comment claims to handle.

**Blast radius (whole corpus):** exactly **2** title-collision groups in
200 papers (198 unique works), both cross-year preprint/published pairs:
1. the hallucination survey above (caused the #1/#11 double-count);
2. "A framework to assess clinical safety and hallucination" —
   `W4402508807` (2024 medRxiv) + `W4410343193` (2025 npj Digital Medicine).

**Impact:** this hits **every count-based scorer**, not just contradictions
— any category/relationship these duplicated papers feed is inflated, and
the 3-independent-paper floor can be met by two copies of one work. Small
here (2 pairs), but structural.

---
The three diagnostics from the prior round, re-confirmed with the papers
behind #1/#7/#9/#11/#14:

## 1. Contamination behind the WikiQA / BoolQ orphans — a PATTERN

Both are snowball hop-2 papers, not in the hand-labelled 60. Two distinct
mislabel channels, both systematic:

- **BoolQ (`W2953271402`) → labelled on-domain / CORE**, reason: *"venue in
  allowlist: 'arXiv'"*. **Root cause: `"arxiv"` is an entry in
  `heuristic_label.VENUE_ALLOWLIST`.** arXiv is a preprint server for all of
  CS/ML, not a domain signal — so any arXiv paper is auto-elevated to core.
  **8 corpus papers were admitted as core this way**: ARC, BoolQ,
  Multi-Task-Learning survey, Deep-Learning-Text-Classification review,
  BARTScore, Adversarial-Attacks-on-NLP, BERT-fine-tuning-stability,
  gradient-based-distribution-shift. Most are general NLP/ML, off the
  calibration/uncertainty domain. (This is the same ARC false-positive the
  earlier audit sample flagged; it persisted.)
- **WikiQA text-matching (`W2953075226`) → labelled borderline / PERIPHERAL**,
  reason: *"no strong signal in either direction"* — the keep-borderline
  fallback. **83 of 166 snowball corpus papers (50%) entered via this
  fallback**, a MIX: legitimate pre-LLM calibration classics with no "LLM"
  anchor (e.g. "Predicting good probabilities with supervised learning",
  "Transforming classifier scores into multiclass probability estimates" =
  Platt/isotonic calibration) AND clear off-domain noise (Monte-Carlo
  sampling, model compression, fake-news detection, legal-education, LLM
  agents). The heuristic cannot separate the two.

**Expanded trace (the five reviewer-flagged items #2,#3,#7,#9,#14):**

| opp | paper | year | label | admit reason | hop / parent |
|:--|:--|:--|:--|:--|:--|
| #2 | W2953075226 *Simple and Effective Text Matching* | 2019 | peripheral | no-signal fallback | hop2 / W2788496822 |
| #3 | W2953271402 *BoolQ* | 2019 | **core** | **arXiv-venue rule** | hop2 / W2788496822 |
| #7,#9 | W2962996600 *LCSTS Chinese Short-Text Summarization Dataset* | 2015 | peripheral | no-signal fallback | hop1 / W4416966348 |
| #14 | W2514278201 *Least Ambiguous Set-Valued Classifiers* | 2017 | peripheral | no-signal fallback | hop1 / W4411121371 |

(#7 and #9 are the SAME source paper, W2962996600 — two future-work items
from one off-domain dataset paper.)

**Verdict: a rubric edge case, not a single seed.** 4 of 5 entered via the
**"no strong signal → keep as borderline"** fallback; only BoolQ is the
arXiv-rule bug. Parents are spread (W2788496822 ×2, W4416966348, W4411121371)
— not one poisoned neighbourhood. Nuance: #14 (*Least Ambiguous Set-Valued
Classifiers*) is a foundational **conformal / selective-prediction**
statistics paper — dated, but topically **legitimate** (selective prediction
is in-domain); the reviewers' "off-domain" flag is wrong for that one, though
"badly dated" is fair. #2, #3, #7/#9 are genuine off-domain contamination
(text matching, QA benchmark, Chinese summarization dataset).

## 2. Opportunity #1 (temperature/hallucination) — CONFIRMED a regime bug

- Paper 1 `W4404534210` (survey): "Elevating sampling temperature increases
  hallucination risk by sampling low-frequency tail tokens" — **general
  open-ended generation; a sampling mechanism.**
- Paper 2 `W4412853478`: "Setting decoding temperature to 0 does not
  significantly reduce hallucination" — but its sibling claims show the
  regime: **adversarially-injected fabricated medical facts in clinical
  vignettes** ("repeat fabricated medical details in 50–82% of cases",
  "prompt-based mitigation 66%→44%", "clinical vignettes"). Hallucination
  here = repeating a *planted* falsehood, which a sampling knob wouldn't fix.

Both claims can be true — different mechanisms and regimes. The contradiction
classifier compared the two sentences **stripped of regime**, because
`Claim` has no experimental-context field.

**A `Claim.condition` field would need to capture:** the experimental regime
(general generation vs adversarial vs domain-specific/clinical), the
dataset/benchmark, the manipulation (e.g. "adversarial fact injection"), the
operational definition of the measured property (hallucination = repeating
planted falsehood vs = factual error in free generation), and the model set.
Two claims should be compared only when same construct AND same regime.

**Cost to add + re-run (corrected thinking-token pricing):**
- Proper fix — add `Claim.condition` (Pydantic + table + migration), a
  v1.2.0 extraction prompt, and **re-extract all 200 papers**: **~$4.65**
  (batch) + contradiction re-run ~$0.71 ≈ **$5.4**. **Over the ~$2 remaining
  budget.**
- Cheap partial — no schema change; re-run only the contradiction classifier
  feeding it each claim's source title + sibling claims as regime context:
  **~$0.71**. Would likely re-label this pair as not-contradictory, but the
  regime stays unrecorded in the schema.

## 3. Terminology-collision rate — NOT uniform; a per-term problem

- **"calibration"** (59 mentions): within the *filtered* corpus, ~1 dominant
  construct — **confidence/probability calibration** (ECE, temperature
  scaling, well-calibrated probabilities) — plus two minor sub-variants
  (linguistic calibration `W4322717046`, human calibration `W4406679533`).
  The dangerous cross-field collisions the criteria doc warned about
  (quantization-calibration, LLM-judge-calibration, SLiC likelihood-
  calibration) were already excluded by the domain filter. **Low collision
  rate — a same-construct check adds little here.**
- **"computational cost"** (the 5-paper persistent-limitation category):
  the normalized category pools **≥4 distinct constructs** — evaluation/
  benchmark cost (`W4281690148`), training cost (`W4388748038`, `W3034199299`:
  multiple models / more epochs), inference/sampling cost (`W4391505381`,
  `W4415914353`: multiple responses / multi-sampling). Broader cost-limitation
  spread: ~15 generic, 10 inference-latency, 7 training, 3 sampling, 3
  memory. **High collision at the CATEGORY-NORMALIZATION level** — the
  persistent-limitations "5 papers agree" is partly an artifact of lumping
  different bottlenecks.

**Verdict:** a same-construct check is needed for a FEW overloaded
terms/categories (generic ones like *computational-cost*), **not before
every comparison** — because the domain filter already removed the worst
cross-field "calibration" collisions, and most on-domain terms resolve to a
single construct within the corpus. The collision problem lives in the
extractor's coarse `normalized_category`, more than in the raw claim text.
