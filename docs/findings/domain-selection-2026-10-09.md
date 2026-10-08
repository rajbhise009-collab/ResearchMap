# Domain selection — 2026-10-09

Which two subjects to build next, and which to queue for the weekly
workflow. Free study: OpenAlex metadata and open full text only, no
language model. Code: `backend/app/corpus/domain_selection.py`; raw
results: `data/coherence/<slug>/` and `data/coherence/selection.json`.

## How each candidate was scored

Weights were fixed before any scoring. Contestedness is weighted heavily
because disagreement-based discovery has only worked in contested fields
(Diet & mortality: 5 hand-checked disagreements; LLM calibration: none).

| part | weight | how it is measured |
|:--|--:|:--|
| contestedness | 0.45 | 0.7 × reputation for active, published disagreement (judgement, reason in the table below) + 0.3 × the coherence predictor's contested score (`backend/app/coherence`, 100 most-cited matching works) |
| open full text | 0.25 | the 25 most-cited works sent through the **libraries' own retrieval code** (arXiv via OpenAlex locations or Semantic Scholar, arXiv title search, Unpaywall / Europe PMC); share returning ≥ 3,000 characters of text. Not open-access flags. |
| audience diversity | 0.15 | new readers compared with the three existing libraries (judgement) |
| 1 − advice risk | 0.15 | how likely a reader is to take results as personal medical, parenting or other advice (judgement) |

Gate: at least 300 matching works in OpenAlex, so a library can be built and
grow. All twelve passed.

The predictor is still a hypothesis, not a validated model
(`docs/findings/domain-coherence-predictor.md`). That is why it carries
less weight than the reputation judgement.

## Results

| # | candidate | OpenAlex matches | reputation | predictor | contestedness | full text (25 probed) | audience | advice risk | composite | decision |
|--:|:--|--:|--:|--:|--:|--:|--:|--:|--:|:--|
| 1 | Nudges and choice architecture: do they work? | 7,559 | 0.90 | 0.50 | 0.78 | 28% | 0.9 | 0.2 | 0.677 | **build now** |
| 2 | Social media and adolescent mental health | 9,983 | 0.95 | 0.83 | 0.91 | 28% | 0.9 | 0.6 | 0.676 | **build now** |
| 3 | Ego depletion and psychology replication debates | 1,867 | 0.95 | 0.51 | 0.82 | 12% | 0.9 | 0.1 | 0.668 | queued |
| 4 | Minimum wage and employment | 8,716 | 0.95 | 0.40 | 0.78 | 16% | 1.0 | 0.2 | 0.663 | queued |
| 5 | Growth-mindset interventions | 6,670 | 0.90 | 0.46 | 0.77 | 24% | 0.9 | 0.3 | 0.646 | queued |
| 6 | Deep reinforcement learning: evaluation and reproducibility | 11,153 | 0.70 | 0.41 | 0.61 | 60% | 0.3 | 0.0 | 0.621 | — |
| 7 | Microplastics and human health | 25,771 | 0.70 | 1.00 | 0.79 | 28% | 0.8 | 0.5 | 0.620 | — |
| 8 | Stereotype threat | 2,210 | 0.85 | 0.59 | 0.77 | 4% | 0.9 | 0.2 | 0.612 | — |
| 9 | Vitamin D supplementation and health outcomes | 10,072 | 0.85 | 0.73 | 0.81 | 32% | 0.5 | 0.9 | 0.536 | — |
| 10 | Empirical software engineering (defect prediction) | 625 | 0.60 | 0.68 | 0.62 | 8% | 0.5 | 0.0 | 0.526 | — |
| 11 | Intermittent fasting and time-restricted eating | 5,478 | 0.80 | 0.66 | 0.76 | 28% | 0.4 | 0.8 | 0.501 | — |
| 12 | Coffee, caffeine and health | 16,272 | 0.60 | 0.56 | 0.59 | 44% | 0.3 | 0.8 | 0.450 | — |

## The judgements, with reasons

| candidate | reputation for disagreement | audience | advice risk |
|:--|:--|:--|:--|
| Microplastics and human health | 0.70: Open disputes over detection methods, contamination of samples and dose-response in humans. | 0.8: Environmental-health readers; no overlap with diet or ML. | 0.5: Readers may ask 'are microplastics harming me'; exposure advice risk is moderate. |
| Intermittent fasting and time-restricted eating | 0.80: Trials disagree on whether benefits exceed plain calorie restriction (e.g. Lowe 2020 vs earlier small trials). | 0.4: Overlaps the Diet library's readers. | 0.8: Directly actionable eating advice; high risk of being read as a recommendation. |
| Coffee, caffeine and health | 0.60: Observational results flip across outcomes and doses; fewer head-on disputes than diet staples. | 0.3: Strong overlap with the Diet library. | 0.8: 'Is coffee good for me' is the first question readers bring. |
| Growth-mindset interventions | 0.90: Large trials and meta-analyses disagree sharply (Yeager 2019 vs Sisk 2018, Macnamara 2023). | 0.9: Education and psychology readers; new audience. | 0.3: Teachers might apply it, but it is not medical advice. |
| Ego depletion and psychology replication debates | 0.95: Canonical replication dispute (Hagger 2016 RRR vs the original depletion literature). | 0.9: Psychology readers; new audience. | 0.1: Low advice risk. |
| Social media and adolescent mental health | 0.95: Openly contested (Twenge/Haidt vs Orben/Przybylski; effect-size and specification debates). | 0.9: Parents, educators, policy readers; new audience. | 0.6: Parents may read results as advice about their children; needs a not-advice note. |
| Deep reinforcement learning: evaluation and reproducibility | 0.70: Henderson 2018 and Agarwal 2021 dispute evaluation practice; many results fail to reproduce. | 0.3: ML readers; overlaps LLM calibration and ML fairness. | 0.0: No advice risk. |
| Minimum wage and employment | 0.95: Classic economics dispute (Card-Krueger vs Neumark-Wascher; Seattle studies disagree). | 1.0: Economics and policy readers; new audience. | 0.2: Policy, not personal advice. |
| Empirical software engineering (defect prediction) | 0.60: Disputes over metrics and datasets (Shepperd 2014 researcher bias vs replies). | 0.5: Software engineers; partial overlap with ML readers. | 0.0: No advice risk. |
| Nudges and choice architecture: do they work? | 0.90: Mertens 2022 meta-analysis vs Maier 2022 (no evidence after bias correction). | 0.9: Behavioural-science and policy readers; new audience. | 0.2: Low advice risk. |
| Vitamin D supplementation and health outcomes | 0.85: Observational benefit vs null large trials (VITAL, D-Health). | 0.5: Health readers; partial overlap with Diet. | 0.9: Supplement advice risk is high. |
| Stereotype threat | 0.85: Meta-analyses disagree on whether the effect survives publication-bias correction. | 0.9: Psychology and education readers; new audience. | 0.2: Low advice risk. |

## Decision

**Build now:**

1. **Nudges and choice architecture** (0.677). It has a sharp published dispute: a large meta-analysis finding medium effects (Mertens et al. 2022) against a re-analysis finding no evidence after publication-bias correction (Maier et al. 2022). It has new readers (behavioural science, policy) and low advice risk. Full text: 28 % of probed papers.
2. **Social media and adolescent mental health** (0.676). It is the most contested candidate, both by reputation (Twenge and Haidt against Orben and Przybylski) and by the predictor (0.83). It reaches parents, educators and policy readers. Its advice risk is the highest of the chosen five, so the library carries a prominent not-advice note that points to real help.

**Queued** (built by the weekly workflow when money allows; prepared now):

3. **Ego depletion** (0.668): the canonical replication dispute. Full text is low (12 %).
4. **Minimum wage and employment** (0.663): a classic economics dispute with an entirely new audience. Full text is low (16 %).
5. **Growth-mindset interventions** (0.646): large trials and meta-analyses disagree.

**Not chosen:**

- **Deep RL reproducibility** has the best full-text coverage (60 %) but overlaps the existing ML libraries' readers.
- **Microplastics** has a predictor score of 1.00, but the field is younger and its disputes are mostly about measurement.
- **Vitamin D, intermittent fasting and coffee** carry high advice risk and overlap Diet.
- **Stereotype threat** has almost no open full text (4 %).
- **Empirical software engineering** has a small field and little open full text.

## What happened next (2026-10-09)

**Blind self-audits.** I labelled 15 papers per domain from titles and abstracts only, with the rubric's labels hidden. A rubric passes at 80 % in-or-out agreement, with one fix allowed.

| domain | first audit | after the one fix | result |
|:--|--:|--:|:--|
| Nudges | 87 % (rubric fixed once before auditing, after inspecting the first pre-label) | — | ready |
| Social media & teens | 87 % | — | ready |
| Ego depletion | 67 % | 87 % | queued |
| Growth mindset | 67 % | 87 % | queued |
| Minimum wage | 60 % | 67 % | **not ready** |
| Deep-RL evaluation (added when minimum wage failed) | 53 % | 67 % | **not ready** |
| Microplastics (added when deep RL failed) | 60 % | 67 % | **not ready** |

The failures share one cause. The shared rubric code keeps a paper as borderline when it has only an outcome term, or when anchor and topic words appear far apart. In broad fields such as labour economics, reinforcement learning and environmental science, that admits many papers about the general field rather than the question. Fixing it needs a change to the shared rubric code or a human-written rubric, so these three wait for the owner (`data/library_registry.json`, status `not-ready`).

**Money.** Social media & teens was built in full: extraction ₹128.32, claim embeddings ₹2.05, disagreement check ₹25.24, plus the future-work matcher and lead confirmation. That left too little of the run's ₹320 for all of Nudges: its extraction alone projects ₹181 with the ×1.5 padding. Following the rule "build the first library completely before starting the second", Nudges stays **queued**, prepared down to its full text. The weekly workflow builds it as soon as the money rule says it is affordable.

**Social media & teens, disagreement check.** 179 closely similar claim pairs were compared, and 6 were flagged. Hand-checked against the abstracts: 2 genuine, 3 artifact, 1 duplicate. The two genuine pairs:

- whether smartphone-era screen use meaningfully lowered adolescents' well-being (Twenge et al. 2018 vs Odgers & Jensen 2020);
- whether the rise in depression across birth cohorts is real or an artifact of recall (1989 cohort studies vs Costello et al. 2006).

## Limits of this choice

- **Reputation, audience and advice risk are one person's judgement**, written down so they can be argued with.
- **The full-text probe uses the 25 most-cited papers.** A library's final mix (two-hop snowball, newer papers) will differ.
- **Full-text rates of 12–28 %** mean most papers in the new libraries will be read from the abstract only. That limits how many stated limitations and next steps can be found. Each library says so on its pages.
