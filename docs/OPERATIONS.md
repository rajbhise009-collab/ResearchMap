# Operations runbook

Two GitHub Actions workflows keep the site growing and watched. Nothing else
runs on its own. The website is static: visitors never trigger an API call,
so they cannot run up costs.

## What runs when

| Workflow | When | What it does | Costs |
|---|---|---|---|
| **Weekly grow** (`.github/workflows/weekly-grow.yml`) | Mondays 05:23 UTC (10:53 IST), or **Actions → Weekly grow → Run workflow** | Adds papers to every growing library, builds a queued library when money allows, checks everything, publishes only if every check passes | Gemini, paced by the money rule (below) |
| **Daily health** (`.github/workflows/daily-health.yml`) | Daily 06:41 UTC (12:11 IST), or by hand | Checks the live site (headers, sitemap, share images, search smoke checks) | Free |
| Vercel | On every push to `main` | Rebuilds and deploys the site | Free |

### Which libraries exist

`data/library_registry.json` is the one place a library is declared.

| status | meaning |
|---|---|
| `built` | On the site. Grown every week unless `frozen`. |
| `queued` | Prepared (rubric, papers, blind audit passed). The weekly run builds it when money allows. |
| `building` | Its extraction batch is submitted. The next weekly run finishes it. |
| `not-ready` | Failed its rubric audit. Never built automatically; see its `not_ready_reason`. |

LLM calibration is `frozen`. Its corpus is the baseline for the planned
validation test (tag `llm-cal-baseline-v1`).

## The money rule (the only spending limit)

`config/money.json`:

- **Ceiling** = `account_total_inr` − `safety_buffer_inr` (1500 − 50 = ₹1450).
- **Remaining:**
  - while `console_spent_inr` is empty: ceiling − the ledger total
    (`data/spend_ledger.json`). The ledger rounds projections up, so this is
    conservative;
  - once you fill in `console_spent_inr` and `console_spent_date`: ceiling −
    console_spent_inr − ledger spend recorded after that date.
- **Enforcement:** at call time, before every paid call, in every path
  (local, batch, Actions). A call that would cross it is refused.
- **Weekly budget** = min(₹60, remaining ÷ weeks left in a 12-week horizon
  starting 2026-10-12). It is recalculated every run.
- **Queued library:** built only when its extraction projection ×1.5 plus
  four weeks of growth fits what remains.
- **Padding:** every projection is padded before it is committed to
  (extraction ×1.5, classification ×2). A stage halts if the real cost per
  call exceeds 1.5× the projection. Batch state is saved, so nothing is paid
  twice.

Each run's Issue shows the remaining money, the weeks left and this week's
budget.

## One weekly run, step by step

1. **Checks.** The run stops if a secret is missing.
   - If `config/growth.json` says `"paused": true`, it does nothing except
     open its Issue.
   - If a `grow/<date>` branch from a failed run is still open, it collects
     what was already paid for but starts nothing new.
2. **Collect** last week's batches. Each is billed to the ledger once, at the
   batch rate. Papers that extracted cleanly join their library.
3. **Follow-on checks** on the new material, within the week's budget:
   - **The disagreement check.** New disagreements show as
     **"Flagged by the system, not yet checked"** and never count until you
     audit them.
   - **The future-work matcher.** Open questions keep their "weak" label.
   - **Method-transfer confirmation.** A lead is shown only after this check
     has looked at it.
4. **Finish a library being built**, if one was started last week. It gets
   the same checks, and its disagreements are flagged, not counted.
5. **Rebuild** site data, docs numbers and (when needed) share images.
6. **Submit** next week's papers. For each growing library:
   - find candidates with free OpenAlex queries (papers citing both sides of
     a checked disagreement, citing a paper whose open question is
     unanswered, or recently citing the library);
   - keep those its rubric accepts;
   - dedupe (id, DOI, title, full ingestion dedupe);
   - fetch open full text.

   The week's budget is then shared round-robin, one paper per library per
   round. Libraries with the most open candidates go first, then those with
   the fewest papers. At most 15 papers per library.
7. **Start a queued library** if it is affordable. Its extraction is
   submitted now and finished next week.
8. **Fingerprint and changelog:** `docs/releases/<date>.json` and
   `docs/CHANGELOG.md`.
9. **Publish gates.** Every one must pass:
   - full test suite, typecheck and production build;
   - the docs check and the cross-surface consistency script;
   - the banned-phrase tests and the search regression suite;
   - the hardening tests, the browser "curious visitor" checks, and the
     smoke checks on the built site.
10. **Publish.**
    - **All pass:** commit to `main` and push. Vercel deploys. After about
      5 minutes the run checks the live site.
    - **Any gate fails:** the site is not changed. The run's work goes to
      `grow/<date>`, and the bookkeeping (everything under `data/`) is
      committed to main so nothing paid for is lost.
11. **One Issue per run,** "Weekly grow — <date>".

### When something goes wrong

| what | what the run does | what you do |
|---|---|---|
| OpenAlex or Gemini hiccup | Retries with backoff (four tries). | Nothing. |
| Still failing after retries | Stops. Commits only the bookkeeping under `data/` to main (ledger, batch states, extractions), so paid work is kept. The site is unchanged, and next week resumes. | Nothing, unless it repeats for weeks. |
| Money runs out (at the start or mid-run) | No new spending. Batches already submitted are still collected. The site stays live. The Issue status says **BUDGET EXHAUSTED**. | Either enter the console's real spend in `config/money.json` (`console_spent_inr` plus `console_spent_date`; the ledger usually overstates, so this frees money), or add money and raise `account_total_inr`. Commit. |
| A publish gate fails | Site unchanged. Branch `grow/<date>` plus an Issue with the failing output. Later runs collect, but start nothing new while that branch exists. | Fix it on the branch, merge into main, delete the branch. |
| Missing or invalid secret | Stops before doing anything. | Add or replace the secret. |
| Live site fails after publishing | Reports it; nothing is auto-reverted. | Roll back (below). |

## What each Issue means

| Issue | Status line | What to do |
|---|---|---|
| Weekly grow — <date> | **published to main** | Read the new items. Audit any flagged pairs. |
| Weekly grow — <date> | **… BUDGET EXHAUSTED** | See the money row above. |
| Weekly grow — <date> | **publish gates failed — the site was not changed** | See "A run failed". |
| Weekly grow — <date> | **stopped cleanly — the site was not changed** | Read "What you need to do" in the Issue. |
| Weekly grow — <date> | **paused** | Nothing; set `paused` to false to resume. |
| Weekly grow — <date> | **… LIVE CHECK FAILED** | Roll back (below). |
| Daily health check failing | (open) | The live site failed its checks. It closes itself when they pass again. |

`needs-action` marks the Issues that need you.

## Auditing flagged disagreements

Each Issue lists new pairs with a checkbox and a link to the card. For each
pair:

1. Open the card and read both abstracts.
2. Decide one verdict:
   - `genuine`: same question, comparable populations, opposite findings;
   - `artifact`: they measure different things;
   - `duplicate`: the same disagreement as another pair.
3. Add the verdict to `data/domains/<library>/reasoning/contradiction_audit.json`
   under `verdicts`:
   ```json
   {"a_paper_id": "openalex:W…", "b_paper_id": "openalex:W…",
    "a_text_starts": "<first ~60 characters of claim A>",
    "b_text_starts": "<first ~60 characters of claim B>",
    "verdict": "genuine", "reason": "<one line>", "topic": "<short topic>"}
   ```
   The ids and texts are in `data/domains/<library>/reasoning/contradictions.json`.
4. Commit. The next run publishes it.

The workflow never writes to `contradiction_audit.json`, the frozen review
folders under `docs/review/`, or the baseline tag.

## Manual runs: cap and dry run

**Run workflow** (Actions → Weekly grow) takes two inputs. They apply only to
manual runs; scheduled Monday runs follow the money rule as described above.

| input | default | effect |
|---|---|---|
| `run_budget_inr` | 25 | Caps **total** spend for this run, in rupees. It is enforced at call time like the money rule: any paid call that would take the ledger past (ledger at the start of the run + this amount) is refused. |
| `build_queued` | false | When false, no queued library is started or finished in this run. |

**See what a run would spend, for free, before running it:**

```bash
.venv/bin/python tools/grow/run_weekly.py --dry-run
GROW_RUN_BUDGET_INR=40 GROW_BUILD_QUEUED=true .venv/bin/python tools/grow/run_weekly.py --dry-run
```

It prints, per library:

- the candidates found (free OpenAlex queries);
- the papers that would be submitted;
- the projected extraction and follow-on cost.

It also prints the cap and the remaining money afterwards. It makes no
Gemini call, writes no commit and opens no Issue.

## Pause, resume, change the pace

- **Pause everything:** set `"paused": true` in `config/growth.json` and
  commit. Set it back to `false` to resume. Or disable the workflow in the
  Actions tab.
- **Lower a week's budget:** the repository variable `WEEKLY_BUDGET_INR`, or
  the Run workflow form. It can only lower the computed budget, never raise
  it.
- **Change the pace** (₹60 cap, 12-week horizon, 4-week reserve for queued
  libraries): edit `config/money.json`.

## Roll back

- **Site broken:** Vercel → the project → **Deployments** → the previous
  deployment → ⋯ → **Promote to Production**.
- **Undo a week's data but keep the bookkeeping** (the money was spent):
  ```bash
  git revert --no-commit <weekly-grow-commit>
  git checkout <weekly-grow-commit> -- data/spend_ledger.json data/spend_projections.jsonl data/domains data/cache data/library_registry.json
  git commit -m "revert weekly grow <date> (bookkeeping kept)"
  ```

## A run failed (publish gate)

The Issue shows which gate failed and its output. The bookkeeping is already
on main. The rest of the run's work is on `grow/<date>`.

1. Fix the cause, on the branch or on main.
2. Merge `grow/<date>` into main, or delete it if the fix is on main.
3. Delete the branch. The next run returns to normal.

## Secrets and variables

| Name | Kind | Used by |
|---|---|---|
| `GEMINI_API_KEY` | secret | Weekly grow ("Grow, gate, publish" step only). Use a key restricted to the Generative Language API. |
| `OPENALEX_API_KEY` | secret | Weekly grow (same step) |
| `WEEKLY_BUDGET_INR` | variable (optional) | Lowers the computed weekly budget |
| `NEXT_PUBLIC_SITE_URL` | variable (optional) | Both workflows; default `https://researchmap-one.vercel.app` |

Secrets are never printed. Every message is redacted, and OpenAlex errors
never carry the request URL, which holds the key.

## Testing the workflows without spending anything

```bash
.venv/bin/python tools/grow/e2e_mock.py           # every gate where it matters
.venv/bin/python tools/grow/e2e_mock.py --quick   # gates skipped except scenario 7
.venv/bin/python tools/qa/synthetic_libs.py       # the UI with 8 libraries
```

The end-to-end test runs ten scenarios in a throwaway clone, with mocked
OpenAlex and Gemini, a temporary ledger and money config, and a local
stand-in for GitHub:

1. Two normal weeks, including a queued library built and published.
2. A missing secret.
3. An OpenAlex outage (bookkeeping kept) and the unblocked next week.
4. Money running out mid-run.
5. A failing gate and the run after it.
6. Pause and resume.
7. The health check going down and up.
