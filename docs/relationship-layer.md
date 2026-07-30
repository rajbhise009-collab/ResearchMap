# Relationship layer (Phase 3) — design & decisions

Deterministic cross-paper relationship layer over the 200-paper corpus.
The LLM boundary is the whole point of this phase, so it is stated first.

## The LLM boundary

**LLMs perceive; code reasons.** In this layer an LLM does exactly one
thing: classify a SINGLE claim pair — "contradicts / supports / none" plus
a one-sentence explanation. That is perception of a relationship, the same
class of task as extraction. Everything numeric is deterministic Python:

- **Shortlisting** (which pairs to even look at) is cosine similarity —
  `relationships/shortlist.py`, pure numpy.
- **Weighting** is `relationships/weighting.py`: `weight = similarity ×
  fidelity_factor`, clamped. No LLM number enters it, and — per
  `docs/confidence-policy.md` — `Claim.confidence` is deliberately NOT an
  input.
- **Future-work matching** and the **citation graph** are cosine + a year
  filter + OpenAlex reference data. No LLM.

If a function reads a claim and returns a number, it is code. The pairwise
classifier never ranks, weights, or scores.

## Combinatorial budget

~1,022 claims ⇒ ~522k naive pairs. All-pairs LLM comparison is forbidden.
Embeddings (cheap) do the pre-selection; only pairs above a similarity
threshold, capped per claim, reach the LLM.

Config-driven knobs (`backend/app/config.py`):

| knob | default | meaning |
|:--|:--|:--|
| `REL_SIMILARITY_THRESHOLD` | 0.78 | min cosine for a candidate pair |
| `REL_MAX_CANDIDATES_PER_CLAIM` | 10 | top-k neighbours kept per claim |
| `REL_CROSS_PAPER_ONLY` | true | a paper cannot contradict itself |
| `REL_FUTUREWORK_MATCH_THRESHOLD` | 0.80 | future-work "addressed" cosine |

### Threshold calibration (measured on this corpus)

| threshold | candidate pairs |
|--:|--:|
| 0.70 | 4874 |
| 0.74 | 1954 |
| **0.78** | **437** |
| 0.80 | 208 |
| 0.82 | 99 |
| 0.85 | 35 |

Inspection showed pairs above ~0.9 are near-duplicate restatements (which
the LLM labels *supports*), while genuine same-construct / opposite-
conclusion pairs sit lower — so a high threshold sacrifices contradiction
recall. 0.78 gives ~440 candidates (~$0.16 batch), well under the $3
gate. The shortlist optimizes recall; the pairwise LLM provides precision.
Raising the threshold cuts cost and recall; lowering it does the reverse.
Every run prints the candidate count and a projected cost, and stops if
the projection exceeds **$3**.

### Recall probe — what it validates, and what it does NOT

A 24-pair labelled probe (`probe_recall.py`) measured the pairwise
CLASSIFIER: given a shortlisted pair, does it correctly call
contradicts / supports / none? Result — recall **10/10** on planted
contradictions, **0/14** false positives, supports 7/7, unrelated 7/7.
This is a real result about the classifier and it stands.

**Scope boundary — the probe validates the classifier, not the shortlist:**

- **Validated:** the pairwise classifier's precision/recall *once a pair
  reaches it*. The prompt is sound; it does not read similarity as
  agreement.
- **NOT validated:** whether the 0.78 cosine shortlist actually surfaces
  real cross-paper contradictions in the first place. The planted
  contradictions were constructed by NEGATING a source claim, so their
  high cosine (0.84–1.0) is a property of that construction (near-identical
  wording), **not** evidence that a contradiction written independently by
  two different papers scores above 0.78. **Shortlist recall on
  naturally-worded contradictions is UNMEASURED.**

Consequence: the 148:2 supports:contradicts ratio is a true property of
the corpus *as filtered by the 0.78 shortlist*. A genuine contradiction
phrased very differently across two papers could fall below 0.78 and never
reach the (accurate) classifier — the shortlist, not the classifier, would
be the bottleneck, and that possibility is currently untested.

**Paraphrase test (RUN, <$0.01, embeddings only).** The 10 planted
contradictions were paraphrased into different surface wording (contradiction
preserved, lexical overlap reduced), embedded, and scored against their
source claim: **9 of 10 still cleared 0.78** (range 0.755–0.933; one missed
at 0.755). So a reworded contradiction about the same specific finding
mostly stays above the shortlist — the shortlist is **likely not** the main
bottleneck for contradictions. Caveat: these paraphrases still share dataset
/ model / metric names with the source; two fully-independent papers could
share fewer surface tokens, so this is reassuring, not conclusive. (No
change proposed — reporting the number only.)

## Why file-backed (not live Postgres)

Embeddings and relationships are persisted to disk
(`data/relationships/`), serialized straight from the Pydantic/SQLAlchemy
models, with cosine shortlisting done in numpy. This is a
**scale-dependent** choice:

- At ~1k claims a full cosine matrix is ~4 MB and runs in milliseconds;
  pgvector's ANN indexes buy nothing at this size.
- Postgres becomes worthwhile at roughly **Phase 6** (the API serving
  live queries) or a corpus in the **tens of thousands of claims**,
  whichever comes first.

Guards against drift (the risk of a parallel file format rotting):

- The file records are `model.model_dump()` / `Model(**row)` — never a
  hand-written format. `ClaimEmbedding`/`ClaimRelationship` field sets
  **equal** their `ClaimEmbeddingRow`/`ClaimRelationshipRow` columns
  (asserted by `test_pydantic_fields_match_orm_columns`).
- `test_migration_ddl_matches_orm` parses migration `007` and asserts the
  DDL columns match the ORM — the file format, the ORM, and the deploy-time
  schema cannot silently diverge.
- The DATABASE_URL loader path (`RelationshipStore.write_to_db` /
  `load_relationships_from_db`) is proven by `test_database_url_path_...`
  on SQLite, so the normally-unused Postgres path does not rot before
  Phase 6.

The pgvector schema (migration `002` + `007`) is the canonical
representation; the same rows load into Postgres via `write_to_db` when a
DATABASE_URL is configured.

## Provenance

Every `ClaimRelationship` carries full provenance (migration 007): both
claim ids, both `*_paper_id`s, `detector_model`, `prompt_hash`, and the
`similarity` that shortlisted it — no orphan conclusions. Claim embeddings
record `input_source` (abstract | fulltext) so downstream scoring can
correct for mixed-fidelity bias.

## Future-work matching & the small-corpus guard

### Two-stage matcher (current) — cosine shortlist → LLM classification

Raw cosine cannot express the "addresses" relation (precision caps ~0.57
at any threshold, below). So future-work matching uses the SAME
architecture validated for contradictions: a wide, recall-first cosine
shortlist (0.70) feeds an LLM that classifies each (future-work,
later-paper) pair as `addressed` / `partial` / `not_addressed` with a
one-sentence justification and the specific addressing claim.
Classification only — the LLM never scores or ranks. Output persists as
`FutureWorkAddressal` rows (migration 008) with full provenance, mirroring
`ClaimRelationship`. Runner: `run_futurework_match.py` (dry-run gates the
LLM spend at **$1**, corrected thinking-token pricing).

**Re-measured against the same 40 hand-labelled band items:**

| matcher | precision | recall | F1 |
|:--|--:|--:|--:|
| (a) raw cosine ≥ 0.74 (old baseline) | 0.41 | 0.70 | 0.52 |
| (b) two-stage, LLM `addressed` only | 0.75 | 0.30 | 0.43 |
| **(b) two-stage, `addressed`+`partial`** | **0.64** | **0.90** | **0.75** |
| (c) two-stage + citation prior | see below | | |

**The two-stage matcher genuinely fixes the signal** (F1 0.52 → 0.75;
precision AND recall both rise) — it does not merely move the noise. The
`addressed`+`partial` reading is preferred for the orphan scorer: recall
0.90 means few real matches are missed, i.e. few false orphans (the costly
error).

**Citation prior (deterministic, free).** For each candidate we record
`cites_source` — whether the later paper cites the source paper (from the
343 intra-corpus citation edges). It is a code-computed feature, never fed
to the LLM to weight. Honest result: **on the 40 labelled items it could
not be evaluated — 0 of the 40 best-match pairs carry a citation edge**
(corpus-wide only 50 of 491 candidates do). So no improvement is
demonstrable on this labelled set; the prior is recorded for downstream use
but its value is currently unmeasured, not shown. Stated rather than
claimed.

**New distribution (n=312 future-work items), two-stage + guard:**

| addressed | partial | unaddressed | indeterminate |
|--:|--:|--:|--:|
| 26 | 34 | 134 (43%) | 118 (38%) |

`addressed`+`partial` (60, 19%) = engaged; `unaddressed` are corpus-relative
orphans (guard: ≥5 near-later papers, none addressing); `indeterminate` =
too few near-later papers to judge. The corpus-relative caveat below still
applies to every `unaddressed` item.

### Legacy: raw-cosine match threshold pinned by measurement (0.74)

*(Superseded by the two-stage matcher above; kept for the record.)*

The "addressed" count swung 13 → 59 → 172 across thresholds 0.80 → 0.75 →
0.70, so the threshold was pinned by hand-labelling, not chosen. 40
future-work items in the sensitive [0.70, 0.80) band (where matches flip)
were labelled in-session (does a later corpus paper actually address the
item?); precision/recall vs those labels:

| threshold | predicted+ | precision | recall | F1 |
|--:|--:|--:|--:|--:|
| 0.70 | 40 | 0.25 | 1.00 | 0.40 |
| 0.72 | 29 | 0.31 | 0.90 | 0.46 |
| **0.74** | 17 | **0.41** | **0.70** | **0.52** |
| 0.75 | 11 | 0.45 | 0.50 | 0.48 |
| 0.76 | 7 | 0.57 | 0.40 | 0.47 |
| 0.78 | 1 | 0.00 | 0.00 | 0.00 |

**0.74 is the F1 optimum and favours recall** — the right bias for an
orphan scorer, because a missed real match becomes a FALSE ORPHAN (the
costly error). The old 0.80 default called *zero* of the 40 band items
addressed, yet 10 of them (25%) genuinely were — i.e. 0.80 was manufacturing
orphans.

**But precision never exceeds ~0.57 at any threshold.** The
future-work↔claim embedding cosine is a genuinely weak signal: "we plan to
explore X" and "we did Y" embed by surface topic, not by the
addresses-relation. So even at the pinned 0.74, ~59% of "addressed" labels
are false-positive topical adjacencies. **The orphaned-future-work scorer
inherits this noise; Phase 4 must treat `addressed`/`unaddressed` as weak,
corpus-relative signals, never as facts about the field.** Worked examples
in `scratch/futurework_audit.md`.

The K (near-later count) and T (topical) guard knobs were NOT
independently pinned: the labelled set answers "did paper X address item
Y?", not the counterfactual "would the addressing work be in the corpus if
it existed?" that K/T govern. Calibrating them would need field-level
ground truth the corpus alone cannot provide — so their defaults (K=5,
T=0.65) remain reasoned, not measured, and are flagged as such.

### Orphan judgments are corpus-relative (never absolute)

**An "orphaned"/`unaddressed` future-work item is a statement about THIS
corpus, not about the field, and must always be reported with the coverage
caveat attached.** "No later paper addressed this" is only informative if
the corpus actually holds later papers that plausibly would have. The
criterion is therefore not "how many later papers exist" (that counts
unrelated work) but **how many later papers are on the same research
thread** — later papers with a claim whose cosine to the future-work item
is ≥ `REL_FUTUREWORK_TOPICAL_THRESHOLD` (0.65). Only when at least
`REL_FUTUREWORK_MIN_NEAR_LATER` (default 5) such papers exist AND none
matched is the item `unaddressed`; otherwise it is
`indeterminate_small_corpus`.

The earlier crude guard (any later papers ≥ 10) produced a non-credible
**91% orphan rate**. The topically-near criterion moves items the corpus
cannot actually judge into `indeterminate`; combined with the pinned 0.74
match threshold (n=312 future-work items):

| config | addressed | unaddressed | indeterminate | orphan-judgeable |
|:--|--:|--:|--:|--:|
| old guard (all later ≥ 10), match 0.80 | 13 | 284 (91%) | 15 (5%) | 95% |
| near-later ≥ 5 @ T=0.65, match 0.80 | 13 | 177 (57%) | 122 (39%) | 61% |
| **near-later ≥ 5 @ T=0.65, match 0.74 (current)** | **82** | **113 (36%)** | **117 (37%)** | **63%** |

Two corrections compound: the recalibrated guard moves un-judgeable items
to `indeterminate` (91%→37% orphan rate), and the pinned 0.74 match
threshold recovers genuine addresses the 0.80 default was mislabelling as
orphans (unaddressed 177→113). **~37% of items still cannot support an
orphan judgment at all** at n=200. Phase 4 must never surface an
`unaddressed` item as a finding without this caveat, and must treat
`indeterminate_small_corpus` items as unscoreable.
