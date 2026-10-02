# Settled-state typing verification — 31/31 pass

- Date: 2026-10-02
- Build sha: `4d071d6d83e4ccfa75f3ee66111e484a13413c7e`
- Tool: Playwright + system Chrome; iPhone 13 descriptor + input events for mobile.
- 1500 ms wait after the LAST keystroke; assertions check SETTLED DOM.
- Target: production-mode static build served on 127.0.0.1:8765.
- Screenshots: `docs/review/screenshots/search3-*.png`.

[PASS] Diet main-box 'alc' settled + 1500ms @120ms
[PASS] Diet main-box 'alcohol str' settled @120ms
[PASS] Diet main-box 'red me' settled @120ms
[PASS] Diet ⌘K 'alc' settled @120ms
[PASS] ml-fairness main-box 'fair' settled @120ms
[PASS] ml-fairness 'demographic par' settled @120ms
[PASS] llm-cal 'halluc' settled @120ms
[PASS] llm-cal 'semantic ent' settled @120ms
[PASS] [diet-and-mortality] 'melanoma treatment' refuses settled @120ms
[PASS] [diet-and-mortality] 'camera cal' settled: no 'edge' lie @120ms
[PASS] [ml-fairness] 'melanoma treatment' refuses settled @120ms
[PASS] [ml-fairness] 'camera cal' settled: no 'edge' lie @120ms
[PASS] [llm-calibration] 'melanoma treatment' refuses settled @120ms
[PASS] [llm-calibration] 'camera cal' settled: no 'edge' lie @120ms
[PASS] Diet main-box 'alc' settled + 1500ms @40ms
[PASS] Diet main-box 'alcohol str' settled @40ms
[PASS] Diet main-box 'red me' settled @40ms
[PASS] Diet ⌘K 'alc' settled @40ms
[PASS] ml-fairness main-box 'fair' settled @40ms
[PASS] ml-fairness 'demographic par' settled @40ms
[PASS] llm-cal 'halluc' settled @40ms
[PASS] llm-cal 'semantic ent' settled @40ms
[PASS] [diet-and-mortality] 'melanoma treatment' refuses settled @40ms
[PASS] [diet-and-mortality] 'camera cal' settled: no 'edge' lie @40ms
[PASS] [ml-fairness] 'melanoma treatment' refuses settled @40ms
[PASS] [ml-fairness] 'camera cal' settled: no 'edge' lie @40ms
[PASS] [llm-calibration] 'melanoma treatment' refuses settled @40ms
[PASS] [llm-calibration] 'camera cal' settled: no 'edge' lie @40ms
[PASS] MOBILE Diet main-box 'alc' settled (input events)
[PASS] MOBILE ml-fairness 'demographic par' settled
[PASS] MOBILE Diet 'melanoma treatment' refuses settled
