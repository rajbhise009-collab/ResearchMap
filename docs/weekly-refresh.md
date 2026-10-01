# Weekly refresh

A free, LLM-free GitHub Actions workflow that scans OpenAlex each week
for newly-published works that might be relevant to this repository's
libraries. The results land as a single GitHub Issue per run. **The
workflow never writes to the repo and never adds anything to a library
on its own.**

Last verified against the live free OpenAlex: 2026-10-01.

## What it does

Per library, per week, two kinds of free OpenAlex queries fire:

1. **cites-both of a confirmed-genuine contradiction pair.** Works
   published in the last ~10 days that cite BOTH sides of a disagreement
   that the audit confirmed as genuine. A later paper discussing both
   sides is the clearest signal that the question is still alive.

2. **cites of the paper behind an orphaned future-work item.** For
   each "what should be studied next" that is still unaddressed, the
   workflow asks OpenAlex for works published in the last ~10 days
   that cite that source paper. The thinking: new citers are the
   plausible place for someone to have picked it up.

Each result is deduped against:
- the library it would belong to (via `papers.json`), and
- the other candidates in the same run,
using a 4-pass check: same OpenAlex wid, same DOI, same normalised
title + same year, same normalised title (any year, for the
arxiv/published sibling case).

The deduped candidates are rendered into one GitHub Issue titled
"Weekly refresh candidates — YYYY-MM-DD". The body **says explicitly
that `flagged` is not `confirmed`** and that no corpus addition
happens. The reader is the next step.

## What it doesn't do

- No LLM calls. No paid APIs.
- No commits to `main`.
- No auto-publishing.
- No per-item classification. A human (or a later pipeline stage)
  decides whether a candidate is worth ingesting.
- No notification spam — one issue per run, labelled
  `weekly-refresh`.

## Requirements

- Repo secret `OPENALEX_API_KEY` (OpenAlex retired the polite-pool
  mailto on 2026-02-13; unauthenticated requests return 409 now).
  The workflow fails loudly if the secret is empty.
- Permissions in the workflow: `issues: write` + `contents: read`.
  Nothing else.

## Schedule

The workflow runs weekly on Mondays at 09:00 UTC
(`cron: "0 9 * * 1"`) and is also runnable from the Actions tab via
`workflow_dispatch` with optional overrides for `lookback_days` and
`top_n`.

**GitHub pauses scheduled workflows after 60 days of repository
inactivity** (no pushes, no human-triggered runs). If this repo goes
quiet for two months the workflow will stop firing until someone
pushes a commit or triggers a run manually. If that happens the
pipeline is unchanged — rerun from the Actions tab or push an empty
commit.

## Dry-run locally

```bash
# with a key (live OpenAlex, uses ~N credits per library):
OPENALEX_API_KEY=sk-... python -m backend.app.refresh.weekly_candidates \
  --slugs diet-and-mortality --lookback-days 10 \
  --out /tmp/wr.json --body-out /tmp/wr.md

# without a key (fixture mode, no network):
python -m backend.app.refresh.weekly_candidates \
  --dry-run-fixture backend/tests/refresh/fixture_sample.json \
  --slugs diet-and-mortality --out /tmp/wr.json --body-out /tmp/wr.md
```

The CLI prints the issue body to stdout and (optionally) writes a
JSON result + the markdown body to files. The GitHub Actions step
runs this exact CLI.

## Costs

Zero dollars per week in the normal case:
- OpenAlex free tier: 10k requests/day. One run touches at most a
  few dozen queries (one per genuine pair + one per orphaned
  future-work item, across the 3 libraries).
- GitHub Actions free-tier minutes for a public repo: unlimited.
- No LLM.

## Honesty invariants

Enforced by the module and tested in
`backend/tests/refresh/test_weekly_candidates.py`:

- The issue body states that `flagged` is not `confirmed`.
- An empty result renders an "Honest zero" sentence rather than a
  misleadingly-worded fallback.
- The `OPENALEX_API_KEY` guard fails the job with a clear message
  rather than running zero queries silently.
- Dedupe is applied against the shipped library AND among candidates;
  the same work never appears twice.
