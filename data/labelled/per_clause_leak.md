# Per-clause leak breakdown — Phase 2 diagnostic

- Sample size: **200** papers
- Raw dump: `data/live_samples/phase2_diagnostic_raw.json` (sha256[:12] = `db26b9f74087`)
- Credit ledger: `{"calls": 1, "credits_used_this_run": 10, "per_endpoint_credits": {"works.search": 10}, "daily_limit": 10000, "daily_remaining": 9937, "seconds_until_reset": 32785}`
- Query filter (frozen): `title_and_abstract.search:("language model" OR "LLM" OR "large language model" OR "neural text generation") AND (calibration OR "uncertainty quantification" OR abstention OR "selective prediction" OR "hallucination detection" OR "confidence estimation" OR "epistemic uncertainty"),primary_topic.subfield.id:1702,type:article|preprint,publication_year:>2018`
- Anchor+topic co-occurrence window: 30 tokens

## Heuristic label distribution

| Label | Count | Share |
|:------|------:|------:|
| on-domain | 180 | 90.0% |
| borderline | 19 | 9.5% |
| off-domain | 1 | 0.5% |

**Heuristic-measured on-domain rate** (on-domain / total) = **90.0%**.

**IMPORTANT: do not read this as precision.** The heuristic is designed to catch CROSS-DOMAIN contamination (chemistry, materials science, medicine venues), which the `primary_topic.subfield.id:1702` filter already removed at query time — so `off-domain` will be near-zero regardless of true within-AI noise. The `borderline` bucket is where within-AI application papers accumulate; the 60-row hand-review CSV is the definitive precision measurement, not this table.

## Per-topic-term leak (strict off-domain rate)

Rate = fraction of papers matching this topic term that the heuristic labelled off-domain. Ranked most-leaky first. Sparse by design — see note above.

| Topic term | Matches | Off-domain hits | Leak rate |
|:-----------|--------:|----------------:|----------:|
| 'calibration' | 105 | 0 | 0.0% |
| 'uncertainty quantification' | 31 | 0 | 0.0% |
| 'abstention' | 6 | 0 | 0.0% |
| 'selective prediction' | 3 | 0 | 0.0% |
| 'hallucination detection' | 40 | 0 | 0.0% |
| 'hallucination' | 49 | 0 | 0.0% |
| 'confidence estimation' | 7 | 0 | 0.0% |
| 'epistemic uncertainty' | 8 | 0 | 0.0% |

## Per-topic-term leak (non-on-domain rate — borderline + off-domain)

The heuristic-informative view. Rate = fraction of papers matching this topic term that the heuristic did NOT confidently label on-domain. Ranked highest-rate first. Not conclusive (borderline includes some real on-domain papers whose co-occurrence didn't tighten enough), but it's the best cheap signal for which clause is pulling the most within-AI grey area.

| Topic term | Matches | Non-on-domain hits | Rate |
|:-----------|--------:|-------------------:|-----:|
| 'epistemic uncertainty' | 8 | 2 | 25.0% |
| 'calibration' | 105 | 8 | 7.6% |
| 'uncertainty quantification' | 31 | 2 | 6.5% |
| 'hallucination' | 49 | 2 | 4.1% |
| 'hallucination detection' | 40 | 1 | 2.5% |
| 'abstention' | 6 | 0 | 0.0% |
| 'selective prediction' | 3 | 0 | 0.0% |
| 'confidence estimation' | 7 | 0 | 0.0% |

## Per-anchor-term leak (strict off-domain rate)

| Anchor term | Matches | Off-domain hits | Leak rate |
|:------------|--------:|----------------:|----------:|
| 'language models' | 185 | 1 | 0.5% |
| 'large language models' | 159 | 1 | 0.6% |
| 'language model' | 31 | 0 | 0.0% |
| 'llm' | 98 | 0 | 0.0% |
| 'llms' | 138 | 0 | 0.0% |
| 'large language model' | 23 | 0 | 0.0% |
| 'neural text generation' | 0 | 0 | - |

## Per-anchor-term leak (non-on-domain rate)

| Anchor term | Matches | Non-on-domain hits | Rate |
|:------------|--------:|-------------------:|-----:|
| 'large language model' | 23 | 4 | 17.4% |
| 'language model' | 31 | 5 | 16.1% |
| 'llm' | 98 | 8 | 8.2% |
| 'language models' | 185 | 14 | 7.6% |
| 'large language models' | 159 | 12 | 7.5% |
| 'llms' | 138 | 10 | 7.2% |
| 'neural text generation' | 0 | 0 | - |

## Files for review

- `data/labelled/heuristic_full_labels.csv` — all 200 papers with heuristic label and matched terms.
- `data/labelled/corpus_relevance_review.csv` — 60-paper sample with an empty `on_domain` column for hand-labelling.
- `data/live_samples/phase2_diagnostic_raw.json` — full OpenAlex response body + credit-ledger headers.

## Agreement between heuristic and hand labels

Not yet measurable — the `on_domain` column in the review CSV is empty until Raj fills it in. Once filled, compute agreement with a follow-up pass over the CSV. Fields to expect: rows where heuristic said `on-domain` but human said `off-domain` (false positives), and vice versa (false negatives).