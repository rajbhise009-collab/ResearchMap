# Labelling rubric

Discriminator: contribution, not vocabulary.

- **on-domain**: the paper's primary contribution is ABOUT calibration,
  uncertainty expression, abstention, selective prediction, or
  hallucination detection in language models — proposing, measuring,
  analyzing, or benchmarking the property as its main object.
- **borderline**: the property is a substantial component but not the
  contribution (a general benchmark with a calibration section; a
  model report with a calibration subsection).
- **off-domain**: the property is mentioned, used as a tool, or appears
  within another task whose contribution lies elsewhere (a medical
  summarization system that mentions hallucination).

Corpus policy: borderline papers are KEPT, not dropped, and tagged
with a `domain_centrality` tier (`core` / `peripheral`). Rationale:
the persistent-limitations scorer counts independent papers reporting
the same limitation, and an application paper reporting a limitation
is genuine independent evidence. Dropping them would delete the
signal that scorer exists to find. Weighting by centrality is a
decision we can measure; exclusion is a guess.
