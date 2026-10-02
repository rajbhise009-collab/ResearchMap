# ResearchMap — iteration 4 report

**2026-10-02.** Every number below comes from `data/spend_ledger.json`,
the files under `data/domains/<slug>/reasoning/`, the shipped
`frontend/public/data/**/stats.json`, or the test/verification runs. Where
something was not measured, it says so.

**552/552 backend tests pass. Typecheck clean. Production static build
clean. LLM-cal manifest hash `44981e91c40dfe6d` unchanged. Git status
clean.** Pushed to `origin/iteration-2` only (sha in the chat summary).

## Spend (from the ledger)

| stage | batch | calls | ₹ |
|:--|:--|--:|--:|
| contradiction_diet-and-mortality | no | 58 | 16.36 |
| extract_fairness_batch | yes (50% rate) | 28 | 72.75 |
| contradiction_ml-fairness | no | 29 | 7.77 |
| **this run** | | | **96.88** (cap ₹126) |

- Ledger cumulative: ₹824.39 → **₹921.27** (ceiling ₹950, enforced at
  call time).
- **Corrected cumulative: ₹920.77.** The ledger holds 200 "unknown"
  entries totalling ₹0.50 that were written by mock-transport unit tests
  (5-token prompts), not by real calls. They are left in place (history
  isn't rewritten); the test suite now uses an isolated ledger, so no
  more can be added.
- Embedding calls (shortlist building) are not recorded in the ledger;
  their cost was **not measured**. Claims embedded this run: 562 (diet),
  466 (ML-fairness). They are now cached, so reruns embed only new claims.
- The ledger and the Google console still disagree; the project budgets
  against the ledger. This is now stated in plain language in the
  library page's "How we checked our own work" section and in
  `docs/findings/ledger-reconciliation-2026-10-02.md`.

## Part 1 fixes (free)

1. **Batch billing.** Batch results are billed to the ledger with
   `batch=true` at half price, exactly once per collected job (state
   flag). Batch is the default for `multi_domain_extract`; sync needs
   `--sync`. Tests: batch costs half of sync; collecting twice bills once.
   Verified live: 28 `extract_fairness_batch` entries, all `batch=true`.
2. **Save as you go.** Every classifier verdict (and every paid parse
   failure) is appended to `reasoning/verdicts.jsonl` with fsync as it
   returns; restarts skip anything saved. Test: killed after 3 of 5
   calls, all 3 are on disk and the restart makes exactly 2 calls. Also
   halts on a run budget and on cost per call above 1.5× projection.
3. **Truthful coverage line** from `reasoning/coverage.json` →
   `stats.disagreement_check_note`, shown on the stats card, `/gaps` and
   the library intro. Before the diet re-run it read "covered 75 of the
   100 papers read … 25 still pending (58 pairs not yet checked)". It
   now reads "compared every shortlisted pair of claims across all 100
   papers read" for both new libraries.
4. **Budget note** added (see above).

Also found and fixed while doing this:

- **Iteration 3 used the wrong shortlist settings.** These libraries'
  documented settings are threshold 0.80, cap 2 (`multi-domain.md` §7);
  iteration 3 ran the code defaults 0.72 / cap 4. That is why its
  shortlists were 954 (diet) and 752 (ML-fairness) pairs instead of 152
  and 95, and why the "≈₹24 diet re-run" looked so small — that figure
  came from a run I had killed. The runner now defaults to 0.80 / 2.
  ML-fairness's verdict files keep the verdicts made at the looser
  setting (none is a contradiction); they are outside the shortlist and
  not counted in coverage.
- Mock-test ledger leaks stopped (isolated ledger per test).
- Embedding cache added; the shortlist no longer silently falls back to
  mock vectors on an API error.
- Unaudited flags now show as "Flagged by the system, not yet checked",
  in their own section, never in the headline.

## Part 2 — diet re-run

- 58 unseen pairs classified at 0.80 / cap 2 (₹16.36). Shortlist 152,
  all classified.
- **3 new flagged pairs**, all the same paper pair: Sarwar et al. 2006
  (*Circulation*, W1976428272) vs Emerging Risk Factors Collaboration
  2009 (*JAMA*, W2127427274), triglycerides and coronary heart disease.

| # | verdict | reason | title |
|--:|:--|:--|:--|
| 8 | artifact | Different adjustment and contrast: Sarwar 2006's own conclusion says its link depends heavily on other risk factors and leaves any independent link open; the 2009 pooled analysis reports the per-SD estimate alongside the other lipids, so both can be true. | Set aside (different measures): Triglycerides and coronary heart disease: a raised risk, or no link once other risk factors are accounted for? |
| 9 | duplicate | Same pair and finding as #8; the EPIC-Norfolk estimate is one component of Sarwar's pooled result. | Set aside (duplicate pair): Triglycerides and coronary heart disease: the EPIC-Norfolk cohort estimate (restated) |
| 10 | duplicate | Same pair and finding as #8; the Reykjavik estimate is one component of Sarwar's pooled result. | Set aside (duplicate pair): Triglycerides and coronary heart disease: the Reykjavik cohort estimate (restated) |

Basis for all three: "builder's hand review against the source
abstracts". **Headline unchanged at 5 confirmed** (raw 10: 5 genuine,
2 artifact, 3 duplicate). No new genuine pair, so no cites-both query was
needed (0 OpenAlex credits used this run).

**Existing verdicts I now doubt (not changed):** pair 5 (red meat / type
2 diabetes) compares "*unprocessed* red meat" with "red meat", which may
be a different exposure; pair 1 (red meat / stroke) sets a null finding
against a per-100 g/day estimate — the same contrast difference I used to
set aside the triglyceride pair. Both stay "genuine"; they are good
questions for the expert packet.

## Part 3 — ML-fairness

- Dry-run: 73 cache hits, 27 to extract. Token-based projection ₹79.31
  (₹118.97 at the 1.5× gate) exceeded the ₹109.25 headroom, so the 3
  lowest-cited papers (95, 89, 86 citations) were cut and 24 submitted
  (projected ₹72.24). Actual: 24 returned, 23 cached, 1 parse-fail
  resubmitted and cached (₹63.40 + ₹3.03). Actual cost came in under
  projection, so the 3 cut papers were then extracted too (₹6.32).
  **Final: 100 / 100 extracted** (50 full text, 50 abstract-only).
- Classification: 29 new shortlisted pairs (impossibility-paper pairs
  first), ₹7.77 — 14 supports, 15 none, **0 contradicts**. The last 3
  papers added no shortlisted pairs. Shortlist 95, all classified.

### Impossibility-result papers at full coverage (from the data)

| paper | shortlisted | classified | flagged |
|:--|--:|--:|--:|
| Kleinberg, Mullainathan, Raghavan 2016 | 12 | 12 | 0 |
| Chouldechova 2017 | 1 | 1 | 0 |
| Friedler et al. 2016 — "On the (im)possibility of fairness" | 0 | 0 | 0 |
| Berk et al. 2018 | 10 | 10 | 0 |
| Corbett-Davies et al. 2017 | 0 | 0 | 0 |
| Menon & Williamson 2018 | 0 | 0 | 0 |
| "Inherent Trade-Offs in Algorithmic Fairness" 2018 | 2 | 2 | 0 |

Friedler et al.'s paper was never compared with anything: none of its
claims reached the similarity threshold against another paper's claims.
Why the classifier flags no contradictions here is not established; the
"definitional disagreement" idea remains a hypothesis.

## Final coverage

| library | claims read | disagreement check | confirmed | zero-note |
|:--|:--|:--|--:|:--|
| llm-calibration | 113 of 113 | every shortlisted pair (437) | 0 | shown |
| diet-and-mortality | 100 of 100 | every shortlisted pair (152) | 5 | hidden |
| ml-fairness | 100 of 100 | every shortlisted pair (95) | 0 | shown |

llm-calibration unchanged: 113 papers, 76 gaps, no verdict labels.

## Part 5 — verification

`docs/review/verification-iteration4.md`: **40/40** on the production
build at `c18d684`, plus **2/2** dev-build checks. Covered: settled-state
search on all three libraries (desktop, and iPhone 13 with insertText),
⌘K, refusals for "melanoma treatment" and "camera cal", diet coverage
lines and headline (5 cards, distinct titles, no verdict words),
set-aside section matching the audit (5), no unaudited section (0), a
genuine gap page's cites-both, timeline and parsed BibTeX (2 entries)
and CSV downloads, ML-fairness coverage and its empty state by gap-card
count, footer per library, the production build ignoring `?dev=1`, and
raw counts under `?dev=1` in a dev build.

The first run scored 37/40. Two were real bugs, fixed in `c18d684`:
"fair" on ML-fairness showed "at the edge" at full coverage, and
"camera cal" stayed in the typing state instead of refusing (iteration
3 had made any prefix suppress refusal, against its own rule that
complete words drive the verdict). The third was a wrong check: dev mode
is inert in production builds by design.

## Not measured / skipped

- Embedding cost (not ledgered; claim counts given above).
- Structural-hole scoring for the new libraries: not run (needs an
  embeddings + addressal pipeline that isn't built).
- Orphaned-future-work matching: skipped by design.
- The five existing genuine diet verdicts were not re-audited against
  the adjustment/contrast test used this run (see doubts above).
- Condition-fields pilot: not part of this run.

## Needs your decision

1. Pairs 1 and 5 above: keep as genuine, or send to expert review first?
2. The ML-fairness verdicts made at iteration 3's looser setting: keep
   (current) or remove from the verdict files.
3. Structural-hole pipeline for the new libraries — engineering, no spend.
4. Ledger ceiling is ₹950 with ₹921.27 used; raise it only if you approve
   another spend window.
