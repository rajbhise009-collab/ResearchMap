# Labelling rubric — social-media-teen-mental-health

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for social media and adolescent mental health, where "social media", "screen time" and "mental health" each appear in thousands of papers that are not about whether young people's technology use relates to their mental health.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's contribution is ABOUT the relation between adolescents' or young people's social-media, smartphone or screen use and their mental health or well-being (depression, anxiety, self-harm, loneliness, life satisfaction): cohort or cross-sectional association studies, experiments that reduce use, specification-curve or meta-analytic work on effect sizes, or arguments about causality and measurement.

- **borderline** (`domain_centrality = peripheral`, KEPT): the subject is a
  substantial component but not the contribution. Examples: studies of adults or of all ages with an adolescent subgroup; studies of cyberbullying or problematic internet use where social media is one channel; mental-health service studies delivered through apps.

- **off-domain**: the words appear but the contribution lies elsewhere.
  Examples: papers that use social media as a data source (sentiment analysis, recruiting participants); screen-time studies of infants' language development; mental-health papers that mention social media only as background.

## How the code applies it

`backend/app/corpus/domains_2026_10.py`. A paper is on-domain only when the
exposure or intervention (strong terms) AND the outcome it is studied against
(pair terms) both appear in the title, or in the same sentence of the
abstract. A paper that names one side only stays borderline or off. Venue
and field lists rescue or veto at the edges. No positive signal means
excluded by default.

## Corpus policy

Borderline is kept and tagged `peripheral`, as in the base rubric: a
peripheral paper reporting the same limitation is independent evidence.

## Check

A blind self-audit of 15 papers (titles and abstracts only, labels hidden)
must agree with the rubric on in-or-out for at least 80 %; the rubric is
fixed once if it does not. Result: `data/domains/social-media-teen-mental-health/audit_result.json`.
