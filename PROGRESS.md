# PROGRESS

## Phase 0 — foundation ✅

Built:

- **Repo scaffolding**: `requirements.txt`, `.env.example` (every env var
  listed empty), `.gitignore` (excludes `.env` + `data/cache/`),
  `README.md`, `pytest.ini`, `CLAUDE.md` (standing rules).
- **Pydantic v2 schemas** in `backend/app/models/schemas.py`. `Paper`,
  `Claim`, `Evidence`, `Methodology`, `Limitation`, `FutureWork`,
  `ClaimRelationship`, `Opportunity`, plus the `PaperExtraction` bundle
  the LLM produces. `extra="forbid"`, DOI normalisation, self-loop
  prevention on relationships, uniqueness of IDs inside extraction
  bundles.
- **DB tables** in `backend/app/db/tables.py` (SQLAlchemy 2.x
  Declarative) mirroring every schema. SQL migrations at
  `backend/app/db/migrations/001_init.sql` (all base tables, indexes,
  check constraints) and `002_pgvector.sql` (vector columns for the
  Phase 3 relationship layer).
- **`config.py`** — pydantic-settings singleton, reads every env var,
  `SecretStr` for sensitive values, custom `__repr__` that never leaks a
  key. Capability flags (`can_use_openalex_live`, `can_use_gemini`,
  `has_database`) so the pipeline can decide live-vs-offline without
  every module re-reading env.
- **Interfaces**:
  - `LLMClient` (`extract` only — no ranking/judgment surface),
    `MockLLMClient` reading canned extractions from
    `data/seed/extractions/`, `GeminiLLMClient` explicit
    `NotImplementedError` for Phase 2.
  - `LitSource` abstract base, `SeedLitSource` serving the committed
    seed corpus.
- **Seed corpus**: 35 papers under `data/seed/papers/` and 35 matching
  extractions under `data/seed/extractions/`. Domain: transformer-based
  time-series forecasting. Every file carries `"seed_sample": true`,
  every ID is `seed:NNNN`, no DOIs — nothing is confusable with a real
  publication. The roster includes:
  - 6 flagship transformer proposals (Informer, Autoformer, FEDformer,
    PatchTST, Crossformer, iTransformer).
  - 3 DLinear-family "linear beats transformer" papers.
  - 3 rebuttal / conditional-win papers.
  - 3 distribution-shift papers.
  - 3 long-horizon studies, 3 few-shot, 3 channel-independence,
    3 frequency, 3 efficiency, 3 transfer, 2 negative-results — chosen
    so the corpus contains genuine cross-paper contradictions and
    unfollowed future-work threads for the Phase 4 reasoning engine.
  - Deterministic citation graph wired between them (99 edges).

Generator: `python -m backend.app.ingestion.seed_generator`.

## Phase 1 — ingestion ✅

Built:

- **`OpenAlexClient`** (`backend/app/ingestion/openalex.py`). Uses the
  public JSON API with the polite-pool `mailto` convention, cursor
  pagination, tenacity-backed exponential retry on 5xx/429, and refuses
  to instantiate without `OPENALEX_MAILTO` set.
- **`SemanticScholarClient`** (`backend/app/ingestion/semantic_scholar.py`).
  Enrichment-first — `.enrich(papers)` looks up each paper by DOI and
  yields the S2 version for merging. Supports offset pagination for
  search and unauthenticated fallback.
- **`normalizer.py`** — `from_openalex()`, `from_semantic_scholar()`,
  DOI/title normalisation, and `deduplicate()` collapsing by DOI first
  then by (normalised title, year). Deterministic merge preference:
  prefer DOI-bearing → prefer abstract-bearing → prefer higher citation
  count → OpenAlex tiebreak. Merges preserve encounter order and union
  citation lists.
- **`pipeline.py`** — one `run_ingestion()` entrypoint plus
  `resolve_sources(prefer="auto"|"live"|"seed")`. `"auto"` falls back to
  the seed corpus when `OPENALEX_MAILTO` is unset, so the pipeline never
  makes surprise network calls.
- **`backend/cli.py`** — the phase-1 demo command:

  ```
  python -m backend.cli ingest --source seed --limit 100
  ```

  Emits `{ query, source_preference, count, papers[] }` JSON to stdout.

## Self-audit

1. **NotImplementedError inventory.** Five hits, all intentional:
   two abstract `LitSource` methods, one abstract `LLMClient.extract`,
   and the `GeminiLLMClient` deferred stub (with a message pointing at
   Phase 2). No function silently returns fake data.
2. **Three outputs trace to real paper IDs.** For `seed:0007`,
   `seed:0022`, `seed:0034` — every paper file's `id`, its extraction's
   `paper_id`, its first `Claim.paper_id`, and its first
   `Limitation.paper_id` all match the seed ID. No orphan objects.
3. **Pytest.** 38 passed, 0 failed. Suite covers schema validation,
   DOI/title normalisation, OpenAlex + S2 mappers, dedup by DOI and by
   title-year, HTTP-mocked search + pagination + `mailto` presence,
   pipeline resolution, end-to-end offline ingestion, CLI subprocess
   run, and settings-repr secret leak check.
4. **Pipeline over seed corpus emits valid JSON.**
   `python -m backend.cli ingest --source seed --limit 100` returns 35
   papers, all IDs unique, years 2021–2024, 99 citation-out edges,
   headline citation count 810.
5. **Pydantic validation.** The end-to-end pipeline test round-trips
   every emitted paper through `Paper.model_validate()`.
6. **No reasoning / ranking leaked into the LLM boundary.** `LLMClient`
   exposes only `.extract()`; the schema check documents the rule as a
   docstring warning. The only `score()`-shaped code lives in
   `normalizer._pick_primary`, which deterministically selects which
   duplicate wins — a merge preference, not a paper-importance judgment.

## What you need to set for live ingestion

- `OPENALEX_API_KEY` — **mandatory since 2026-02-13**. OpenAlex retired
  the polite-pool mailto convention on that date; unauthenticated calls
  now return HTTP 409 once the shared 100-credit/day pool is spent.
  The client refuses to instantiate without a key. Free keys at
  https://openalex.org/settings/api. Passed as `?api_key=…` query
  parameter (docs are explicit that no header form is supported).
- `SEMANTIC_SCHOLAR_API_KEY` — optional; enrichment still works
  unauthenticated but with a stricter rate limit.
- `DATABASE_URL` — a Postgres URL with `pgvector` installed. Not needed
  for Phase 0/1 (nothing writes to the DB yet); it's the first thing
  Phase 3 will consume.

Nothing else is required. The offline seed pipeline runs with **none of
these set** — confirmed against a clean subprocess env in the pytest
suite (`_isolated_env` fixture blanks every relevant var).

## What was NOT built (deliberately)

- No extraction pipeline yet — Phase 2 wires `MockLLMClient` and
  `GeminiLLMClient` into an end-to-end extractor. `MockLLMClient`
  already returns the pre-authored seed extractions, so Phase 2 is
  really about the live Gemini path plus the disk cache under
  `data/cache/`.
- No relationship layer (Phase 3), no reasoning engine (Phase 4), no
  ranking / opportunity generation (Phase 5), no HTTP API (Phase 6),
  no frontend (Phase 7). Every future phase is listed in `CLAUDE.md`.

## Patch — 2026-07-22 — OpenAlex auth model migration

**Bug.** The Phase-1 OpenAlex client was built on the polite-pool
`mailto` convention. OpenAlex made API keys mandatory on 2026-02-13 and
returns HTTP 409 once the shared 100-credit unauthenticated pool is
spent, so the old client would 409 against the live API.

**Fix.** Replaced `OPENALEX_MAILTO` with `OPENALEX_API_KEY` everywhere:
`config.py` (SecretStr field, capability flag, secret-safe `__repr__`),
`.env.example`, the user's `.env`, `OpenAlexClient` instantiation guard
+ every request path, all 7 client tests, both docs. Verified auth
shape against `developers.openalex.org/api-reference/authentication` —
key is a **query parameter** only (`?api_key=…`), no header form is
supported; the tests assert we don't accidentally send it as
`Authorization` or `x-api-key`.

**Credit-awareness added.** Client now parses these response headers
into a `CreditLedger` per session:

    X-RateLimit-Limit          daily credit budget
    X-RateLimit-Remaining      credits left in today's budget
    X-RateLimit-Credits-Used   cost of this request
    X-RateLimit-Reset          seconds until midnight-UTC reset

`client.credits.as_dict()` reports `calls`, `credits_used_this_run`,
`per_endpoint_credits`, and the last-seen `daily_limit`/
`daily_remaining`/`seconds_until_reset`.

**Filter preference.** New `OpenAlexClient.search_filtered(filter=…,
search=…, sort=…, limit=…)` method sends filter-only calls as a
`works.list` endpoint (1 credit per page) instead of `works.search`
(10 credits per page). The docstring points callers at this method
whenever a structured filter would give the same result set.

**409 handling.** New `OpenAlexQuotaError` raised on 409, carrying the
last-seen daily limit and remaining count. Tenacity retries no longer
mask quota exhaustion.

## Live-call proof — 2026-07-22

Ran one **real** call against the live OpenAlex API (not mocked,
network-observable, credit-charged). Query:

    search: "language model calibration" OR "uncertainty quantification
            language models" OR "selective prediction" OR "hallucination
            detection" OR "confidence estimation large language models"
            OR "abstention language models"
    filter: type:article|preprint, publication_year:>2018
    sort  : cited_by_count:desc
    per-page: 25

**Result.** 25 papers returned. Full raw JSON (including
`X-RateLimit-*` headers, OpenAlex `meta` block, and every work's full
inverted-index abstract) saved to `/tmp/researchmap_live_sample.json`.

**Credit ledger for the run.**

    {
      "calls": 1,
      "credits_used_this_run": 10,
      "per_endpoint_credits": {"works.search": 10},
      "daily_limit": 10000,
      "daily_remaining": 9989,
      "seconds_until_reset": 73655
    }

That's 10 credits (single `works.search` page) against the user's
10,000-credit daily quota, leaving 9,989 remaining. The 1-credit
difference between "10 used, 9,989 remaining out of 10,000" appears to
be OpenAlex's own accounting overhead — reported verbatim, not
massaged.

**Confirmation this is real API data.** Response includes real OpenAlex
IDs (`W4384071683`, `W4399803256`, `W4404534210`, …) that resolve at
`openalex.org/works/…`, real citation counts, real DOIs, real 2019-2024
publication years, and a bearer of legitimately-cited abstracts. Papers
mix on-topic hits (Farquhar et al. 2024 semantic-entropy hallucination
detection at `W4399803256`; Hüllermeier & Waegeman aleatoric/epistemic
uncertainty at `W3014596384`; three hallucination surveys) with a
long tail of chemistry / materials-science papers that OR-match one
phrase but aren't calibration research — exactly what raw retrieval
looks like before topical filtering, and useful signal for how much
work the Phase 2+ pipeline will need to do.

## Self-audit — 2026-07-22

1. **NotImplementedError inventory.** Unchanged from Phase 1 baseline:
   five hits, all intentional (three abstract-base-class methods, one
   `GeminiLLMClient` deferral for Phase 2, one docstring reference to
   the deferral). No silent hardcoded fakes.
2. **Three outputs trace to real paper IDs.** Live-call proof papers
   `openalex:W4399803256`, `openalex:W4384071683`, `openalex:W3014596384`
   are resolvable at `api.openalex.org/works/{id}`; every field in the
   proof file came from the response body, not fabricated.
3. **Pytest.** 41 passed, 0 failed. New coverage: refuses without
   `OPENALEX_API_KEY`, sends `api_key` as query param and *not* as
   header or `mailto`, records per-page + per-endpoint credit usage,
   filter-only path bills as `works.list` (1 credit) not `works.search`
   (10 credits), and 409 raises `OpenAlexQuotaError`.
4. **Pipeline over seed corpus still emits valid JSON.**
   Auth refactor did not regress the offline path — the seed-run
   subprocess test still passes.
5. **Pydantic validation.** Every paper in the live response either
   validated cleanly via `from_openalex` or was skipped as malformed
   (the client's normal behaviour); nothing wrote through
   unvalidated.
6. **No reasoning / ranking leaked into the LLM boundary.** `LLMClient`
   surface unchanged. The `sort=cited_by_count:desc` on OpenAlex is a
   *provider-side* sort and does not touch our reasoning layer.
7. **PROGRESS.md updated** — this section.

## Patch — 2026-07-22 — retrieval-quality fix + hit-rate assessment

**Cause.** V1 was 40% off-target because bare-OR search picked up
chemistry/materials-science papers where "uncertainty quantification"
and "calibration" mean something entirely different from what LLM
researchers use those terms for. Cross-domain terminology collision.

**Two changes.**

(a) **Anchored the query.** Every result must now contain BOTH an
LLM/NLP token AND a topic term:

    search : ("language model" OR "LLM" OR "large language model"
              OR "neural text generation")
             AND
             (calibration OR "uncertainty quantification" OR abstention
              OR "selective prediction" OR "hallucination detection"
              OR "confidence estimation" OR "epistemic uncertainty")

(b) **Topical filter added.** Verified against the live OpenAlex API
(not guessed): `Computer Science` is field 17, `Artificial
Intelligence` is subfield 1702 under it. Filter used:

    filter: primary_topic.subfield.id:1702,
            type:article|preprint,
            publication_year:>2018

Chose `primary_topic.subfield.id` over `topics.subfield.id` because the
primary version is stricter — it drops papers where AI is only a
tangential topic. Same 10-credit cost as before.

## Live-call proof v2 — 2026-07-22

25 papers, real API, `works.search` = 10 credits (9,967 remaining of
10,000). Raw JSON at `scratch/live_sample_raw.json`, readable dump
with full abstracts at `scratch/live_sample_readable.md`. Both are
gitignored — `scratch/` was added to `.gitignore` alongside them.

**Real-data confirmation.** IDs like `W4399803256` (Farquhar semantic
entropy), `W4378189609` (HELM), `W4327810158` (GPT-4 technical report),
`W4404534210` (LLM hallucination survey) all resolve at
`api.openalex.org/works/{id}` with matching abstracts and citation
counts.

**Hit-rate assessment.** Of the 25:

- **2 core on-topic** (paper is primarily about the target constructs):
  `W4404534210` (hallucination survey), `W4399803256` (Farquhar et al.
  semantic-entropy hallucination detection).
- **3 adjacent on-topic** (LLM paper with a documented dedicated
  calibration/uncertainty section): `W4327810158` (GPT-4 tech report,
  has post-RLHF calibration subsection), `W4281690148` (BIG-Bench,
  calibration among task categories), `W4378189609` (HELM, calibration
  is one of 7 headline metrics).
- **20 off-topic** — general LLM/AI surveys, prompting surveys,
  explainability (distinct from calibration), knowledge-graphs review,
  autoencoders/RNN/self-supervised/zero-shot reviews, LLM applications
  (clinical, nano-photonics), and one XAI manifesto. Full list in the
  turn transcript.

**Score: 5/25 = 20% on-topic, 80% noise. Still above the 15% ceiling.**

**Progress vs. v1.** The topical filter eliminated *all* chemistry /
materials-science contamination — the class the user flagged in v1 is
gone (zero out of 25). What replaced it is a different noise class:
highly-cited general AI/LLM surveys that mention our target terms in
passing among many topics, promoted to the top by
`sort=cited_by_count:desc`.

**Proposed third refinement (NOT applied — waiting for approval).**
Two-part:

1. **Drop `sort=cited_by_count:desc`, use default relevance sort.**
   Citation-order promotes generic high-impact surveys over targeted
   calibration papers. Relevance-order will rank on match quality
   instead.
2. **Move search from `search=` query param to
   `filter=title_and_abstract.search:…`.** The `search=` parameter
   matches across the full indexed text; the title+abstract filter
   requires our terms to be prominent enough to appear in the paper's
   own summary. Together these should promote papers where
   calibration/hallucination is the actual subject, not a bibliography
   entry.
   Same credit cost (`works.search` = 10 credits/page either way).

If those two together still leave >15% noise, the third fallback is
narrowing to specific OpenAlex topic IDs (finer-grained than the
Artificial Intelligence subfield). That requires one lookup call to
map "LLM safety / hallucination / calibration" to concrete
topic IDs — not going to guess this either.

## Self-audit — 2026-07-22 (post-retrieval-fix)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference). No silent fakes.
2. **Three outputs trace to real paper IDs.** `openalex:W4399803256`,
   `openalex:W4378189609`, `openalex:W4327810158` — each resolves via
   the OpenAlex singleton endpoint with matching titles/years, and
   every field written to `scratch/live_sample_raw.json` came from
   the response body verbatim.
3. **Pytest.** 41 passed, 0 failed. Retrieval-quality fix touched no
   test-covered code — the query construction lives in the one-shot
   proof script.
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged.
5. **Pydantic validation.** Each of the 25 live results either mapped
   cleanly through `from_openalex` (as measured by the readable dump
   containing 25 well-formed entries) or would have been skipped.
6. **No reasoning / ranking leaked into the LLM boundary.** The
   `sort=cited_by_count:desc` and my hit-rate assessment are BOTH
   provider-side / analyst-side judgments, not decisions embedded in
   the extraction interface.
7. **PROGRESS.md updated** — this section, plus the failure-mode
   entry added to `docs/opportunity-criteria.md` verbatim under
   `## Named failure modes` (only that section; the other four
   headers stay empty).

## Patch — 2026-07-22 — v3 retrieval refinement applied

Both parts:

1. Dropped `sort=cited_by_count:desc`. Default relevance ordering now
   governs — citation-based sort was promoting high-impact generic
   surveys over targeted calibration papers.
2. Moved the boolean query from `search=X` to
   `filter=title_and_abstract.search:X`. The `search=` param covers
   full indexed text; the filter version requires the query terms to
   appear in title or abstract — a much tighter signal.

Same 10-credit cost — moving the query into the filter doesn't leave
the search-price tier because `title_and_abstract.search` is still a
search endpoint. Balance: 9,957 / 10,000.

## Live-call proof v3 — 2026-07-22

Real API. Scratch files overwritten. Real-data spot check: IDs
`W4285429195` (Kadavath), `W4327810286` (SelfCheckGPT), `W3199958362`
(Jiang calibration) all resolve at `api.openalex.org/works/{id}` with
matching abstracts and citation counts.

**Strict grading — primary-subject-only:**

- **Strict hits: 16/25 = 64%.** Sample: Kadavath *Mostly Know What
  They Know*, SelfCheckGPT, LM-Polygraph benchmark, three UQ-for-LLMs
  surveys (2024/2025 vintages), Farquhar-adjacent metamorphic
  hallucination detectors, Jiang *Calibration of LMs*, the
  What-LLMs-know-vs-what-users-think paper (explicit "calibration
  gap"), and the recent epistemic-failure-modes taxonomy.
- **Near-misses: 3/25.** BIG-Bench (calibration is one task type),
  HELM (calibration is 1 of 7 metrics), *LLMs are not Fair Evaluators*
  (proposes a "calibration framework" but for judge order-bias in
  LLM-as-judge, adjacent to but not the confidence-calibration
  literature).
- **Off-topic: 6/25 = 24%.** Sample: *Zero-Shot Time Series
  Forecasters* (mentions "poor uncertainty calibration" of GPT-4 as
  an aside), SPeC (uses "calibration" for prompt-variance tuning, not
  confidence-accuracy alignment), MiniLLM (KD paper mentioning
  calibration as a downstream result), chatHPC, geoscience LLM
  survey, LLMs for language teaching.

Full paper list with abstracts is in `scratch/live_sample_readable.md`.

**Delta over v2.** Strict hit rate 20% → 64%. Off-topic 80% → 24%.
Both refinements pulled their weight — dropping the citation sort
demoted high-citation generic LLM surveys, and the title/abstract
filter dropped papers that only mentioned our terms deep in the body.

**Still above the 15% noise ceiling by 9 percentage points.** Also:
strict grading exposed a known-dedup edge case — the same
Jiang/Neubig calibration paper appears as `W3199958362` (2021
journal) and `W3162385798` (2020 preprint) with different years and
no shared DOI in the OpenAlex records. Our current
DOI-then-normalized-title-year dedup will not collapse this pair.
Noting; not fixing in this batch.

## Ingestion redesign assessment — seed + citation snowball

**Request.** Replace keyword-query ingestion with: pick 10-20
hand-curated seed papers, expand 2 hops via OpenAlex citation edges,
apply the AI subfield filter as a gate, dedupe.

### What already exists in the ingestion layer

- **`OpenAlexClient.get_by_id(paper_id)`** — singleton fetch, 0
  credits (this is the free tier per OpenAlex pricing). Handles the
  seed-lookup step directly.
- **`Paper.citations_out`** — populated from OpenAlex
  `referenced_works`. This is exactly the outgoing (backward-in-time)
  citation edge list — the first half of a snowball hop is already
  built.
- **`OpenAlexClient.search_filtered(filter=…)`** — 1 credit per page
  of up to 200 results. Can be pointed at any filter — including the
  ones we'd need for snowballing.
- **`deduplicate(papers)`** — collapses by DOI then by
  normalized-title+year. Works fine at the end of a snowball run.
- **`normalizer.from_openalex(record)`** — accepts any OpenAlex Work
  JSON and produces a validated `Paper`. Every fetched candidate,
  whether by ID, cites-filter, or referenced-works-filter, comes out
  the other side as a `Paper`.

### What is missing

1. **Inbound citation retrieval.** `Paper.citations_in_count` stores
   only the count. To follow forward citations we'd need
   `filter=cites:W123` (1 credit / page) — the client supports this
   filter shape but no method exposes it as "give me the papers that
   cite X." Small addition on top of `search_filtered`.
2. **Batch-fetch primitive.** OpenAlex's
   `filter=ids.openalex:W1|W2|…|W50` collapses up to 50 singleton
   fetches into one 1-credit list call. Snowballing at hop 2 will
   want this. Not implemented.
3. **Snowball orchestrator.** The traversal itself — a
   frontier + visited set + per-hop cap + total-cap loop that (a)
   loads each seed, (b) enumerates outbound and inbound citations
   via the two filter calls above, (c) gates each candidate against
   the AI subfield filter, (d) dedupes into the visited set, (e)
   stops at hop-K or total-N. Also not present.
4. **Provenance tracking.** Each paper's presence in the corpus
   would carry a chain (seed → hop-1 → this) instead of being
   anonymous. Right now `Paper` has no provenance field. The Phase 4
   reasoning engine will want this — "why is this paper here?" is
   part of the evidence trail.
5. **Seed manifest format.** No file schema for a hand-curated seed
   list. Needs at minimum {id, doi, seed_note} per row plus a
   generated-vs-committed marker parallel to the existing
   `seed_sample: true`.
6. **Config knobs.** Max hops, max papers per hop per seed, subfield
   gate ID(s), whether to walk inbound-only / outbound-only / both.
   None wired into `config.py` or CLI yet.

### Failure modes to be aware of

1. **Seed bias / echo-chamber contamination.** If seeds all cluster
   in one subcommunity (e.g. only NeurIPS-lineage calibration papers),
   the snowball will mirror that community's citation network and
   miss parallel work (Nature-published Farquhar semantic-entropy;
   clinical-uncertainty literature). Countermeasure: distribute the
   seed list across venues and years intentionally, and record how
   each seed was chosen in `seed_note` so this bias is auditable.
2. **Hop-2 combinatorial explosion.** A single seed with 100
   references at hop 1 pulls in up to 100 records; each of those has
   ~50 references, so hop-2 can hit ~5,000 candidates per seed. With
   15 seeds that's ~75,000 candidates before dedup. Needs
   aggressive per-hop and per-seed caps or the credit budget goes
   sideways. In credit terms it's cheap (1 credit per 50-batch =
   ~1,500 credits worst case) but dedup + gate cost real time.
3. **AI-subfield gate drops legitimate off-subfield hits.** Farquhar
   *et al.* semantic entropy is a Nature paper — its OpenAlex
   `primary_topic.subfield` may be Biology or general Nature-family
   subfield rather than 1702 Artificial Intelligence. A hard gate
   would drop it. Softer alternatives: use
   `primary_topic.field.id:17` (Computer Science field, broader) as
   the gate; or gate on `topics.subfield.id:1702` (any of the paper's
   topics, not just primary); or gate on ANY of several relevant
   subfields.
4. **Hub-paper dominance.** Any seed that cites Vaswani *Attention
   Is All You Need* will pull in Vaswani → and at hop 2, everything
   citing Vaswani, which is thousands of off-topic papers. The
   snowball must either (a) blacklist known hub papers before
   expanding, or (b) apply per-node "topical stickiness" scoring
   before continuing to hop 2.
5. **Time-direction asymmetry.** Outbound (referenced_works) walks
   BACKWARD in time — you'll find antecedents. Inbound (cites:X)
   walks FORWARD — you'll find successors. A snowball that does
   both at every hop mixes causal directions in one corpus. That
   may be desired (both build the "map" the project wants) but
   should be a deliberate choice with the direction stored on the
   provenance edge.
6. **OpenAlex citation-graph gaps.** Not every reference in an
   OpenAlex Work resolves to an OpenAlex ID — older venues,
   non-Crossref sources, and preprint-vs-published mismatches
   silently drop edges. Snowball will look complete but isn't.
7. **Preprint-vs-published duplication in the snowball.** Same paper
   appears as arXiv preprint (heavy inbound citations) and journal
   publication (fewer inbound but higher `cited_by_count`). Current
   dedup won't collapse the pair unless they share a DOI record.
   This is the same edge case we hit in v3 grading with the two
   Jiang calibration papers.
8. **No stopping rule beyond "N papers".** Without a topical-quality
   score attached to each fetched candidate, the snowball keeps
   expanding into progressively less relevant territory. The
   quality/quantity trade-off has to be an explicit config knob, not
   an emergent property of the walk.
9. **Seed poison.** A single mis-tagged seed (e.g. a hallucination
   paper that turns out to be a chemistry paper about "hallucination"
   in a totally different sense) will pollute an entire branch.
   Countermeasure: require abstract-level review of seeds before
   they enter the manifest, and record `seed_note` explaining topical
   fit.

### My recommendation on the trade-off

The snowball is the right long-run approach — its whole appeal is
that each paper in the corpus has a traceable provenance chain, which
is exactly what the "no orphan conclusions" rule in `CLAUDE.md`
demands. Keyword ingestion can never provide that. But the pieces
missing (inbound-citation retrieval, batch fetch, orchestrator,
provenance model, seed manifest, config knobs) are enough that it
would be a full sub-phase of work, not a small patch.

The keyword pipeline as it stands (v3, 64% strict hits) is good
enough to feed Phase 2 extraction as a smoke test — Phase 2 processes
each paper independently and the extraction schema will surface
off-topic papers as papers with poorly-formed claims, which is
diagnostic in its own right. If you want to do the snowball redesign,
it's cleaner as a separate Phase 1.5 before extraction goes live.

## Self-audit — 2026-07-22 (post-v3)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference).
2. **Three outputs trace to real paper IDs.** `openalex:W4285429195`
   (Kadavath), `openalex:W4327810286` (SelfCheckGPT),
   `openalex:W3199958362` (Jiang calibration) — each resolves via
   the OpenAlex singleton endpoint with matching titles/years, and
   every field written to `scratch/live_sample_raw.json` came from
   the response body verbatim.
3. **Pytest.** 41 passed, 0 failed. Retrieval refinement lived in
   the one-shot proof script, not the test-covered code.
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged.
5. **Pydantic validation.** All 25 v3 results validate cleanly against
   the OpenAlex mapper.
6. **No reasoning / ranking leaked into the LLM boundary.** The
   `title_and_abstract.search` filter and the hit-rate assessment are
   both analyst-side / provider-side decisions, not encoded in the
   extraction interface.
7. **PROGRESS.md updated** — this section. Failure-mode entry in
   `docs/opportunity-criteria.md` unchanged.

## Patch — 2026-07-22 — dedup: cross-year preprint/published collapse

**Motivation (scoring integrity, not cosmetic).** Two records for the
same underlying work — a preprint and a subsequent journal
publication, or the same paper across two venues — would be counted
as independent papers by any downstream scorer that treats "papers
reporting a claim" as a count. That would fake replication where none
occurred and inflate the persistent-limitations scorer,
finding-support scores, and any opportunity scoring that leans on
independence of evidence. This one belongs in ingestion, before
extraction ever sees the corpus.

New third dedup pass added after the DOI and (title, year) passes:

    Pass 3 — same normalized title, |Δyear| ≤ CROSS_YEAR_WINDOW (=2),
             AND at least one shared normalized last-name → merge.

Author normalization reduces every input to a lower-cased,
ASCII-folded last-name token. Handles the format variants OpenAlex
and Semantic Scholar actually emit:

    "John A. Doe"    → "doe"
    "J. Doe"         → "doe"
    "Doe, John"      → "doe"
    "María Müller"   → "muller"      (diacritics stripped)

Overlap is set-intersection on those tokens. Empty on either side is
"no positive evidence" and refuses to merge — protects against
false-positive collapses of two truly distinct same-titled papers
where one record lacks author metadata.

**Also fixed while here: HTML tags in titles.** OpenAlex serves
inline markup in titles (`<i>When</i>`, `<sub>2</sub>`, `<scp>AI</scp>`).
Un-stripped, tag names leaked into the normalized key as `i`, `sub`,
`scp` tokens and defeated title-based dedup. `normalize_title` now
strips HTML tags as its first step. This was the actual reason the
Jiang preprint/journal pair had different normalized titles despite
being identical modulo formatting.

**Verified on the v3 live sample.** Feeding all 25 v3 papers through
`deduplicate()` post-fix collapses **two real preprint→published
pairs**:

- `W3162385798` (2020 arXiv Jiang *How Can We Know When LMs Know?*)
  collapses into `W3199958362` (2021 TACL journal version). Different
  DOIs (arXiv 10.48550/… vs TACL 10.1162/…), different years, same
  authors, same title modulo the `<i>` italic tag on `<i>When</i>`.
- `W4388585881` (2023 arXiv *Survey on Hallucination in LLMs*)
  collapses into `W4404534210` (2024 journal version). Same story.

**These would have inflated replication counts by 2 out of 25 in a
single 25-paper sample** — an 8% inflation rate on any
paper-count-dependent score if the fix hadn't landed. Enough that the
persistent-limitations score would meaningfully change.

**What the fix deliberately does NOT do.**

- No arXiv-specific DOI heuristic. Records with different DOIs are
  still treated as potentially-distinct; the merge only fires when
  title + author + adjacent-year all agree. If we later want to
  treat `10.48550/arxiv.*` as a preprint marker and eagerly-collapse
  against journal DOIs of the same paper, that's a Phase 1.5 add-on.
- No fuzzy title match. Edit-distance / token-set overlap could
  catch harder cases ("Attention Is All You Need" vs
  "Attention Is All You Need (Extended)") but also expands the
  false-positive surface. Held off deliberately.
- No cross-year merge without author evidence. If either record has
  empty authors, we refuse to merge — a safe default that trades a
  small under-dedup risk for zero false-positive risk.

## Self-audit — 2026-07-22 (post-dedup-fix)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference). No new silent stubs.
2. **Three outputs trace to real paper IDs.** V3 live-sample dedup
   demo above collapses `openalex:W3162385798` into
   `openalex:W3199958362` and `openalex:W4388585881` into
   `openalex:W4404534210`. All four IDs resolve via
   `api.openalex.org/works/{id}`; the collapses are verifiable by
   inspecting `scratch/live_sample_raw.json` against `Paper.model_validate`
   and `deduplicate`.
3. **Pytest.** 49 passed, 0 failed (+8 tests from Phase 1 baseline).
   New coverage:
   - `test_dedup_collapses_preprint_and_published_across_years`
     (the exact v3 case)
   - `test_dedup_does_not_collapse_same_title_different_authors`
     (false-positive safety)
   - `test_dedup_does_not_collapse_when_year_gap_exceeds_window`
   - `test_dedup_refuses_cross_year_merge_when_authors_missing`
   - `test_dedup_cross_year_pass_tolerates_author_format_variants`
   - `test_dedup_cross_year_within_window_but_not_at_zero_or_beyond`
     (boundary — Δ=1,2 merge; Δ=3 doesn't)
   - `test_author_helpers_normalize_expected_formats`
     (`_normalize_last_name`, `_authors_overlap`)
   - `test_normalize_title_strips_inline_html_tags`
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged;
   seed titles have no HTML tags and no cross-year duplicates.
5. **Pydantic validation.** All merges route through `Paper.model_validate`
   in `_merge`.
6. **No reasoning / ranking leaked into the LLM boundary.** The
   dedup fix lives entirely in `backend/app/ingestion/normalizer.py`;
   the `LLMClient` interface still exposes only `.extract()`. Author
   overlap is set intersection on normalized tokens — pure syntactic
   equality, not a judgment call.
7. **PROGRESS.md updated** — this section. Failure-mode entry added
   verbatim to `docs/opportunity-criteria.md` under
   `## Named failure modes` (the other four section headers stay
   empty for hand-fill).


## Next step

Nothing autonomous. Awaiting explicit call on:

1. Whether to do the seed + citation snowball redesign as a **Phase
   1.5** before Phase 2 (assessment stands in the previous section).
2. Whether to proceed to Phase 2 extraction with the v3 keyword
   corpus (now 64% strict hits with cross-year dedup in place) as a
   smoke-test corpus.
3. Whether to add an arXiv-DOI-aware collapse (would catch
   preprint/journal pairs where the DOIs differ but one is
   `10.48550/arxiv.*`). Currently deferred.
## Patch — 2026-07-22 — merge policy + arXiv-DOI pass (change A)

Merge semantics were previously implicit. Made everything explicit and
deterministic. This is one logically-independent change; the arXiv
pass below (change B) is the second.

**Survivor rule — deterministic, order-independent.** Written up in
`docs/merge-policy.md`; realised in `_survivor_key(p)` + `_pick_survivor(a, b)`.
Precedence tiers, higher wins:

    (1) is_pub_doi        — non-arXiv DOI beats arXiv-DOI beats no DOI
    (2) has_venue         — presence of a venue string
    (3) citations_in_count
    tiebreak: lex-lower id

`_pick_survivor(a, b)` and `_pick_survivor(b, a)` return the same
`(survivor, loser)` pair. Removed the previous source-of-record
ranking (OpenAlex > S2 > seed) — provider identity shouldn't decide
which record is canonical, only paper-content signals should.

**Per-field merge policy — every Paper field spelled out** in
`docs/merge-policy.md`. Categories:

- survivor-only: `id`, `source`, `source_id`, `title`
- fill-in (survivor's if truthy, else loser's): `doi`, `abstract`,
  `year`, `authors`, `venue`, `fulltext`
- union: `citations_out` (order-stable, survivor first)
- OR: `oa_fulltext_available`
- policy-controlled: `citations_in_count`
- transitive union: `merged_from`

**`CITATIONS_MERGE_POLICY = "max"`** — named module-level constant.
Rejected `"sum"` (double-counts anyone citing both versions) and
`"survivor"` (silently loses information). `max` is conservative and
grep-able; ranking (Phase 5) will read the constant, not a magic
number.

**`merged_from` list added to the `Paper` schema (Pydantic v2 + DB).**
Every collapse writes the loser's ID (plus any prior `merged_from`)
into the survivor's `merged_from`, transitively. Survivor's own ID is
never in its own list. Order-stable, de-duplicated. This gives Phase 4
the audit trail promised by the *no orphan conclusions* rule — asking
"what did we collapse to get this record?" now has a concrete answer.

Migration `001_init.sql` gained a `merged_from TEXT[] NOT NULL
DEFAULT '{}'` column on `papers`. `PaperRow` mirrors it. No live DB
has run against the migration, so editing it in place was safe.

**Output ordering.** `deduplicate()` now returns `sorted(by_id.values(),
key=lambda p: p.id)`. Feeding it any permutation of the same input
produces byte-identical output. Verified by the new
`test_dedup_is_order_independent` and separately on the live 25-paper
sample.

**Forward-compat commitment for Phase 2.** Merge policy for `Claim`,
`Evidence`, `Methodology`, `Limitation`, `FutureWork`, and
`ClaimRelationship` is written down in `docs/merge-policy.md` under
*Forward-compat commitment for Phase 2* — flagged NOT-YET-IMPLEMENTED
but locked in so Phase 2 doesn't invent policy at the wrong time. Key
promise: no entity attached to a merged-away paper is silently
dropped.

## Patch — 2026-07-22 — arXiv-DOI-aware pass (change B)

New pass 4 in `deduplicate()`. Fires when: one record has an arXiv
DOI (`10.48550/arxiv.*` prefix — case-insensitive), the other has a
non-arXiv DOI, both have the same normalized title, and there's at
least one shared normalized last-name. **No year-window constraint**
— the arXiv/non-arXiv DOI pair is already strong evidence, so long
preprint→journal lags (e.g. 5-year gaps) collapse too.

**Deliberately not merged by pass 4:**

- arXiv-DOI + different authors → different people happen to have
  used the same title.
- Two arXiv DOIs → both preprints, neither is canonical; refuse.
- arXiv-DOI + different title → almost certainly two papers by the
  same prolific author.

**Not in scope, deliberately deferred:** fuzzy / edit-distance title
matching. Would add real false-positive surface without a scoring
model to defend against it — waiting for that until the reasoning
engine has an evaluator that can tell us the trade-off matters.

## Live-call proof — 2026-07-22 (post-policy patch)

Re-ran dedup against the v3 25-paper sample. **Before: 25. After: 23.**
Same collapses as prior patch (both already handled by pass 3):

- `openalex:W3162385798` → `openalex:W3199958362` (Jiang, 2020 arXiv
  → 2021 TACL). Survivor's `merged_from = ["openalex:W3162385798"]`.
- `openalex:W4388585881` → `openalex:W4404534210` (Hallucination
  Survey, 2023 arXiv → 2024 journal). Survivor's `merged_from =
  ["openalex:W4388585881"]`.

Also verified order-independence on the real sample: reversing the
25-paper input list produces a byte-identical output list (compared
via `model_dump()`). That's the property the code change guarantees;
the live sample confirms it in the wild.

**NOT characterised as a rate.** This sample is known ~40% off-target
from the earlier OR-matching issue and has 25 papers — nowhere near a
population estimate. The value here is that the code works on real
API data, not that we've measured how often duplicates occur.

## Self-audit — 2026-07-22 (post-policy patch)

1. **NotImplementedError inventory.** Unchanged: 5 hits, all
   intentional (3 abstract-base-class methods, `GeminiLLMClient`
   Phase-2 deferral + its docstring reference). No new silent stubs.
2. **Three outputs trace to real paper IDs.** `openalex:W3199958362`,
   `openalex:W4404534210`, and the untouched `openalex:W4285429195`
   (Kadavath) all resolve at `api.openalex.org/works/{id}` with
   matching titles/years; the two merged records both carry a
   `merged_from` pointer to a second real OpenAlex ID.
3. **Pytest.** 62 passed, 0 failed (+13 tests over the previous batch).
   New coverage:
   - `test_survivor_prefers_non_arxiv_doi_over_arxiv`
   - `test_survivor_falls_through_to_lex_lower_id_on_total_tie`
   - `test_dedup_is_order_independent` (the killer test)
   - `test_merged_from_records_the_collapsed_id`
   - `test_merged_from_accumulates_transitively_over_chain`
   - `test_merged_from_never_includes_survivor_own_id`
   - `test_citations_merge_policy_is_max`
   - `test_pass4_collapses_arxiv_and_non_arxiv_doi_pair`
   - `test_pass4_collapse_survives_wide_year_gap`
   - `test_pass4_does_not_collapse_when_authors_disjoint`
   - `test_pass4_does_not_collapse_two_arxiv_dois`
   - `test_pass4_does_not_collapse_when_titles_differ`
   - `test_is_arxiv_doi_recognises_the_prefix`
4. **Pipeline over seed corpus still emits valid JSON.** Unchanged;
   seed corpus has no arXiv DOIs and no cross-year duplicates.
5. **Pydantic validation.** New `merged_from` field is a
   `list[NonEmptyStr]` with `default_factory=list`; existing seed
   JSON files (which lack the field) still validate via the default.
   No schema regression.
6. **No reasoning / ranking leaked into the LLM boundary.** Survivor
   selection is a pure function of three explicit metadata tiers +
   a lex tiebreak. `CITATIONS_MERGE_POLICY` is a merge rule, not a
   ranking judgment. `LLMClient` interface still exposes only
   `.extract()`.
7. **PROGRESS.md updated** — this section. `docs/merge-policy.md`
   is the source of truth for the policy; PROGRESS.md links to it
   rather than duplicating the field table.

## Next step

Nothing autonomous. Awaiting explicit call on:

1. Whether to do the seed + citation snowball redesign as a **Phase
   1.5** before Phase 2.
2. Whether to proceed to Phase 2 extraction with the v3 keyword
   corpus (64% strict hits, dedup + merge policy now solid) as a
   smoke-test corpus.

## Patch — 2026-07-23 — Phase 1 flagged-item cleanups

Three flagged items from the previous session addressed together:

**Item 1 — `by_id` key vs `merged.id` inconsistency.** Previously,
after a merge where the newcomer won the survivor pick, `by_id`
stayed keyed by the first-seen ID while the stored record's own
`.id` was the survivor's. Downstream index lookups (`title_index`
buckets) then referenced a key that no longer had a `by_id` entry,
so later dedup passes silently missed collapses. New `_rekey(old,
new)` helper rewrites every index (`doi_index`, `title_year_index`,
`title_index`) when the survivor identity flips, and the merge
branch removes/reinstates the `by_id` entry under the survivor's
ID. Regression test:
`test_by_id_key_agrees_with_merged_id_after_newcomer_wins`
exercises a 3-way collapse where the middle record wins over the
first-seen; without the rekey the third record wouldn't find the
survivor.

**Item 2 — Pass 2 author check.** Symmetry with passes 3 and 4:
same-title + same-year is now conditional on ≥1 shared normalized
last-name. Empty authors on either side refuses to merge (positive
evidence rule). New tests:
- `test_pass2_collapses_when_authors_overlap` (positive baseline)
- `test_pass2_does_not_collapse_when_authors_disjoint` (two truly
  distinct papers with the same title in the same year survive)
- `test_pass2_refuses_merge_when_authors_missing`

Two existing tests (`test_dedup_collapses_by_title_year_when_doi_missing`
and `test_dedup_prefers_record_with_doi_and_abstract`) had no
authors on either side; they now include `["Ashish Vaswani"]` /
`["A. Vaswani"]` to keep their semantic intent (pass-2 title+year
merge; DOI preference on merge) while satisfying the new rule.

**Item 3 — Seed corpus regeneration.** All 35 seed paper JSONs on
disk now carry the `merged_from: []` field explicitly. To keep
future regenerations diff-clean, the `PaperExtraction.extracted_at`
timestamp for seed extractions is now a fixed value
(`2026-07-21T00:00:00Z`) instead of `datetime.now()` — regenerating
the corpus produces byte-identical output.

**Tests:** 66 passing (+4 over change B). No live LLM calls made;
no API keys touched.

## Flagged, not acted on

**"Commit separately" was requested but ResearchMap is not a git
repo.** No `.git` in the project directory. I structured the two
follow-ups as logically-independent change blocks (change A: merge
policy + `merged_from` + order-independence + docs; change B: arXiv-
DOI-aware pass 4) so they'd map cleanly to two commits if you
`git init` here, but I did NOT initialise the repo or make any
commits. Say the word and I'll init + commit both as separate
commits with messages, or you can do it yourself.

Also would want changed but not acting on:

- The `by_id` internal key can differ from `merged.id` after a
  merge where the loser was first-seen. Currently harmless (output
  is `sorted(by_id.values())` and no downstream code reads the
  key), but it's a latent inconsistency I'd rather clean up. Could
  do this by rekeying `by_id[loser_id] → by_id[survivor_id]` at
  merge time; low-risk but worth its own change.
- The seed-corpus JSON files on disk don't carry the new
  `merged_from` field (they were generated before it existed).
  Currently harmless — `Paper.model_validate` fills the default —
  but a stray `seed_generator` re-run would rewrite them all with
  the field explicitly. Not a bug, worth normalising when
  convenient.
- Pass 2 (`same title, same year`) still has no author check — an
  edge case for two truly distinct same-titled papers in the same
  year. Not observed in the wild yet, but worth extending to
  require author overlap for symmetry with pass 3 / pass 4.
