# Repository audit — 2026-10-05

Read-only audit before advertising the site. Scripts and logs are kept
outside the repo (`~/ResearchMap-private/launch-qa/`). Nothing was deleted,
rewritten or rotated.

## Visibility

`GET https://api.github.com/repos/rajbhise009-collab/ResearchMap` → **200:
the repository is public.** `site.config.json` has `repoIsPublic: true`.

## Secrets

All 131 commits reachable from any ref (`git rev-list --all`: `main`,
`phases-5-6-7`, `pre-push-backup`, `origin/*`) were scanned with `git grep`.
Values were never printed.

| check | result |
|:--|:--|
| literal value of `GEMINI_API_KEY` from `.env` | 0 hits |
| literal value of `OPENALEX_API_KEY` from `.env` | 0 hits |
| `AIza…` (Google key pattern) | 0 hits |
| `ghp_…` / `github_pat_…` | 0 hits |
| long values assigned to `*_API_KEY` / `TOKEN` / `SECRET` | 0 hits |
| `sk-…` | 4 locations, all false positives: the words "ta**sk-**dependent-performance" and "ta**sk-**and-model-specific-training" inside limitation categories in two LLM-calibration paper JSON files |
| `.env` (any non-example env file) tracked in any commit | none |

**No secret found.**

## Answer keys

- No answer-key file is reachable from any ref on GitHub (`main`,
  `iteration-2`).
- Locally, the old in-repo key path
  (`docs/review/diet-contradictions/_answer_key_DO_NOT_SHARE/`) is reachable
  only from the local branch `pre-push-backup`, which has never been pushed.
- **However, GitHub still serves some earlier commits by SHA** (from the push
  that commit `eac5be9` describes), and the old key file can be downloaded
  from them. The old key records paper IDs per item, so rotating the shuffle
  seed did not hide which v1 pairs were flagged and which were controls. The
  commit identifiers and the measured overlap are kept outside the repo
  (`~/ResearchMap-private/launch-qa/answer-key-exposure.md`) so this page does
  not point to them. Removing them needs a GitHub Support request; see the
  launch report.

## Large files

No file at HEAD is over 5 MB. `docs/review/` holds 46.6 MB, mostly QA
screenshots (largest 2.46 MB) that the site never reads at runtime; they are
left in place (removing them from history would be a rewrite). From this run
on, QA screenshots go to `~/ResearchMap-private/launch-qa/`.
