# Schema pressure-test

Aggregate findings from a hand-review of 60 randomly-sampled abstracts
against four extraction-schema hypotheses. Reviewer: me, offline, no
LLM calls. Sample size and inference limits: 56 with abstracts + 4
without, drawn deterministically (`RNG_SEED=20260723`) from a 200-paper
OpenAlex pull under the v3 query. The population is on-topic-adjacent
LLM papers post-`primary_topic.subfield.id:1702` filter, so treat every
number as a within-that-slice estimate, not as a corpus-wide constant.

## Findings

### 1. Do abstracts state a limitation? — **71.4% yes** (40/56)

Higher than expected. Enough that **abstract-only extraction WILL feed
the persistent-limitations scorer** at meaningful volume. OA full text
is NOT a hard requirement for the scorer to run; it would raise
recall, not enable the function.

Caveat: my "yes" marker did not distinguish limitations OF the paper's
own work from limitations OF prior work stated as motivation
("existing methods have X problem, so we…"). Both are common in
abstracts. If we count them the same, we'll double-attribute:
Paper A cites Paper B's limitation → the extractor emits it as a
limitation OF Paper A. See schema decision #1 below.

Cross-tab by on-domain bucket (over 56 with abstracts):

| Bucket | has_limitation=yes | share |
|:-------|-------------------:|------:|
| on-domain (n=26)  | 20 | 76.9% |
| borderline (n=9)  |  8 | 88.9% |
| off-domain (n=21) | 12 | 57.1% |

On-domain and borderline papers are more limitation-dense than
off-domain — which makes sense because our target literature (UQ,
hallucination detection) is fundamentally about known failures, so
its abstracts open with motivational limitations of prior work.

### 2. Firm vs. hedged claims — **91.1% firm** (51/56)

Dominant. Only 4 hedged and 1 mixed in the whole sample. **Assertion
strength does NOT need to be a separate field on `Claim`.** With 91%
firm, a per-claim strength enum would concentrate almost all its mass
on a single value; the variance isn't there to feed downstream
ranking. See schema decision #3.

That means `Claim.confidence` is free to carry ONE thing: the
extractor's confidence that the extracted text faithfully represents
what the paper says. That is a much cleaner semantic. Downstream
scorers that want "how strongly is the claim asserted?" can look at
the surface text (linguistic hedges like "may", "suggest",
"tentatively") when they need to, without a redundant schema field.

### 3. Future-work explicitness — **41.1% present** (23/56)

Explicit: 12.5% (7/56). Implied: 28.6% (16/56). None: **58.9% (33/56).**

Majority of abstracts have NO future-work content. This is a real
recall problem for `FutureWork` extraction: **the scorer looking for
"unfollowed future-work threads" will miss ~60% of them if fed
abstracts only.** Future-work paragraphs live in the paper's discussion
/ conclusion, not the abstract. See schema decision #4.

### 4. Compound-claim sentences — **58.9% yes** (33/56)

Majority of abstracts contain at least one sentence carrying two or
more claims that need separate evidence. Common shapes:

- Finding lists in one sentence ("achieves state-of-the-art on X,
  reduces cost by Y%, and generalizes to Z").
- Motivation compounds ("existing methods are slow, brittle, AND
  overconfident").
- Contribution enumerations ("we propose 1) …, 2) …, and 3) …").

**The extraction prompt MUST split compound sentences into separate
`Claim` records with separate `Evidence` records.** If it doesn't,
the persistent-limitations scorer (and any support/contradict scorer)
gets its evidence granularity wrong — two claims sharing one evidence
row would double-weight the shared evidence. See schema decision #2.

## Decision list — schema changes

These are the changes I recommend, sorted by whether they're required
for extraction to serve the reasoning engine at all versus optional
quality lifts.

### Required before Phase 2 extraction goes live

1. **Add `Limitation.source_scope` field.**
   Values: `"this_work"` | `"prior_work"`. Default `"this_work"`.
   Rationale: 71% of abstracts state some limitation, but a large
   fraction of those are prior-work limitations stated as motivation.
   Without this field, the persistent-limitations scorer will
   double-attribute Paper A's cited limitation as a limitation OF
   Paper A.
   Migration cost: **cheap.** Pydantic add + one SQL migration
   (nullable text column with default). Extractor prompt needs a
   short "distinguish motivating limitations from stated limitations
   of THIS work" instruction — one paragraph in the prompt.

2. **Formalize the compound-claim splitting rule in the extractor
   contract.**
   Not a schema field per se — a prompt-level contract that
   `PaperExtraction.claims` must contain one entry per atomic
   assertion, never a compound sentence. Optional supporting field:
   `Claim.source_sentence_id` (nullable str) so a later analysis can
   see which claims came from the same source sentence.
   Migration cost: **cheap.** Nullable field. The bigger cost is
   prompt-engineering the splitter to be reliable — that's Phase 2
   work, not a schema question.

### Recommended, non-blocking

3. **Do NOT add `Claim.assertion_strength` as a separate field.**
   Reason: 91% of claims read as firm; the field would have negligible
   discriminative power. If a future scorer wants hedge information,
   it can compute it from the claim text with a cheap linguistic
   check, no schema needed.
   Migration cost: **zero.** This is a rejection.

4. **`FutureWork` extraction from abstracts is a coverage floor, not a
   ceiling.** For Phase 2 extraction on the small-sample corpus, run
   the extractor on abstracts and accept ~40% future-work coverage.
   For the reasoning engine to genuinely surface unfollowed-future-
   work threads, we will eventually need OA full text (arXiv PDF,
   Europe PMC, publisher OA).
   Migration cost: **larger.** OA full-text ingestion means:
   - New literature sources: arXiv PDF fetch, Europe PMC, PubMed
     Central. All exist as OA endpoints; the pattern is the same as
     OpenAlex + Semantic Scholar.
   - Storage: `Paper.fulltext` already exists in the schema; SQL
     column already there. Just needs populating.
   - Parsing: PDF → text (grobid or similar; ~1 dependency).
   - Section detection: to isolate future-work paragraphs from
     methodology paragraphs, use section-heading heuristics ("Future
     Work", "Conclusion", "Discussion").
   Recommendation: **defer to Phase 1.5, after Phase 2 has proven the
   extraction pipeline works on abstracts.** Do not build OA
   ingestion speculatively.

## What I would do next

- Land decisions #1 (`source_scope`) and #2 (compound splitting rule)
  as a small schema patch before Phase 2 extraction starts. Both are
  cheap; both are strictly required to avoid known-broken scoring.
- Explicitly park decision #3 (assertion strength) — write a one-line
  "considered and rejected because 91% of the corpus is firm" note in
  `docs/merge-policy.md` next to `Claim` policy, so a future reader
  doesn't re-open the question.
- Park decision #4 (OA full text). Note it in `PROGRESS.md` as a
  Phase 1.5 candidate contingent on Phase 2 showing that abstract-only
  future-work coverage is a bottleneck.

## Population caveat

56 is a small n. The 91% firm and 59% compound rates in particular
are point estimates with wide binomial confidence intervals; expect
them to move by ±5–10 points on a larger sample. The DIRECTION of
each finding (firm dominant, compound common, future-work sparse,
limitations dense) is robust; the exact percentages are not.
