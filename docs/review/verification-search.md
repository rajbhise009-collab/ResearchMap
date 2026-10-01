# Search verification (real typing) — 8/8 pass

- Date: 2026-10-01
- Tool: Playwright + system Chrome, fresh browser context per check.
- Target: production-mode static build served on 127.0.0.1:8765.
- Screenshots: `docs/review/screenshots/search-*.png`.

[PASS] Diet main-box: 'alcohol' returns the alcohol gaps
[PASS] Diet main-box: 'red meat' returns the red-meat gaps
[PASS] Diet ⌘K: 'alcohol' returns alcohol gaps
[PASS] ml-fairness main-box: 'fairness' returns results
[PASS] LLM-cal main-box: 'hallucination' returns results
[PASS] diet-and-mortality main-box: OOD query refuses honestly
[PASS] ml-fairness main-box: OOD query refuses honestly
[PASS] llm-calibration main-box: OOD query refuses honestly
