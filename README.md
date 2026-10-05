# ResearchMap

ResearchMap reads the research papers on one subject and lists questions those
papers leave open: things a paper said should be studied next that no later
paper in the collection took up, limits that keep coming back, and pairs of
findings that appear to disagree. Every result links to the papers and
sentences behind it.

It is a working prototype and a research aid. It is not peer review and not
advice of any kind.

## What it is not

- **Not complete.** It only knows the papers in the selected library. "Nobody
  has answered this" means "no paper in this library answered it".
- **Not validated.** Whether the questions it lists predict later research has
  not been tested yet.
- **Not a full reading of every paper.** Where no open-access copy exists, only
  the abstract is read, and each paper's page says which.
- **Not independent review.** Disagreements were checked by hand by the
  person who built the project, not by outside experts.

## How it works

1. Papers on one subject are collected from [OpenAlex](https://openalex.org)
   and sorted into on-topic, borderline and off-topic by fixed keyword rules.
2. A language model (Google Gemini) reads each paper and writes down, in a
   fixed format, its claims, the limits it admits, its methods and what it
   says should be studied next. It does not rank or judge anything.
3. Plain code compares those notes across papers. For possible
   disagreements, code shortlists pairs of very similar claims and the model
   is asked about one pair at a time whether they conflict.
4. Code orders the results by fixed rules. The model's own confidence never
   feeds a score.
5. Results are checked by hand where possible, and doubts about those checks
   are published.

The governing rule is **LLMs extract, code reasons**. See `CLAUDE.md`.

## The libraries

| Library | Subject |
|:--|:--|
| Language-model reliability | How language models express confidence, when they should refuse to answer, how uncertainty is measured, and why they state false things as fact |
| Diet and all-cause mortality | What the epidemiology and trial literature says about diet and mortality-related outcomes (not dietary or medical advice) |
| Algorithmic fairness in machine learning | Fairness definitions and metrics, incompatibility results, bias-mitigation methods and audits |

Current counts (papers, how many were read in full, what was checked by hand)
are generated from the data and shown on the site's **Method** page. Libraries
are built one subject at a time and do not update themselves.

## Run it locally

Requirements: Python 3.11+, Node.js 20+.

```bash
# Python side (tests, snapshot export) — no API keys needed
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest backend/tests

# Website (static export, no server at runtime)
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run build        # static site in frontend/out/
npm run launch-check # pre-launch checklist over frontend/out/
```

The committed snapshot in `frontend/public/data/` is everything the site
needs. `npm run snapshot` (or `python -m backend.app.api.multi_library_export`)
regenerates it from the cached pipeline output. Live paper collection and
extraction need API keys (see `.env.example`) and cost money; nothing in the
website or the test suite calls a paid API.

On macOS, `ResearchMap.app` / `ResearchMap.command` start the local stack
without a terminal (keep the folder outside `~/Downloads`, `~/Documents` and
`~/Desktop`, which macOS protects).

## Deploying

The site is a static export. On Vercel, `vercel.json` builds it as is. Set
`NEXT_PUBLIC_SITE_URL` to the site's public address so canonical links,
share previews and the sitemap use it; only production builds
(`VERCEL_ENV=production`) are indexable. The site name lives in
`frontend/site.config.json`. Step-by-step launch notes: `docs/LAUNCH.md`.

## Licence

Code: [MIT](LICENSE). Paper metadata comes from OpenAlex (CC0); paper text
belongs to its authors and publishers, and the site shows only short
extracted claims, abstracts and links, never full text.

## How to cite

Use the metadata in [`CITATION.cff`](CITATION.cff) (GitHub shows a "Cite this
repository" button). Results are an unvalidated prototype's output and should
not be cited as primary research findings.

## Contact

Use the site's **Contact** page, or open an issue in this repository.

## Sources and attribution

[OpenAlex](https://openalex.org) (CC0) for paper metadata and abstracts;
[Semantic Scholar](https://www.semanticscholar.org),
[Unpaywall](https://unpaywall.org), [Europe PMC](https://europepmc.org) and
[arXiv](https://arxiv.org) for enrichment and open-access full text.
