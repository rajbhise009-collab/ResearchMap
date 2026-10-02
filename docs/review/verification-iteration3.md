# Iteration-3 verification — 15/15 pass

- Date: 2026-10-02
- Build sha: `be0b8710cc7855974529cb63608d05bb8ab5e7f5`
- Tool: Playwright + system Chrome; iPhone 13 for mobile.
- 1500 ms wait after last keystroke; checks the SETTLED DOM.
- Screenshots: `docs/review/screenshots/iter3-*.png`.

[PASS] settled: diet-and-mortality 'alc' — results + no banner
[PASS] settled: diet-and-mortality 'alcohol str' — results + no banner
[PASS] settled: diet-and-mortality 'red me' — results + no banner
[PASS] settled: ml-fairness 'demographic par' — results + no banner
[PASS] settled: llm-calibration 'halluc' — results + no banner
[PASS] settled: llm-calibration 'semantic ent' — results + no banner
[PASS] settled: diet-and-mortality 'melanoma treatment' refuses
[PASS] settled: ml-fairness 'melanoma treatment' refuses
[PASS] settled: llm-calibration 'melanoma treatment' refuses
[PASS] diet /gaps: set-aside (2) section visible
[PASS] diet /gaps: Alcohol and stroke title present
[PASS] diet home: stats show 100/100 coverage
[PASS] ml-fairness home: 73 of 100 coverage
[PASS] llm-cal home: 113 + no verdict labels
[PASS] MOBILE diet 'alc' settled: alcohol + no refusal

## Post-audit additions (same day)

The original 15 checks accepted any "paper" text for ml-fairness "fair",
so they could not detect a wrong zero-gap message. After switching the
zero-gap condition to count actual gap cards (a code-only
persistent-limitations yield had made ml-fairness say "No gaps match"
instead of "no gaps to show yet"):

- [PASS] ml-fairness 'fair' settled: "This library has no gaps to show yet." + zero-note present
- [PASS] diet-and-mortality 'mediterranean' settled: gaps shown or "No gaps match this search."
