# Multi-domain expansion — 3-library results

**First written 2026-09-29; numbers regenerated 2026-10-04.** Wave 2 of
ResearchMap. Built two additional libraries alongside the frozen
LLM-calibration library (113 papers, manifest label `44981e91c40dfe6d`,
unchanged; a frozen identifier, not a content hash — the content
fingerprint is in `data/llm_cal_fingerprint.json`), then compared contradiction yield, assertion-strength
distribution, and full-text coverage across all three.

Every table in this document is generated from data files by
`python -m backend.app.corpus.doc_numbers` (sources listed in that
script). Prose between the tables is hand-written.

FX: 1 USD = ₹84.

## 1. Corpus stats

<!-- gen:corpus -->
| library | slug | papers | core | peripheral | full text | claims extracted |
|:--|:--|--:|--:|--:|--:|--:|
| LLM calibration | `llm-calibration` | 113 | 100 | 13 | 67 (59%) | 113 of 113 |
| Diet & mortality | `diet-and-mortality` | 100 | 67 | 33 | 17 (17%) | 100 of 100 |
| ML fairness | `ml-fairness` | 99 | 99 | 0 | 50 (51%) | 99 of 99 |
| Social media & teens | `social-media-teen-mental-health` | 100 | 68 | 32 | 22 (22%) | 99 of 100 |
<!-- /gen:corpus -->

Diet & mortality was completed in iteration 3 (synchronous API). ML
fairness went 51 → 73 papers in iteration 3 (synchronous) and 73 → 100 in
iteration 4 (batch API). Both new libraries are at full extraction
coverage.

## 2. Contradiction yield

<!-- gen:yield -->
| library (shortlist settings) | shortlisted pairs | classified | flagged by classifier | hand-audited genuine | artifact | duplicate |
|:--|--:|--:|--:|--:|--:|--:|
| LLM calibration (frozen 2026-07; threshold 0.78, cap 10) | 437 | 437 | 2 | 0 | — | — |
| Diet & mortality (threshold 0.80, cap 2) | 152 | 152 | 10 | 5 | 2 | 3 |
| ML fairness (threshold 0.80, cap 2) | 91 | 91 | 0 | 0 | — | — |
| Social media & teens (threshold 0.80, cap 2) | 179 | 179 | 6 | 2 | 3 | 1 |
<!-- /gen:yield -->

Only shortlisted pairs are ever checked: a pair of claims reaches the
classifier only if their embeddings are at least as similar as the
library's threshold, and each claim keeps at most its top few neighbours.
A disagreement between two claims that are not similar enough to be
shortlisted is never looked at.

LLM calibration uses its own, earlier settings (threshold 0.78, cap 10).
Its classifier flagged 2 pairs; a later regime-context check (see
`RESEARCHMAP-FINDINGS.md`, "Experimental-regime conflation") set both
aside, so its confirmed count is 0.

Iteration 3 mistakenly ran its incremental pass at 0.72 / 4, so the
ML-fairness verdict files also hold verdicts for pairs outside the
documented shortlist; none of those is a contradiction, and they are kept
rather than deleted. They are not counted in the table above.

### Diet & mortality — hand-audit of every flagged pair

<!-- gen:diet-audit -->
| pair | verdict | topic | papers | reason |
|--:|:--|:--|:--|:--|
| 1 | genuine | red meat / stroke | `W2109401990` vs `W2513212958` | Both are meta-analyses of unprocessed red meat and incident stroke on comparable adult populations; a 2010 pooled null vs a 2016 updated point estimate — the canonical time-updated red-meat disagreement. |
| 2 | artifact | alcohol / MI dose-shape | `W2126726883` vs `W2787107952` | Different populations (US male health professionals only vs mixed IPD across 19 countries) AND different dose constructs (per-drinking-day vs per-week). The apparent conflict evaporates once the measures are reconciled — a regime-conflation, not a real disagreement. |
| 3 | genuine | alcohol / stroke — is there an association? | `W2109129984` vs `W2787107952` | Both are meta-analyses of adult drinkers with comparable methods; an older pooled null vs a newer IPD's linear positive slope. Direct disagreement on whether an aggregate association exists. |
| 4 | genuine | alcohol / ischemic stroke dose-shape | `W2064137374` vs `W2787107952` | Both meta-analyses on comparable populations; the disagreement is model choice (fractional-polynomial J-shape vs assumed linear). A modelling-choice disagreement on the same construct is a substantive disagreement. |
| 5 | genuine | red meat / type 2 diabetes | `W2109401990` vs `W2955331731` | Same time-updated red-meat pattern as pair #1: 2010 pooled null vs 2019 umbrella-positive on the same construct. |
| 6 | genuine | alcohol / all-cause mortality — J-shape vs quality-adjusted null | `W2109129984` vs `W2311763102` | Same construct (light drinking vs abstention on all-cause mortality) but with Stockwell's abstainer-bias correction applied. The central controversy in alcohol epidemiology; systematic reviews reaching opposite conclusions after quality adjustment. |
| 7 | duplicate | alcohol / all-cause mortality — duplicate of previous | `W2109129984` vs `W2311763102` | Same paper pair and same topic as the pair immediately above (BMJ 2011 vs Stockwell 2016 alcohol/mortality). The other Claim B here is a near-identical restatement of the abstainer-bias correction. Counted once. |
| 8 | artifact | triglycerides / coronary heart disease — independent of other risk factors? | `W1976428272` vs `W2127427274` | Different adjustment and contrast: Sarwar 2006's own conclusion says its triglyceride–heart-disease link depends heavily on other risk factors and leaves any independent link open, while the 2009 pooled analysis reports the per-standard-deviation estimate alongside the other blood lipids, so both statements can be true. |
| 9 | duplicate | triglycerides / coronary heart disease — EPIC-Norfolk estimate (duplicate) | `W1976428272` vs `W2127427274` | Same paper pair and same finding as the triglyceride pair above; the EPIC-Norfolk estimate is one component of Sarwar 2006's pooled result. |
| 10 | duplicate | triglycerides / coronary heart disease — Reykjavik estimate (duplicate) | `W1976428272` vs `W2127427274` | Same paper pair and same finding as the triglyceride pair above; the Reykjavik estimate is one component of Sarwar 2006's pooled result. |
<!-- /gen:diet-audit -->

All verdicts are the builder's hand review against the source abstracts,
not expert review. The expert-review packet in
`docs/review/diet-contradictions/` is what settles disputed pairs. The
three "duplicate" verdicts are the same two papers counted more than once
through different claims (see `duplicate-check.md`).

**Diet-and-mortality is the first ResearchMap library with hand-confirmed
contradictions.**

### The audited genuine diet contradictions

Every pair below is two claims from two different papers that Gemini
classified as `"relationship": "contradicts"` at temperature 0 AND that
survived a hand-audit for population / dose / study-design comparability.

1. **Red meat and stroke.** A (`W2109401990`, Circulation 2010,
   dose-response meta-analysis): "Unprocessed red meat consumption is
   not associated with incident stroke." B (`W2513212958`, J Intern
   Med 2016, literature review + meta-synthesis): "Consumption of 100
   g/day of unprocessed red meat is associated with an 11% increased
   risk of stroke." Same construct (unprocessed red meat + incident
   stroke), both meta-analytic; a 2010 pooled null vs a 2016 updated
   point estimate.
2. **Alcohol and stroke, presence of association.** A (`W2109129984`,
   BMJ 2011 systematic review + meta-analysis): "Alcohol consumption
   is not significantly associated with overall incident stroke
   compared with non-drinking (pooled adjusted RR 0.98)." B
   (`W2787107952`, Lancet 2018 IPD meta-analysis, n=599 912): "Higher
   alcohol consumption is roughly linearly associated with a higher
   risk of stroke (HR 1.14 per 100 g/week)." Same construct (alcohol
   + incident stroke); both meta-analytic on general adult drinkers.
3. **Alcohol and ischemic stroke, dose-response shape.** A
   (`W2064137374`, BMC Public Health 2010 meta-regression with
   fractional polynomials): "Alcohol consumption exhibits a curvilinear
   J-shaped dose-response relationship with the relative risk of
   ischemic stroke." B (`W2787107952`, Lancet 2018 IPD linear model):
   "Higher alcohol consumption is roughly linearly associated with a
   higher risk of stroke." Both meta-analyses; the disagreement is
   model choice (fractional-polynomial J-shape vs linear).
4. **Red meat and type 2 diabetes.** A (`W2109401990`, Circulation
   2010 dose-response meta-analysis): "Unprocessed red meat intake is
   not associated with incident diabetes mellitus." B (`W2955331731`,
   BMJ 2019 umbrella review of meta-analyses): "Higher intake of red
   meat is associated with increased incidence of type 2 diabetes."
   Same time-updated red-meat pattern as #1. (Doubt raised in iteration
   4: A says *unprocessed* red meat, B says red meat — possibly a
   different exposure. Verdict unchanged pending expert review.)
5. **Alcohol and all-cause mortality, J-shape vs quality-adjusted null.**
   A (`W2109129984`, BMJ 2011 systematic review + meta-analysis):
   "Alcohol consumption is associated with a lower risk of all-cause
   mortality compared with non-drinking (pooled adjusted RR 0.87)."
   B (`W2311763102`, J Stud Alcohol Drugs 2016 systematic review +
   meta-regression): "Analyses of higher-quality, bias-free studies
   fail to find a reduced mortality risk for low-volume alcohol
   drinkers." An abstainer-bias-adjusted re-analysis set against the
   earlier J-shape.

The single regime-conflation artifact among the first seven flags (alcohol
/ MI dose-shape) is the same failure LLM-calibration's scorer showed in an
earlier iteration; catching it here is a reminder that the hand-audit is
part of the honest contradiction count, not optional polish.

### ML fairness — what was measured

<!-- gen:mlf-facts -->
- Claims extracted from 99 of 99 papers.
- 91 of 91 shortlisted pairs classified; 0 flagged as contradictions.
<!-- /gen:mlf-facts -->
- Pairs touching the impossibility-result papers, rebuilt from the cached
  claim embeddings at the library's shortlist settings:

<!-- gen:impossibility -->
| paper | shortlisted pairs | classified | flagged |
|:--|--:|--:|--:|
| Inherent Trade-Offs in the Fair Determination of Risk Scores (2016) (`W4386564359`) | 12 | 12 | 0 |
| Fair Prediction with Disparate Impact: A Study of Bias in Recidivism Prediction Instruments (2017) (`W2543774860`) | 1 | 1 | 0 |
| On the (im)possibility of fairness (2016) (`W2524301210`) | 0 | 0 | 0 |
| Fairness in Criminal Justice Risk Assessments: The State of the Art (2018) (`W2599025709`) | 10 | 10 | 0 |
| Algorithmic Decision Making and the Cost of Fairness (2017) (`W2584805976`) | 0 | 0 | 0 |
| The cost of fairness in binary classification (2018) (`W2790025105`) | 0 | 0 | 0 |
| Inherent Trade-Offs in Algorithmic Fairness (2018) (`W2808105152`) | 2 | 2 | 0 |
<!-- /gen:impossibility -->

"On the (im)possibility of fairness" was never compared with anything:
none of its claims reached the similarity threshold against another
paper's claims.

### Why zero? Not established

The zero is a measurement of this pipeline on this corpus. Why it is
zero has not been tested. Candidate explanations, none of them tested:

- **(a)** Fairness disagreements are mostly definitional or theoretical
  (which criterion to use), not between empirical claims of the kind the
  classifier is asked about.
- **(b)** The shortlist threshold or the classifier misses them: the
  disagreeing claims are not similar enough to be shortlisted, or the
  classifier labels them `supports` or `none`.
- **(c)** Extraction phrased the claims so they no longer conflict (for
  example, by dropping the conditions under which each holds).

Only shortlisted pairs were ever checked, so nothing here says the
literature contains no disagreements.

### Audit doubts

No published verdict has changed. These are doubts about our own checks,
written down so a reader can weigh them (generated from each library's
`reasoning/audit_doubts.json` by `backend/app/corpus/audit_doubts.py`):

<!-- gen:audit-doubts -->
- **Diet & mortality.** We doubt our own "disagreement" verdict on red meat / stroke: one paper reports no link while the other gives a risk per 100 g a day — the same kind of difference in how results were measured that got the triglyceride pair set aside. The verdict is unchanged; the pair has been added to a packet for expert review (not yet sent).
- **Diet & mortality.** We doubt our own "disagreement" verdict on red meat / type 2 diabetes: one paper is about unprocessed red meat and the other about red meat in general, which may not be the same exposure. The verdict is unchanged; the pair has been added to a packet for expert review (not yet sent).
- **ML fairness.** 123 of this library's classifier verdicts are for pairs outside the ones we report: 113 were made with a looser matching setting than the library's documented one (similarity below 0.80; iteration 3 ran at 0.72 with up to 4 matches per claim), and 10 no longer rank among each claim's top 2 matches. None of them is a disagreement, and none is counted.
<!-- /gen:audit-doubts -->

The two doubted diet pairs have been added to a second expert-review
packet, `docs/review/diet-contradictions-v2/`. Which packet items they are
is recorded only in the private answer key, so the packet stays blind.

## 3. Predictor check

Diet-and-mortality was picked despite its moderate contested score, on the
reputational grounds that meta-analyses in this field famously disagree.

<!-- gen:predictor -->
| library | predictor contested score | hand-audited confirmed contradictions |
|:--|--:|--:|
| LLM calibration | 0.818 (high) | 0 |
| Diet & mortality | 0.44 (moderate) | 5 |
| ML fairness | 0.667 (high) | 0 |
| Social media & teens | 0.833 (high) | 2 |
<!-- /gen:predictor -->

On these three libraries the predictor's ordering does not match the
measured yield: the two libraries it scored highest have zero confirmed
contradictions, and the one it scored moderate has the only non-zero
count. Three libraries are far too few to fit or reject the predictor;
`domain-coherence-predictor.md` already flagged diet as its likely miss
(high modularity is ambiguous between "distinct schools argue" and
"distinct application areas don't interact"). The diet result is
consistent with the first reading; it does not establish it.

## 4. Assertion-strength — REPORTED AS UNTESTED

The prediction going into this run: **biomedical hedges more than ML**,
so diet-and-mortality would show a lower firm-share than LLM-cal.

**No number in this section survives the honesty bar.** Three
successive attempts and why each was dropped:

1. **Lexical hedge classifier** (`is_hedged` in
   `multi_domain_findings.py`) came in at diet 99.7% / fairness 98.4%
   firm vs the LLM-cal hand baseline of 91.1% (n=56,
   `docs/schema-pressure-test.md` §2). Dropped as blunt on this
   vocabulary.
2. **LLM-based classifier** (`multi_domain_hedge.py`, Gemini-3.6-flash,
   temp 0) ran on 200 of 338 diet claims before being halted at the
   ₹150 gate (actual hedge-stage spend: see §6, `hedge_diet-and-mortality`).
   Reported diet at 96% firm — same directional signal as the lexical
   run. **Halted with partial data**, so no cross-domain contrast to
   publish.
3. **Extraction-strip audit** (hand-comparison of 5 firm-labelled
   diet claims against their source abstracts): 2 of 5 showed
   extraction stripping hedge language ("inconsistently associated"
   → "not associated"; "indicate" → "shows"), 3 of 5 had firm source
   wording (typically epidemiological RR-with-CI reporting) that the
   extractor preserved faithfully.

**Interpretation:** the firm-share numbers a classifier produces
against these extractions are a mix of (a) genuine source-abstract
firmness — biomedical papers often report primary findings as RRs
with CIs, which reads firm — and (b) extraction-prompt-induced
firmness — the v1.1.0 prompt tends to rewrite "may reduce" as
"reduces" when producing atomic claims. **No classifier that sees
only the extracted claim text can separate (a) from (b).**

The honest verdict: **domain-conditional hedging cannot be measured
from these extractions.** A fair three-way contrast would need to
either (i) apply the classifier to source-abstract sentences before
extraction, or (ii) re-prompt extraction to preserve hedge tokens.
Both are structural changes to the pipeline, not a follow-up run.

The **91.1% LLM-cal baseline** in
`docs/schema-pressure-test.md` §2 stands — it was a hand-classified
sample of 56 raw source-abstract sentences, not extracted claims, and
does not have the extraction-strip problem this section flags.

Files kept for the audit: `data/domains/diet-and-mortality/hedge/`
directory (partial run, no labels.json written because the process was
killed mid-loop; the ledger entries in `data/spend_ledger.json` under
`hedge_diet-and-mortality` record the calls that ran).

## 5. Full-text coverage

<!-- gen:fulltext -->
| library | full text | abstract only | full-text share |
|:--|--:|--:|--:|
| LLM calibration | 67 | 46 | 59% |
| Diet & mortality | 17 | 83 | 17% |
| ML fairness | 50 | 49 | 51% |
| Social media & teens | 22 | 78 | 22% |
<!-- /gen:fulltext -->

Diet's full-text share is the lowest of the three. Biomedical journals are
frequently not open access, and green-OA copies often return 403 at the
publisher. The persistent-limitations and orphaned-future-work scorers
draw on full text where it exists, so raw diet limitation counts are not
directly comparable with the other two libraries.

Gap-type raw counts from the extractions:

<!-- gen:gap-types -->
| library | papers extracted | limitations | future-work items |
|:--|--:|--:|--:|
| Diet & mortality | 100 (17 full text) | 141 | 57 |
| ML fairness | 99 (50 full text) | 218 | 146 |
| Social media & teens | 99 (22 full text) | 136 | 93 |
<!-- /gen:gap-types -->

## 6. Spend

The whole ledger (`data/spend_ledger.json`), by stage. This includes
spend from before this multi-domain wave. The
`correction_mock_test_entries` row is an appended negative entry that
removes 190 entries proven to have been written by mock-transport unit
tests, not by billed calls (`ledger-unknown-entries.md`); no history was
edited.

<!-- gen:spend -->
| stage | entries | USD | INR |
|:--|--:|--:|--:|
| `contradiction_diet-and-mortality` | 267 | $0.8849 | ₹74.33 |
| `contradiction_ml-fairness` | 218 | $0.6878 | ₹57.77 |
| `contradiction_social-media-teen-mental-health` | 179 | $0.3005 | ₹25.24 |
| `correction_mock_test_entries` | 1 | $-0.0057 | ₹-0.48 |
| `embed_fw_diet-and-mortality` | 1 | $0.0041 | ₹0.34 |
| `embed_fw_ml-fairness` | 2 | $0.0098 | ₹0.83 |
| `embed_fw_social-media-teen-mental-health` | 1 | $0.0060 | ₹0.50 |
| `embed_social-media-teen-mental-health` | 5 | $0.0244 | ₹2.05 |
| `extract_diet` | 101 | $4.6220 | ₹388.25 |
| `extract_fairness` | 75 | $3.5563 | ₹298.73 |
| `extract_fairness_batch` | 28 | $0.8660 | ₹72.75 |
| `extract_social-media_batch` | 100 | $1.5277 | ₹128.32 |
| `fw_match_diet-and-mortality` | 23 | $0.0481 | ₹4.04 |
| `fw_match_ml-fairness` | 225 | $0.3836 | ₹32.22 |
| `fw_match_social-media-teen-mental-health` | 129 | $0.2465 | ₹20.70 |
| `hedge_diet-and-mortality` | 200 | $0.3444 | ₹28.93 |
| `hole_confirm_ml-fairness` | 2 | $0.0039 | ₹0.33 |
| `hole_confirm_social-media-teen-mental-health` | 1 | $0.0021 | ₹0.18 |
| `unknown` | 200 | $0.0060 | ₹0.50 |
| **total (ledger, after corrections)** | 1758 | **$13.5183** | **₹1,135.54** |
| ceiling (config/money.json: account total − safety buffer) |  |  | ₹1,450.00 |
| remaining (money rule) |  |  | ₹314.46 |
<!-- /gen:spend -->

The project budgets against this ledger, which records more spend than
Google's billing console showed when last checked
(`ledger-reconciliation-2026-10-02.md`). Embedding calls were not
ledgered before iteration 5, so their past cost is not measured; from
iteration 5 on they are recorded (estimated tokens, upper-bound rate).

## 7. Cuts applied (in order)

- **(a) Skip structural-hole LLM confirmations** — applied at dry-run.
- **(b) Tighten per-claim contradiction cap 4→2, threshold 0.72→0.80** —
  applied after the first diet shortlist produced 596 pairs (2-hour
  runtime). These remain the settings for both new libraries.
- **(c) Reduce corpus size** — not applied to the corpus itself (100
  kept per domain). Extraction was halted at 59 diet + 51 fairness papers
  in the first wave to preserve budget; both libraries were completed to
  100 of 100 in iterations 3 and 4. ML fairness has 99 papers since the
  2026-10-04 merge of a duplicate (`duplicate-check-v2.md`).

## 8. All four scorers on the new libraries (2026-10-07)

The two new libraries now run the same scorers, thresholds and plain-language
translation as LLM calibration (`backend/app/api/library_cards.py`,
`backend/app/reasoning/library_corpus.py`). Results per scorer:

<!-- gen:scorer-yields -->
| library | disagreements kept after checking | recurring limitations | method-transfer leads | unfollowed questions | set aside after checking | total results |
|:--|--:|--:|--:|--:|--:|--:|
| LLM calibration | 0 | 1 | 2 | 63 | 10 | 66 |
| Diet & mortality | 5 | 2 | 0 | 5 | 5 | 12 |
| ML fairness | 0 | 1 | 0 | 54 | 2 | 55 |
| Social media & teens | 2 | 4 | 0 | 26 | 5 | 32 |
<!-- /gen:scorer-yields -->

- **Persistent limitations** — free, code only, same minimum of 3
  independent papers.
- **Structural holes** — topic groups k = max(2, round(√N)) = 10 (the
  scaling study's correction), the same similarity threshold (0.72) and
  weak-bridge rule (at most 2 citation edges between groups). Diet has 1
  method-type claim among its 562, so the method-transfer scorer has almost
  nothing to work from and found no leads. ML fairness has many candidate
  pairs above the similarity threshold, but its topic groups cite each other
  heavily, so only 2 pass the weak-bridge rule. Both were checked by the
  language model with LLM calibration's prompt and labelled "not
  addressing"; they are shown as unverified leads with that label.
- **Orphaned future work** — the two-stage matcher (cosine shortlist 0.70,
  up to 4 later papers per item, then a language-model check) ran on Diet.
  For ML fairness its projection, doubled for safety, did not fit the
  remaining budget, so it was skipped and the site says so.
- **Disjoint bridging** — off in every library, as before.
- Diet's five audited disagreements and their audit are unchanged.

Why these counts are what they are is described above as measured; whether
more papers, or a different scorer, would change them has not been tested.
