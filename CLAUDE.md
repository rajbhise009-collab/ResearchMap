# ResearchMap — Standing Instructions

This file is the source of truth for every session working on ResearchMap.
Read it fully before touching any code.

## What ResearchMap is

A literature-based discovery (LBD) system for a single scientific domain.
It ingests papers, decomposes each into structured knowledge with an LLM,
builds a cross-paper relationship layer, and runs a deterministic reasoning
engine that ranks evidence-backed research opportunities with fully
traceable justification.

## The core rule — above all else

**LLMs EXTRACT. Code REASONS.**

LLMs are used only to convert unstructured paper text into structured JSON
(claims, methods, limitations, future work). Every ranking, score,
contradiction resolution, and opportunity-detection decision is
deterministic Python that a human can read, unit-test, and defend
academically.

If you ever find yourself about to ask an LLM to "rank," "judge which is
promising," or "decide importance" — STOP. That logic belongs in the
reasoning engine as inspectable code. This division is the entire point of
the project; violating it destroys its value.

Corollary: `Claim.confidence` is an LLM self-assessment, so it MUST NOT
feed any score — it is a pre-scoring filter hook only. See
`docs/confidence-policy.md`. Any code that reads `Claim.confidence` in a
scoring path is a violation of this rule.

## Honesty rules — non-negotiable

1. Never fabricate paper content, citations, scores, or evidence. Every
   field in every output must trace to a real source paper ID.
2. Never stub a function with plausible-looking hardcoded output. If a
   piece is not yet built, `raise NotImplementedError` with a clear
   message. Silent fakes are worse than crashes.
3. When evidence is thin, produce fewer and weaker opportunities and say
   so explicitly. Confident-looking noise is a failure, not a feature.

## Locked stack

- Python 3.11+
- FastAPI
- Pydantic v2
- PostgreSQL + pgvector (must work on plain local Postgres; Supabase-compatible)
- Gemini Flash for extraction, Claude for synthesis — both behind a single
  swappable `LLMClient` interface
- Next.js + TypeScript on Vercel for frontend (built last)
- Literature sources: OpenAlex (primary — MANDATORY `OPENALEX_API_KEY`
  since 2026-02-13, passed as `?api_key=…` query param; the old
  polite-pool mailto is retired and returns 409), Semantic Scholar
  (enrich), arXiv / PubMed / Europe PMC (open-access full text). Prefer
  `filter=` over `search=` on OpenAlex — filter list endpoints cost 1
  credit vs. 10 for search.

Every external dependency — LLM provider, DB, literature source — sits
behind an interface so it can be mocked or swapped. No provider SDK is
ever imported directly from business logic.

## Repository layout

```
ResearchMap/
  CLAUDE.md
  PROGRESS.md
  README.md
  requirements.txt
  .env.example
  .gitignore
  backend/
    cli.py
    app/
      config.py
      ingestion/
      extraction/
      relationships/
      reasoning/        # the core — deterministic Python
      ranking/
      validation/
      api/
      models/           # Pydantic v2 schemas
      db/               # SQLAlchemy tables + migrations
    tests/              # mirrors app/ subpackages
  data/
    cache/              # per-paper extraction cache, keyed by paper ID
    seed/               # committed offline sample corpus
  frontend/             # built in a later phase
```

## Data model

Implement each of these as a Pydantic v2 model AND a DB table.

- **Paper** — id, source, source_id, doi, title, abstract, year, authors,
  venue, citations_out, citations_in_count, oa_fulltext_available, fulltext
- **Claim** — id, paper_id, text, type (`finding` | `method` |
  `theoretical` | `negative`), confidence (0–1)
- **Evidence** — id, claim_id, description, strength
- **Methodology** — id, paper_id, name, description, datasets, conditions
- **Limitation** — id, paper_id, text, normalized category
- **FutureWork** — id, paper_id, text, addressed_by (nullable paper id)
- **ClaimRelationship** — id, from_claim_id, to_claim_id, type (`supports`
  | `contradicts` | `extends` | `depends_on` | `similar_to` |
  `uses_method`), weight, evidence_note
- **Opportunity** — id, gap_type, title, score, component_scores,
  explanation, supporting_paper_ids, contradiction_ids, confidence,
  evidence_trail

**No orphan conclusions. Every field traces to concrete paper/claim IDs.**

## How you work

- **One phase at a time.** Do not scaffold future phases ahead of the
  current one.
- **"Done" means:** real logic (no fakes), tests written and passing,
  PROGRESS.md updated, one command that demonstrates the phase.
- **At the end of every phase:** run the self-audit loop below, update
  PROGRESS.md, then STOP and wait for explicit approval before starting
  the next phase.
- **Commit the seed corpus.** The entire pipeline and test suite must run
  offline with no API keys. Live keys only activate real ingestion/
  extraction.
- **Secrets** load from env vars via `config.py`. Never hardcode, never
  print, never log a secret. `.env` is gitignored.

## Self-audit loop (run at end of every phase)

1. Confirm every function has real logic. List any `NotImplementedError`s
   and confirm none silently return fake data.
2. Spot-check that 3 outputs trace to real paper IDs.
3. Run pytest, paste the summary, fix failures before proceeding.
4. Run the pipeline against the seed corpus and confirm it emits valid
   JSON.
5. Confirm outputs validate against the Pydantic schemas.
6. Confirm no reasoning or ranking logic leaked into an LLM call.
7. Update PROGRESS.md and report: what was built, audit results, next
   step, anything needed from the user.

## Autonomy policy

**Default to maximum autonomy.** Build, test, self-audit, commit, and
continue to the next phase WITHOUT waiting for approval, EXCEPT at
the five stop points below. Outside them, proceed. Do not ask
permission for ordinary implementation choices; make them, document
them in `PROGRESS.md`, and flag anything you would want revisited.

### Hard stops — halt and report before acting

(a) **Any action that spends money or calls a paid API.** Always stop
and give Raj the estimated cost first. Examples: live LLM extraction
(Gemini, Anthropic), Semantic Scholar API keys with billing enabled,
OpenAlex usage over the daily quota triggering paid tiers, any
cloud-compute launch. Cost includes credit budgets even when the
cash-equivalent is small — the point is a spend approval, not a
dollar threshold.

(b) **Anything requiring a credential, account, or human transaction.**
Signing up for an API, requesting an increase, verifying an email,
running a `pip install` that prompts for authentication, opening a
GitHub issue on someone else's repo. These all require a human
transaction Raj must consent to.

(c) **Phase 4 reasoning-engine output.** Raj must personally judge
whether the top-ranked opportunities are good; this is the project's
only quality signal and cannot be delegated. When Phase 4 produces
its first ranked list, stop and hand it over — do not proceed to
Phase 5 (ranking) or Phase 6 (validation) autonomously.

(d) **Any decision that would change a documented policy in `docs/`.**
Merge policy, labelling rubric, opportunity criteria, schema
pressure-test conclusions. If new evidence surfaces that would
overturn one of these, halt and report the evidence; do not silently
rewrite the doc. Extending is fine; overturning requires approval.

(e) **Anything you assess as architecturally irreversible.** Deleting
a database, force-pushing to a shared branch (this repo has no
remote yet, so `git push --force` is not relevant here), renaming a
public data-model class that other modules import from a stable
alias, removing a Pydantic field that a persisted extraction depends
on. The heuristic: can a future session undo this in ≤ 1 commit
without losing information? If no, halt.

Outside these five, do not ask; do it, log it, flag it.

## Non-negotiable: no reasoning phases built against mock or seed data

**Phase 3 (relationship layer) and Phase 4 (reasoning engine) must
NOT be built against the mock LLM path or the seed corpus.** Both
phases produce scorers whose behaviour is only meaningful when the
inputs are real. Building them earlier — against the seed corpus's
planted contradictions or against mock-generated claims — produces
scorers that appear to work because they were validated against
their own answer key.

Concretely: any Phase 3 or Phase 4 code must be gated on the
existence of a real-extraction corpus (defined as: at least one
`PaperExtraction` on disk whose `extractor` is `gemini-flash-*` or
another real LLM name, not `mock-seed`, `seed-fixture`, or
`programmable-mock`). If that gate hasn't been crossed, do not start
those phases even if they look ready.

The seed corpus is for pipeline validation and offline tests, not
for scorer validation.

## Phase index

**Numbering note (2026-08-03).** The commits shipping API and frontend
were labelled "Phase 6" and "Phase 7" in commit messages and PROGRESS.md,
skipping the validation phase originally slated as Phase 6 here. That
labelling is a historical fact in the git log — do not renumber the
commits — but the plan's numbering is the source of truth for what's
DONE and what's OUTSTANDING. **Validation (retrospective time-split
test) has not been built.**

- Phase 0 — foundation: repo, data model (Pydantic + DB), config,
  interfaces, mocks, seed corpus. **BUILT.**
- Phase 1 — ingestion: OpenAlex + Semantic Scholar clients, normalizer,
  dedup, tests. Small-sample corpus only at this phase (100–300 papers
  from keyword retrieval). Full-scale corpus construction — snowball
  expansion, adjacent-domain sweeps, OA-full-text retrieval — is
  deferred until AFTER extraction is proven on the small sample. The
  corpus requirements are downstream of what extraction actually
  needs: for example, if abstracts alone yield too few limitations to
  score anything, we need OA full text, and that changes ingestion
  and storage before we scale corpus size. Do not scale up ingestion
  until Phase 2 tells us what the corpus has to contain. **BUILT.**
- Phase 2 — extraction. **BUILT** (real Gemini extraction over the
  113-paper corpus, ~$7.40 spend to date).
- Phase 3 — relationship layer. **BUILT** (2026-07-25; see PROGRESS.md).
- Phase 4 — reasoning engine. **BUILT** (2026-07-26).
- Phase 5 — ranking. **BUILT** (2026-07-30; commit `98566be`
  "Phase 5: ranking + versioned evidence-card assembly").
- Phase 6 — validation. **NOT BUILT — OUTSTANDING.** Its own gated
  phase. The retrospective time-split test — freezing the corpus at
  year Y and checking whether the ranking recovers year-(Y+k) actual
  research activity — is the project's publishable claim. It gets a
  full phase, not a half-phase bundled with ranking. The commits
  labelled "Phase 6" (`cceac22` "Phase 6: read-only FastAPI + static
  snapshot export") actually shipped Phase 7 (API); validation was
  skipped in that push and remains the next real piece of work.
- Phase 7 — API. **BUILT** (2026-07-30; the commit above is misnamed
  "Phase 6" in the message but implements this phase per the plan).
  Adds no reasoning or ranking — read-only over the file-backed
  reasoning output.
- Phase 8 — frontend. **BUILT** (2026-07-31 consumer rebuild; 2026-08-01
  premium UI pass; 2026-08-02 wired to the live FastAPI for the .app's
  full-stack "genuine app" mode). Includes the honest search gate and
  the plain-language translation layer.

The next work-shaped thing is Phase 6 (validation). Nothing that ships
after this line should be described as "complete" without acknowledging
validation is still owed.
