# Prompt v1.1.0 — proposal (NOT applied)

Based on reading all 30 real Gemini 3.6 Flash extractions under
`v1.0.0`. **Do not apply without approval** — bumping the prompt
changes `prompt_hash`, which invalidates the 30 cached extractions and
forces a re-run.

Each change below cites the specific v1.0.0 behaviour it fixes.

## 1. Remove `extractor` and `extracted_at` from the schema example

**Observed:** the model echoed the literal example values from the
prompt — every extraction came back with `"extractor":
"gemini-flash-2.5"` (a stale wrong string) and a fabricated
`"extracted_at": "2025-01-01T00:00:00Z"`.

**Already mitigated in code** (the orchestrator now overrides both
fields authoritatively — committed this session). But the model still
spends output tokens emitting them, and the echo is a latent trap if
the override is ever removed.

**Change:** delete the `extractor` and `extracted_at` lines from the
JSON schema block in the prompt. They are provenance the code owns;
the model should never see or emit them.

## 2. Fix the `confidence` field — it is currently all 1.0

**Observed:** 29 of 30 papers returned `confidence: 1.0` on every
single claim; one paper had a lone 0.95. The field carries zero
signal — it does not discriminate anything.

**Root cause:** the v1.0.0 definition ("your confidence that the
extracted text faithfully represents what the paper says") invites 1.0
for any near-verbatim extraction, which is almost all of them.

**Change:** redefine confidence to track *evidential strength of the
claim within the paper*, with anchored guidance:
- `1.0` — a headline result with a specific quantified figure
  ("AUROC 0.781").
- `0.7` — a stated finding without a specific number.
- `0.4` — a comparative or promotional assertion ("more transparent",
  "cost-effective") not backed by a reported measurement.
Give the model those three anchors verbatim. This turns confidence
into a usable down-weighting signal for the reasoning engine.

## 3. Stop extracting promotional claims as high-confidence findings

**Observed:** Chainpoll produced 11 claims including "ChainPoll is
cost-effective", "offers greater transparency", and "exceeds industry
standards by over 23%" — all `type=finding, confidence=1.0`. These are
marketing, not evidence. A persistent-limitations / support scorer
that treats them as findings inherits promotional noise.

**Change:** add a rule — "Do NOT extract self-promotional or
comparative superiority claims (e.g. 'more efficient', 'more
transparent', 'state-of-the-art') as findings UNLESS the paper gives a
specific measured result for that claim. When in doubt, assign the
lower confidence anchor from rule 2 rather than dropping it."

## 4. Tighten `source_scope` toward catching own-work limitations

**Observed:** 73% agreement (22/30) with my hand labels. The
disagreements cluster on the model UNDER-extracting `this_work`
limitations — it reliably tags prior-work motivation ("existing
methods X have problem Y") but often misses the paper's own stated
weaknesses. Example: the UQ survey (`W4411121371`) — I labelled
own-work (the survey analyses method strengths/weaknesses), the model
emitted only a prior_work limitation about LLM hallucination in
general.

**Change:** add an explicit `this_work` trigger — "If the paper
EVALUATES something and reports where its own method, model, or
findings perform poorly, fall short, or are constrained, that is a
`this_work` limitation — even if phrased mildly. Extract it." Plus one
worked example of each scope.

**Note:** one apparent disagreement was the model being *right*: on
`W4414620308` (Trustworthy Summarization) the model correctly found no
stated limitation, where my hand-label of "both" over-read the
abstract. So the true agreement is a bit higher than 73%; don't
over-correct.

## 5. NOT changing: future-work sparsity

25 of 30 papers extracted zero future-work items. This is **not** a
prompt bug — it is the abstract-only corpus property already
documented in `docs/schema-pressure-test.md` (41% of abstracts carry
any future work; most future-work lives in the paper's Discussion
section). No prompt change fixes this; OA full-text ingestion is the
lever. Leave the future-work instructions as-is.

## 6. NOT changing: the compound-splitter contract

The splitter fired **0 times across all 30 papers** — because Gemini
3.6 Flash already atomizes compound sentences itself (e.g. BIG-Bench's
"performance and calibration both improve with scale" came back as two
separate claims). The splitter is a safety net for weaker models that
don't self-atomize; keep it, but note it is currently dormant on this
model. The v1.0.0 prompt rule 1 (one atomic claim per entry) is doing
the work at generation time — keep it, and it pairs well with change
#3 above.

## Cost of applying

Re-running all 30 papers under v1.1.0: ~30 × (1,400 in + 1,600 out
tokens) ≈ 90k tokens, ~$0.20 reference (free tier — not billed). The
real cost is the cache invalidation, not dollars: the 30 v1.0.0
extractions become stale and any Phase-3 work started against them
would need redoing. Apply v1.1.0 BEFORE building relationships, not
after.
