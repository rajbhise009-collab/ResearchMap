# Operations runbook

Two GitHub Actions workflows keep the site growing and watched. Nothing else
runs on its own. The website itself is static: visitors never trigger an API
call, so they cannot run up costs.

## What runs when

| Workflow | When | What it does | Costs |
|---|---|---|---|
| **Weekly grow** (`.github/workflows/weekly-grow.yml`) | Mondays 05:23 UTC (10:53 IST), or **Actions → Weekly grow → Run workflow** | Adds new papers to the Diet & mortality and ML fairness libraries, checks them, rebuilds the site data, and publishes only if every check passes | Gemini, capped (below) |
| **Daily health** (`.github/workflows/daily-health.yml`) | Daily 06:41 UTC (12:11 IST), or run it by hand | Checks the live site (headers, sitemap, share images, search smoke checks) | Free |
| Vercel | On every push to `main` | Rebuilds and deploys the site | Free |

The LLM calibration library is **not** grown. Its corpus is the frozen
baseline for the planned validation test (git tag `llm-cal-baseline-v1`).

### One weekly run, step by step

Each run does two things, a week apart: it collects the batch it submitted
last week, and it submits a new one.

1. **Safety checks.** The run stops if a required secret is missing, if the
   lifetime ledger has no headroom, or if an earlier run's `grow/<date>`
   branch is still unmerged (the bookkeeping on `main` would be out of date).
2. **Collect.** Last week's Gemini batch is fetched and billed to
   `data/spend_ledger.json` once, at the batch rate (half price). Papers that
   extracted cleanly join their library. Papers that failed are listed in the
   Issue and left out.
3. **Follow-on checks** on the new material. Each one runs only if its
   projection fits this week's budget:
   - the disagreement check on new claim pairs. A new disagreement shows on
     the site as **"Flagged by the system, not yet checked"** and never counts
     in any headline until you audit it;
   - the future-work matcher, which decides whether new papers answer old
     open questions and whether the new papers' own questions are open.
     Open questions keep their "weak" label;
   - confirmation of method-transfer leads. A lead is shown only after this
     check has looked at it.
4. **Rebuild** the site data, the generated numbers in the docs, and (only
   when what they show changed) the share images.
5. **Submit** next week's batch. For each library the run:
   - finds candidates with free OpenAlex queries: papers that cite both sides
     of a checked disagreement, papers that cite a paper whose open question
     is still unanswered, and recent papers that cite the library;
   - keeps only those the library's labelling rubric accepts;
   - removes duplicates (same id, DOI or title; the full ingestion dedupe;
     anything already in the library or already pending);
   - fetches open-access full text where it exists;
   - submits at most 15 papers per library, fewer if the budget runs out.
6. **Release fingerprint** (`docs/releases/<date>.json`) and a changelog
   entry (`docs/CHANGELOG.md`).
7. **Publish gates.** Every one must pass:
   - full test suite, typecheck and production build;
   - the docs-numbers check and the cross-surface consistency script;
   - the banned-phrase tests and the search regression suite;
   - the hardening tests, the browser "curious visitor" checks, and the
     smoke checks on the built site.
8. **Publish.**
   - **All gates pass:** commit to `main` and push. Vercel deploys. After
     about 5 minutes the run checks the live site.
   - **Any gate fails:** nothing goes to `main`. The run's work goes to the
     branch `grow/<date>`.
9. **One Issue per run,** titled "Weekly grow — <date>".

## What it costs

- **Weekly budget:** `WEEKLY_BUDGET_INR`, default **₹25**. This covers new
  spending decided in that run, with every projection padded before
  committing to it: extraction ×1.5, classification ×2. Last week's batch,
  collected this week, was paid for out of last week's budget.
- **Lifetime ceiling:** the ledger's `cap_inr` (₹1200). It is enforced in
  code before every paid call. At the ceiling the run stops and opens an
  Issue.
- **Typical cost:** about ₹1 per abstract-only paper at the batch rate. Full
  text costs more. So ₹25 a week means roughly 10–15 new papers.
- **OpenAlex:** a few dozen free credits a week.
- **Your Google Cloud billing cap** is separate from all of this and is not
  changed by anything here.

To see the spend: each run's Issue gives "recorded this run", "new
commitments" and the lifetime total. The ledger itself is
`data/spend_ledger.json` (append-only).

## What each Issue means

| Issue | Status line | What to do |
|---|---|---|
| Weekly grow — <date> | **published to main** | Read the new items. Audit any flagged pairs (below). |
| Weekly grow — <date> | **publish gates failed — nothing published** | See "A run failed". |
| Weekly grow — <date> | **stopped cleanly — nothing published** | The Issue's "What you need to do" section says exactly what. Typical causes: a missing or invalid secret, Gemini or OpenAlex down (re-run later), lifetime ceiling reached, an unmerged `grow/<date>` branch. |
| Weekly grow — <date> | **… LIVE CHECK FAILED** | See "Roll back". |
| Daily health check failing | (open) | The live site failed its checks. Look at the output; roll back if the site is broken. It closes itself when the checks pass again. |

Issues labelled `needs-action` need you; `weekly-grow` alone means the run
was routine.

## Auditing flagged disagreements

Each run's Issue lists new pairs with a checkbox and a link to the card. For
each pair:

1. Open the card. Read both abstracts (linked from the card).
2. Decide one verdict:
   - `genuine`: same question, comparable populations, opposite findings;
   - `artifact`: they measure different things;
   - `duplicate`: the same disagreement as another pair.
3. Add the verdict to `data/domains/<library>/reasoning/contradiction_audit.json`,
   in the `verdicts` list:
   ```json
   {"a_paper_id": "openalex:W…", "b_paper_id": "openalex:W…",
    "a_text_starts": "<first ~60 characters of claim A>",
    "b_text_starts": "<first ~60 characters of claim B>",
    "verdict": "genuine", "reason": "<one line>", "topic": "<short topic>"}
   ```
   The ids and texts are in `data/domains/<library>/reasoning/contradictions.json`.
4. Commit to `main`. The next weekly run publishes the result. To publish it
   sooner, run `python -m backend.app.api.multi_library_export`, then
   `cd frontend && npm run build` locally, and commit.

The workflow never writes to `contradiction_audit.json`, the frozen review
folders under `docs/review/`, or the baseline tag. Your verdicts are only
ever changed by you.

## Pause growth

- **Pause:** Actions → **Weekly grow** → ⋯ → **Disable workflow**. Re-enable
  it the same way.
- **Run with (almost) no new spending:** set the repository variable
  `WEEKLY_BUDGET_INR` to `0`. The run still collects a batch already
  submitted (that spending already happened) and embeds the collected
  papers' claims (fractions of a rupee; the site cannot be rebuilt
  without them), but submits nothing and runs no paid checks.

## Change the weekly budget

GitHub → repo **Settings → Secrets and variables → Actions → Variables** →
`WEEKLY_BUDGET_INR` (create or edit). The value is in rupees, for example
`25`. A manual run also takes a one-off value in the **Run workflow** form.
The lifetime ceiling still applies whatever the weekly value is.

## Roll back

- **The site is broken:** Vercel → the project → **Deployments** → the
  previous deployment → ⋯ → **Promote to Production**. This is instant and
  changes nothing in git. Nothing is ever auto-reverted.
- **A week's data should be undone:** revert that run's commit, but keep
  the bookkeeping. The money was spent, and the batch state lets the next
  run collect what was paid for:
  ```bash
  git revert --no-commit <weekly-grow-commit>
  git checkout <weekly-grow-commit> -- data/spend_ledger.json data/spend_projections.jsonl data/domains/diet-and-mortality/grow data/domains/ml-fairness/grow
  git commit -m "revert weekly grow <date> (bookkeeping kept)"
  ```

## A run failed

The Issue shows which gate failed, with its output. The run's work is on
`grow/<date>`. Growth is paused until that branch is gone, because it
carries the ledger update.

1. Look at the failure. Fix it on the branch, or on `main` if the cause is
   there.
2. Merge `grow/<date>` into `main`. This keeps the spend record and the
   pending batch.
3. Delete the branch. The next run (or a manual one) proceeds normally.

Delete the branch without merging only if its Issue says the run recorded
no spend and submitted nothing.

## Secrets and variables

| Name | Kind | Used by |
|---|---|---|
| `GEMINI_API_KEY` | secret | Weekly grow (the "Grow, gate, publish" step only). Use a key restricted to the Generative Language API. |
| `OPENALEX_API_KEY` | secret | Weekly grow (same step) |
| `WEEKLY_BUDGET_INR` | variable (optional) | Weekly grow; default 25 |
| `NEXT_PUBLIC_SITE_URL` | variable (optional) | Both workflows; default `https://researchmap-one.vercel.app` |

Secrets are never printed: every message the runner writes is passed
through a redaction step. To rotate a key, replace the secret value in
Settings; nothing in the repository changes.

## Testing the workflows without spending anything

```bash
.venv/bin/python tools/grow/e2e_mock.py           # ~40 min, every gate
.venv/bin/python tools/grow/e2e_mock.py --quick   # gates skipped
```

This runs seven scenarios in a throwaway clone, with mocked OpenAlex and
Gemini, the clone's own copy of the ledger, and a local stand-in for GitHub:
two normal weeks, a missing secret, an OpenAlex outage, the unmerged-branch
guard, a failing gate, and the daily health check going down and up.
