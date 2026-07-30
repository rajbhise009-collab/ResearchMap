# ResearchMap — a methodological report on LLM-assisted literature-based discovery

**Standalone finding, 2026-07. Written for a reader who has not seen the
codebase.** Every number below is measured, not projected, unless marked as
an extrapolation. Detail lives in the `docs/findings/` and `docs/` files
cited per section.

## What was built, and the one rule

ResearchMap is a literature-based-discovery (LBD) pipeline for a single
scientific sub-domain (LLM calibration / uncertainty / hallucination). It
ingests papers, uses an LLM to decompose each into structured JSON (claims,
methods, limitations, future-work), builds a cross-paper relationship layer,
and runs a deterministic reasoning engine that surfaces candidate research
gaps with a traceable evidence chain.

The governing constraint: **LLMs EXTRACT, code REASONS.** An LLM only turns
paper text into structured records or classifies a single pair
("perception"); every count, weight, rank, and score is inspectable Python.
This report is mostly about what that discipline *revealed* when the outputs
were measured honestly.

Corpus: a 26-paper hand-labelled seed, snowball-expanded and then corrected
down to **113 clean papers** (67 full-text, 46 abstract-only). Model:
`gemini-3.6-flash`, temperature 0. Total spend to produce everything here:
**~$7.4**.

---

## 1. Full text is required for the signals LBD needs (paired, n=21)

*(detail: `docs/findings/fulltext-vs-abstract-finding.md`)*

A paired comparison over the 21 papers that had BOTH an arXiv full text and
an abstract — same papers, same model, same prompt, the only variable being
input source:

| signal (per paper) | abstract | full text | ratio |
|:--|--:|--:|--:|
| **own-work limitations** | 0.19 | 2.19 | **11.5×** |
| **future-work items** | 0.14 | 1.76 | **12.6×** |
| prior-work limitations *(negative control)* | 1.10 | 1.43 | 1.3× |

**The negative control is the point.** Prior-work limitations — which
authors state in abstracts and related-work framing — barely move. Only the
two own-paper-scoped signals, which live in discussion/conclusion sections
that abstracts omit, move an order of magnitude. This rules out "full text
just yields more of everything"; the lift is specific to *where the
information lives*.

**Lower-bound framing:** the comparison model is a small "Flash"-tier model
that tends to *under*-exploit long context. So the test is biased *against*
full text — yet full text wins by ~12×, making the effect a **conservative
lower bound**. A stronger extractor would widen the gap, not close it.

Consequence for anyone building LBD: abstract-only corpora starve exactly
the scorers that matter (own-work limitations, future-work). Budget for
full-text retrieval, and treat `abstract_only` as a fidelity flag, not a
minor caveat.

---

## 2. Corpus-scaling study — what scales, what doesn't

*(detail: `docs/findings/corpus-scaling-study.md`; free — subsampling the
113-paper corpus, 5 stratified draws per N)*

**Contradictions: the work scales, the yield does not.** Candidate pairs
(the deterministic cosine shortlist) grow **~N^1.89** — nearly pairwise,
exactly the super-linear shape a real-but-sparse signal would show. But
**confirmed contradictions are 0 at every N**. So the pairwise interaction is
present and the signal is absent, not merely sparse. With 0 in 256
candidates at full size, the confirmed rate is **bounded under ~0.4%**.
Scaling multiplies the bill without producing contradictions (see §5 for
why this is the *correct* result here).

**Structural holes: size-dependent — with a methodological caution.** Our
first pass concluded structural-hole yield was "flat / size-independent
(~10 at every N)." **That was wrong, and the error is instructive.** The
scorer clustered papers with a *fixed* k=8, which caps the number of cluster
pairs at k(k−1)/2 = 28 regardless of N — so flat yield was guaranteed by
construction (and the count was also hitting an output cap). Re-running the
sweep **uncapped, with k scaling as N**:

| k schedule | N=40 | N=60 | N=80 | N=100 |
|:--|--:|--:|--:|--:|
| fixed k=8 (uncapped) | 9.6 | 13.2 | 12.2 | 12.4 |
| k = round(√N) | 5.2 | 13.2 | 16.0 | 19.2 |
| k = round(N/10) | 2.8 | 5.4 | 12.2 | **19.2** |

With cluster granularity held constant (k∝N), yield **rises with N**
(2.8 → 19.2 across N=40→100), tracking the growing cluster-pair count.
**Lesson: a scaling curve produced under a fixed structural parameter can be
an artifact of that parameter, not a property of the data.** We reversed our
own conclusion after checking it — a caution worth carrying into any
"does-X-scale?" study.

---

## 3. Precision measurements — cosine is a shortlist, not an answer

Two scorers were measured against hand labels; both show the same shape.

**Future-work "addressed_by" matching** *(detail: `docs/relationship-layer.md`,
`scratch/futurework_audit.md`)*. Raw embedding cosine cannot express the
"addresses" relation: hand-labelling 40 items in the threshold-sensitive
band, **precision peaks at ~0.57 at any threshold** (best F1 = 0.52 at
cosine 0.74). The fix — a two-stage **cosine shortlist → LLM pair
classification** — reaches **F1 0.75 (precision 0.64, recall 0.90)**. The
LLM expresses a relation the geometry structurally cannot.

**Structural-hole leads** *(detail: `docs/findings/corpus-scaling-study.md`)*.
Same pattern: a semantic cosine shortlist produced 12 leads; an LLM confirm
step ($0.02, classification only) judged **only 2 of 12 SUBSTANTIVE** — 3
were trivial ("run a larger evaluation" / "apply method X to dataset Y"), 7
were topical adjacency (not actually addressing). **Substantive precision of
the semantic shortlist ≈ 1 in 6.** The confirm step is not optional.

General principle: embedding cosine is a good *recall-first shortlist* and a
bad *final answer* for any "addresses / contradicts / transfers" relation.
The reliable pattern is shortlist (cheap, deterministic) → single-pair LLM
classification (perception, bounded).

---

## 4. Failure taxonomy — what LBD gets wrong, and how to catch it

*(detail: `docs/findings/phase4-investigations.md`)*. Each failure below
produced a confident, plausible-looking output that was wrong. All were
caught by *reading the evidence chain*, which the "code reasons" discipline
makes possible.

1. **Experimental-regime conflation.** *Looks like:* the top-ranked
   opportunity — a "contradiction" that survey X says raising decoding
   temperature increases hallucination, while paper Y says temperature=0
   doesn't reduce it. *Mechanism:* Y measured hallucination as *repeating
   adversarially-injected false medical facts in clinical vignettes*; X
   described general open-ended sampling. Different regimes, both true. The
   `Claim` schema had no field for experimental condition, so the classifier
   compared sentences stripped of the very information that distinguishes
   "different regimes" from "disagreement." *Detected:* pulling the two
   claims and their sibling claims. *Cost:* it was the #1 opportunity, a
   false positive; the cheap partial (re-run the classifier with sibling
   claims as regime context, $0.51) drove confirmed contradictions to 0; a
   proper structured `Claim.condition` field + re-extraction is ~$5.4,
   backlogged.

2. **Duplicate-inflated independence counts.** *Looks like:* two "separate"
   unresolved contradictions (#1 and #11). *Mechanism:* the same hallucination
   survey existed as an arXiv preprint (2023) and its published version
   (2024) that were never merged — so it was counted twice, and both
   "contradictions" were the same pair. *Detected:* pulling the four papers
   behind #1/#11 by ID (identical titles, different DOIs/years). The
   corpus-assembly dedup keyed on `(title, YEAR)`, which by construction
   cannot collapse a cross-year preprint/published pair — the exact failure
   mode its own comment claimed to handle. *Cost:* free to fix (route
   assembly through the full 4-pass, author-aware dedup); corpus 200→198,
   then downstream. Affects *every* count-based scorer, not just
   contradictions.

3. **Permissive-default corpus contamination.** *Looks like:* orphaned
   future-work items about WikiQA variance and BoolQ document-level QA in a
   *calibration* corpus. *Mechanism:* two systematic label leaks — `"arxiv"`
   was in the venue allowlist (so any preprint auto-cleared as on-domain,
   admitting BoolQ, ARC, a text-classification survey…), and the labeller's
   default for no-signal was *borderline-keep* rather than exclude (admitting
   ~50% of snowball papers, a mix of real pre-LLM classics and off-domain
   noise like model compression and fake-news detection). *Detected:* tracing
   flagged opportunities to their source labels + counting admit reasons.
   *Cost:* free; fixing the rubric (remove arXiv rule; no-signal → exclude;
   add a high-precision strong-topic list to keep foundational pre-LLM work)
   cut the corpus 200 → 113 clean papers.

4. **Terminology collision.** *Looks like:* "5 papers agree on a
   computational-cost limitation." *Mechanism:* the normalized category
   pooled ≥4 distinct constructs (evaluation cost, training cost, inference
   cost, sampling cost). By contrast "calibration," post domain-filter,
   resolved to essentially one construct — so collision is a *per-term*
   problem, not universal. *Detected:* sampling the claims under each term.
   *Cost:* free; a config-driven same-construct gate splits gated categories
   by sub-construct before clustering, and the spurious 5-paper cluster
   dissolved.

5. **Corpus-relative orphan artifacts.** *Looks like:* 91% of future-work
   items "orphaned / never followed up." *Mechanism:* in a corpus that is a
   reading list rather than a field snapshot, "no later paper addressed this"
   mostly reflects corpus coverage, not the field. *Detected:* the 91% rate
   was not credible on its face. *Cost:* free; a guard that only calls an
   item orphaned when enough later, topically-near papers exist (else
   `indeterminate`) moved the split from 5% indeterminate to ~37%. Orphan
   claims must always carry the coverage caveat.

6. **Trivial method↔limitation pairings.** *Looks like:* a "method transfer"
   opportunity. *Mechanism:* semantically related but reduces to "evaluate on
   a bigger dataset" or "apply an existing method to another task" — a valid
   pairing that fails the non-triviality/actionability bar. *Detected:* the
   LLM confirm step (§3) flagged 3 of 12 as trivial. *Cost:* $0.02, part of
   the confirm pass.

The through-line: **plausible-looking output is the default failure**, and
the only defense is an inspectable evidence chain plus a human/LLM check on
what the numbers actually rest on.

---

## 5. The domain-coherence precondition (for anyone building LBD)

Contradiction-based LBD — the Swanson-style promise of "the engine finds the
disagreement no one noticed" — **requires a contested field.** Our corpus
returned **zero confirmed contradictions**, and that is the *correct* answer,
not a scorer failure: LLM calibration/uncertainty is a young, coherent
sub-field where papers largely corroborate or address orthogonal questions;
genuine same-construct, same-regime disagreements are rare. The candidate
count scaled ~N^1.89 while confirmed stayed at 0 precisely because the
interactions exist but the disagreements don't.

**State this as a domain-selection precondition:** before building
contradiction/structural-hole LBD, verify the target field is *contested and
mature* enough to contain the signal. A young consensus field will pay the
quadratic candidate bill for near-zero contradiction yield — not because the
method is broken, but because the field has not yet disagreed. Field
selection is a design decision upstream of any scorer.

---

## 6. Honest bottom line

**What worked.**
- Faithful extraction under "LLMs extract, code reasons"; every output traced
  to real paper IDs.
- The full-text finding (§1) — a clean, conservative, reusable result.
- The two-stage cosine→LLM pattern (§3): F1 0.52→0.75 for future-work; it
  turned 12 raw structural-hole leads into 2 defensible ones.
- The semantic structural-hole matcher: 0 → 12 leads for free, and the yield
  genuinely scales with corpus size (§2).
- The measurement discipline itself caught six distinct failure modes (§4),
  including reversing our own scaling conclusion.

**What didn't (in this domain).**
- Contradiction-based discovery: 0, because the field is coherent (§5) — a
  precondition failure, not a code failure.
- Persistent-limitations: only generic categories (computational-cost,
  small-sample-size) reached the evidence floor; low actionability.
- Orphaned-future-work: fires often but each item is weak and corpus-relative.

**What it cost.** ~**$7.4** total to build the corpus, extract 113 papers,
embed, run the relationship layer and reasoning engine, and run every
measurement above — under corrected thinking-token pricing (an early
accounting bug under-counted spend ~40% by ignoring `thoughtsTokenCount`,
which bills at output rates; all gates are now thinking-aware).

**The measured path forward.** The one axis that *does* scale here is
structural holes. Extrapolating the measured curves (leads scale ~linearly
with N under k∝N; substantive precision ~1-in-6): a **N≈500** corpus would
cost **~$20** (extraction ~$12, contradiction classification ~$8, ingestion
free — see the cost table in the scaling study) and yield on the order of
**~8 substantive structural-hole leads**. This is an extrapolation from five
points, not a law (§2's own caution applies), and it buys structural-hole
leads specifically — not contradictions (§5) and not less-generic persistent
limitations. Whether ~8 leads justifies ~$20 and the effort is the reader's
call; the honest contribution of this project is the *measurement*, not a
pile of discoveries.

---

### Pointers to detail

- `docs/findings/fulltext-vs-abstract-finding.md` — the paired extraction study.
- `docs/findings/corpus-scaling-study.md` — scaling curves, k-artifact correction, costs.
- `docs/findings/phase4-investigations.md` — the failure investigations with source IDs.
- `docs/relationship-layer.md` — two-stage matching, thresholds pinned by hand-labelling.
- `docs/reasoning-engine.md` — the five deterministic scorers, weights, and the LLM boundary.
- `docs/opportunity-criteria.md` — the validity/non-triviality/actionability spec and named failure modes.
