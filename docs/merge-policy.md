# Merge policy

Formal specification of what `backend.app.ingestion.normalizer.deduplicate`
does when two records collapse. This is the source of truth; the code is
the runtime realisation.

Scope: this document governs merges for `Paper` today, and by explicit
forward-compat commitment (last section) it governs merges for
`Claim`, `Evidence`, `Methodology`, `Limitation`, `FutureWork`, and
`ClaimRelationship` when Phase 2 ingests them.

---

## Matching passes

Passes 1–4 are described in the `normalizer.py` module docstring (DOI;
title + year + shared author; cross-year title + shared author;
arXiv/non-arXiv DOI + title + shared author). Pass 5 was added on
2026-10-04 (owner decision, iteration 6):

### Pass 5 — title similarity

Catches a journal version that was retitled after its preprint, which
passes 1–4 miss because they need an identical DOI or normalized title.
All of these must hold:

| condition | value | constant |
|:--|:--|:--|
| same normalized first-author surname | — | — |
| years within | 2 | `TITLE_SIM_YEAR_WINDOW` |
| title-token Jaccard at least | 0.75 | `TITLE_SIM_JACCARD` |
| numeric title tokens identical | (e.g. edition years, version numbers) | — |
| both abstracts present, abstract-token Jaccard at least | 0.50 | `ABSTRACT_SIM_JACCARD` |

When several earlier records match, the lexically lowest id is taken.
`deduplicate(papers, title_similarity=False)` disables the pass;
`title_similarity_candidates()` is a report-only view that merges nothing.

**Why these thresholds** (sweep in `docs/findings/duplicate-check-v2.md`,
data in `data/duplicate_check_v2.json`). Over every same-first-author,
within-two-years pair in the three libraries plus every raw OpenAlex
record seen while building the two new ones, the only true duplicate
with distinct titles is AI Fairness 360 (title Jaccard 0.80, abstract
Jaccard 0.62). Title similarity alone cannot separate it safely: a
different-work pair by the same authors scores 0.78, and annual
editions of the same guideline chapter score up to 0.88. The two extra
guards remove every such negative in the sweep: the numeric-token rule
blocks the annual editions (whose abstracts can be identical), and the
abstract rule blocks the same-authors different-study pair (abstract
Jaccard 0.24). Requiring both abstracts means a pair with a missing
abstract is never merged by this pass. A false merge (two works counted
as one) is treated as worse than a missed duplicate, so anything the
rule does not clear is listed for a human, not merged.

---

## Survivor rule

Deterministic, order-independent. Given two records `a` and `b` matched
by any of the dedup passes, the survivor is chosen by comparing this
tuple lexicographically (higher wins):

| Tier | Field | Higher = wins | Rationale |
|-----:|-------|---------------|-----------|
| 1 | `is_pub_doi` | Non-arXiv DOI beats arXiv DOI beats no DOI. | Published version is canonical; arXiv DOIs (`10.48550/arxiv.*`) mark preprints. |
| 2 | `has_venue`  | Presence of a `venue` string. | A venue implies the record came through peer review. |
| 3 | `citations_in_count` | Higher wins. | Proxy for which version of the work the field actually cites. |
| **tie** | `id` | Lexically-lower `id`. | Deterministic tiebreak — never iteration-order-dependent. |

Implemented in `_survivor_key(p)` (tiers 1–3) and `_pick_survivor(a, b)`
(tiebreak). Both are pure functions; `_pick_survivor(a, b)` and
`_pick_survivor(b, a)` always return the same `(survivor, loser)` pair.

### Rejected alternatives

- **Source-of-record ranking** (OpenAlex > S2 > seed). Previously used
  as a tiebreak. Removed because it embedded a provider preference in
  a policy that should be decided by paper properties, not by which
  side of the pipeline saw the record first.
- **Prefer record with abstract**. Now handled by the fill-in policy
  below rather than by survivor selection — the abstract shouldn't
  decide *which* ID is canonical, only what content ends up on it.

---

## Field-level merge policy

For every field on `Paper`, the merge outcome is one of:

- **survivor-only** — survivor's value wins outright, loser's is dropped.
- **fill-in** — survivor's value wins if truthy; else loser's is used.
- **max** / **sum** / **union** / **or** — combining operator.

| Field | Policy | Notes |
|-------|--------|-------|
| `id` | survivor-only | Identity field. The merged record's `id` is the survivor's `id`. |
| `source` | survivor-only | Identity field. |
| `source_id` | survivor-only | Identity field. |
| `title` | survivor-only | Survivor is the canonical version; its title is canonical. |
| `doi` | fill-in | If survivor has no DOI, take loser's — retains linkability. |
| `abstract` | fill-in | Preserve any abstract text we've seen. |
| `year` | fill-in | Survivor's year (typically the journal year) wins; loser's fills a gap. |
| `authors` | fill-in (list-level) | If survivor `authors` is empty, take loser's. No per-name union to avoid dependency on author-string normalization. |
| `venue` | fill-in | Fill missing venue from loser. |
| `fulltext` | fill-in | Any full text we have beats nothing. |
| `citations_out` | union (order-stable, survivor first) | Both sources' outgoing references count. |
| `citations_in_count` | **policy-controlled: `CITATIONS_MERGE_POLICY`** | Default `"max"`. See below. |
| `oa_fulltext_available` | OR | Either side being open-access makes the merged record open-access. |
| `merged_from` | transitive union | Every collapsed ID lands here — see below. |

### `CITATIONS_MERGE_POLICY`

Module-level constant in `backend/app/ingestion/normalizer.py`. Values:

- **`"max"`** *(default)*. Take the higher of the two counts. Under-counts
  by exactly the number of citers who reference BOTH versions (rare in
  practice — bibliographers usually pick one). Conservative.
- **`"sum"`**. Add both. Systematically double-counts anyone who cites
  the preprint and separately the journal — every entry in this
  overlap inflates the score. Rejected.
- **`"survivor"`**. Keep survivor's, drop loser's. Silently loses
  information (the preprint's cited-by count often exceeds the
  journal's during the first year). Rejected.

This constant is deliberately named and exported so any change is
grep-able and auditable. Downstream ranking (Phase 5) will read it.

### `merged_from`

Every merge appends the loser's `id`, plus the loser's own
`merged_from` list, to the survivor's `merged_from`. The result is
order-stable and deduplicated; the survivor's own `id` is never in
its own `merged_from`. This gives the reasoning engine a full audit
trail: if the corpus reports 4 papers supporting a claim, each of the
4 records carries a `merged_from` chain that can be inspected before
treating them as independent.

---

## Forward-compat commitment for Phase 2

Phase 2 will ingest `Claim`, `Evidence`, `Methodology`, `Limitation`,
`FutureWork`, and `ClaimRelationship`. The intended merge policy for
each — **not yet implemented, decided now so Phase 2 doesn't guess**:

| Entity | On paper merge | Rationale |
|--------|-----------------|-----------|
| `Claim` | **union**, keyed by `(paper_id, normalized_text)` | Each version of the paper might phrase a claim differently; we keep both phrasings but treat them as the same claim if the paper is the same. The reasoning engine has to reconcile at the *claim* level. |
| `Evidence` | **union**, keyed by `id` | Evidence rows are anchored to claims; extractor may produce different evidence rows from preprint vs. journal, both are informative. |
| `Methodology` | **union**, keyed by `(paper_id, normalized_name)` | Journal versions sometimes describe methods more completely than the preprint — dropping either version loses signal. |
| `Limitation` | **union**, keyed by `(paper_id, normalized_category)` | Same reasoning as methods. |
| `FutureWork` | **union**, keyed by `id` | Journal-review comments often surface additional future-work items. |
| `ClaimRelationship` | **union**, keyed by `(from_claim_id, to_claim_id, type)` | Relationships are between claims; two relationship rows with the same endpoints and type are the same relationship. |

**Non-negotiable for Phase 2:** an entity attached to the loser paper
must NOT be silently dropped on merge. Either it survives on its own
via the union rule above, or extraction re-runs it against the merged
paper. Either is acceptable; silent loss is not.

**What Phase 2 must decide** (deferred):

1. Whether merged `Claim.confidence` uses `max`, `mean`, or survivor.
2. Whether preprint-vs-journal `Limitation.text` mismatches should
   flag for human review or silently keep both.
3. Whether `merged_from` should propagate to entity records (so that
   a claim knows which paper-versions it was extracted from).

Written down here so Phase 2 doesn't invent policy on the fly.
