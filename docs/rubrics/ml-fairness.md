# Labelling rubric — ml-fairness

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for a domain where "fair" and "bias" appear
across many machine-learning tasks — most of which are not fairness
research.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's primary
  contribution is ABOUT algorithmic fairness in machine learning —
  proposing a fairness definition, characterising a fairness-accuracy
  trade-off, arguing over the incompatibility of fairness criteria,
  building a bias-mitigation method, auditing a deployed ML system for
  fairness, or analysing the social/policy implications of an ML
  system's disparate treatment. Impossibility results, formal
  definitions, and empirical audits all count.

- **borderline** (`domain_centrality = peripheral`, KEPT): fairness /
  bias is a substantial component but not the contribution. Examples:
  a general benchmark paper with a fairness track (BIG-bench-lite);
  a foundation-model report with a fairness section; a broad survey
  of trustworthy ML that has a fairness chapter; a robust-optimisation
  paper whose worked example is a fairness constraint.

- **off-domain**: bias/fairness is mentioned in passing, used as a
  narrow tool, or appears in a task whose contribution lies elsewhere.
  Examples: a bias-variance decomposition paper (statistical bias,
  not group fairness); a NAS paper whose search-bias section is about
  architecture search; a medical-imaging paper that mentions "bias
  in patient selection" as a limitation.

## Corpus policy

Borderline is KEPT, not dropped, tagged `peripheral`. Same reasoning
as the base rubric: the persistent-limitations scorer counts
independent papers reporting the same limitation, and a peripheral
paper that reports "our post-processing method degrades utility" is
genuine independent evidence.

No-signal → EXCLUDE by default. A paper with no positive on-domain
signal is off-domain until proven otherwise.

## What counts as an on-domain signal

**Strong terms alone** (specific enough that a bare match is
disqualifying-unless-context-changes):

- "algorithmic fairness"
- "demographic parity"
- "equalized odds", "equal opportunity" (in the Hardt-Price-Srebro sense)
- "equal treatment"
- "counterfactual fairness"
- "individual fairness", "group fairness", "subgroup fairness"
- "calibration fairness", "fairness through calibration" — **note:**
  this phrase collides with the LLM-calibration library's terminology.
  The full phrase is fairness-specific; the bare word "calibration" is
  NOT in this list and would collide.
- "disparate impact", "disparate treatment", "disparate mistreatment"
- "fair classification", "fair regression", "fair clustering",
  "fair ranking", "fair representation", "fair representation learning"
- "fairness through unawareness"
- "protected attribute" (when used technically, not colloquially)
- "predictive parity"
- "bias mitigation" (fairness-context)
- "fairness constraint", "fairness metric", "fairness definition"

**Anchor + topic co-occurrence** within 30 tokens in the abstract,
or 12 tokens in the title:

- Anchors (the ML noun): `classifier`, `classification`, `machine
  learning`, `algorithm`, `model`, `prediction`, `supervised learning`,
  `deep learning`, `neural network`, `learned model`
- Topics (the fairness noun): `fairness`, `fair`, `unfair`, `bias`
  (paired with a group-level modifier: `gender bias`, `racial bias`,
  `demographic bias`), `discrimination`, `equity`, `equality`

**Venue allowlist** — fairness-oriented and general ML venues that
would rarely publish a bias/fairness paper that wasn't fairness
research:

- FAT* / FAccT (ACM Conference on Fairness, Accountability, and
  Transparency)
- Ethics and Information Technology
- Big Data & Society
- AI and Society
- Journal of Machine Learning Research (JMLR)
- Transactions on Machine Learning Research (TMLR)
- NeurIPS / ICML / ICLR / AAAI / IJCAI / AISTATS (rescue rule —
  fairness papers at general ML venues need the topic terms too)
- ACL / EMNLP / NAACL when combined with fairness terms (bias in NLP)

## What counts as off-domain

**Venue denylist** — bias/fairness in these contexts usually means
something else:

- Chemistry, Materials Science, Physics, Earth Sciences journals
- Medical / Life Sciences journals (unless the topic is fairness of
  medical ML systems, in which case the venue allowlist would already
  admit them via general ML terms)
- Robotics conferences (bias usually means sensor bias)
- Signal-processing journals (bias-variance, estimator bias)
- Nature / Science top-line papers with a fairness section — the
  paper's contribution is usually a broader benchmark or model
  release, not fairness research (mark as borderline)

**Primary field denylist**:

- Chemistry, Materials Science, Physics, Earth Sciences, Engineering
  (unless CS is a co-topic AND the on-domain signal is strong)
- Medicine (same rescue caveat as above)

## Named failure modes worth watching

Domain-specific senses of "bias" that will trip a naive keyword rule:

1. **Statistical bias** (bias-variance, estimator bias, sampling bias).
   Off-domain unless the paper's contribution is group-fairness
   analysis. Anchor+topic discipline (`group bias`, `demographic bias`)
   should catch most.
2. **Inductive / architectural bias** (bias in neural network
   architectures — the useful kind of bias). Off-domain. The audit
   sample should include one.
3. **Confirmation / cognitive bias.** Off-domain — psychology
   literature, not ML fairness.
4. **Selection bias in observational studies.** Off-domain unless the
   study is specifically about who is (un)fairly selected by an
   algorithmic decision system.
5. **"Bias" in reinforcement learning** (reward-shaping bias,
   exploration bias). Off-domain unless the paper is about fairness
   of RL agents in their decisions.
6. **LLM alignment / value learning papers.** Borderline at most —
   these are often about model safety or values rather than group
   fairness in the technical sense. Keep as peripheral if the topic
   is bias in generation but not in the group-fairness / disparate-
   impact tradition.
7. **Facial-recognition audits.** On-domain when the contribution is
   the audit / disparate-error-rate analysis (Buolamwini & Gebru's
   Gender Shades line of work). Off-domain when the paper is a
   face-recognition method that happens to report per-demographic
   error rates as one of many metrics.

The audit sample includes at least three of these hard cases, flagged
`hard=true`.

## Why this rubric matters for the reasoning engine

Ml-fairness is chosen specifically because the field has documented,
mathematically-proven incompatibilities: Kleinberg-Mullainathan-
Raghavan showed calibration, balance-for-positive-class, and
balance-for-negative-class cannot all hold simultaneously except in
trivial cases; Chouldechova showed the same for calibration,
false-positive-rate parity, and false-negative-rate parity. These are
NAMEABLE contradictions the scorer should find. If the corpus
admits enough on-topic material, we expect confirmed contradictions
where LLM-calibration produced zero — the test of whether the scorer
works when disagreement actually exists.

## What is NOT on-domain

- Bias-variance decomposition, generalisation-bias analyses, other
  statistical-bias uses of the word.
- Adversarial-robustness papers (unless the perturbation is a
  demographic-shift analysis).
- Explainability / interpretability papers (unless the contribution is
  a fairness-related explanation).
- Privacy papers (differential privacy interacts with fairness but is
  a separate literature).
- Model-alignment / RLHF papers (unless fairness is the specific
  alignment target).
- Recommendation-diversity papers (unless framed as fairness for a
  protected attribute).
