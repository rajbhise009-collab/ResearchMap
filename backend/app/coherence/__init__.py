"""Domain-coherence pre-flight predictor.

Answers a single question, using ONLY free OpenAlex metadata: given a
candidate research domain, how likely are the reasoning engine's scorers
(contradictions, structural holes, persistent limitations, orphaned
future-work) to find signal in it?

This is a *hypothesis*, not a validated model. We have one domain with
ground-truth yield measurements (LLM calibration/uncertainty — near-zero
contradictions, some structural holes) so n=1 for prediction accuracy.
What the predictor CAN do honestly:

  1. Compute reproducible features that plausibly proxy "how contested
     and mature is this field."
  2. Rank candidate domains against each other by those features.
  3. Show whether our own corpus scores as its measured yield would
     predict.

What it CANNOT do:
  - Predict actual yield in dollars or gap counts. That needs the
    validation loop documented in the finding.

All computation runs on cached OpenAlex JSON — the fetch script is
budgeted at ~1 credit per domain (via free `filter=` list calls) and
caches everything under data/coherence/{domain-slug}/.
"""
