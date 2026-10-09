# Validation v1 — result (2026-10-09)

**Verdict (pre-registered categories): INCONCLUSIVE.** Not yet validated. The pre-registered test was inconclusive: too few open questions to tell a useful ranking from chance, and on the numbers it has, the engine did not do better than ranking by citation count.

Protocol: docs/findings/validation-protocol-v1.md, committed before any
outcome was computed (commit `1bcdb4b`). Run once, as
registered. Code: `backend/app/validation/v1.py`. Every OpenAlex fetch and
embedding is cached in `data/validation/v1/`, so it reproduces for free.

## Limits first

- **Citing is not addressing.** "Addressed" means a later paper that cites
  the source paper has an abstract close in meaning to the open question.
  That is a proxy: a citing paper can be close in topic without answering
  the question, and a paper can answer it without citing the source.
- **Underpowered by design.** The pool is 88 open questions across
  four libraries, 15 of them addressed (17%).
  Detecting AUC 0.65 at 80% power needs 209
  at that share. Power here was 0.446. The protocol
  therefore allowed no claim either way.
- **Small, uneven libraries.** Most open questions come from two libraries
  (ML fairness, Social media). Diet contributed 4, LLM calibration 1.
- **The hand audits behind the libraries are the builder's own,** not
  experts'.
- **Caps:** at most 5 citing papers per open question (the
  smallest pre-registered cap, forced by the ₹20 budget); abstracts cut to
  600 characters. Papers with no abstract in OpenAlex are not seen.
- **Calibration:** τ was set per library from the libraries' own older
  papers (amendment of 2026-10-09). That method was chosen after the
  pilot, which therefore does not count.

## Numbers

| ranking | AUC | 95% CI | P@5 | P@10 | P@20 |
|:--|--:|:--|--:|--:|--:|
| Engine (open-question score) | 0.574 | [0.429, 0.713] | 0.00 | 0.10 | 0.25 |
| Citations to the source paper up to Y | 0.601 | [0.438, 0.76] | 0.60 | 0.40 | 0.25 |
| Newest source paper first | 0.474 | [0.317, 0.628] | 0.00 | 0.00 | 0.05 |
| Random ranking (10,000 permutations) | 0.5 | — | 0.17 | 0.17 | 0.17 |

- **Engine against random:** permutation p = 0.1857 for AUC;
  p@5 = 1.0, p@10 = 0.86,
  p@20 = 0.2214.
- **Engine minus citation baseline:** AUC difference 95% CI
  [-0.225, 0.176].
- **Popularity-matched subset:** 15 pairs, engine AUC
  0.569 [0.356, 0.779].

| library | open questions | addressed | τ |
|:--|--:|--:|--:|
| llm-calibration | 1 | 1 | 0.6326 |
| diet-and-mortality | 4 | 3 | 0.6539 |
| ml-fairness | 54 | 6 | 0.7544 |
| social-media-teen-mental-health | 29 | 5 | 0.7351 |

## Correction (2026-10-09, same day)

The first run listed each library's paper files in directory order, which
differs between platforms and checkouts. The seeded draws behind τ
therefore depended on the machine; the weekly workflow's runner caught it
(two τ values differed). The code now lists files in sorted order and the
numbers above were recomputed from the same cached data at no cost.

- τ changed for Diet (0.6691 → 0.6539) and Social media (0.7348 → 0.7351).
- The set of addressed questions, every measure and the verdict are
  unchanged.

The original record is kept in
`data/validation/v1/result_2026-10-09_original_order.json`. This is a
reproducibility fix, not a parameter change.

## Reading it plainly

On these numbers the engine's ranking is not distinguishable from chance,
and it did not beat ranking by how often the source paper was already cited.
On the point estimates, citation count did slightly better. The test was too
small to show either way. The project therefore makes **no validation
claim**. A powered test needs at least 209
open questions at this share, which means larger historical libraries. Any
change to this protocol is a v2 with its own pre-registration.
