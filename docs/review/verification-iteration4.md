# Iteration-4 verification — 40/40 pass

- Date: 2026-10-02
- Build sha (HEAD of the tree the static build was made from): `c18d684baea9ca3d6e5024eb2c9c7df6fe2b61ea`
- Playwright + system Chrome; fresh context per check; library via ?lib=<slug>.
- Settled state: 1500 ms after the last keystroke. Mobile: iPhone 13 descriptor, insertText input events.
- Expected values are read from the shipped JSON, not hard-coded.
- Screenshots: `docs/review/screenshots/iter4-*.png`.

[PASS] settled main box: diet-and-mortality 'alc' → results, no refusal/edge
[PASS] settled main box: diet-and-mortality 'alcohol str' → results, no refusal/edge
[PASS] settled main box: diet-and-mortality 'red me' → results, no refusal/edge
[PASS] settled main box: ml-fairness 'fair' → results, no refusal/edge
[PASS] settled main box: ml-fairness 'demographic par' → results, no refusal/edge
[PASS] settled main box: llm-calibration 'halluc' → results, no refusal/edge
[PASS] settled main box: llm-calibration 'semantic ent' → results, no refusal/edge
[PASS] settled ⌘K: diet 'alc' → alcohol gaps
[PASS] settled: llm-calibration 'melanoma treatment' refuses or stays neutral
[PASS] settled: llm-calibration 'camera cal' refuses or stays neutral
[PASS] settled: diet-and-mortality 'melanoma treatment' refuses or stays neutral
[PASS] settled: diet-and-mortality 'camera cal' refuses or stays neutral
[PASS] settled: ml-fairness 'melanoma treatment' refuses or stays neutral
[PASS] settled: ml-fairness 'camera cal' refuses or stays neutral
[PASS] ml-fairness 'fair' empty-state matches gap-card count (0)
[PASS] diet stats card shows disagreement-check coverage line
[PASS] diet stats card shows claims-read coverage line
[PASS] diet /gaps headline cards = audited-genuine count (5)
[PASS] diet /gaps genuine titles distinct
[PASS] diet /gaps titles contain no verdict words
[PASS] diet set-aside section count matches audit (5)
[PASS] diet set-aside titles all shown
[PASS] diet unaudited section present iff unaudited pairs exist (0)
[PASS] diet /gaps shows disagreement-check coverage line
[PASS] diet /gaps consumer view hides raw counts
[PASS] production build ignores ?dev=1 (no raw counts on public deploys)
[PASS] genuine gap page renders cites-both (or honest empty state)
[PASS] genuine gap page renders the timeline
[PASS] BibTeX download parses (2 entries, no undefined/null)
[PASS] CSV download parses (2 rows)
[PASS] ml-fairness shows true claims-read coverage
[PASS] ml-fairness shows disagreement-check coverage
[PASS] ml-fairness zero-note shown iff confirmed = 0
[PASS] footer follows ml-fairness
[PASS] llm-cal data unchanged (113 papers, 76 gaps)
[PASS] llm-cal shows no verdict labels
[PASS] footer follows llm-cal
[PASS] footer follows diet
[PASS] MOBILE diet 'alc' (insertText) settled
[PASS] MOBILE genuine gap page renders title + timeline

## Dev-mode checks (separate ENABLE_DEV=1 build)

[PASS] dev build: /gaps?dev=1 shows raw counts (raw_flagged=10)
[PASS] dev build without ?dev=1: consumer view hides raw counts

## First run (at 131e23e) — 37/40, fixed before this run

- `ml-fairness 'fair'` showed "at the edge of this library": at full
  coverage "fair" had become a vocabulary word and was judged alone.
  Fixed in c18d684 (a word that starts a more frequent library term is
  still being typed; typing-time only).
- `llm-calibration 'camera cal'` sat in the typing state instead of
  refusing: iteration 3's code turned any refusal into "typing" when the
  last word was a prefix. Fixed in c18d684 (complete tokens drive the
  verdict).
- `?dev=1` raw counts "missing" in the production build: correct
  behaviour (dev mode is inert unless built with ENABLE_DEV=1). The
  check was wrong; it now asserts the production build ignores ?dev=1,
  and the dev-build checks above confirm the raw counts render there.
