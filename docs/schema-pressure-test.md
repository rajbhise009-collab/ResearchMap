# Schema pressure-test

Aggregate findings from a hand-review of 60 randomly-sampled abstracts
against four extraction-schema hypotheses. Reviewer: me, offline, no
LLM calls. Sample size and inference limits: 56 with abstracts + 4
without, drawn deterministically (`RNG_SEED=20260723`) from a 200-paper
OpenAlex pull under the v3 query. The population is on-topic-adjacent
LLM papers post-`primary_topic.subfield.id:1702` filter, so treat every
number as a within-that-slice estimate, not as a corpus-wide constant.

## Findings

### 1. Do abstracts state a limitation? — 71.4% yes, but **only 21.7% are usable evidence**

Revised finding (this section supersedes the original 71.4% headline).

Second-pass classification of the 40 "has_limitation=yes" papers into
scope — own-work, prior-work, or both. The result:

| Scope | Count | Share of 60 |
|:------|------:|------------:|
| own (paper's method or its own subject-finding) | 10 | 16.7% |
| both (own + prior-work) | 3 | 5.0% |
| prior-work only (motivational citation) | 27 | 45.0% |
| none (has_limitation=no) | 16 | 26.7% |
| unknown (no abstract) | 4 | 6.7% |

**Only own-work and both entries are usable evidence for the
persistent-limitations scorer.** Prior-work limitations stated as
motivation ("existing methods X have problem Y, so we propose Z")
almost never name the specific prior work in the abstract; without
that attribution, the extractor cannot honestly point the limitation
back to the paper it belongs to. Emitting them as limitations of the
citing paper is the prior-work-limitation-misattribution failure
mode already listed in `docs/opportunity-criteria.md`.

**Own + both = 13/60 = 21.7%.** That is **well below the ~50%
threshold** at which the scorer can operate on abstract-only
extraction and produce meaningful signal.

**Revised conclusion: OA full text is a PREREQUISITE for the
persistent-limitations scorer, not a lift.** Abstracts alone give
about 22% of papers a limitation the scorer can honestly count.
Ranking research opportunities on 22% coverage is dominated by
noise. This flips schema decision #4 below.

Cross-tab (own + both, over 56 with abstracts):

| Bucket | usable | share |
|:-------|-------:|------:|
| on-domain (n=26)  | 8 | 30.8% |
| borderline (n=9)  | 3 | 33.3% |
| off-domain (n=21) | 2 |  9.5% |

Even in the on-domain bucket only 31% of papers give the scorer
usable evidence from the abstract — the abstract is the wrong
extraction target for this specific field.

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

3. **Do NOT add `Claim.assertion_strength` as a separate field —
   FOR THIS CORPUS.** Reason: 91% of claims read as firm; the field
   would have negligible discriminative power. If a future scorer
   wants hedge information, it can compute it from the claim text
   with a cheap linguistic check, no schema needed.
   Migration cost: **zero.** This is a conditional rejection.

   **Domain-conditional.** ML abstracts are unusually assertive;
   biomedical, BCI, clinical trial, and psychology literatures hedge
   far more (routine "may", "suggest", "our data are consistent
   with", "further work is needed" phrasings dominate). Before
   ResearchMap is pointed at a new field, re-run this pressure-
   test's `claim_hedged` classification on a fresh 50-abstract
   sample from that field, and re-open decision #3 if the firm rate
   drops below ~70%.

### Reclassified — required, given the revised finding #1

4. **OA full text is a PREREQUISITE for the persistent-limitations
   scorer.** This decision was originally "deferred to Phase 1.5,
   run abstracts first, accept 40% future-work coverage". After
   splitting the limitation labels by scope (see finding #1),
   abstract-only extraction gives the scorer usable evidence on
   only 22% of papers. That is too low to feed the scorer honestly
   — most of what looks like a limitation from an abstract is a
   prior-work citation the extractor cannot attribute.

   OA-full-text ingestion is now on the critical path for the
   scorer to function, not a quality lift. Concretely:

   - New literature sources: arXiv PDF fetch (very high coverage
     for this domain — see finding #5 below), Europe PMC, PubMed
     Central. All exist as OA endpoints; the pattern is the same as
     OpenAlex + Semantic Scholar.
   - Storage: `Paper.fulltext` already exists in the schema; SQL
     column already there. Just needs populating.
   - Parsing: PDF → text (grobid or similar; ~1 dependency).
   - Section detection: isolate future-work paragraphs and
     limitations paragraphs from methodology sections using heading
     heuristics ("Future Work", "Conclusion", "Discussion",
     "Limitations", "Threats to Validity").

   Recommendation: **land OA full-text ingestion before Phase 4
   reasoning goes live.** It is safe to run Phase 2 (extraction)
   on abstracts first as a smoke test of the pipeline — that gives
   us end-to-end validation of prompts, cache, retry, persistence
   — but the Phase 4 output on abstract-only extractions is
   guaranteed to be dominated by noise, so do not ship the reasoning
   engine on abstract-only data.

## What I would do next

- Land decisions #1 (`source_scope`) and #2 (compound splitting rule)
  as a small schema patch before Phase 2 extraction starts. Both are
  cheap; both are strictly required to avoid known-broken scoring.
- Record decision #3 (assertion strength) as **domain-conditional**
  in the same schema doc — rejected for this corpus, not permanently.
- **Land decision #4 (OA full-text ingestion) before Phase 4.**
  Revised from the original defer-until-Phase-1.5 posture. Phase 2 on
  abstracts is fine for pipeline validation; the reasoning engine
  cannot honestly ship on 22% limitation-evidence coverage.

## Population caveat

56 is a small n. The 91% firm and 59% compound rates in particular
are point estimates with wide binomial confidence intervals; expect
them to move by ±5–10 points on a larger sample. The DIRECTION of
each finding (firm dominant, compound common, future-work sparse,
limitations dense) is robust; the exact percentages are not.
