# Labelling rubric — minimum-wage

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for minimum wage and employment, where "wage", "employment" and "labour market" cover most of labour economics.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's contribution is ABOUT the effect of a minimum wage (or living wage, wage floor) on employment, hours, earnings, prices or the wage distribution: natural experiments, border-county or bunching designs, meta-analyses of the employment elasticity, or arguments over methods and comparison groups.

- **borderline** (`domain_centrality = peripheral`, KEPT): the subject is a
  substantial component but not the contribution. Examples: studies of minimum-wage effects on health, crime or prices where employment is a secondary outcome; general labour-market models with a minimum-wage application.

- **off-domain**: the words appear but the contribution lies elsewhere.
  Examples: papers mentioning the minimum wage only as background or as a parameter; studies of wages in general (collective bargaining, the gender gap) with no minimum-wage question.

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
fixed once if it does not. Result: `data/domains/minimum-wage/audit_result.json`.
