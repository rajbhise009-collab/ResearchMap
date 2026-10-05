# ResearchMap — launch-readiness report

**2026-10-05.** Goal: safe to advertise on a real domain. No paid API calls;
`data/spend_ledger.json` is byte-identical to the start of the run (SHA-256
`01d9c8a9…733c` before and after). 631/631 backend tests, typecheck,
production build, `doc_numbers --check` and the LLM-cal fingerprint test
(4/4) pass. Git status clean.

**Preview HEAD:** this report is committed on top of the commit recorded in
the chat summary; the exact pushed HEAD is `git rev-parse origin/iteration-2`
(a commit cannot contain its own sha).

## Read this first — the old answer key is still downloadable from GitHub

**No secret (API key or token) was found** in any of the 131 commits reachable
from any ref, so no rotation is needed.

The blind-review answer key, however, is not fully private:

- No branch on GitHub contains it.
- GitHub still serves 3 earlier commits by their identifiers, from the push
  described in commit `eac5be9`, and the old key file downloads from each of
  them (HTTP 200 on both the contents API and raw.githubusercontent).
- That old key lists the paper IDs for every item. **7 of the 11 distinct
  (paper pair → flagged or control) mappings in today's v1 key match it**, so
  rotating the shuffle seed did not hide which v1 pairs are controls.
- v2 items 01–12 are the v1 items, so v2 is affected too.

The commit identifiers are kept out of the repo, in
`~/ResearchMap-private/launch-qa/answer-key-exposure.md`. **Your options:**
1. Ask GitHub Support to remove the cached views and unreferenced commits.
   Their "Removing sensitive data from a repository" guide ends with this
   step. Give them the three SHAs from the private file.
2. Treat both packets as partly unblinded and build a v3 with new controls
   before sending anything to experts.

Nothing was attempted.

## Part 0 — repository audit (`docs/review/repo-audit.md`)

- **Visibility:** public (GitHub API 200). `repoIsPublic: true` is set in
  `frontend/site.config.json`.
- **Secrets:** none.
  - 0 hits for the literal `GEMINI_API_KEY` and `OPENALEX_API_KEY` values.
  - 0 hits for `AIza…`, `ghp_` / `github_pat_`, or long values assigned to
    `*_API_KEY` / `TOKEN` / `SECRET`.
  - 4 `sk-` hits, all false positives inside the words
    "ta**sk-**dependent-performance" and "ta**sk-**and-model-specific-training".
  - No `.env` file was ever tracked.
- **Answer keys:**
  - Not reachable from any GitHub ref.
  - Reachable locally only from the unpushed branch `pre-push-backup`.
  - Still served by SHA on GitHub (above).
- **Large files:** none over 5 MB at HEAD. `docs/review/` holds 46.6 MB of
  QA screenshots the site never reads; they are left in place (removing
  them from history would be a rewrite). From this run on, QA artefacts go
  to `~/ResearchMap-private/launch-qa/`.

## Part 1 — shared links

**Owner resolution.** Each gap and paper page knows at build time which
libraries own its id; across all libraries there are 86 gap ids and 312 paper
ids, none shared. If a link has no `?lib`, or a `?lib` that doesn't own the
id, the page:
- switches to the owner;
- rewrites `?lib` in the address bar;
- stores the choice when storage is available;
- tells the switcher, footer and palette;
- shows "Opened in the <library> library".

With several owners, `?lib` decides, otherwise the default library.

**Other changes:**
- All storage goes through `lib/storage.ts`, wrapped in try/catch.
- Unknown ids get an on-brand 404 with search and library links. The old
  "not in this library" text is gone.
- "How to cite" and a new "Copy link" use the canonical absolute URL with
  `?lib`.
- Diet gap and paper pages show the not-advice note inline.

**Playwright, 22/22.** Each library's gap and paper were opened with no
`?lib`, the right `?lib`, a wrong `?lib` and storage blocked, each checking
the heading, page title, resulting `?lib`, notice and stored choice. Two
unknown ids returned a 404 page. ml-fairness has no gap cards, so only its
paper was tested.

## Part 2 — domain, SEO, share previews

- **One site URL.** `NEXT_PUBLIC_SITE_URL` (fallback
  `https://researchmap-one.vercel.app`) is the only host. `grep` over
  `frontend/app`, `lib`, `scripts` and the config finds no other host
  besides that fallback constant and a code comment.
- **One site name.** `site.config.json` `siteName` drives the wordmark,
  footer, every title, share images, the manifest and the cited name. The
  Python language pack reads the same file.
- **Per-page metadata.** Every page gets a title, description, canonical
  URL, Open Graph and Twitter tags, built from data at build time.
  - The 418 titles are unique: 8 cards shared 3 headlines, and their page
    titles now add the problem paper's title.
  - No verdict words appear in titles or descriptions (test).
  - Every Diet gap and paper description ends "not dietary or medical
    advice." (test).
- **Share images.** `tools/og/make_og_images.py` renders 1200×630 cards from
  the CSS tokens and `site-facts.json`: llm-calibration 50 KB, diet 46 KB,
  ml-fairness 56 KB, default 67 KB. It also makes the apple-touch, 192 and
  512 icons.
- **Sitemap and robots.** `sitemap.xml` has 418 URLs with no `?lib`
  duplicates. Listing pages are canonical without `?lib` because their
  static file is identical for every library. Non-production builds emit
  `noindex, nofollow` and a disallow-all `robots.txt`; the production
  simulation emits `index, follow` and points to the sitemap.
- **Web manifest** and light/dark `theme-color` are in place.

## Part 3 — trust pages and config

- **New pages:** /about, /method, /privacy, /terms and /contact, linked
  from the nav (About) and the footer (all five).
- **/method numbers** come from `site-facts.json`, written by
  `backend/app/api/site_facts.py`: per-library papers, claims read, full
  text vs abstract, build date (with its basis), and pairs checked, flagged,
  kept and set aside. It says plainly that hand checks were done by the
  builder, and that the expert packet exists but has not been sent.
- **/contact:** there is no email configured and the repo is public, so it
  shows the GitHub Issues link only. Empty fields are never shown.
- **"Build a library" panel:** the consumer view now shows one paragraph
  pointing to /contact. Prices, hours, the pre-flight lookup and the
  predictor note appear only under `?dev=1`.
- **Launch check:** `npm run launch-check` is a gate, not part of the build.

**Launch-check output, local build (expected 6/8):**

```
PASS  contact route configured (contactEmail or repoIsPublic)  — contactEmail=empty, repoIsPublic=true
FAIL  build uses a custom https NEXT_PUBLIC_SITE_URL (not *.vercel.app)  — canonical host in build: researchmap-one.vercel.app; env not set now
PASS  no "TODO" / "placeholder" / "lorem" in page text
PASS  no localhost (or vercel.app, once a custom URL is set) in canonical/OG tags
PASS  sitemap.xml and robots.txt present  — 418 URLs
FAIL  built as production: crawlable robots.txt and no noindex  — robots.txt disallows everything (non-production build)
PASS  analytics script present (Vercel Web Analytics)
PASS  every page title unique (418 pages)
6/8 passed
```

With `NEXT_PUBLIC_SITE_URL=https://example.org VERCEL_ENV=production` the
same check passes **8/8**, and no `vercel.app` string appears anywhere in the
built HTML.

## Part 4 — honest copy

- **Headline kept:** "Find research questions nobody has answered yet."
- **Qualifier added directly under it:** "Results come only from the papers
  in the selected library. They are a starting point for reading, not a
  verdict."
- **Built line:** home and the library page show "Library built <date> · N
  papers · claims read from N of M" from data. "Built" is defined per
  library in `data/library_builds.json`: llm-calibration 2026-07-30,
  diet-and-mortality 2026-10-02, ml-fairness 2026-10-04.
- **No refresh claims:** nothing on the public site mentions weekly or
  automatic updates. /about says libraries "do not update themselves".

**Three alternative headlines** (not applied):
1. "See which questions a field's papers leave open."
2. "Open research questions, traced back to the papers that raised them."
3. "Find the questions a body of research left unanswered."

**Every public string changed:**

| where | before → after |
|:--|:--|
| `what_it_does` (home lede, meta) | "…questions a paper said needed studying that nobody followed up on, problems that several teams independently ran into, and methods… that might solve a problem in another" → "…that no later paper in the library followed up on, problems that several teams ran into, findings that appear to disagree, and methods… that might help with a problem in another" |
| `headline_qualifier` | new (above) |
| `no_disagreements.headline` | "No disagreements found — and that is a real result." → "No disagreements found among the pairs we checked." |
| `no_disagreements.body` | claimed "every pair… that could plausibly disagree" was checked and that "the papers… largely agree… rather than arguing" (a hypothesis stated as fact) → says only similar pairs were compared, that this is a measurement not proof, and that why is not established |
| `one_library_note` | "reading thousands of papers… only this one exists so far" (false) → "Each library is built one subject at a time… only a few subjects are covered so far." |
| `privacy_note.body` | removed the sentence about an unwired query scrubber (not a live feature) |
| `search.out_of_domain.build_cta` | "Build a library for this" → "Want a library on this subject?" |
| `build_library.title` | "Building a new library" → "Libraries on new subjects" |
| `build_library.consumer_body` | new: "Libraries are built one subject at a time, and there isn't one on this subject yet. If you'd like one, you can suggest it on the contact page." |
| `build_library.predictor_note` (dev only) | dropped the stale "one confounded by partial extraction" |
| Hero stats card | "Confirmed disagreements" → "Disagreements kept after checking"; the summed "Gaps found" fallback → "Results you can open" (actual card count) |
| 404 page | "Not in this library…" → on-brand "That page isn't here." with search and library links |
| Gap pages | new "Our own doubt:" note on the two doubted Diet verdicts; new "Opened in the … library" notice |
| Nav / footer | "About" added to nav; About · Method · Privacy · Terms · Contact · report a problem added to footer |
| Cite | the citation's site name comes from config; a "Copy link" button was added |
| Page titles / descriptions | new for every page (built from data) |
| New pages | /about, /method, /privacy, /terms, /contact |

## Part 5 — quality gates (`docs/review/verification-launch.md`)

| gate | result |
|:--|:--|
| Shared links (Chromium) | 22/22 |
| Console errors + hydration warnings, every page type per library | 24/24 |
| Failure modes (9 snapshot-JSON 404s, slow 3G, blocked storage) | 11/11 — always a message or loading line, never blank |
| Search: Chromium + **WebKit** × desktop + iPhone 13 (insertText) | 36/36 |
| axe-core 4, WCAG 2.1 AA, 10 pages × light + dark | 0 serious/critical (after fixes) |
| Keyboard + reduced motion | 8/8 |
| Internal link crawl | 418 rendered pages, 501 internal links, **0 broken** |
| External sample (40 doi.org/OpenAlex, 1/s) | 19 OK; 21 × 403 from publishers refusing automated requests (reported only) |

The final all-sections run had 4 failures, all while the link crawl was
loading the same single-process test server: 3 × `ERR_CONNECTION_RESET` and
one mobile search with 0 results. Re-run alone, console and search passed
60/60.

**Bugs found and fixed:**
- Colour contrast in three places.
- Missing focus rings on `summary`/`pre`, and a BibTeX preview that couldn't
  get keyboard focus.
- CLS of 0.52–0.76.
- Every page embedded about 1 MB of every library's documents.
- **Double-prefixed DOI links** (`https://doi.org/https://doi.org/…`) on the
  two new libraries: 26 of 40 sampled links.
- llm-calibration gap pages overwrote their unique title on the client.

**Lighthouse mobile, final (second) pass:**
- Performance: home 89, /gaps 80, gap 80 (first pass: 55 / 69 / 65).
- CLS: 0.082 / 0 / 0.
- Accessibility: 100 / 98 / 100.
- Best practices: 96 on all three. This is the Vercel analytics script,
  absent on the local server.
- SEO: 66, because of the deliberate local `noindex`.
- The local server does not compress, so Vercel should do better. That has
  not been measured on Vercel.

**Page weight** (uncompressed, cold cache):

| page | requests | size |
|:--|--:|--:|
| home | 30 | 924 KB |
| /gaps | 34 | 846 KB |
| gap page | 31 | 792 KB |
| paper page | 31 | 809 KB |
| /about | 20 | 574 KB |

**Edge requests per typical visit** (home → search "alc" → open a gap, one
cold browser session): **45**, all to this site. A returning visitor with a
warm cache would make fewer; that was not measured.

**Security headers** were added to `vercel.json`: nosniff,
`strict-origin-when-cross-origin`, a Permissions-Policy denying camera,
microphone, geolocation and payment, and `X-Frame-Options: DENY`. The file
parses, and a structural comparison shows every other key unchanged; the
textual diff adds only a comma after `trailingSlash`. **No CSP** this run:
the static export relies on inline scripts, and a CSP would need hashes kept
in step with every build.

## Part 6 — docs

- `README.md` rewritten for a public reader, with no counts, private paths
  or secrets.
- `CITATION.cff`: version 1.0.0 (from `frontend/package.json`), MIT. The
  author is the entity "ResearchMap contributors", because `authorName` is
  empty and CFF requires an author.
- `docs/LAUNCH.md`: your manual steps, in order.

## Failed, skipped or worth knowing

- Commit `a18afde` does not typecheck on its own (its page files landed in
  the next commit). Left as is: no history rewrites.
- Not measured: performance on Vercel's CDN, real share-preview rendering
  on social platforms, and whether the 21 publisher 403s open in a normal
  browser.
- The weekly-refresh GitHub workflow is unchanged. It fails without an
  `OPENALEX_API_KEY` secret; `docs/LAUNCH.md` step 9 asks you to set the
  secret or disable the workflow.

## Needs your decision

1. The answer-key exposure (top of this report).
2. Fill in `frontend/site.config.json` (contact email; name and affiliation
   are optional). Then follow `docs/LAUNCH.md`.
3. Keep the headline, or choose one of the three alternatives.
4. Weekly-refresh workflow: set the secret or disable it.
