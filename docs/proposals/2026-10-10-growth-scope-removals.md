# Proposal: remove papers added by weekly growth run #5 — **APPLIED 2026-10-10**

**Status: APPLIED (owner-approved 2026-10-10).** The owner approved the 4
proposed removals plus W7215843351 (ML fairness; owner's judgement). They
were applied by `tools/corpus/apply_removals.py data/removals/2026-10-10.json`
at no cost (₹0, ledger unchanged).

Each paper moved from the library's `prelabelled.json` "entries" to
"removed", with its reason. Nothing was deleted: its record, extraction
and spend stay on file. Weekly growth can never re-add a removed paper,
either by selection or by collection (tests in
`backend/tests/grow/test_scope.py`). The record is in
`docs/releases/2026-10-10-removals.json` and `docs/CHANGELOG.md`.

## Applied

| library | paper | reason |
|:--|:--|:--|
| Diet | W7218462786 | outside the core scope: no mortality or survival outcome (metabolic syndrome) |
| Diet | W7220707047 | outside the core scope: a commentary; mortality is mentioned only as background |
| Social media | W7220846371 | outside the core scope: no adolescents or young people |
| Social media | W7220964018 | outside the core scope: no adolescents or young people |
| ML fairness | W7215843351 | outside the core scope (owner's judgement): about people's AI literacy, not the fairness of algorithmic decisions |

**Papers:** Diet 103 → 101, Social media 103 → 101, ML fairness 102 → 101.

**Results shown, before → after (scorers re-run):**

- Diet: 11 → 11, unchanged.
- Social media: 32 → 32, unchanged.
- ML fairness: 60 → 58. Two open questions are no longer shown:
  `opp-ml-fairness-orphan-openalex-w3159960173-f1` and
  `opp-ml-fairness-orphan-openalex-w3203106571-f2`. Each needs at least 5
  later, topically near papers that do not address it. W7215843351 was one
  of exactly 5 for each, so each now has 4. These are the only results that
  depended on the removed papers. Two never-shown, set-aside method-transfer
  leads also dropped, because candidates are recomputed from the paper
  clusters.

**Correction to the original proposal below.** It said the ML fairness
results were unaffected. That was checked only for the 4 proposed papers;
W7215843351 was added later and does affect two results, as listed above.

---

*Original proposal, as written before approval:*

## The rule

From now on, weekly growth adds a paper only if both of these hold:

1. The domain rubric labels it **on-domain**. Borderline papers are
   excluded, as before.
2. It meets the domain's **core scope**
   (`backend/app/grow/scope.py`; deterministic, no language model):

| library | core scope required |
|:--|:--|
| Diet & mortality | A mortality or survival outcome. It must be in the title, or in an abstract sentence that reports a result (an association, a risk, an attributable estimate, or a defined outcome). A background mention does not count. |
| Social media & teens | Adolescents or young people **and** a mental-health outcome. |
| ML fairness | Fairness of algorithmic decisions: a fairness term and an algorithm or model term, in the title or in the same sentence. |

## The 9 papers run #5 added

All 9 passed the rubric as **on-domain**; none was borderline.

| library | paper | rubric reason | core scope | verdict now |
|:--|:--|:--|:--|:--|
| Diet | W7218462786 Mediterranean diet, physical activity and metabolic syndrome in breast cancer survivors | anchor + topic in title | no mortality or survival outcome (the outcome is metabolic syndrome) | **drop** |
| Diet | W7220707047 Beyond lifestyle advice: chronic disease prevention… (commentary) | anchor + topic within 30 tokens | mortality appears only as background ("NCDs account for a major share of global mortality") | **drop** |
| Diet | W7220864522 Sodium intake, mortality and life expectancy in US adults | strong term in title ('sodium intake') + 'all-cause mortality' | 'mortality' in title | keep |
| ML fairness | W7214947317 SLF–FST: stress-testing fairness under progressive label bias | 'algorithmic fairness' | same sentence: 'inequit' + 'machine learning' | keep |
| ML fairness | W7215843351 AI literacy as a driver of trust, fairness and evidence appraisal in public health | anchor + topic in title | title: 'fairness' + 'artificial intelligence' | keep (**your call**: passes the rule, but it is about people's AI literacy, not the fairness of an algorithm's decisions) |
| ML fairness | W7219603619 Human-centred AI framework for equitable higher-education enrolment | anchor + topic within 30 tokens | title: 'equit' + 'artificial intelligence'; the abstract addresses algorithmic bias in admissions | keep |
| Social media | W7220393051 Social media screen time, depression and anxiety among adolescents | anchor + topic in title | 'adolescen' + 'depress' | keep |
| Social media | W7220846371 Unifinal framing promotes intention to use social media for social connection | strong term in title ('social media') + 'loneliness' | no adolescents or young people | **drop** |
| Social media | W7220964018 NLP + LLM ensemble for detecting suicidal ideation in social media text | anchor + topic in title | no adolescents or young people (Reddit and Twitter posts, population unstated) | **drop** |

## Proposed removals (approve or strike each)

- [ ] diet-and-mortality: W7218462786
- [ ] diet-and-mortality: W7220707047
- [ ] social-media-teen-mental-health: W7220846371
- [ ] social-media-teen-mental-health: W7220964018

**Open questions that came only from these papers: none.** The papers are
from 2026. An open question needs its source paper to have been open for at
least 2 years, so none of their future-work items is shown.

Recomputing the scorers without the 4 papers (free) leaves the open-question
lists unchanged: Diet keeps 4 and Social media keeps 26. No shipped result
cites them.

The ML fairness papers are all kept. The 5 new ML fairness results from
run #5 drew on two of them (W7214947317 and W7219603619), so they are
unaffected by these removals.

The papers' extraction cost is already spent (part of ₹21.76). Removing them
refunds nothing.

## Already submitted, left as they are (as instructed)

| library | paper | core scope |
|:--|:--|:--|
| Diet | W7221006525 Comparative associations of six predefined dietary patterns with site-specific cancer… | **would fail**: the outcome is cancer incidence, not mortality. It will be collected next run. Add it to the list above if you want it removed after collection. |
| ML fairness | W7219660580 Deep learning–driven chest radiography… | passes: 'fairness' + 'deep learning' in title |

## What the rule costs

Measured on each library's founding on-domain papers:

| library | founding papers that would fail | which kind |
|:--|--:|:--|
| Diet & mortality | 30 of 67 | All have no mortality or survival term at all: CVD, diabetes or weight incidence, mechanisms, guidelines. Every founding paper that reports a mortality outcome passes (tested). |
| ML fairness | 6 of 99 | Governance, point-of-care testing, virtual worlds, attack detection, foundation models. Test: at most 10%. |
| Social media & teens | 21 of 68 | General-population or adult samples (Facebook studies, older adults, app reviews). |

The rule applies only to new candidates. Founding papers are not touched.
Weekly growth will now be narrower than the founding libraries, notably for
Diet (mortality only) and Social media (young people only).

## To apply after approval

Removing a paper means taking it out of the library's `prelabelled.json`
and rebuilding that library's reasoning and export, with no paid calls.
The run's result accounting will then record each result that leaves, with
its reason.
