# Launch verification — 2026-10-05

Production static build (`npm run build`, no ENABLE_DEV) of the tree at
`d995aa1` (plus docs-only commits after it), served by `tools/qa/serve.py`, which
mirrors Vercel: trailing-slash 308s, 404.html with a 404 status, and the
`vercel.json` headers. Fresh browser context per check; settled waits. Raw
logs and all screenshots: `~/ResearchMap-private/launch-qa/` (not in the
repo). Curated screenshots: `docs/review/screenshots/launch-*.jpg`.

| section | checks | result |
|:--|--:|:--|
| Shared links: each library's gap and paper with no ?lib, right ?lib, wrong ?lib, storage blocked; 2 unknown ids | 22 | 22 pass |
| Console: errors + hydration warnings, every page type per library, trust pages, 404 | 24 | 24 pass (re-run alone; see below) |
| Failure modes: snapshot JSON 404 ×9, slow 3G, blocked storage | 11 | 11 pass |
| Search: Chromium + WebKit × desktop + iPhone 13 (insertText) × 9 queries | 36 | 36 pass (re-run alone; see below) |
| axe-core 4 (WCAG 2.1 AA), 10 pages × light + dark | 20 | 0 serious/critical |
| Keyboard: skip link, search, switcher, open result, gap page focus, reduced motion | 8 | 8 pass |
| Internal link crawl: 418 rendered pages, 501 internal links | 501 | 0 broken |
| External sample: 40 doi.org/OpenAlex links, 1 req/s | 40 | 19 OK (16 × 200, 3 × 202); 21 × 403 from publishers refusing automated requests (reported, not failed) |

Run history:
- First passes found and fixed: llm-cal gap titles overwritten client-side;
  colour contrast (caveat labels, warn tag, dark not-advice box); unfocusable
  BibTeX preview; no focus ring on summary/pre; CLS 0.52–0.76; ~1 MB of
  every library's documents embedded in every page; double-prefixed DOI
  links (26 of 40 sampled). QA-side bugs fixed: the server did not
  URL-decode paths; two test expectations were wrong.
- The final full run (all sections at once) had 4 failures, all while the
  link crawl was hitting the same single-process server at the same time:
  3 × `net::ERR_CONNECTION_RESET` console errors and 1 mobile search with 0
  results. Re-run with the server otherwise idle: console 24/24, search
  36/36.
- WebKit installed (Playwright webkit-2359) and ran the search suite.

Lighthouse 12.8.2, mobile, second (final) pass:

| page | performance | accessibility | best practices | SEO | LCP | CLS |
|:--|--:|--:|--:|--:|--:|--:|
| home | 89 | 100 | 96 | 66 | 3.6 s | 0.082 |
| /gaps | 80 | 98 | 96 | 66 | 5.3 s | 0 |
| gap page | 80 | 100 | 96 | 66 | 5.5 s | 0 |

SEO 66 is the deliberate `noindex` of a non-production build; the
production simulation (`VERCEL_ENV=production`) emits `index, follow`.
Best practices 96 is the Vercel analytics script, which exists only on
Vercel (404 on the local server). The local server does not compress, so
LCP and weight are worse than on Vercel's CDN.

Page weight (uncompressed, cold cache, Diet library): home 30 requests /
924 KB; /gaps 34 / 846 KB; gap 31 / 792 KB; paper 31 / 809 KB; /about 20 /
574 KB. A typical visit (home → search "alc" → open a gap) made 45
same-origin requests, all to this site's edge.
