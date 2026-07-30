<!-- DRAFT — pending Raj's revision. First-draft content by Claude, based on CLAUDE.md, PROGRESS.md, the labelling rubric, and the schema pressure-test. Delete or overwrite freely; the terminology-collision, duplicate-inflation, and application-noise failure modes below are your originals — those stay unless you explicitly revise them. -->

## What makes an opportunity valid (minimum evidence bar)

An **opportunity** is a claim by the reasoning engine that a specific
gap in the literature is worth pursuing. A candidate opportunity is
**valid** — meaning it survives the reasoning engine's own filters and
earns a place in the ranked output — only if all of the following
hold:

1. **Paper support: at least three independent on-domain papers.**
   Where "independent" means:
   - Distinct `Paper.id` after all four dedup passes;
   - Not present in each other's `merged_from` list;
   - No shared first author across the supporting set (author overlap
     for co-authorship on ≥ 2 papers is allowed and common; identical
     first authors on ≥ 2 papers count as one).
   Rationale: any single paper's claims can be idiosyncratic.
   Two-paper agreement is common by chance in a small corpus. Three
   independent papers is the smallest set where the persistent-
   limitations scorer meaningfully moves off zero. See `docs/schema-
   pressure-test.md` for the coverage numbers.

2. **Traceable evidence chain.** Every field in the emitted
   `Opportunity` object must trace back to concrete `Paper.id` +
   `Claim.id` or `Limitation.id` values. `Opportunity.evidence_trail`
   must not be empty; `Opportunity.supporting_paper_ids` must not be
   empty. No orphan conclusions — a rule already enforced in the
   Pydantic schema.

3. **Reasoning path is deterministic Python, not LLM output.** The
   opportunity's `component_scores` dict must contain the concrete
   scorer names and numeric contributions that produced its overall
   `score`. If a component score comes from an LLM call, the
   opportunity is invalid by construction — the core rule
   ("LLMs extract, code reasons") is being violated. This is a
   runtime check, not just a review guideline.

4. **No overlap with the terminology-collision, duplicate-inflation,
   or within-domain application-noise failure modes** listed below.
   The reasoning engine must, before scoring, run a self-check that
   answers "would this opportunity survive if we removed the noisy
   contributors from its evidence set?" If removing the failure-mode
   contributors drops paper support below the 3-paper floor, the
   opportunity is not valid.

5. **Explanation constructed by the synthesis step, not the ranker.**
   `Opportunity.explanation` is written by the Claude-side synthesis
   step from the deterministic evidence trail — it does NOT feed back
   into the score. If the explanation cannot be written from the
   evidence trail alone (e.g. needs LLM judgment about "which
   limitation is more important"), the opportunity is invalid: the
   scorer has under-specified its own output.

## What makes an opportunity non-trivial

Even a valid opportunity can be trivial — obvious to any working
researcher in the field, so surfacing it adds no signal. An
opportunity is **non-trivial** if at least one of the following holds:

1. **The gap is between fields the primary papers do not cite each
   other.** If Paper A reports a limitation and Paper B proposes a
   method that plausibly addresses it, the opportunity is trivial if
   A cites B or B cites A — the connection was already made. It is
   non-trivial when the citation graph shows no path between them.
   Requires the relationship layer (Phase 3) to be in place; before
   then, "non-triviality" reduces to (2) and (3).

2. **The gap contains an unresolved contradiction.** Two papers
   reporting incompatible findings on the same construct where the
   reasoning engine can name the specific claim IDs on both sides.
   Trivial version: both papers cite the same third paper as the
   canonical evaluation. Non-trivial version: the two report
   contradictory results and neither acknowledges the other.

3. **The gap is a future-work thread that stayed unfollowed for ≥ N
   years.** Concretely: `FutureWork.text` from a paper published in
   year Y is semantically similar to no `Claim.text` in any paper
   published in year Y+1 through the corpus cutoff. `N` is a
   config knob; a defensible starting value is 2 years. Note: given
   the 41% future-work coverage from abstracts alone (see schema
   pressure-test), this criterion is severely under-powered until OA
   full text is ingested.

4. **The method transfer is across a domain boundary the citation
   graph does not cross.** A calibration technique from tabular ML
   never referenced by an NLP paper is a non-trivial transfer
   opportunity; the two conventional citation-graph clusters need to
   be visible before the reasoning engine can call it non-trivial.

## What makes an opportunity actionable

An opportunity that is valid AND non-trivial can still be a bad
recommendation — too broad to translate into a research program.
**Actionable** requires:

1. **A named object of study.** The opportunity's title must contain
   at least one concrete construct (e.g. "the discrepancy between
   epistemic vs. aleatoric uncertainty under retrieval-augmentation
   in code-generation LLMs"). Titles like "improve calibration" fail
   this bar.

2. **A named minimal experiment.** The opportunity's explanation
   should suggest an experiment small enough that a graduate student
   could scope it in a week (not necessarily execute in a week, but
   scope). If the explanation is only "study X more", it is not
   actionable.

3. **A named contradiction or unresolved question, not a general
   agenda.** "Uncertainty quantification is important" is not
   actionable. "Papers X, Y, Z disagree on whether epistemic
   uncertainty decomposes linearly, and none has run the ablation
   Paper W's limitation section names" IS actionable.

4. **A cost floor the reader can estimate.** Even a hand-wavy one:
   "requires access to a model where log-probabilities are exposed",
   "requires ≥ N annotated samples of type T". This is what
   distinguishes a research prompt from a research proposal.

## Named failure modes

- Terminology collision across fields: two papers using the same term
  with different meanings (e.g. "calibration" in NLP vs. in materials
  science) being detected as a scientific contradiction. A
  contradiction is only valid if both claims concern the same
  construct, not merely the same word. Corpus contamination makes
  this failure mode more likely, so corpus purity is a precondition
  for contradiction scoring, not a nice-to-have.

  **Worked examples — intra-field collisions found in the 60-paper
  hand-review** (all within ML, all mis-classifiable as on-domain by
  keyword filters, all off-domain per the labelling rubric because
  their "calibration" is a different construct):
  - `openalex:W4378770815` *LLMs are not Fair Evaluators* — proposes
    a three-part "calibration" framework, but the construct being
    calibrated is LLM-as-judge order bias in **score normalization**,
    not the model's confidence-accuracy relationship. If the scorer
    counted this alongside confidence-calibration papers, it would
    be pooling two unrelated phenomena.
  - `openalex:W4377121527` *SLiC-HF: Sequence Likelihood Calibration
    with Human Feedback* — the paper's whole method name uses
    "calibration", but the construct is **likelihood shaping for
    preference alignment** in the RLHF-alternative sense. Two of
    these papers agreeing that "calibration works" would be an
    invalid signal at the reasoning-engine level; they're not making
    a compatible claim.
- Duplicate or near-duplicate papers (preprint + published version,
  or the same work across venues) counted as independent sources,
  inflating replication counts and any score that depends on the
  number of independent papers reporting a finding.
- Within-domain application noise: a paper that uses the domain
  vocabulary correctly but whose contribution lies in another task
  (e.g. medical summarization mentioning hallucination). These are
  not terminology collisions — the terms mean the same thing — but
  the paper is evidence about the application, not the property.
  Keyword filtering cannot separate these; only contribution-level
  judgment can.
- **DRAFT — prior-work limitation misattribution.** When a paper
  cites a limitation of prior work as motivation ("existing methods
  are miscalibrated, so we propose X"), a naive extractor emits it
  as a `Limitation` of the CURRENT paper. The persistent-limitations
  scorer would then count the same underlying limitation once per
  paper that cites it — turning citation-driven mention frequency
  into false replication signal. Countermeasure encoded in
  `docs/schema-pressure-test.md` decision #1: `Limitation.source_scope`
  field.
- **DRAFT — compound-claim under-splitting.** When an extractor
  emits a single `Claim` for a sentence carrying multiple assertions,
  the evidence chain becomes non-atomic: one `Evidence` row supports
  a multi-claim `Claim`, so the reasoning engine cannot check
  support for the individual assertions independently. 59% of the
  hand-review sample contained compound sentences; failing to split
  means a majority-share of downstream evidence attribution is
  wrong. Countermeasure in schema-pressure-test decision #2.
- **DRAFT — evaluation-set contamination in retrospective validation.**
  If the corpus at the frozen year Y contains papers that later
  claimed the "opportunity" the engine surfaced, the retrospective
  time-split test measures leakage, not discovery. Countermeasure:
  the corpus manifest must record the ingestion cutoff date; the
  retrospective test filters any paper whose OpenAlex `updated_date`
  or `created_date` post-dates the frozen cutoff.
- Mixed-fidelity corpus bias: full-text papers yield several times
  more limitations and future-work items than abstract-only papers
  (measured: ~2.8× limitations, ~11× own-work limitations, ~12×
  future-work — see `docs/findings/fulltext-vs-abstract-finding.md`),
  and full-text availability tracks venue and OA status, not scientific
  merit. Any scorer that counts independent papers reporting something
  will therefore systematically over-represent full-text-available work.
  This is structural and must be corrected for in scoring, not solved by
  better retrieval alone.

  **Severity is a function of coverage — record it per corpus.** The
  bias is not a fixed constant; it scales with the abstract-only share:
  - At **19% full text** (the expanded corpus *before* OA recovery), the
    bias was **severe, not marginal**: the two full-text-dependent
    scorers effectively ran on n=38 of 200 papers, so limitation-derived
    gaps would have over-represented arXiv-preprint-culture work almost
    entirely — the 162 abstract-only papers contributed structure and
    prior-work limitations but almost no own-work limitations or
    future-work. At that level the persistent-limitations and
    orphaned-future-work scorers are measuring "who posts to arXiv," not
    the field.
  - After Unpaywall + Europe PMC OA recovery, coverage is **54.5%
    full text** (109/200; arXiv 38, Unpaywall 63, Europe PMC 8). At this
    level the bias is **moderate, no longer severe**: the full-text
    scorers now draw from n=109 (≈3× the pre-recovery n=38), and full
    text is the majority of the corpus. The 45.5% abstract-only share is
    still above the ~30% baseline of any corpus, so the mixed-fidelity
    correction (weight or gate by `input_source`) is **still required** —
    but the corpus is no longer dominated by abstract-only papers, and
    the full-text-dependent scorers are now defined on a real majority of
    the corpus rather than a small arXiv-skewed slice.

  Because full-text availability correlates with venue/OA rather than
  merit, the residual 45.5% abstract-only papers are not random: they
  skew toward closed/hybrid journal work. Scoring must treat
  `abstract_only=true` as a fidelity flag, not drop those papers.
- **Small-corpus false positives.** Below a corpus size that plausibly
  contains the addressing work, several scorers report artifacts of
  corpus size rather than the field's behaviour:
  - *Orphaned-future-work scoring.* "No paper addressed this
    future-work statement" is only meaningful if a paper that *would*
    have addressed it is plausibly in the corpus. In a small corpus
    nearly every future-work item reads as unaddressed — not because
    the field ignored it, but because the corpus is a reading list, not
    a field snapshot. The scorer becomes unfalsifiable: it cannot
    distinguish a genuinely orphaned direction from one whose follow-up
    simply was not ingested.
  - *Structural-hole and disjoint-bridging scorers* are undefined below
    the size at which papers form actual clusters rather than a flat
    reading list. A "hole" between two literatures, or a "bridge"
    joining them, presupposes that the two literatures are each
    represented densely enough to be clusters; with tens of papers
    there are no clusters, only points, and the geometry these scorers
    read does not yet exist.

  Countermeasure: expand the corpus (snowball from the on-domain seeds,
  both citation directions, with an AI-subfield gate) to a size where
  the addressing/clustering work is plausibly present before running
  any of these scorers. This is a precondition, like corpus purity — a
  scorer run below its defined corpus size produces confident output
  that is an artifact of the input, not a finding.

## Matching rule for retrospective validation

The project's publishable claim is: at time Y, the reasoning engine
would have ranked opportunity O highly; between years Y+1 and Y+k,
research activity R actually occurred that addressed O. The
**matching rule** governs when we call R a match for O:

1. **Corpus freeze at year Y.** The reasoning engine sees only papers
   with `Paper.year ≤ Y` AND `Paper.created_date ≤ freeze_date`
   (the second guard defends against retroactive OpenAlex updates).
   The frozen corpus is snapshotted into `data/corpora/YYYY-frozen/`
   with a manifest hash.

2. **Evidence R is drawn from papers with `Paper.year` in
   [Y+1, Y+k].** A defensible k for the LLM-safety literature is 2
   years — that's roughly the peer-review lag plus one arXiv cycle.

3. **A matching R for opportunity O satisfies both:**
   - At least one paper in R contains a `Claim` whose normalized text
     is semantically close to `O.title` (embedding cosine similarity
     ≥ threshold, threshold chosen so the false-positive rate on a
     held-out negative set is < 5%);
   - AND at least one paper in R's `Claim.text` field, when compared
     against the pre-freeze corpus, has zero equivalent claim (i.e.
     the addressed opportunity was genuinely open at year Y).

4. **Precision, not recall.** The retrospective test reports what
   fraction of the reasoning engine's top-K opportunities were
   subsequently addressed. It does NOT try to measure how many
   subsequent-year research programs the engine failed to predict —
   the base rate for that is uncomputable without ground-truth
   research-program labels. Top-K precision is the honest metric.

5. **The rule is deterministic Python.** No LLM judgment enters the
   matching. `Claim.text` similarity uses a fixed embedding model
   (pinned in `docs/merge-policy.md` when Phase 3 ships) and a fixed
   threshold. If we later find the embedding cutoff is wrong, we
   change it in one place and re-run — the entire evaluation is
   reproducible from the frozen corpus and the code snapshot.

**Anti-goal:** the matching rule does NOT reward opportunities the
engine surfaced that are "interesting" but not addressed. Every
opportunity gets a binary match/no-match on the historical record. If
we relax this to "expert judgment says this was still a valuable
suggestion", the evaluation becomes uncheckable and the project loses
its only quantitative claim.
