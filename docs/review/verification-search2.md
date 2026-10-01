# Search polish verification (real typing) — 7/7 pass
- Date: 2026-10-01
- Tool: Playwright + system Chrome, fresh context per check.
- 120 ms per keystroke; banner-presence check between keystrokes.
- Target: production-mode static build served on 127.0.0.1:8765.
- Screenshots: `docs/review/screenshots/search2-*.png`.

[PASS] Diet main-box: 'alcohol' type-ahead, no mid-type refusal
[PASS] Diet main-box: 'red meat' type-ahead
[PASS] Diet ⌘K: 'al' empty + 'alc' returns alcohol gaps
[PASS] ml-fairness: 'fairness' shows '0 gaps · M papers'
[PASS] ml-fairness: 'demographic parity' in-domain (no edge banner)
[PASS] LLM-cal: 'hallucination' + 'semantic entropy' return results
[PASS] 'melanoma treatment' refuses per library after Enter — no mid-type flash
