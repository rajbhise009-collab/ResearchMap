# Labelling rubric — growth-mindset

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for growth-mindset interventions, where "mindset" is common in business, health and popular writing.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's contribution is ABOUT implicit theories of intelligence or ability (growth versus fixed mindset) and their relation to learning, achievement or motivation: mindset interventions and their trials, meta-analyses of mindset effects, replications, or arguments about heterogeneity and effect sizes.

- **borderline** (`domain_centrality = peripheral`, KEPT): the subject is a
  substantial component but not the contribution. Examples: studies where mindset is one of several motivational measures; mindset in sport or health with an achievement outcome; teacher-mindset studies.

- **off-domain**: the words appear but the contribution lies elsewhere.
  Examples: "entrepreneurial", "clinical" or "design" mindset; popular-press style papers using 'mindset' to mean attitude; studies of beliefs unrelated to ability.

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
fixed once if it does not. Result: `data/domains/growth-mindset/audit_result.json`.
