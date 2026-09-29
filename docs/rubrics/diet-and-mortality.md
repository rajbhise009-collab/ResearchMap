# Labelling rubric — diet-and-mortality

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for a biomedical/epidemiology domain where
"mortality" and "diet" appear across a wide range of tangential fields.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's primary
  contribution is ABOUT the relationship between diet — a food group,
  nutrient, dietary pattern, or dietary intervention — and mortality
  or a major disease-mortality outcome (cardiovascular disease, cancer,
  type 2 diabetes, all-cause mortality). Proposing a hypothesis,
  measuring an association, running an RCT, synthesising a meta-
  analysis, or arguing about methodology are all on-domain contribution
  shapes.

- **borderline** (`domain_centrality = peripheral`, KEPT): diet-and-
  mortality is a substantial component but not the primary contribution.
  Examples: a general cohort description paper whose findings include a
  diet-mortality association among many outcomes; a broad review of
  chronic disease that has a diet section; a methods paper on Cox
  models whose worked example is a diet-mortality study.

- **off-domain**: diet or mortality is mentioned, used as a tool, or
  appears within another task whose contribution lies elsewhere.
  Examples: a food-chemistry paper on flavonoid stability that
  mentions cardiovascular health in the intro; a genome-wide
  association study that happens to control for diet; an oncology
  trial whose primary outcome is tumour response, not mortality.

## Corpus policy

Borderline is KEPT, not dropped, and tagged `peripheral`. Same reasoning
as `docs/labelling-rubric.md`: the persistent-limitations scorer counts
independent papers reporting the same limitation, and a borderline paper
that reports "residual confounding by physical activity" is genuine
independent evidence — dropping it would delete the signal.

No-signal → EXCLUDE by default (the corrected 2026-07-29 rubric). A
paper with no positive on-domain signal from any of the anchor + topic
co-occurrence, strong-term match, venue allowlist, or field allowlist
is off-domain until proven otherwise.

## What counts as an on-domain signal

**Strong terms alone** (high-precision — the paper is almost certainly
about the relationship):

- "all-cause mortality" paired with any dietary component in the same
  document
- "dietary pattern" + outcome noun
- Nameable diet regimes: "mediterranean diet", "dash diet",
  "plant-based diet", "vegetarian diet", "vegan diet",
  "ketogenic diet", "low-carbohydrate diet", "low-fat diet",
  "high-protein diet"
- Nameable food groups against mortality: "red meat", "processed meat",
  "ultra-processed food", "sugar-sweetened beverage", "trans fat",
  "saturated fat", "whole grain", "fibre intake" / "fiber intake",
  "sodium intake", "alcohol consumption"
- "dietary intervention", "nutritional intervention"

**Anchor + topic co-occurrence** within 30 tokens in the abstract, or
within 12 tokens in the title:

- Anchors (the diet noun): `diet`, `dietary`, `nutrition`,
  `nutritional`, `food intake`
- Topics (the outcome noun): `mortality`, `death`, `all-cause`,
  `cardiovascular disease`, `coronary heart disease`, `stroke`,
  `cancer incidence`, `type 2 diabetes`, `metabolic syndrome`,
  `hypertension`

**Venue allowlist** (the paper appearing here is prima-facie on-domain
when it uses any diet terminology at all):

- American Journal of Clinical Nutrition
- The Journal of Nutrition
- Nutrients
- European Journal of Clinical Nutrition
- BMJ / British Medical Journal
- The Lancet / Lancet Public Health / Lancet Diabetes & Endocrinology
- New England Journal of Medicine
- JAMA / JAMA Internal Medicine / JAMA Network Open
- Circulation / Circulation Research
- American Journal of Epidemiology
- International Journal of Epidemiology
- Epidemiology
- European Heart Journal
- Diabetes Care
- Public Health Nutrition

## What counts as off-domain

**Venue denylist** — the paper's home suggests the diet-mortality
mention is incidental, not the contribution:

- Journals of chemistry, materials, and physics (all)
- Food Chemistry, Journal of Agricultural and Food Chemistry
  (food science / composition, not health outcomes)
- Journal of Food Science, LWT — Food Science and Technology
- Analytical Chemistry
- Computer Science / AI conferences (NeurIPS, ICML, etc.)
- Geoscience, Earth Sciences journals
- Veterinary journals

**Primary field denylist** (unless a title-level rescue fires — same
mechanism as LLM-calibration's failure-mode-3 guard):

- Chemistry
- Materials Science
- Physics and Astronomy
- Earth and Planetary Sciences
- Computer Science
- Chemical Engineering
- Energy
- Engineering

## Named failure modes worth watching

The heuristic will get these wrong until an audit corrects them:

1. **Food-chemistry co-mention.** A paper on antioxidant stability in
   olives that says "olive-oil consumption is associated with reduced
   cardiovascular mortality" in the intro is off-domain — its
   contribution is chemistry. The venue denylist should catch most; the
   audit sample should include one to check.
2. **Nutrition-and-not-mortality.** A paper measuring dietary intake
   patterns in a population (with no health outcome) is off-domain by
   this rubric's contribution definition, even though "dietary pattern"
   is a strong term. If it appears the strong-term rule is too loose
   and needs the outcome co-occurrence check.
3. **Mortality without diet.** A trauma-mortality paper mentioning a
   dietary confounder is off-domain. Anchor+topic co-occurrence
   discipline handles this.
4. **Animal / cell studies.** In-vivo (non-human) diet studies that
   claim mortality reduction in mice are off-domain — the rubric is
   for the human diet-mortality literature. Requires a `human` /
   `adult` cohort marker or the audit should flag.
5. **Genetic / metabolomic co-mention.** GWAS or metabolomics papers
   that adjust for diet are off-domain unless their primary contribution
   is the diet-mortality link.

The audit sample deliberately includes at least three cases from these
failure modes, marked `hard=true`, so the rubric's borders are exposed
in the sample rather than hidden.

## What is NOT on-domain

- Papers where "diet" means fed diet in animal nutrition experiments
  (unless directly tested for human relevance).
- Micro-nutrient (vitamin/mineral) supplementation studies whose
  primary outcome is a biomarker, not disease or mortality.
- Weight-loss RCTs whose primary outcome is weight change, not
  cardiovascular or cancer mortality (weight is a proxy; disease
  outcomes are the domain).
- Sports-nutrition studies (performance outcomes, not disease).
- Eating-disorder clinical papers (mental-health outcomes, not
  diet-mortality).

## Why this rubric matters for the reasoning engine

The whole point of building this library is to test the contradiction
scorer, which produced zero confirmed contradictions on LLM-calibration
(a coherent field). Diet-and-mortality is reputationally the field
where meta-analyses reach opposite conclusions on the same food group
(red meat, saturated fat, alcohol, coffee, low-carb). If the rubric
lets in too much off-topic material, the contradiction scorer will
either miss real disagreements (buried in noise) or flag many false
positives (papers that disagree because they're about different things,
not because they contradict). Both wreck the test.
