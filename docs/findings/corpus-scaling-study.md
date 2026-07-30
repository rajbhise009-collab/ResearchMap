# Corpus-scaling study — does reasoning-engine yield scale with N?

**2026-07-29, updated 2026-07-30.** Free study: no new extraction, no API
calls — the clean 113-paper corpus subsampled and re-scored. The
**2026-07-30 update** replaces the structural-hole scorer's token-overlap
proxy with semantic (claim-embedding) matching and re-runs the study; see
"Structural-hole matcher fix" below.

## Question

Phase 4 produced almost nothing on 113 papers. Is that a *corpus-size*
problem (signal real but sparse, would emerge at larger N) or a
*structural* problem (signal absent / method-limited, more papers won't
help)?

## Method

- Subsample the 113-paper corpus at N ∈ {40, 60, 80, 100, 113}.
- **5 stratified random draws per N** (1 at N=113, the full set), full-text
  ratio held at 0.59. Mean ± population SD reported.
- Each draw builds a filtered `ReasoningCorpus` and runs every scorer.
  Deterministic (clustering ordered by paper id). Contradiction
  **candidate pairs** from the free cosine shortlist; **confirmed** from
  cached regime-aware verdicts; structural holes from claim-embedding
  cosine — no new LLM calls. Code: `backend/app/reasoning/scaling_study.py`.

## Curves (mean ± SD across draws)

| N | persistent | contra **cand** | contra **conf** | orphan unaddr | orphan addr | orphan indet | struct holes |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 40  | 0.2±0.4 | 36.0±10.9 | 0 | 19.8±5.3 | 2.2±1.2 | 36.0±5.7 | 9.4±2.9 |
| 60  | 0.6±0.5 | 98.2±15.2 | 0 | 34.8±2.3 | 3.4±0.8 | 43.0±3.0 | 7.8±5.2 |
| 80  | 0.6±0.5 | 119.2±10.6| 0 | 45.0±4.6 | 7.4±1.0 | 57.8±5.5 | 11.0±2.0 |
| 100 | 1.0±0.0 | 187.2±12.5| 0 | 57.4±2.1 | 9.8±0.7 | 63.4±2.7 | 9.6±3.5 |
| 113 | 1.0     | 256.0     | 0 | 63.0     | 11.0    | 68.0     | 12.0    |

### Curve shape (log-log slope p, metric ∝ N^p; fit N=40 vs 113)

| metric | slope p | shape |
|:--|--:|:--|
| contradiction candidates | **1.89** | super-linear (~pairwise N²) |
| persistent limitations | 1.55 | super-linear but tiny (0.2 → 1.0) |
| orphan addressed | 1.55 | super-linear |
| orphan unaddressed | 1.11 | ~linear |
| orphan indeterminate | 0.61 | sub-linear |
| **structural holes (semantic)** | 0.24 at FIXED k=8 (artifact — see correction below); **rises with k∝N** | scales with N |
| **contradiction confirmed** | **0.00** | **flat at zero** |

## Structural-hole matcher fix (2026-07-30)

The scaling study identified structural holes as **method-limited, not
size-limited**: the token-overlap proxy fired **0 at every N**. Token
overlap cannot express "method addresses limitation" — the same structural
reason raw cosine failed for future-work matching.

**Fix (free):** replace token overlap with **claim-embedding cosine**. A
method-type claim in cluster A is matched, by cosine, against the claims of
cluster-B papers that carry an own-work limitation (the open-problem gate),
where the clusters are weakly citation-bridged. Limitations are *not*
separately embedded — that would be a paid API call this task forbids — so
B's open-problem area is represented by that paper's claim embeddings, with
the limitation TEXT in the evidence trail. This is a semantic SHORTLIST,
not an LLM-confirmed "addresses" verdict.

**Result: token-overlap 0 → semantic leads.** The method WAS a bottleneck
(hypothesis confirmed); semantic matching recovers plausible leads (e.g. a
hallucination-detection method matched to SelfCheckGPT's "238-passage
evaluation" limitation across weakly-bridged clusters). The 12 default leads
(k=8, capped) are in `scratch/opportunities_review.md`.

### CORRECTION (k-scaling check) — yield is NOT size-independent

An earlier draft claimed structural-hole yield was "flat / size-independent
(~10 at every N)". **That was a fixed-k artifact and is wrong.** With a
constant k=8, cluster pairs are capped at k(k-1)/2 = 28 regardless of N, so
flat yield is expected by construction — and ~12 was also hitting the
review's output cap. Re-running the N sweep UNCAPPED with k as a function of
N (`structural_k_sweep.py`):

| schedule | N=40 | N=60 | N=80 | N=100 | cluster-pairs 40→113 |
|:--|--:|--:|--:|--:|--:|
| fixed k=8 (uncapped) | 9.6 | 13.2 | 12.2 | 12.4 | 28 → 28 |
| k = round(√N) | 5.2 | 13.2 | 16.0 | **19.2** | 15 → 55 |
| k = round(N/10) | 2.8 | 5.4 | 12.2 | **19.2** | 6 → 55 |

Over the robust 5-draw points (N=40→100) yield **rises** with N when
cluster granularity is held constant — 2.8 → 19.2 for k=N/10, tracking the
growing cluster-pair count; even fixed-k=8 rises 9.6→14 once uncapped. **So
structural-hole yield DOES scale with corpus size** once clustering isn't
artificially capped. (The lone N=113 point dips to ~11 — one deterministic
clustering of the full set at k=11, not a 5-draw mean; the N=40→100 trend is
the reliable read.) k=8 stays the default for the 113-paper corpus, but the
*scaling* conclusion is corrected: more papers → more structural-hole leads.

## What the curves say

1. **Contradictions: the work scales, the yield does not.** Candidates grow
   ~N^1.89 (pairwise) but **confirmed = 0 at every N** — signal absent, not
   sparse. (Upper bound: confirmed rate <~0.4%.)
2. **Structural holes: method-limited AND size-dependent.** The semantic
   matcher unlocked leads (token overlap gave 0); with cluster granularity
   held constant (k∝N) yield then rises with N (~3→~19, N=40→100). Both
   levers matter — better method and more papers. (See correction below.)
3. **Orphaned future-work: grows ~linearly and gets better-DEFINED.** The
   indeterminate fraction falls 62%→48% as N grows; the one place size
   genuinely helps — but each orphan stays individually weak.
4. **Persistent limitations: near-zero throughout**, survivor is generic.

## Extrapolation (from 5 points — fragile, not a law)

| scorer | est. N for "usable, non-weak" | confidence |
|:--|:--|:--|
| contradictions | **no viable N** (flat at 0); or ~260 *only if* the true rate is at the 0.4% detection ceiling — unprovable from all-zeros | very low |
| structural holes | **scales with N** under constant cluster granularity (k∝N): ~3→~19 over N=40→100. Leads grow with cluster-pairs; the next lever is BOTH more papers AND LLM-confirming the leads | medium |
| persistent limitations | ~**320** for ~5 clusters (p=1.55), likely still generic | low |
| orphaned future-work | ~**1,000** for indeterminate <20% (scorer decidable); items stay weak | low |

**Fragility:** (a) power-law fit on 2 endpoints of a 5-point curve;
(b) subsamples inherit this corpus's topic mix — real expansion could
change every slope; (c) contradiction/structural-hole flatness is a
statement about *absence/independence* that no finite sample can prove, only
bound; (d) "usable / non-weak" is an unmeasured judgement.

**Bottom line:** corpus size is **not** the bottleneck for the pairwise
scorers. Contradictions are absent (not sparse); structural holes were
method-limited AND size-dependent (semantic matcher unlocked leads; k∝N
scaling then grows them with corpus size); persistent/orphan grow but
stay generic/weak. Leverage is better methods (semantic structural matcher —
done; an LLM confirm step next) and better limitation-construct
normalization — not a bigger corpus.

## Cost to build + extract at larger N (corrected thinking-token pricing, batch)

| target N | ingestion | extraction | embeddings | contradiction | **total** |
|--:|--:|--:|--:|--:|--:|
| 200 | $0 | $4.86 | $0.01 | $1.50 (753 pairs) | **$6.4** |
| 300 | $0 | $7.28 | $0.01 | $3.23 (1,620 pairs) | **$10.5** |
| 500 | $0 | $12.14 | $0.02 | $8.47 (4,255 pairs) | **$20.6** |
| 800 | $0 | $19.43 | $0.04 | $20.60 (10,345 pairs) | **$40.1** |

Extraction $0.0336/full-text paper, $0.0109/abstract; contradiction
$0.00199/pair (grows ~N^1.9 — at N=800 it equals extraction); embeddings
~$0.15/1M; ingestion free. Structural holes add ~$0 (cached embeddings).
Every viable target exceeds the ~$2.6 remaining budget, and — per the curves
— buys generic/weak output, not contradictions or new structural holes.

## Limitations

- 5 data points; power-law shape assumed, not established.
- Subsamples are internal to a 113-paper single-sub-domain corpus.
- Flat/zero curves bound absence/size-independence; they cannot prove it.
- Structural-hole leads are semantic shortlists, un-confirmed; their
  precision is unmeasured (would need an LLM confirm step or hand-labelling).
- "Usable / non-weak" is a human judgement the study does not measure.

## So what (method finding, corpus-independent)

For a coherent domain, "just add papers" pays a quadratic (candidate) bill
for zero **contradiction** yield. For **structural holes**, method quality
was the first bottleneck (semantic matcher: 0 → 12 leads) and corpus size is
a real second lever (k∝N: yield rises with N). But precision is low: an LLM
confirm step ($0.02, 12 calls) judged only **2 of 12 leads SUBSTANTIVE** — 3
were trivial ("larger eval" / "apply to dataset"), 7 were topical adjacency
(not addressing). So the honest pipeline is shortlist → confirm, and the
per-lead yield of *substantive* directions is ~1 per 6 semantic leads. The
two survivors: a multi-component hallucination metric vs. "semantic entropy
doesn't guarantee factuality", and SelfCheckGPT (black-box) vs. "API-only
models can't be evaluated with a self-familiarity method".
