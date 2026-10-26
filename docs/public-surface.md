# What the public site serves

The site is a static export: everything in `frontend/public/` is copied into
`frontend/out/`, and everything in `frontend/out/` is served to anyone at
https://www.research-map.com. Nothing else in the repository is deployed.
`backend/tests/api/test_public_surface.py` fails if build-time-only material
reaches either folder (it runs in CI and in every publish gate, after the
build).

## Public by design (the browser needs it)

| served | why |
|:--|:--|
| HTML pages (`/`, `/gaps/`, `/gap/<id>/`, `/paper/<id>/`, `/papers/`, `/findings/…`, `/method/`, `/about/`, `/contact/`, `/privacy/`, `/terms/`, `404`) and their `index.txt` (Next's page payload) | the pages themselves |
| `_next/static/…` | the compiled site (JavaScript and CSS); no source maps are built or shipped |
| `og/*.png`, icons, `manifest.webmanifest` | share images, browser icons |
| `robots.txt`, `sitemap.xml` | search-engine indexing of the pages |
| `prefetch.js` | warms the library list before the page script runs |
| `data/libraries.json`, `data/site-facts.json`, `data/language.json` | library list, the facts and wording every page shows |
| per library (`data/` for the default, `data/library/<slug>/` for the rest): `opportunities.json`, `opportunity/<id>.json`, `papers.json`, `paper/<id>.json`, `stats.json`, `findings.json`, `search-index.json`, `language.json`, `meta.json`; plus `data/validation.json` (the method page) | what the pages fetch: results, their evidence trail, the papers behind them, the counts and caveats, the published findings, in-browser search |

The paper files carry the paper's title, year, venue, DOI, abstract (from
OpenAlex) and the claims, methods, limitations and future-work items
extracted from it, each with its paper ID: the site's traceability rule. The
result files carry the scores and caveats the pages show.

`/findings/` publishes the files in `docs/findings/` (rendered from
`findings.json`), except notes whose first line is
`<!-- internal: not published -->`: they stay in the repo and are not
exported. The ledger notes and the scorer-status note are marked so. Any
other file put in that folder becomes public.

## Build-time only (never deployed)

| kept in the repo, not served | where |
|:--|:--|
| raw corpora, scope and records files, prelabelled sets | `data/domains/` |
| extraction cache, relationship layer, embeddings | `data/cache/`, `data/relationships/` |
| the spend ledger, money and growth config, pending batch files, queued-build log | `data/spend_ledger.json`, `config/`, `data/domains/*/grow/`, `data/grow/` |
| prompts | `backend/app/extraction/prompts/` |
| rubrics, labelling and review packets, answer keys | `docs/rubrics/`, `docs/review/`, `backend/app/review/` (answer keys live outside the repo) |
| proposals and internal docs | `docs/proposals/`, `docs/*.md`, reports at the repo root |
| claim-relationship export (`relationships.json`) | no longer exported: no page read it, and it carried pipeline fields (`prompt_hash`, `detector_model`) |

## How the test decides

A deployed file fails if any folder in its path is one of `docs`, `review`,
`proposals`, `rubrics`, `domains`, `cache`, `grow`, `config`, `backend`,
`tools`, `scratch`, `seed`, `prompts`; if its name is a known build-time file
(ledger, money/growth config, registry, pending, prelabelled, answer key,
`relationships.json`) or starts with `records`, `scope`, `rubric`, `prompt`,
`packet`; if it is a source map, `.md`, `.py`, `.jsonl`, `.npy`, `.csv`,
`.log`; if a deployed JSON file contains a pipeline or money key
(`prompt_hash`, `detector_model`, `account_total_inr`, `console_spent_inr`,
`proj_cost_inr`, `cap_inr`, `api_key`); or if any deployed file is a byte
copy of a tracked file under `config/`, `data/domains/`, `data/grow/`,
`docs/review/`, `docs/proposals/`, `docs/rubrics/`,
`backend/app/extraction/` or `backend/app/review/`.
