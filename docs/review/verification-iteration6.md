# Iteration-6 verification — 55/55 pass

- Date: 2026-10-04
- Build sha (HEAD of the tree the static build was made from): `ac11a98453374cc4df034c6a1f1cb1e4f4c7fe21`
- Production static build (`npm run build`, no ENABLE_DEV), served from frontend/out.
- Playwright + system Chrome; fresh context per check; library via ?lib=<slug>.
- Settled state: 1500 ms after the last keystroke.
- Denylist imported from backend/tests/api/test_public_claims.py.
- Screenshots: `docs/review/screenshots/iter6-*.png`.

[PASS] llm-calibration: /findings/RESEARCHMAP-FINDINGS renders, no denylisted phrase
[PASS] llm-calibration: /findings/corpus-scaling-study renders, no denylisted phrase
[PASS] llm-calibration: /findings/domain-coherence-predictor renders, no denylisted phrase
[PASS] llm-calibration: /findings/duplicate-check-v2 renders, no denylisted phrase
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
[PASS] diet-and-mortality: /findings/duplicate-check-v2 renders, no denylisted phrase
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
[PASS] ml-fairness: /findings/duplicate-check-v2 renders, no denylisted phrase
[PASS] ml-fairness: /findings/duplicate-check renders, no denylisted phrase
[PASS] ml-fairness: /findings/fulltext-vs-abstract-finding renders, no denylisted phrase
[PASS] ml-fairness: /findings/ledger-reconciliation-2026-10-02 renders, no denylisted phrase
[PASS] ml-fairness: /findings/ledger-unknown-entries renders, no denylisted phrase
[PASS] ml-fairness: /findings/multi-domain renders, no denylisted phrase
[PASS] ml-fairness: multi-domain shows 'Why zero? Not established' with hypotheses (a)-(c)
[PASS] ml-fairness: /findings/new-library-scorer-status renders, no denylisted phrase
[PASS] ml-fairness: /findings/phase4-investigations renders, no denylisted phrase
[PASS] ml-fairness stats card shows 99 papers and the true coverage
[PASS] footer lists ml-fairness with 99 papers
[PASS] diet-and-mortality: /library shows the audit-doubts section (2 items)
[PASS] ml-fairness: /library shows the audit-doubts section (1 items)
[PASS] llm-calibration: multi-domain findings show the audit-doubts section
[PASS] diet-and-mortality: multi-domain findings show the audit-doubts section
[PASS] ml-fairness: multi-domain findings show the audit-doubts section
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
