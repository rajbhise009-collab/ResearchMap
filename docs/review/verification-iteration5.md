# Iteration-5 verification — 45/45 pass

- Date: 2026-10-04
- Build sha (HEAD of the tree the static build was made from): `c1b88728e71106d21129b42ac2a874fc5705c756`
- Production static build (`npm run build`, no ENABLE_DEV), served from frontend/out.
- Playwright + system Chrome; fresh context per check; library via ?lib=<slug>.
- Settled state: 1500 ms after the last keystroke.
- Denylist imported from backend/tests/api/test_public_claims.py.
- Screenshots: `docs/review/screenshots/iter5-*.png`.

[PASS] llm-calibration: /findings/RESEARCHMAP-FINDINGS renders, no denylisted phrase
[PASS] llm-calibration: /findings/corpus-scaling-study renders, no denylisted phrase
[PASS] llm-calibration: /findings/domain-coherence-predictor renders, no denylisted phrase
[PASS] llm-calibration: /findings/duplicate-check renders, no denylisted phrase
[PASS] llm-calibration: /findings/fulltext-vs-abstract-finding renders, no denylisted phrase
[PASS] llm-calibration: /findings/ledger-reconciliation-2026-10-02 renders, no denylisted phrase
[PASS] llm-calibration: /findings/ledger-unknown-entries renders, no denylisted phrase
[PASS] llm-calibration: /findings/multi-domain renders, no denylisted phrase
[PASS] llm-calibration: multi-domain shows 'Why zero? Not established' with hypotheses (a)-(c)
[PASS] llm-calibration: /findings/new-library-scorer-status renders, no denylisted phrase
[PASS] llm-calibration: /findings/phase4-investigations renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/RESEARCHMAP-FINDINGS renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/corpus-scaling-study renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/domain-coherence-predictor renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/duplicate-check renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/fulltext-vs-abstract-finding renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/ledger-reconciliation-2026-10-02 renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/ledger-unknown-entries renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/multi-domain renders, no denylisted phrase
[PASS] diet-and-mortality: multi-domain shows 'Why zero? Not established' with hypotheses (a)-(c)
[PASS] diet-and-mortality: /findings/new-library-scorer-status renders, no denylisted phrase
[PASS] diet-and-mortality: /findings/phase4-investigations renders, no denylisted phrase
[PASS] ml-fairness: /findings/RESEARCHMAP-FINDINGS renders, no denylisted phrase
[PASS] ml-fairness: /findings/corpus-scaling-study renders, no denylisted phrase
[PASS] ml-fairness: /findings/domain-coherence-predictor renders, no denylisted phrase
[PASS] ml-fairness: /findings/duplicate-check renders, no denylisted phrase
[PASS] ml-fairness: /findings/fulltext-vs-abstract-finding renders, no denylisted phrase
[PASS] ml-fairness: /findings/ledger-reconciliation-2026-10-02 renders, no denylisted phrase
[PASS] ml-fairness: /findings/ledger-unknown-entries renders, no denylisted phrase
[PASS] ml-fairness: /findings/multi-domain renders, no denylisted phrase
[PASS] ml-fairness: multi-domain shows 'Why zero? Not established' with hypotheses (a)-(c)
[PASS] ml-fairness: /findings/new-library-scorer-status renders, no denylisted phrase
[PASS] ml-fairness: /findings/phase4-investigations renders, no denylisted phrase
[PASS] llm-calibration: footer shows corrected library notes
[PASS] diet-and-mortality: footer shows corrected library notes
[PASS] ml-fairness: footer shows corrected library notes
[PASS] settled: diet-and-mortality 'alc' → 13 results present, no banner
[PASS] settled: ml-fairness 'fair' → 5 results present, no banner
[PASS] settled: llm-calibration 'halluc' → 24 results present, no banner
[PASS] settled: llm-calibration 'melanoma treatment' refuses
[PASS] settled: diet-and-mortality 'melanoma treatment' refuses
[PASS] settled: ml-fairness 'melanoma treatment' refuses
[PASS] llm-calibration: /library shows no spend figure
[PASS] diet-and-mortality: /library shows no spend figure
[PASS] ml-fairness: /library shows no spend figure

## Run history

- Run 1: 45/45, but its "results present" check only looked for the query
  word in the page text, which "fair" passes trivially (it is in the
  library's name). Tightened to count `.results-list` children.
- Run 2 (tightened): 44/45. `ml-fairness 'melanoma treatment' refuses`
  failed once with the page text stopping at "skip to content" (not
  hydrated when read). Repeated alone 5 times in fresh contexts: refused
  5/5. Recorded as a timing flake, not a product bug.
- Run 3 (tightened, this file): 45/45.
