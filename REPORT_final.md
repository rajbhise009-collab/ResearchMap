# REPORT — final run: publish-ready, unsupervised-safe, weekly growth (2026-10-08)

## Money

- **Spent this run: ₹32.22**, all in Part 1 (ML fairness future-work matching, batch rate). Nothing else this run made a paid call. The workflow tests used mocks only.
- **Ledger:** ₹958.55 of the ₹1200 lifetime ceiling (raised from ₹990 as you approved, and enforced at call time). That leaves ₹241.45 of headroom, about 9 weeks at the full ₹25 weekly budget.
- The Google console cap is unchanged.

## Visible results per library (Part 2)

Results the confirmation step labelled "not addressing" or "trivial" are now listed under **Set aside after checking**, with the reason in plain words. They are not counted and not searchable.

| Library | Before Part 2 | After Part 2 | After Part 1 (final) | Set aside |
|:--|--:|--:|--:|--:|
| LLM calibration | 76 | 66 | 66 | 10 |
| Diet & mortality | 12 | 12 | 12 | 5 |
| ML fairness | 3 | 1 | **55** (1 persistent limitation + 54 open questions) | 2 |

**Consistency:** `frontend/scripts/consistency.mjs` checks every count and title across the surfaces below. It runs before and after `next build`, so any mismatch fails the build and the tests:

- home card, toggle and /gaps;
- the library page and /method;
- search, the sitemap and gap page titles;
- share images and the findings doc.

## Part 3: the curious-user hunt

**Coverage:**

- `tools/qa/hunt.py`: 76 browser checks, all passing on Chromium and on WebKit.
- `backend/tests/api/test_hardening.py`: 10 source, data and TypeScript tests.
- `tools/qa/smoke.py`: 44 checks across Chromium and WebKit, desktop and iPhone 13.

| # | Issue found | Fix | Test |
|--:|:--|:--|:--|
| 1 | The query words `constructor`, `__proto__` and `toString` **crashed search**, because they matched built-in object properties instead of the index. | Index lookup tables get a null prototype. | `test_prototype_words_do_not_break_search`; hunt "inject" |
| 2 | Control, zero-width and bidi characters and nulls were kept, and long queries were echoed in full. | `cleanQuery` strips them and caps queries at 200 characters; echoes are capped at 80 inside `<bdi>`; React escapes all HTML. | `test_clean_query_strips_and_caps`; hunt: 10 injection inputs plus `?q=` with script |
| 3 | Diet questions phrased as advice showed results without a prominent caution. | The not-advice note leads Diet results. Advice-like queries add "We can't tell you what to eat or drink. This only shows what research papers report." | 10 advice queries: `test_advice_queries_are_recognised` and hunt "medical" |
| 4 | Offensive or off-topic queries were offered "build a library on this". | A small panel-only blocklist (self-harm, sexual, slur stems, personal names) hides the offer. Self-harm queries also get a crisis-line note. Ordinary off-topic subjects still get the offer. | `test_panel_blocklist`; hunt "offensive" |
| 5 | An author's email address in an OpenAlex abstract was republished. | Redacted to "[email address removed]". | `test_no_costs_or_contact_emails_in_shipped_data` |
| 6 | Per-library spend figures were shipped in public stats. | Removed; costs appear only where /method states them. | same test; `test_api` |
| 7 | "/" and ⌘K/Ctrl+K could fire while typing in another field. | Both are ignored in any input, select or editable field. "/" belongs to the search box where there is one. Focus returns when the palette closes. | hunt "keyboard" (4 checks) |
| 8 | A denied clipboard failed silently. A double-click downloaded twice. | Plain "Your browser blocked copying…" message. Repeat downloads within 1 s are ignored. | hunt "races" |
| 9 | Some new-tab links lacked `noopener`. | `rel="noopener noreferrer"` everywhere. | `test_every_new_tab_link_has_noopener` |
| 10 | With JavaScript disabled the page was an empty shell. | A plain `<noscript>` message. | hunt "env" |
| 11 | Forced-colours mode lost focus rings and chip borders, and there was no print style. | `@media (forced-colors)` and `@media print` rules. | hunt "env" |
| 12 | Hidden results (set aside or unconfirmed) could be found through search. | The search index holds visible results only. | `test_search_per_library` |
| 13 | Search index key order changed on every export, so each export showed spurious diffs. | Sorted; exports are byte-identical. | checked by double export |

**Verified with no change needed:**

- **URL abuse:** 17 malformed or hostile paths each give the on-brand 404 or the default library, never a blank page or a stack trace.
- **Races:** rapid library switching, back/forward through search states, and two tabs on different libraries all behave.
- **Small screens:** 320 px, 200 % zoom and landscape phone show no horizontal scroll on 4 page types.
- **Simulated page translation, and offline after first load:** search still answers.
- **Raw HTML:** the only `dangerouslySetInnerHTML` is the static theme script, which only sets light or dark.
- **Open questions:** all 185 are verbatim quotes with their paper.
- **"Weekly":** no page mentions it until the growth test passes (`test_no_claim_of_automatic_growth_until_it_runs`).

**Abuse cost:** the site makes **no** paid or rate-limited call at runtime. The hunt records every request host across 7 page types plus the library-request flow: only the site itself. A source test forbids `fetch` to OpenAlex, Gemini, Semantic Scholar, Unpaywall or Europe PMC. OpenAlex and Gemini are build-time and workflow-time only.

**Secrets scan** of the built output and every JS bundle found no API-key patterns, no `.env` values (the only matches are non-secret names), no `/Users` or `ResearchMap-private` paths, and no email addresses other than site.config's.

**`?dev=1` on production shows nothing.** The developer view is compiled out of public builds: `NEXT_PUBLIC_ENABLE_DEV` is unset on Vercel, so the context stays off and no banner or block renders. The hunt checks 4 pages for 12 internal markers.

In local developer builds only, `?dev=1` shows the banner "Developer mode is on — showing raw scores, scorer internals, and pipeline provenance", plus:

- raw values and component scores;
- pipeline provenance;
- underlying JSON;
- the local pre-flight API.

## Part 4: unsupervised operations

`.github/workflows/weekly-grow.yml` and `.github/workflows/daily-health.yml` replace `weekly-refresh.yml`. Their security:

- triggers are `schedule` and `workflow_dispatch` only;
- actions are pinned by commit SHA;
- permissions are minimal (grow: contents and issues write; health: contents read, issues write);
- secrets go only into the one step that needs them, and every message is redacted.

`backend/tests/grow` enforces all of this.

The full flow, phases and Issue meanings are in **docs/OPERATIONS.md**. In short: collect last week's batch (billed once, batch rate), budget-gated follow-on checks, rebuild, submit the new batch (₹25 × 1.5 padding, plus the lifetime ceiling), fingerprint and changelog, gates, then main or `grow/<date>`, a live check, and one Issue.

**Mocked end-to-end test** (`tools/grow/e2e_mock.py`): a throwaway clone, a local bare repository standing in for GitHub, mocked OpenAlex and Gemini, the clone's own copy of the ledger, and file-backed Issues. **Result: 38/38 checks passed, every publish gate run for real** (marker `docs/releases/growth-e2e-passed.json`, tested commit `23d80c9`).

| Scenario | Checked |
|:--|:--|
| 1. Week 1 | Exits 0. Main advanced (`ls-remote` = local). A batch pending per library. Issue "published". Fingerprint records every gate passing. |
| 2. Week 2 | Papers added to both libraries: exactly the submitted ones that extracted cleanly. The planted DOI duplicate, title duplicate, twin and off-topic record were dropped. Last week's batch was billed at the batch rate. Site facts show the new counts. A new disagreement shows as "Flagged by the system, not yet checked" and does not count. Every shown method-transfer lead was confirmed. The Issue has an audit checklist, and a changelog entry was written. |
| 3. Missing secret | Exit 2, nothing pushed. The Issue names the secret to add. The secret that *was* set appears nowhere. |
| 4. OpenAlex down after collecting | Exit 2, main untouched. Work and spend record pushed to `grow/<date>`. The Issue explains. |
| 5. Unmerged `grow/*` | Refuses to run: nothing spent, nothing submitted. The Issue names the branch. |
| 6. Failing gate | Exit 1, nothing to main, `grow/<date>` pushed. The Issue shows the failed gate's output. |
| 7. Daily health | Site down: Issue opened. Site up: Issue closed. |
| All | The real ledger was never touched, and no secret appears in any Issue. |

**What the test found and I fixed:**

- A fresh checkout could not rebuild the site (needed data was gitignored).
- LLM calibration's "built" date came from a file's mtime.
- A result dissolved by new papers kept a stale page in the sitemap.
- Gates ran tests before the build, so 19 rendered-output tests silently skipped.
- Two tests froze the disagreement count at 10. They now pin the hand audit by hash and allow new, unaudited pairs.
- My own search test caught a mock artifact.

No real paid call was made in testing.

## Part 6: verify and publish

**Local, on the final build:**

- **Tests:** 673 passed, with nothing skipped because a build was missing.
- **Typecheck and production build:** pass, and the consistency script runs inside the build.
- **Docs check:** current.
- **Browser hunt:** 76/76 on Chromium and 76/76 on WebKit.
- **Smoke checks: 44/44** across Chromium and WebKit, desktop and iPhone 13:
  - a Diet shared link with no `?lib` opens Diet;
  - Diet "alc", ML fairness "fair" and LLM calibration "halluc" give results including gaps;
  - "melanoma treatment" refuses on all three libraries;
  - axe finds 0 serious or critical issues on 3 page types;
  - no console errors.

**Pushed** (each confirmed by exit code 0 and `git ls-remote` equal to the local sha):

- `iteration-2` → `4efa6c6`;
- `main` → `4efa6c6`, fast-forward from `9fb1222`;
- tag `llm-cal-baseline-v1` → `994cbf5` (annotated, on `0a25083`).

One small tools/report commit follows; its sha is in the summary.

**Production, about 4 minutes after the push** (https://researchmap-one.vercel.app):

- **Live check:** 0 failed, 11 passed, 1 warning (the analytics script returns 404 until you enable Web Analytics), 2 skipped (no custom domain yet).
- **Smoke checks: 44/44.** The new /method "How the libraries grow" section is live.
- **Hunt against production: 73 site checks pass.** Three hostile URLs never reach the site. Vercel's edge refuses them with its own plain response (no internals, no stack trace) instead of the on-brand 404, and a static site cannot change that:
  - `/gap/%00/` → 400 "Bad request";
  - `/gap/..%2f..%2fetc%2fpasswd/` → 400 "Bad request";
  - `/data/../../etc/passwd` → 403 "Forbidden" (Vercel firewall).

  The hunt now records these as platform refusals, and only when Vercel's own headers are present.

No revert was needed.

## What you need to do (I can't do these)

1. **Secrets, then one run:** add the GitHub secrets `GEMINI_API_KEY` (a **new** key restricted to the Generative Language API) and `OPENALEX_API_KEY`, then run **Weekly grow** once from the Actions tab. Its first real run only submits a batch; papers arrive the following Monday.
2. **Google Cloud budget alert** on the project that owns the key.
3. **Enable Vercel Web Analytics.**
4. **Name, domain, `NEXT_PUBLIC_SITE_URL` and contact email.** Set the URL in Vercel and as a GitHub Actions variable.
5. **Legal review** of /terms and /privacy.
6. **The expert review.**

These steps are also in `docs/LAUNCH.md` §11. The runbook is `docs/OPERATIONS.md`.

## Decisions I made (flag if you disagree)

- **LLM calibration is not grown.** It is the frozen baseline for the still-owed validation phase (tag `llm-cal-baseline-v1`).
- **Committed data.** A fresh checkout could not rebuild the site, so I committed about 22 MB of previously ignored data:
  - the extraction cache (no full text);
  - LLM calibration's reasoning and relationship outputs;
  - the claim embeddings;
  - slimmed OpenAlex records;
  - the corpus manifest.

  Full text of papers is still never committed.
- **Weekly budget scope.** It counts this run's new commitments. Collecting last week's batch is recorded, but it counts against last week's budget.
- **Failed runs.** If a run fails after spending, its ledger update would exist only on `grow/<date>`. So every later run refuses to spend until that branch is merged or deleted.
- **Results that dissolve.** A result that new papers dissolve loses its page (404) and is listed in that run's Issue under "no longer shown".
- **Copy on /method and /about.** These say the two libraries are "set up to grow once a week", next to counted figures: papers added by weekly runs so far (0) and the last date (none yet). They do not promise growth that has not happened.
