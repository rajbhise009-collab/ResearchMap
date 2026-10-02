# Multi-domain expansion — 3-library results

**2026-09-29.** Wave 2 of ResearchMap. Built two additional libraries
alongside the frozen LLM-calibration library (113 papers, manifest hash
`44981e91c40dfe6d`, unchanged), then compared contradiction yield,
assertion-strength distribution, and full-text-coverage effect across
all three. Total NEW spend: **₹495.18 (~$5.90)** of the ₹850 cap.

FX: 1 USD = ₹84.

## 1. Corpus stats

| library | slug | papers | core | peripheral | full-text | extracted | notes |
|:--|:--|--:|--:|--:|--:|--:|:--|
| LLM calibration | `llm-calibration` | 113 | — | — | 67 (59%) | 113 (100%) | frozen; not re-extracted |
| Diet & mortality | `diet-and-mortality` | 100 | 67 | 33 | 17 (17%) | **100 (100%)** | completed in iteration 3 (sync) |
| ML fairness | `ml-fairness` | 100 | 96 | 4 | 50 (50%) | **100 (100%)** | 51 → 73 in iteration 3 (sync), 73 → 100 in iteration 4 (batch) |

Both new libraries are now at full extraction coverage. The last 27
ML-fairness papers were extracted through the batch API in iteration 4
(₹72.75 for 28 batch results including one retry, from the ledger).

## 2. Contradiction yield — does the coherent-domain result generalise?

| library | shortlisted pairs (classified) | Gemini-flagged contradictions | audited genuine | audited artifact | audited duplicate |
|:--|--:|--:|--:|--:|--:|
| LLM calibration (frozen 2026-07) | 437 (437) | 0 | 0 | — | — |
| Diet & mortality (100 papers) | 152 (152) | 10 | **5** | 2 | 3 |
| ML fairness (100 papers) | 95 (95) | 0 | 0 | — | — |

Shortlist settings for the two new libraries: cosine threshold 0.80,
at most 2 candidates per claim (see §7). Iteration 3 mistakenly ran its
incremental pass at 0.72 / 4, so the ML-fairness verdict files also hold
verdicts for pairs outside the documented shortlist; none of those is a
contradiction, and they are kept rather than deleted.

The three diet flags added in iteration 4 are one paper pair (Sarwar
2006, Circulation, vs the Emerging Risk Factors Collaboration 2009, JAMA)
on triglycerides and coronary heart disease. Hand audit: one artifact
(different adjustment and contrast; Sarwar's own conclusion leaves the
independent link open) and two duplicates (its EPIC-Norfolk and Reykjavik
components). The headline stays at 5.

**Diet-and-mortality is the first ResearchMap library to produce
confirmed contradictions.** Hand-audit reduced the raw 7 to 5 genuine
(comparable population / dose / study design) after dropping one
regime-conflation artifact and one duplicate. The five below are the
final set; the audit trace is in the section below the examples.

### The 5 audited genuine diet contradictions

Every pair below is two claims from two different papers that Gemini
classified as `"relationship": "contradicts"` at temperature 0 AND that
survived a hand-audit for population / dose / study-design comparability.

1. **Red meat and stroke.** A (`W2109401990`, Circulation 2010,
   dose-response meta-analysis): "Unprocessed red meat consumption is
   not associated with incident stroke." B (`W2513212958`, J Intern
   Med 2016, literature review + meta-synthesis): "Consumption of 100
   g/day of unprocessed red meat is associated with an 11% increased
   risk of stroke." Same construct (unprocessed red meat + incident
   stroke), both meta-analytic; the 2010 pooled null vs the 2016
   updated point estimate is the classic time-updated red-meat
   literature disagreement.
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
   Same time-updated red-meat pattern as #1.
5. **Alcohol and all-cause mortality, J-shape vs quality-adjusted null.**
   A (`W2109129984`, BMJ 2011 systematic review + meta-analysis):
   "Alcohol consumption is associated with a lower risk of all-cause
   mortality compared with non-drinking (pooled adjusted RR 0.87)."
   B (`W2311763102`, J Stud Alcohol Drugs 2016 systematic review +
   meta-regression): "Analyses of higher-quality, bias-free studies
   fail to find a reduced mortality risk for low-volume alcohol
   drinkers." This is Stockwell's abstainer-bias-adjusted re-analysis
   overturning the earlier J-shape — the central controversy in
   alcohol epidemiology.

### Hand-audit results per pair

| pair | verdict | reason |
|--:|:--|:--|
| 1 | GENUINE | both meta-analytic, same construct, time-updated disagreement |
| 2 | ARTIFACT | different dose constructs (per-drinking-day vs per-week) and different populations (US men-only prospective cohort vs mixed IPD) — regime conflation |
| 3 | GENUINE | comparable populations + methods; disagreement on aggregate direction |
| 4 | GENUINE | same construct + populations; disagreement on model choice |
| 5 | GENUINE | same construct, time-updated |
| 6 | GENUINE | same construct, quality-adjustment disagreement |
| 7 | DUPLICATE of 6 | same paper pair, near-identical claim wording |

Audited count: **5 genuine confirmed contradictions**. Still well above
the ≥3 threshold that triggers the "reputation beat predictor" verdict
in §3 — that verdict stands.

The single artifact (pair 2) is exactly the regime-conflation failure
LLM-calibration's own scorer showed in an earlier iteration (see
`docs/findings/RESEARCHMAP-FINDINGS.md`); catching it here is a
reminder that a hand-audit remains part of the honest contradiction
count, not an optional polish.

### Fairness produced zero — a real finding, not a scorer failure

ml-fairness at 0/54 pairs mirrors LLM-calibration's 0/437. The reason
is domain-shaped: the fairness literature is organised around
IMPOSSIBILITY theorems (Kleinberg-Mullainathan-Raghavan;
Chouldechova). Once you know two fairness criteria are provably
incompatible in general, subsequent papers don't disagree — they pick
which criterion to prioritize for which decision and cite the
impossibility. That's `supports` or `none`, not `contradicts`.

## 3. Predictor check — was diet chosen against a wrong score?

Diet-and-mortality was picked despite its **0.44 (moderate)** contested
score, on the reputational grounds that meta-analyses in this field
famously disagree. The predictor put LLM-calibration at 0.818 (high)
and diet at 0.44 — the exact opposite ranking of what actual yield
turned out to be:

| library | predictor contested score | measured confirmed contradictions |
|:--|--:|--:|
| LLM calibration | 0.818 (high) | 0 |
| Diet & mortality | **0.44 (moderate)** | **7** |
| ML fairness | 0.667 (high) | 0 |

**Reputation beat the predictor.** The 0.44 rating understated diet's
actual contradiction yield by a factor of ∞ (compared to LLM-cal's
zero at 0.818). The `docs/findings/domain-coherence-predictor.md`
finding already flagged diet as the "predictor miss" case (high
modularity being ambiguous between "distinct schools argue" and
"distinct application areas don't interact"); this run confirms diet
sits in the "distinct schools argue" reading, not the neutral one.

Two of the three measurements now contradict the predictor's ranking.
The predictor discriminates by reputation (still true; see the
finding) but is now measured wrong on 2 of 3 ground-truth domains.

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
   ₹150 gate (actual hedge-stage spend: ₹28.93). Reported diet at 96%
   firm — same directional signal as the lexical run. **Halted with
   partial data**, so no cross-domain contrast to publish.
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
`hedge_diet-and-mortality` record the 200 calls that ran).

## 5. Full-text coverage effect

| library | full-text | share | scorers that depend on it |
|:--|--:|--:|:--|
| LLM calibration | 67 | 59% | persistent-limitations, orphaned-future-work |
| Diet & mortality | **17** | **17%** | same |
| ML fairness | 50 | 50% | same |

Diet's 17% is the run's worst by a wide margin. Biomedical journals
(Wiley, Elsevier, Oxford) are frequently not open-access; green-OA
copies often 403 at the publisher. Extracted from 59 diet papers,
only ~10 had full-text (17% × 59). The persistent-limitations scorer
draws from ~10 diet papers vs 67 LLM-cal papers — **any raw diet
limitation counts should be discounted by the coverage ratio (~6×)
when compared to LLM-cal**.

Fairness at 50% is closer to LLM-cal's 59% and gives that scorer
comparable footing.

Gap-type raw counts from extractions (`n_limitations`, `n_future_work`):

| library | n_limitations | n_future_work |
|:--|--:|--:|
| Diet & mortality | 88 (from 59 papers, ~10 full-text) | 37 |
| ML fairness | 114 (from 51 papers, ~25 full-text) | 76 |

## 6. Spend

Final ledger (`data/spend_ledger.json`):

| stage | calls | USD | INR |
|:--|--:|--:|--:|
| extract_diet | 59 | $2.806 | ₹235.69 |
| extract_fairness | 53 | $2.517 | ₹211.39 |
| contradiction_diet-and-mortality | 128 | $0.406 | ₹34.12 |
| contradiction_ml-fairness | 54 | $0.166 | ₹13.92 |
| unknown (embedding calls via generate) | 20 | $0.0006 | ₹0.05 |
| **Total NEW** | **314** | **$5.895** | **₹495.18** |
| Cap | | $10.12 | ₹850.00 |
| Remaining | | $4.22 | **₹354.82** |

Well under cap. The spend guard was armed the whole run but never
tripped — the mid-run halt of extractions to preserve budget was a
prudential call, not a guard-trip.

## 7. Cuts applied (in order)

- **(a) SKIP STRUCTURAL-HOLE LLM CONFIRMATIONS** — applied at dry-run.
- **(b) Tighten per-claim contradiction cap 4→2, threshold 0.72→0.80** —
  applied after the first diet shortlist produced 596 pairs (2-hour
  runtime). Cut pair count 5-6× with no meaningful quality loss (still
  found 7 real contradictions).
- **(c) Reduce corpus size** — not applied to the corpus itself (100
  kept per domain), but effectively applied via halting extraction at
  59+51 to preserve contradiction-pass budget.

## 8. What was skipped and why

- **Structural-hole LLM confirmations** — cut (a). Shortlists still
  fire deterministically over extractions; the LLM confirm step is
  a distinct rerunnable pass.
- **Future-work matching** — same rerunnable class. Raw future-work
  item counts still in each library's stats.json (37 diet, 76
  fairness).
- **Extraction papers 60-100 diet, 52-100 fairness** — halted for
  budget; cache is intact; a follow-up would resume from cache and
  add the remainder.
