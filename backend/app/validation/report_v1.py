"""Write docs/findings/validation-v1.md and frontend/public/data/validation.json
from data/validation/v1/result.json (numbers by script, never by hand)."""
from __future__ import annotations

import json

from backend.app.config import REPO_ROOT

RES = REPO_ROOT / "data" / "validation" / "v1" / "result.json"
DOC = REPO_ROOT / "docs" / "findings" / "validation-v1.md"
PUB = REPO_ROOT / "frontend" / "public" / "data" / "validation.json"

PLAIN = {
    "supported": "The pre-registered test supports the claim.",
    "not supported": "The pre-registered test does not support the claim.",
    "not supported: popularity": ("The engine beat chance but not simple popularity, so the test does not "
                                  "support the claim that it finds anything beyond popular papers."),
    "inconclusive": ("Not yet validated. The pre-registered test was inconclusive: too few open questions to "
                     "tell a useful ranking from chance, and on the numbers it has, the engine did not do "
                     "better than ranking by citation count."),
}


def _ci(c):
    return f"[{c[0]}, {c[1]}]" if c and c[0] is not None else "—"


def main() -> int:
    r = json.loads(RES.read_text())
    R = r["results"]
    v = r["verdict"]
    rows = []
    for name, key in (("Engine (open-question score)", "engine"), ("Citations to the source paper up to Y", "citations_up_to_Y"),
                      ("Newest source paper first", "recency")):
        m = R[key]
        p = m["precision"]
        rows.append(f"| {name} | {m['auc']} | {_ci(m['auc_ci'])} | {p['5']:.2f} | {p['10']:.2f} | {p['20']:.2f} |")
    rnd = R["random"]
    rows.append(f"| Random ranking (10,000 permutations) | {rnd['auc_null_mean']} | — | "
                f"{rnd['precision_null_mean']['5']:.2f} | {rnd['precision_null_mean']['10']:.2f} | "
                f"{rnd['precision_null_mean']['20']:.2f} |")
    lib_rows = "\n".join(f"| {s} | {d['N']} | {d['addressed']} | {r['tau'][s]} |" for s, d in r["by_library"].items())
    DOC.write_text(f"""# Validation v1 — result (2026-10-09)

**Verdict (pre-registered categories): {v.upper()}.** {PLAIN[v]}

Protocol: docs/findings/validation-protocol-v1.md, committed before any
outcome was computed (commit `{r['protocol']['commit']}`). Run once, as
registered. Code: `backend/app/validation/v1.py`. Every OpenAlex fetch and
embedding is cached in `data/validation/v1/`, so it reproduces for free.

## Limits first

- **Citing is not addressing.** "Addressed" means a later paper that cites
  the source paper has an abstract close in meaning to the open question.
  That is a proxy: a citing paper can be close in topic without answering
  the question, and a paper can answer it without citing the source.
- **Underpowered by design.** The pool is {r['N']} open questions across
  four libraries, {r['addressed']} of them addressed ({r['share_addressed']:.0%}).
  Detecting AUC 0.65 at 80% power needs {r['n_required_at_observed_share']}
  at that share. Power here was {r['power_at_observed_share']}. The protocol
  therefore allowed no claim either way.
- **Small, uneven libraries.** Most open questions come from two libraries
  (ML fairness, Social media). Diet contributed 4, LLM calibration 1.
- **The hand audits behind the libraries are the builder's own,** not
  experts'.
- **Caps:** at most {r['cap_used']} citing papers per open question (the
  smallest pre-registered cap, forced by the ₹20 budget); abstracts cut to
  600 characters. Papers with no abstract in OpenAlex are not seen.
- **Calibration:** τ was set per library from the libraries' own older
  papers (amendment of 2026-10-09). That method was chosen after the
  pilot, which therefore does not count.

## Numbers

| ranking | AUC | 95% CI | P@5 | P@10 | P@20 |
|:--|--:|:--|--:|--:|--:|
{chr(10).join(rows)}

- **Engine against random:** permutation p = {rnd['p_auc']} for AUC;
  p@5 = {rnd['p_precision'].get('5')}, p@10 = {rnd['p_precision'].get('10')},
  p@20 = {rnd['p_precision'].get('20')}.
- **Engine minus citation baseline:** AUC difference 95% CI
  {_ci(R['engine_minus_citation_auc_ci'])}.
- **Popularity-matched subset:** {R['matched']['pairs']} pairs, engine AUC
  {R['matched']['auc']} {_ci(R['matched']['auc_ci'])}.

| library | open questions | addressed | τ |
|:--|--:|--:|--:|
{lib_rows}

## Reading it plainly

On these numbers the engine's ranking is not distinguishable from chance,
and it did not beat ranking by how often the source paper was already cited.
On the point estimates, citation count did slightly better. The test was too
small to show either way. The project therefore makes **no validation
claim**. A powered test needs at least {r['n_required_at_observed_share']}
open questions at this share, which means larger historical libraries. Any
change to this protocol is a v2 with its own pre-registration.
""")
    PUB.write_text(json.dumps({
        "verdict": v, "plain": PLAIN[v], "protocol_commit": r["protocol"]["commit"],
        "n": r["N"], "addressed": r["addressed"], "n_required": r["n_required_at_observed_share"],
        "power": r["power_at_observed_share"],
        "engine_auc": R["engine"]["auc"], "engine_auc_ci": R["engine"]["auc_ci"],
        "citation_auc": R["citations_up_to_Y"]["auc"], "citation_auc_ci": R["citations_up_to_Y"]["auc_ci"],
        "recency_auc": R["recency"]["auc"], "random_auc": rnd["auc_null_mean"],
    }, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
