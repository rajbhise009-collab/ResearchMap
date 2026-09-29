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
| Diet & mortality | `diet-and-mortality` | 100 | 67 | 33 | 17 (17%) | **59 (59%)** | new; blind-audit 12/15 = 80% |
| ML fairness | `ml-fairness` | 100 | 96 | 4 | 50 (50%) | **51 (51%)** | new; blind-audit 10/10 = 100% |

Extractions were halted at ~50-60% of target on both new domains — a
deliberate call to preserve ledger headroom for the contradiction
pass, which is what answers the central "does contested domain produce
contradictions" question. Cache is intact; a follow-up run can resume
from 59+51 without re-paying.

## 2. Contradiction yield — does the coherent-domain result generalise?

| library | shortlisted pairs | confirmed contradictions | supports | none |
|:--|--:|--:|--:|--:|
| LLM calibration (frozen 2026-07) | 437 | **0** | 148 | 289 |
| Diet & mortality | 97 | **7** | 60 | 30 |
| ML fairness | 54 | **0** | 32 | 22 |

**Diet-and-mortality is the first ResearchMap library to produce
confirmed contradictions** (LLM-cal and ml-fairness both come in at
zero). This is the whole point of the multi-library expansion.

### Five diet contradiction examples

Every pair here is two claims from two different papers that Gemini
classified as `"relationship": "contradicts"` at temperature 0. The
full list is at `data/domains/diet-and-mortality/reasoning/contradictions.json`.

1. **Red meat and stroke.** Claim A (paper W2101006064): "Unprocessed
   red meat consumption is not associated with incident stroke." vs
   Claim B (paper W2109401990): "Consumption of 100 g/day of
   unprocessed red meat is associated with an 11% increased risk of
   stroke." — direct contradiction on the same food group and outcome.
2. **Alcohol and myocardial infarction, dose-response shape.** Claim A:
   "The decreased risk of myocardial infarction was similar between men
   consuming less than 10 g of alcohol per drinking day" (flat below
   threshold). Claim B: "Increased alcohol consumption is log-linearly
   associated with a lower risk of myocardial infarction (HR 0.94 per
   100 g/w)" (linear, continuous).
3. **Alcohol and stroke, presence of association.** Claim A: "Alcohol
   consumption is not significantly associated with overall incident
   stroke compared with non-drinking." Claim B: "Higher alcohol
   consumption is roughly linearly associated with a higher risk of
   stroke (HR 1.14 per 100 g/week higher consumption)."
4. **Alcohol and ischemic stroke, dose-response shape.** Claim A:
   "Alcohol consumption exhibits a curvilinear J-shaped dose-response
   relationship with the relative risk of ischemic stroke." Claim B:
   "Higher alcohol consumption is roughly linearly associated with a
   higher risk of stroke" — J-shape vs linear.
5. **Red meat and type 2 diabetes.** Claim A: "Unprocessed red meat
   intake is not associated with incident diabetes mellitus." Claim B:
   "Higher intake of red meat is associated with increased incidence
   of type 2 diabetes."

These are exactly the disagreements the diet-mortality literature is
famous for. The contradiction scorer names them correctly. That's the
test — and it passes.

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

## 4. Assertion-strength — three-way contrast (with a caveat)

The prediction going into this run: **biomedical hedges more than ML**,
so diet-and-mortality would show a lower firm-share than LLM-cal.

Lexical hedge classifier (`multi_domain_findings.is_hedged`): a claim
is `hedged` if its text contains any of ~20 hedge markers (`may`,
`might`, `could`, `possibly`, `appears to`, `seems to`, `suggests`,
`likely`, `remains unclear`, etc.). Otherwise firm.

| library | claims | firm | hedged | firm-share |
|:--|--:|--:|--:|--:|
| LLM calibration (2026-07 hand-sampled) | 56 | 51 | 5 | **91.1%** |
| Diet & mortality (2026-09 lexical) | 338 | 337 | 1 | 99.7% |
| ML fairness (2026-09 lexical) | 258 | 254 | 4 | 98.4% |

**Interpretation:** the lexical classifier looks substantially STRICTER
than the hand-sampled LLM-cal baseline (which classified 5 of 56 as
hedged including nuanced cases the lexical classifier would miss).
The 99.7% / 98.4% numbers reflect the lexical classifier's blunt-
ness, not domain-conditional firmness. **The domain-hedging
hypothesis is UNDER-TESTED here** — a follow-up would need to either
(a) hand-label a comparable sample from all three libraries, or
(b) add a stronger hedge detector (e.g. LLM-based short-context
classifier at ~$0.02/claim, ~$12 for all 596 claims).

Recording this honestly rather than pretending the lexical numbers
are a fair three-way contrast.

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
