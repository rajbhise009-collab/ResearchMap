# Labelling rubric — nudge-effectiveness

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for nudges and choice architecture, where "default", "nudge" and "choice" appear across physics (the nudged elastic band method), computing (software defaults), marketing and medicine.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's contribution is ABOUT whether a nudge or choice-architecture intervention changes behaviour: a field experiment or trial of a default, reminder, social-norm message, simplification or commitment device; a meta-analysis or re-analysis of nudge effects; a replication; or an argument about publication bias, heterogeneity or welfare effects of nudges.

- **borderline** (`domain_centrality = peripheral`, KEPT): the subject is a
  substantial component but not the contribution. Examples: a behaviour-change trial whose intervention is partly a nudge (a reminder alongside financial incentives); a review of behavioural public policy with a nudge chapter; a theory paper on choice architecture with only illustrative evidence.

- **off-domain**: the words appear but the contribution lies elsewhere.
  Examples: "nudge" in another sense (molecular dynamics, robotics, a 'nudge' to an algorithm); a marketing study of product defaults with no behaviour-change question; a medical paper that mentions 'default settings' of a device.

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
fixed once if it does not. Result: `data/domains/nudge-effectiveness/audit_result.json`.
