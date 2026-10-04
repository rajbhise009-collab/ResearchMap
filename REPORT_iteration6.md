# ResearchMap — iteration 6 report

**2026-10-04.** Your four decisions on the iteration-5 findings, applied.
No paid API calls. Numbers below come from `data/domains/ml-fairness/merge_log.json`,
`data/duplicate_check_v2.json`, `data/llm_cal_fingerprint.json`,
`data/spend_ledger.json`, the shipped stats files, and the test and
verification runs.

**626/626 backend tests pass. Typecheck clean. Production static build
clean. `doc_numbers.py --check` passes. Playwright 55/55. Git status
clean. Pushed to `origin/iteration-2` only.**

**Preview HEAD:** this report is committed on top of
`7a0ea1657629ef3edfec01b6657f6d2a99e24b71`. A commit cannot contain its
own sha; the exact pushed HEAD (the commit adding this file) is given in
the chat summary and is `git rev-parse origin/iteration-2`.

## Spend

₹0. The ledger is unchanged: 1,090 entries, ₹920.79 cumulative, cap
₹920.79. Nothing was raised. No projection was recorded, because no paid
stage ran.

## 1. Ledger cap

Left at ₹920.79.

## 2a. AI Fairness 360 duplicate — merged

- Recorded in `data/domains/ml-fairness/merges.json`; applied by
  `python -m backend.app.corpus.merges --slug ml-fairness --apply`.
- **Survivor:** `W2974817986` (IBM J. Res. Dev. 2019). The policy's own
  `_pick_survivor` was checked, and the script refuses if it disagrees
  with the record. Tier 1 decides it: a non-arXiv DOI beats an arXiv DOI.
- **Merged record:** survivor-only title and identity; citations
  max(887, 267) = 887; full text filled in from the preprint (marked
  `fulltext_source: merged:openalex:W4289438483`); `merged_from:
  ["openalex:W4289438483"]`, also shown on the paper's public JSON.
- **Nothing lost:** the extraction cache is never rewritten. At load time
  the preprint's extraction is unioned onto the survivor using the
  Phase-2 keys in `docs/merge-policy.md`. The journal record had 0
  limitations and 0 future-work items; the preprint's 5 and 3 are kept.
- **The 4 self-"supports" verdicts** were moved to
  `reasoning/dropped_by_merge.json`, each with its reason. They are not
  deleted, and they are not counted.
- **Published verdicts:** none changed. Flagged contradictions were 0
  before and 0 after.

Before and after, per library (from `merge_log.json`, and from coverage
for the unchanged libraries):

| library | papers | shortlisted pairs | classified | supports verdicts | flagged |
|:--|:--|:--|:--|:--|:--|
| llm-calibration | 113 → 113 | 437 → 437 | 437 → 437 | unchanged | 2 → 2 (0 confirmed) |
| diet-and-mortality | 100 → 100 | 152 → 152 | 152 → 152 | unchanged | 10 → 10 (5 confirmed) |
| ml-fairness | **100 → 99** | **95 → 91** | 95 → 91 | **82 → 78** | 0 → 0 |

ML-fairness claims: 466 before and 466 after (the union kept all 10
claims of the two records). Full text: 50 before and 50 after (now of
99). Removing the self-pairs brought no new pair into the shortlist, so
nothing needed classifying.

Paper counts on the site (footer, library manifest) are now read from
the corpus files instead of the literal 100.

## 2b. Title-similarity dedup (pass 5)

**Rule** (`normalizer.py`, documented in `docs/merge-policy.md`). All of
these must hold:
- same normalised first-author surname;
- years within 2;
- title-token Jaccard of at least **0.75**;
- **identical numeric title tokens**;
- both abstracts present, with abstract-token Jaccard of at least
  **0.50**.

`title_similarity_candidates()` is the report-only view.
`deduplicate(…, title_similarity=False)` turns the pass off.

**Why those thresholds.** The sweep covered all three libraries plus
every raw OpenAlex record seen while building the two new ones (113 +
428 + 645 records). Title similarity alone cannot be made safe:

- AI Fairness 360, the only true duplicate with different titles,
  scores **0.80**.
- A same-authors, different-study pair in llm-calibration scores **0.78**.
- Annual editions of an ADA guideline chapter score up to **0.88**, and
  some have identical abstracts.

The numeric-token guard blocks the annual editions. The abstract guard
blocks the different-study pair (abstract overlap 0.24, against 0.62 for
AI Fairness 360). I added both guards beyond the three conditions in your
brief, because any title threshold that catches AI Fairness 360 also
admits a false merge.

**Every pair the rule flagged** (report-only floor: title Jaccard of 0.6
or more):

| set | pair | title / abstract Jaccard | rule outcome | action |
|:--|:--|:--|:--|:--|
| ml-fairness, before merge | `W2974817986` / `W4289438483` (AI Fairness 360) | 0.80 / 0.62 | merge | Merged (2a) |
| llm-calibration | `W7131427313` / `W7147133480` | 0.78 / 0.24 | blocked: abstract | Not merged; different works (hand-checked) |
| diet sweep, not in library | `W1617145133` / `W3143437408` (GBD 2016 vs 2015) | 0.77 / — | blocked: numbers | Nothing to do |
| diet sweep, not in library | `W4311263988` / `W4405187504` (ADA 2023 vs 2025 chapter) | 0.88 / 0.96 | blocked: numbers | Nothing to do |
| diet sweep, not in library | `W4249178369` / `W4255618880` (ADA 2018 vs 2019 chapter) | 0.64 / 1.00 | blocked: title | Nothing to do |

**Applied merges beyond AI Fairness 360: none. Uncertain pairs: none.**
Details: `docs/findings/duplicate-check-v2.md`. Tests cover the
retitled-preprint merge, the same-title-family different-papers negative,
annual editions with identical abstracts, a different first author, and
a missing abstract.

## 3. Manifest label and fingerprint

- `44981e91c40dfe6d` is kept and documented as a **frozen label**. It was
  written at generation, before later steps changed the records, so it is
  not a content hash.
- **Content fingerprint (SHA-256 over canonical sorted records, 113 records):**
  **`5ee219f437e0b9e379c50316eb64c7eb2371c77e1fa0a00e9a640507c76fd8f7`**
- It is produced by `backend/app/corpus/llm_cal_fingerprint.py` and stored
  in `data/llm_cal_fingerprint.json`. It ships in llm-calibration's
  `stats.json` beside `manifest_hash`. The test suite recomputes it
  whenever the gitignored manifest is present; a keyless clone skips that
  one test, with the reason given.
- The manifest file's SHA-256 is unchanged since iteration 5.

## 4. Audit doubts and the second packet

- No published verdict changed; a test pins diet audit rows 1 and 5 as
  "genuine".
- The doubts are generated into `reasoning/audit_doubts.json` by
  `backend/app/corpus/audit_doubts.py`. They are rendered on each
  library's page under "How we checked our own work" ("Our own verdicts
  we now doubt") and in a generated "Audit doubts" section of
  `multi-domain.md`.
- **Diet:** red meat / stroke (null vs per-100 g/day estimate) and red meat
  / type 2 diabetes (unprocessed vs all red meat). One sentence each; both
  say "added to a packet for expert review (not yet sent)".
- **ML fairness, measured:** 123 verdicts are for pairs outside the
  reported shortlist.
  - 113 have similarity below 0.80, so they were made at a looser setting
    (iteration 3 ran at 0.72 / 4).
  - 10 no longer rank in each claim's top 2.
  - None is a disagreement, and none is counted. I did not state that all
    123 came from iteration 3, because only the 113 are proven.
- **Second packet:** `docs/review/diet-contradictions-v2/`, built by
  `backend/app/review/build_diet_packet_v2.py`.
  - Items 01–12 are copied byte-for-byte from the frozen v1 `packet.md`
    (tested).
  - Items 13–14 use v1's own formatter. Seeded order, plus one added rule:
    an item never sits directly after its own twin. The seeded order had
    put v1 item 12's twin at position 13.
  - **Key:** `~/ResearchMap-private/answer_key_v2.json` (+ `README_v2.md`).
  - `docs/review/diet-contradictions/` and the v1 `answer_key.json` /
    `README.md` were verified byte-identical before and after.

## Verification (`docs/review/verification-iteration6.md`)

**55/55** on the production build:

- all 11 findings pages on all three libraries, with no banned phrases
  and no generator markers (33 checks);
- the "Why zero" section (3);
- the ml-fairness stats card showing 99 of 99 and its true coverage (1),
  and the footer listing ml-fairness with 99 papers (1);
- the audit-doubts section on both library pages (2) and on the findings
  page in all three libraries (3);
- the footer notes (3);
- diet "alc" → 13 results, ml-fairness "fair" → 5, llm-calibration
  "halluc" → 24, all with no banner (3);
- "melanoma treatment" refused on all three (3);
- no spend figure on any /library page (3).

Run 1 was also 55/55, but reading a screenshot showed the doubt text said
the pairs were "sent for expert review", which was untrue. I fixed it at
the source, added a test, rebuilt, and re-ran.

## Not measured / skipped

- Mobile emulation and dev-build checks: not in this run's list; not run.

## Needs your decision

1. **The v2 packet is only partly blind.**
   - Items 13 and 14 repeat v1 items 06 and 12, and the packet says so
     (otherwise a reviewer would be confused).
   - The public site lists the two doubted topics (both red meat). A
     reviewer who has read the site could infer which repeated items are
     the doubted ones. I removed every public mention of the item numbers,
     but the inference stays possible.
   - Options: send v2 only to reviewers who have not seen the site, or
     treat 13–14 as a test-retest consistency check.
2. **Files added to `~/ResearchMap-private/`.** The standing rules freeze
   that folder, and your decision 4 asked for the key there. I added two
   new files and changed nothing existing (verified by hash). Confirm
   that is what you wanted.
3. **Pass 5 is on by default** in `deduplicate()` for future ingestion.
   The frozen llm-calibration manifest was not rebuilt (and the rule
   flags nothing in it).
4. Carried over: raising the ₹920.79 cap is still your call when you want
   to spend.
