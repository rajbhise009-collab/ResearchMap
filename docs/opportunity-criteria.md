<!-- Filled in by Raj — not auto-generated. This is the project's core hypothesis document. -->

## What makes an opportunity valid (minimum evidence bar)

## What makes an opportunity non-trivial

## What makes an opportunity actionable

## Named failure modes

- Terminology collision across fields: two papers using the same term
  with different meanings (e.g. "calibration" in NLP vs. in materials
  science) being detected as a scientific contradiction. A
  contradiction is only valid if both claims concern the same
  construct, not merely the same word. Corpus contamination makes
  this failure mode more likely, so corpus purity is a precondition
  for contradiction scoring, not a nice-to-have.
- Duplicate or near-duplicate papers (preprint + published version,
  or the same work across venues) counted as independent sources,
  inflating replication counts and any score that depends on the
  number of independent papers reporting a finding.
- Within-domain application noise: a paper that uses the domain
  vocabulary correctly but whose contribution lies in another task
  (e.g. medical summarization mentioning hallucination). These are
  not terminology collisions — the terms mean the same thing — but
  the paper is evidence about the application, not the property.
  Keyword filtering cannot separate these; only contribution-level
  judgment can.

## Matching rule for retrospective validation
