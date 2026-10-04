# Finding: a metadata-only domain-coherence predictor — hypothesis with
# suggestive evidence, not a validated model

**2026-08-09.** Free study — one live OpenAlex fetch across 9 candidate
domains (90 credits used of a 100,000/day quota; $0). No LLM, no
extraction, no full-text retrieval. Corpus stays frozen at 113 papers.

## What this tests

`docs/findings/RESEARCHMAP-FINDINGS.md` § 5 asserts that contradiction-
based LBD needs a *contested* field — measured on n=1 (our own corpus:
0 confirmed contradictions on 113 papers). That is a strong claim
resting on a single observation. This finding tries to build a cheap
pre-flight predictor that would let anyone decide, before spending on
extraction, whether their candidate domain is likely to yield the
signals the reasoning engine looks for.

**The predictor is a hypothesis. It has not been validated.** What
follows is the honest report of what the features say, what they
predict, and what full validation would cost.

## Method

1. **Feature extraction from OpenAlex metadata.** Seven features per
   domain, all deterministic, all computable from a single free
   OpenAlex `filter=` list call (~10 credits per domain). Code:
   `backend/app/coherence/features.py`. Every feature carries a
   documented "what it proxies for" claim in the module docstring;
   those are the load-bearing hypotheses:

   | feature | proxy for | direction |
   |---|---|---|
   | `intracorpus_reference_rate` | co-citation density | — |
   | `citation_reciprocity` | mature back-and-forth conversation | consolidation ↑ |
   | `citation_modularity` | schools of thought | ambiguous — see v0.2 |
   | `review_ratio` | see v0.2 reversal below | contest ↑ |
   | `temporal_churn` | fast-moving frontier | — |
   | `venue_concentration` | flagship venue exists | consolidation ↑ |
   | `term_vector_spread` | topical breadth | — |

2. **Nine domains fetched**, chosen for range (not statistical
   representativeness): the measured domain (llm-calibration), three
   reputationally-consolidated (protein structure prediction, formal
   methods for concurrency, transformer attention), five
   reputationally-contested (empirical software engineering, ML
   fairness, diet-and-mortality, microplastics-health, deep-RL
   continuous control). Each domain: 100 papers, ranked by citation
   count, publication year filter varies by domain (see `DOMAINS` in
   `backend/app/coherence/fetch.py`).

3. **Two composite scores** (`contested_score`,
   `method_transfer_score`), each an unweighted mean over three
   feature contributions in the direction hypothesised. **No
   parameters were fit to data.** Weights would be the first thing
   to change with a validation loop, and any tuning at n=1 would just
   overfit the single measurement.

## The feature table

Fetched 2026-08-09, all 100-paper corpora ranked by OpenAlex
`cited_by_count:desc`:

| slug | N | intra | recip | mod | rev | churn | HHI | spread | contested | mt-lead | reputation |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|
| microplastics-health | 100 | 0.044 | 0.000 | 0.266 | 0.25 | 0.753 | 0.065 | 0.910 | **1.000** | 0.773 | contested |
| deep-rl-continuous-control | 100 | 0.013 | 0.000 | 0.408 | 0.22 | 0.842 | 0.076 | 0.802 | **0.852** | 0.633 | contested |
| **llm-calibration** | 100 | 0.033 | 0.000 | 0.375 | 0.17 | 0.932 | 0.063 | 0.947 | **0.818** | 0.799 | **measured** |
| empirical-software-engineering | 100 | 0.028 | 0.000 | 0.323 | 0.03 | 0.767 | 0.049 | 0.836 | 0.684 | 0.679 | contested |
| ml-fairness | 100 | 0.012 | 0.000 | 0.446 | 0.11 | 0.870 | 0.016 | 0.945 | 0.667 | 0.621 | contested |
| formal-methods-concurrency | 100 | 0.015 | 0.000 | 0.448 | 0.02 | 0.925 | 0.080 | 0.981 | 0.546 | 0.652 | consolidated |
| diet-and-mortality | 100 | 0.009 | 0.000 | 0.682 | 0.08 | 0.962 | 0.038 | 0.958 | 0.440 | 0.594 | contested |
| protein-structure-prediction | 100 | 0.065 | 0.034 | 0.247 | 0.01 | 0.833 | 0.063 | 0.914 | 0.395 | 0.808 | consolidated |
| transformer-attention | 100 | 0.014 | 0.033 | 0.587 | 0.03 | 0.913 | 0.087 | 0.968 | **0.147** | 0.636 | consolidated |

Individual features already discriminate. Consolidated fields have
**~7× lower review ratio** (0.02 vs 0.14 mean) than contested ones; the
two domains with non-zero citation reciprocity are both consolidated
(preprint↔published cycles reflect mature canon); protein-structure-
prediction has the lowest modularity of the sample (0.25 — post-
AlphaFold, all the work extends the same architecture rather than
splitting into schools).

## Does it discriminate?

**Reputationally: mostly yes.** Sorted by `contested_score`, the top
five all carry the "contested" or "measured" reputation label; the
bottom three carry "consolidated." Two of the nine land on the wrong
side of the moderate/high threshold:

- **formal-methods-concurrency scores 0.546 (moderate).** Reputation is
  consolidated. The predictor sees moderate modularity and low
  reciprocity but nothing tips it decisively toward "consolidated";
  the review ratio (0.02) is doing most of the work in the right
  direction, offset by a modularity below the "consolidated" cutoff.
- **diet-and-mortality scores 0.440 (moderate).** Reputation is
  contested — the field is notorious for meta-analyses reaching
  opposite conclusions on the same food group. The predictor sees a
  **very** high modularity (0.68, highest in the sample) and a modest
  review ratio (0.08). Interpretation: the field's disagreements are
  organised into cleanly-separated methodological camps that don't
  cite each other much, so the modularity-based signal fires the
  wrong way. This is a real feature limitation — high modularity can
  mean "distinct schools of thought" (contested) OR "distinct
  application areas that don't interact" (independent). The predictor
  can't tell them apart.

**Against the one measured ground truth: WRONG.** llm-calibration
scored **0.818 (high contestedness)**, ranking 3rd of 9. Yet the
measured yield on our 113-paper build was **zero confirmed
contradictions**. This is the single most important failure to
report — the predictor's headline number disagrees with the only
domain where we can grade it.

The most likely reasons:

- 100 top-cited papers on an OpenAlex filter is not the same corpus
  as our 113-paper hand-labelled + snowball-expanded seed. The
  metadata predictor sees a *reference sample* of the field, not the
  corpus you would actually build. This is a design fact, not a bug:
  the whole point of a metadata predictor is that it runs BEFORE you
  build a corpus, so it must work off a reference sample. But it
  means "the predictor says field X is contested" is a claim about
  the ~100 top-cited papers, not about any specific 113-paper mix.
- The high review ratio for our domain (0.17) reflects a genuine
  survey wave in the LLM-hallucination literature over 2023-2025.
  Under v0.2 of the hypothesis (below) that codes as "contested,"
  but the surveys are largely *taxonomies* (types of hallucination,
  detection methods), not *disagreement resolution*. Review ratio may
  need to be decomposed by review type — a feature the OpenAlex
  metadata alone can't provide without an LLM classifier, which is
  out of scope here.

**Verdict: the predictor discriminates by reputation, but is wrong on
n=1 measured yield.** That is exactly the outcome the setup section
warned about: a single ground-truth point cannot validate a predictor.
It can only expose a specific class of failure, which it did.

## The v0.1 → v0.2 reversal

The first draft of `contested_score` hypothesised that a HIGH review
ratio signalled consolidation ("field is ready to write the textbook").
The fetched data flipped that unambiguously: reputationally-contested
domains had 5-10× more surveys/reviews than consolidated ones
(microplastics 0.25, deep-RL 0.22, llm-calibration 0.17 vs protein
0.01, formal-methods 0.02, transformer 0.03). Reviews turn out to be
mostly *responses to disagreement*, not consolidation writeups. The
weights inverted in v0.2 and the reputational discrimination emerged.

The reversal is worth flagging because it's the same failure mode our
scaling-study finding warned about (§ 2 of the main findings report):
a plausible hypothesis producing a clean-looking curve that turns out
to be an artifact of the parameters. Here it was a directional
hypothesis flipped by data; that direction is now baked in and any
future version should track further reversals here rather than
silently rewriting the doc.

## What full validation would require

To move this from "hypothesis with suggestive evidence" to
"predictive model," we need actual yield measurements on domains
other than llm-calibration. The cost of one full validation loop:

| step | per domain | notes |
|:--|--:|:--|
| Ingestion (OpenAlex, snowball to ~200 papers) | $0 | filter+cite endpoints |
| Full-text retrieval (~70% coverage typical) | $0 | arXiv/PubMed/Europe PMC — free |
| Extraction (Gemini Flash, ~200 papers) | ~$5 | @ $0.0336/full-text, $0.011/abstract |
| Relationship layer (embeddings + cosine) | ~$0.02 | Gemini embedding-001 |
| Contradiction classifier (candidate pairs) | ~$1-3 | scales ~pairwise |
| **Per-domain total** | **~$6-8** | one shot |

**Two contrasting domains** (one predicted-contested, one predicted-
consolidated) run through the whole pipeline: **~$12-16 total.** That
gives us n=3 measurements, still not statistical validation but enough
to at least verify the direction of the prediction and either confirm
or falsify the llm-calibration surprise above. The obvious pair:
**microplastics-health** (highest predicted contestedness, 1.00) vs
**transformer-attention** (lowest, 0.147).

**Three domains** (add one moderate — say ml-fairness at 0.667):
**~$18-24 total.** Gets us n=4, enough to sketch a rank correlation.

Neither is being run in this task — the acceptance says "do not run
it," and validation is a distinct project that needs a budget approval
per CLAUDE.md's hard-stop (a). Recording it here so the numbers are
already framed for whoever chooses to do it next.

## Provenance

- Feature computation: `backend/app/coherence/features.py`
- Fetch + CLI: `backend/app/coherence/fetch.py`
- Tests: `backend/tests/coherence/test_features.py`
- Raw fetches (regenerable): `data/coherence/{slug}/openalex.json`
- Feature table: `data/coherence/features.json`
- Total cost: **$0.00** (OpenAlex credits: 90 of 100,000/day quota)
- Pinned to OpenAlex API as of 2026-08-09; if OpenAlex changes their
  response shape, `test_llm_calibration_features_within_expected_ranges`
  will catch it before the composite scores drift silently.

## Limitations

- **n=1 ground truth.** llm-calibration is the only domain where we
  have measured yield to grade against. That's not validation.
- **100-paper OpenAlex sample ≠ the corpus you'd actually build.** The
  predictor sees a *reference distribution*, which is what a
  pre-flight tool must do — but the "measured" comparison isn't
  apples-to-apples with our 113-paper hand-labelled corpus.
- **Unweighted composite means.** No data-fit weights. Every future
  attempt to tune weights on limited ground truth risks overfitting
  the one available domain.
- **"Reputation" is my judgment call.** The reputational labels used
  above are consensus among ML researchers I've read, not a
  systematic survey. A skeptical reader should treat "reputation:
  contested" as this-author's-prior, not established.
- **The predictor cannot distinguish "distinct schools argue" (high
  modularity, contested) from "distinct applications don't overlap"
  (high modularity, independent).** The diet-and-mortality miss above
  is the clearest example.
- **Review-ratio conflates response-to-disagreement with taxonomy
  surveys.** Both count as "review" in OpenAlex; only the former
  signals contestedness. Separating them would need an LLM
  classifier on titles/abstracts, which is out of scope for a
  free-metadata tool.

## Bottom line

The features are cheap, deterministic, and reveal real differences
between domains — anyone can compute them for their own candidate
field for $0 and 8 seconds. The composite scoring is a hypothesis
that discriminates by reputation but gets the one measured domain
wrong; the direction of that error (over-predicting contestedness
from surveys-as-responses-to-disagreement) is documented so the next
person to touch this knows what to watch out for. It's a starting
point for a validation loop, not a substitute for one.

## Live validation loop underway (2026-09-28)

Two new domains being built to n=3 total, deliberately spanning the
predictor's confidence range so this run measures whether it discriminates:

| domain | contested score | band | reputational label | why chosen |
|:--|--:|:--|:--|:--|
| **diet-and-mortality** | 0.440 | moderate | contested | **Chosen AGAINST its score.** Reputationally the classic "meta-analyses reach opposite conclusions" domain; the predictor scores it moderate because its very high modularity (0.68) reads as "isolated schools" — the doc's named ambiguous case. Raj can judge the outputs (red meat, saturated fat, alcohol are nameable disagreements). |
| **ml-fairness** | 0.667 | high | contested | Aligned with score. Documented impossibility results (Kleinberg / Chouldechova) give the contradiction scorer nameable targets. |

## Measured record — n = 3 (2026-10-02 iteration-4 update, DO NOT REFIT)

Both new libraries are now at full extraction coverage, and every
shortlisted claim pair in each has been classified (threshold 0.80,
cap 2). **Do not use these three points to refit the weights** — n=3 is
far below the noise floor of a 7-feature composite. This section records
the numbers so the next validation attempt (~8–10 domains minimum) has a
starting table, not a prediction claim.

<!-- gen:measured -->
| library | predictor score | predictor label | raw flagged | audited genuine | claims-read coverage | pairs checked | confounds |
|:--|--:|:--|--:|--:|:--|:--|:--|
| llm-calibration | 0.818 | high | 2 | 0 | 113 / 113 (100%) | 437 / 437 | own shortlist settings (0.78, cap 10); both flags set aside as regime conflation |
| diet-and-mortality | 0.44 | moderate | 10 | 5 | 100 / 100 (100%) | 152 / 152 | hand audit is the builder's, not expert review |
| ml-fairness | 0.667 | high | 0 | 0 | 99 / 99 (100%) | 91 / 91 | zero not explained (see multi-domain.md §2, hypotheses untested) |
<!-- /gen:measured -->

Two of three predictions miss, now without coverage confounding:
- **diet** scored moderate yet produced 5 genuine contradictions. The
  three extra flags from the full-coverage pass were set aside by hand
  audit (one artifact, two duplicates), so the count did not move.
- **ml-fairness** scored high yet produced 0 at full coverage. Of the
  25 shortlisted pairs touching the impossibility-result papers, 0 were
  flagged; Friedler et al.'s "(im)possibility" paper had no shortlisted
  pairs at all. Why the classifier finds no contradictions here is not
  established. The idea that fairness disagreements are definitional
  rather than empirical remains a **hypothesis**, not a finding; see
  `multi-domain.md` §2 "Why zero? Not established" for the candidate
  explanations, none tested.

Per-paper counts at full coverage (generated from the cached claim
embeddings and verdict files):

<!-- gen:impossibility -->
| paper | shortlisted pairs | classified | flagged |
|:--|--:|--:|--:|
| Inherent Trade-Offs in the Fair Determination of Risk Scores (2016) (`W4386564359`) | 12 | 12 | 0 |
| Fair Prediction with Disparate Impact: A Study of Bias in Recidivism Prediction Instruments (2017) (`W2543774860`) | 1 | 1 | 0 |
| On the (im)possibility of fairness (2016) (`W2524301210`) | 0 | 0 | 0 |
| Fairness in Criminal Justice Risk Assessments: The State of the Art (2018) (`W2599025709`) | 10 | 10 | 0 |
| Algorithmic Decision Making and the Cost of Fairness (2017) (`W2584805976`) | 0 | 0 | 0 |
| The cost of fairness in binary classification (2018) (`W2790025105`) | 0 | 0 | 0 |
| Inherent Trade-Offs in Algorithmic Fairness (2018) (`W2808105152`) | 2 | 2 | 0 |
<!-- /gen:impossibility -->

### Fairness-miss free diagnostic (no new spend; run at 51 of 100 papers)

This diagnostic predates full coverage and is kept as a record. The
counts above supersede its counts.

Hypothesis: the contradiction scorer looks for EMPIRICAL disagreement
("does X reduce Y or not") while fairness's famous disagreements are
DEFINITIONAL / THEORETICAL — different papers formalize incompatible
fairness definitions.

Method (all reads, no calls):
1. Search the 51 extracted fairness papers for impossibility /
   incompatibility papers by title. Found 6:
   - Kleinberg-Mullainathan-Raghavan 2016 (`W4386564359`, "Inherent
     Trade-Offs in the Fair Determination of Risk Scores")
   - Berk et al. 2018 (`W2599025709`, "Fairness in Criminal Justice
     Risk Assessments")
   - Friedler et al. 2016 (`W2524301210`, "On the (im)possibility
     of fairness")
   - Corbett-Davies et al. 2017 (`W2584805976`, "Algorithmic
     Decision Making and the Cost of Fairness")
   - Menon-Williamson 2018 (`W2790025105`, "The cost of fairness in
     binary classification")
   - Chouldechova / Roth 2018 (`W2808105152`, "Inherent Trade-Offs
     in Algorithmic Fairness")
2. Scan the classifier's pair verdicts (contradictions.json,
   supports.json, nones.json) for pairs involving any of those six
   paper ids.

Results:
- **0** pairs marked `contradicts`.
- **1** pair marked `supports` (W2599025709 ↔ W4386564359):
  Gemini said *"Both claims state the same impossibility theorem in
  algorithmic fairness: calibration and error rate balance cannot be
  simultaneously achieved when base rates differ."* Correct call.
- **3** pairs marked `none`. Representative Gemini rationale:
  *"The claims present distinct impossibility theorems involving
  different combinations of fairness criteria under unequal base
  rates."* Also *"Both claims address trade-offs among algorithmic
  fairness metrics, but they focus on different combinations of
  criteria."*

**Reading (the builder's interpretation of these four verdicts; not
tested):** the classifier's rationales describe the impossibility
results as concerning different combinations of fairness criteria, so
under its prompt's definition of `contradicts` ("cannot both be true
about the same construct") it did not flag them. Whether that is the
reason the library yields zero is not established.

**Hypothesis (not established):** the contradiction scorer's built-in
notion of disagreement (empirical claim vs empirical claim) is a
poor fit for fields where disagreement is definitional / axiomatic.
A domain-typed scorer variant — one that flags DEFINITIONAL
incompatibility explicitly — might find disagreements in this fairness
corpus; that is untested. Building that variant is out
of scope for this run.

### What a recalibration would need

The current composite scores are unweighted means of 3 features each
per axis, chosen by hypothesis alone (see §"Method" above). Anything
worth calling "recalibration" would need:

1. **Measured yield on 8–10 domains** across a range of predicted
   scores. n=3 is not enough to fit anything without overfitting.
2. **Scorer-variant for definitional disagreement**, if hypothesis (a)
   in `multi-domain.md` §2 is ever tested and holds — or else a
   documented reason why ml-fairness's zero should or should not count
   against the predictor.
3. Even after (1)–(2), any weight fit should hold out at least 2
   domains as a validation set — otherwise the fit tests itself.

Done: **ml-fairness re-run at full extraction** (iteration 4,
2026-10-02): 100 of 100 papers, 95 of 95 shortlisted pairs, still 0
flagged. (After the 2026-10-04 merge of a duplicate paper the library has
99 papers; current counts are in the table above.) Its zero is no longer confounded by partial coverage.

Until those are done, the predictor stays where it is: **a
hypothesis-driven diagnostic that discriminates domains by
reputation, is measurably wrong on 2 of 3 ground-truth cases, and
must not be presented as validated.**

## The 2026-09-28 chosen domains — original selection notes

The diet pick doubles as a **test of the predictor**: if diet produces
substantial confirmed contradictions after Part D scoring, the score's
0.44 was wrong and reputational judgment beat the metric. If it produces
zero, the predictor was right and the reputational label was misleading.
Either result goes back into this finding after Part D. Not silently
rewriting the doc's earlier conclusions — extending them with n=3.

