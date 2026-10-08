# Labelling rubric — ego-depletion

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for ego depletion and the strength model of self-control, where "self-control" and "depletion" appear across clinical, ecological and resource-management research.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's contribution is ABOUT whether exerting self-control depletes a limited resource and impairs later self-control: depletion experiments, registered replications, meta-analyses and re-analyses of the depletion effect, glucose and motivation accounts, or arguments about the strength model.

- **borderline** (`domain_centrality = peripheral`, KEPT): the subject is a
  substantial component but not the contribution. Examples: self-control or self-regulation studies that test depletion as one condition among several; reviews of self-regulation with a depletion section.

- **off-domain**: the words appear but the contribution lies elsewhere.
  Examples: "resource depletion" in ecology or economics; ozone or nutrient depletion; self-control studies (e.g. trait self-control and grades) that never manipulate or measure depletion.

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
fixed once if it does not. Result: `data/domains/ego-depletion/audit_result.json`.
