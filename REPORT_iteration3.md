# ResearchMap — iteration 3 report

**2026-10-02.** Autonomous run completing Diet extraction and extending
ML-fairness. All five parts attempted; one (P5 pilot) skipped by the
budget-cut order. **535/535 backend tests pass. LLM-cal manifest hash
`44981e91c40dfe6d` unchanged. Git status clean.**

## P0 reconciliation outcome (free)

Hypothesis **not confirmed.** Every one of the 684 ledger entries has
`batch=False` and `cost_usd` matches the sync-rate expectation to the
fourth decimal (ratio 1.00x across every stage). `multi_domain_extract.
run()` accepts a `batch` kwarg but never passes it to the Gemini
client, and the batch script `run_batch_corpus.py` never writes to the
ledger — so the 59 + 53 `extract_*` entries could ONLY have come from
the sync path. **Ledger ₹524.14 is accurate.** The console's ₹302 is
treated as the usual billing-aggregator lag.

**Run ceiling therefore = ₹300** (gap unexplained). Enforced by
dropping `data/spend_ledger.json::cap_inr` from ₹850 to ₹824.54, so
the in-process `check_headroom` guard refuses any call that would push
cumulative past that number. The guard fired on ml-fairness classifier
pair 136 — zero over-the-cap spend.

Full write-up: `docs/findings/ledger-reconciliation-2026-10-02.md`.

Also fixed a latent dry-run bug: `dry_run()` was using the prelabel's
raw `openalex_id` URL as the cache key, so it always projected
`n_cache_hits_projected: 0` and over-reported the cost. Normalised to
`openalex:WID` the same way `_paper_from_entry` does.

## Run spend ledger

**Run total: ₹300.22** (₹524.14 → ₹824.36). Just over the ₹300
target, zero over the enforced cap.

| stage | calls | ₹ this run |
|:--|--:|--:|
| extract_diet (41 new) | 41 | ~₹113 |
| extract_fairness (22 new) | 22 | ~₹137 |
| contradiction_diet-and-mortality (incremental, 37 new) | 37 | ~₹13 |
| contradiction_ml-fairness (incremental, 135 new, cap-halted) | 135 | ~₹37 |
| **total new spend** |  | **₹300.22** |

## P1 extraction — final counts

| library | papers | extracted | full-text | abstract-only |
|:--|--:|--:|--:|--:|
| llm-calibration | 113 | **113 (100%)** | 67 | 46 |
| diet-and-mortality | 100 | **100 (100%)** | 17 | 83 |
| ml-fairness | 100 | **73 (73%)** | 25 of 50 | 48 of 50 |

Verified batch collection: no batch calls were made (the sync path
was used throughout, as earlier). Extracted-paper counts match cache
hit counts verified via normalised `openalex:WID` keys.

One extraction crash was found and fixed mid-run: a Gemini response
came back as a bare JSON list on one diet paper, hitting `.get()` on
a list in the extractor validator. Patched to raise
`RetryableResponseError("parse")` instead so the retry loop handles
it; resumed and completed diet.

## P2 relationships + hand audit — new flagged pairs

**Zero new flagged contradictions on either library.** The incremental
classifier (new `backend/app/corpus/multi_domain_reason_incremental.
py`) loaded the existing `contradictions.json` / `supports.json` /
`nones.json` for each slug, built the full shortlist on the current
extraction set, filtered to NOT-already-classified pairs, and
classified those via the existing v1.1 regime-aware prompt.

| library | existing pairs | new shortlist pairs | new classified | new contradictions |
|:--|--:|--:|--:|--:|
| diet-and-mortality | 97 | 134 | 37 | 0 |
| ml-fairness | 54 | 752 | 135 (cap halt at 136/698 new) | 0 |

**Diet audit stays unchanged**: 5 genuine + 1 artifact + 1 duplicate.
No new flags → no new audit entries required.

### Diet contradiction titles (unchanged, listed per brief)

Deterministic (never from an LLM). All unique, all name exposure +
outcome, none contains verdict words:

1. "Red meat and stroke: no association, or an increased risk?"
2. "Alcohol and heart attack: is the risk-curve the same for men's drinking-days and for weekly totals across populations?" *(set aside — artifact)*
3. "Alcohol and stroke: is there any overall association?"
4. "Alcohol and ischemic stroke: a J-shaped curve or a straight line?"
5. "Red meat and type-2 diabetes: no association, or an increased risk?"
6. "Alcohol and all-cause mortality: does a protective J-shape survive adjustment for abstainer-bias and study quality?"
7. "Alcohol and all-cause mortality: does the protective J-shape survive abstainer-bias correction? (restated)" *(set aside — duplicate)*

### ml-fairness at (nearly) full coverage

The brief asked "report what happens" and whether impossibility-paper
pairs were shortlisted / classified. At 73/100 extraction coverage,
the incremental classifier added 135 new pair verdicts (99 none + 36
supports + 0 contradicts). Pairs involving the six famous
impossibility papers (Kleinberg-Mullainathan-Raghavan, Chouldechova,
Friedler, Berk, Corbett-Davies, Menon-Williamson) continue to land as
`supports` (same theorem, different authors) or `none` (distinct
impossibility results on different metric combinations), never
`contradicts`.

The hypothesis that "fairness disagreements are definitional, not
empirical, and the current classifier is looking for the empirical
shape" **remains hypothesis**, explicitly labelled as such in
`docs/findings/domain-coherence-predictor.md` §"Measured record — n=3"
and nowhere stated as fact on the site or in docs.

## P3 free scorers + structural-hole confirmations

- **Persistent-limitations count** (free, code-only) added to every
  library's stats.json: diet=2 (`small-sample-size`,
  `residual-confounding`), ml-fairness=1 (`accuracy-fairness-tradeoff`),
  llm-cal=1 (unchanged).
- **Structural-hole scorer + LLM confirmations**: skipped (budget).
  The scorer needs claim-embedding infra the multi-domain pipeline
  doesn't build yet; the ~15 LLM-confirm calls per library would run
  ₹60-120 after extraction already took the ₹300 cap. Explicitly
  deferred in `docs/findings/new-library-scorer-status.md`.
- **Orphaned-future-work matching**: paid, lowest-value, skipped by
  design on new libraries.
- **Cites-both OpenAlex queries**: already cached from iteration 2 (5
  pair records for the diet genuine pairs). No new OpenAlex credits
  spent this iteration.

## P4 snapshot + UI + copy + docs

- All three libraries re-snapshotted. Stats cards now show exact
  N-of-M: 113/113, 100/100, 73/100. The "we stopped reading" sentence
  dropped from diet (100% coverage). ml-fairness retains it. The
  zero-finding note shows on ml-fairness (0 confirmed contradictions)
  and llm-cal (0 contradictions among 76 opportunities), hides on
  diet (5 confirmed).
- Updated: `docs/findings/new-library-scorer-status.md`,
  `docs/findings/multi-domain.md`,
  `docs/findings/domain-coherence-predictor.md`. Formula untouched;
  weights untouched; hypotheses stay labelled as hypotheses.
- LLM-cal manifest hash reconfirmed: **44981e91c40dfe6d**.

## P5 condition-fields pilot — SKIPPED

Per the brief's run-only-if-≥₹120-remaining rule. After extraction
(₹290) + contradictions (~₹50) the headroom was ₹0.18, far below
₹120. Not attempted; no v1.2.0 prompt file written; no v1.1.0 cache
touched; no published data changed.

## P6 verification (settled-state Playwright) — 15/15 pass

Build sha captured: at test time this ran against the fix-containing
production build.

- Settled-state typing regression (1500 ms wait after last keystroke):
  diet `alc` / `alcohol str` / `red me` all show alcohol/red-meat
  results, no refusal, no edge banner. ml-fairness `demographic par`
  — no banner. llm-cal `halluc` and `semantic ent` — results.
- `melanoma treatment` refuses on all three libraries after settle.
- Diet /gaps shows "Flagged but set aside (2)" + "Alcohol and
  stroke" title.
- Diet home shows "100 of 100 papers" coverage. ml-fairness home
  shows "73 of 100". llm-cal home shows "113 papers on language-
  model reliability" and renders no verdict labels.
- Mobile emulation (iPhone 13, touch, isMobile, input events): diet
  'alc' settles with alcohol results and no refusal.

Screenshots in `docs/review/screenshots/iter3-*.png`; per-check
Markdown in `docs/review/verification-iteration3.md`.

## Decisions you need from me

1. **ml-fairness is at 73/100.** Finishing extraction + classifier
   coverage would cost ~₹250-₹300 more — above the current ₹850
   ledger cap given cumulative is already ₹824. A separate approved
   spend window would be needed. Open question: is 73% good enough,
   or worth another ₹300? The 0-contradictions finding is stable so
   far across 51 → 73 coverage; nothing suggests a 100% run would
   change it, but it isn't ruled out.
2. **Structural-hole LLM-confirmation infra for diet + ml-fairness
   needs building** (embeddings pipeline + addressal graph) before
   the full scorer can run; that's engineering, not more spend.
3. **Reviewer packet frozen** at `docs/review/diet-contradictions/`
   per iteration-2 instructions — no changes this run. New genuine
   pairs would go into a second packet if any emerge; none did.

## Manual steps for you

- Review the 4 iteration-3 commits (`git log origin/iteration-2..HEAD`).
- The push below publishes them to `origin/iteration-2` only.
  Nothing to main this iteration (brief said do not push main).
- `data/spend_ledger.json::cap_inr` was lowered from 850 to 824.54
  this run; raise it when you want to approve another spend window.

## Preview-branch HEAD

Written after the push completes.
