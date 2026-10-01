# Headless-Chrome verification

- Date: 2026-10-01
- Tool: Chrome `--headless=new --dump-dom --screenshot` against `frontend/out` served on `127.0.0.1:8765`.
- Fresh `--user-data-dir` per invocation (no stored library bleed).
- Screenshots: `docs/review/screenshots/*.png`.

**29 pass / 0 fail.**

- [PASS] Diet /gaps renders (DOM non-empty)
- [PASS] Diet /gaps shows topic title "Red meat and stroke"
- [PASS] Diet /gaps shows topic title "Alcohol and stroke"
- [PASS] Diet /gaps shows topic title "J-shaped"
- [PASS] Diet /gaps shows topic title "Red meat and type-2 diabetes"
- [PASS] Diet /gaps genuine titles have no "genuinely" verdict word in any h3
- [PASS] Diet /gaps has "Flagged but set aside (2)" or similar
- [PASS] Diet /gaps shows the "Checked by hand" label chip
- [PASS] Diet /gaps shows coverage note "Claims read from 59 of 100 papers"
- [PASS] Diet /gaps DOES NOT contain the backwards "bounded above" wording
- [PASS] Diet /gaps DOES NOT contain the jargon "budget halt"
- [PASS] ml-fairness /gaps renders
- [PASS] ml-fairness /gaps shows the plain "Zero here means" sentence
- [PASS] ml-fairness /gaps shows "Claims read from 51 of 100 papers"
- [PASS] llm-cal /gaps renders
- [PASS] llm-cal /gaps does NOT show a verdict-chip (no audit data for this lib)
- [PASS] Diet gap detail renders a topic-specific h1 (not the verdict text)
- [PASS] Diet gap detail shows "Checked by hand against the abstracts" chip
- [PASS] Diet gap detail has a BibTeX button
- [PASS] Diet gap detail has a CSV button
- [PASS] Diet gap detail has a timeline section
- [PASS] Diet paper detail renders single-entry BibTeX section
- [PASS] Footer on diet-home says "100 papers on diet and all-cause mortality"
- [PASS] Footer on ml-fairness-home says "100 papers on algorithmic fairness in machine learning"
- [PASS] Footer on llm-cal-home says "113 papers on language-model reliability"
- [PASS] Diet /papers lists real diet papers (not just LLM-cal)
- [PASS] ?dev=1 does NOT load the Vercel Analytics script
- [PASS] Footer privacy note states queries are NOT sent to any server
- [PASS] Footer libraries intro no longer promises /library/<slug>/ URLs
