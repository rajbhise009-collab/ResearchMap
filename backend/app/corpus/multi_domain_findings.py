"""Assemble the per-domain findings from extractions + contradictions.

Post-hoc analysis, no LLM calls. Reads:
  data/domains/<slug>/extractions (via the shared extraction cache)
  data/domains/<slug>/reasoning/{contradictions,supports,nones}.json

Produces:
  - assertion_strength distribution (lexical firm/hedged classifier)
  - gap-type counts (limitations by category, future-work counts)
  - contradiction summary (count + top 5 examples per domain)
  - predictor-check verdict (diet: does actual contradiction yield
    match its predicted 0.44 or contradict it?)

Prints one JSON dump to stdout; also writes
`data/domains/multi_domain_findings.json` for the exporter to pick up.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.corpus.multi_domain_reason import load_extractions  # noqa: E402


HEDGE_MARKERS = (
    " may ", " might ", " could ", " possibly ", " perhaps ",
    "appears to", "seems to", "tends to", "suggests", "suggest",
    " likely ", " unlikely ", " probable ", " plausible ",
    " we speculate", " we hypothesize", " we hypothesise",
    "remains unclear", "is not clear", "it is possible that",
    " indicate that", " may indicate", " may suggest", " may imply",
    "warrant further", "warrants further",
)


def is_hedged(text: str) -> bool:
    """Lexical firm-vs-hedged classifier. Any hedge marker in the claim
    text → hedged. Matches the schema-pressure-test's 91% firm baseline
    (docs/schema-pressure-test.md § 2)."""
    if not text:
        return False
    padded = f" {text.lower()} "
    return any(m in padded for m in HEDGE_MARKERS)


def assertion_strength(exts) -> dict:
    from collections import Counter
    c = Counter()
    for e in exts:
        for cl in (e.claims or []):
            c["hedged" if is_hedged(cl.text) else "firm"] += 1
    total = sum(c.values())
    return {"total_claims": total, "firm": c["firm"], "hedged": c["hedged"],
            "firm_share": c["firm"] / total if total else 0.0,
            "hedged_share": c["hedged"] / total if total else 0.0}


def gap_type_counts(exts) -> dict:
    from collections import Counter, defaultdict
    lim_cats = defaultdict(set)
    fw_count = 0
    for e in exts:
        for l in (e.limitations or []):
            cat = getattr(l, "normalized_category", None) or "uncategorized"
            lim_cats[cat].add(e.paper_id)
        fw_count += len(e.future_work or [])
    return {
        "n_papers": len(exts),
        "n_limitations": sum(len(v) for v in lim_cats.values()),
        "limitation_category_top": [
            {"category": k, "n_independent_papers": len(v)}
            for k, v in sorted(lim_cats.items(), key=lambda x: -len(x[1]))[:10]
        ],
        "n_future_work_items": fw_count,
    }


def contradiction_summary(slug: str) -> dict:
    """Read contradictions.json for a domain if it exists."""
    p = REPO_ROOT / "data" / "domains" / slug / "reasoning" / "contradictions.json"
    if not p.exists():
        return {"n_contradictions": 0, "examples": [],
                "status": "no contradiction pass run"}
    d = json.loads(p.read_text())
    examples = [
        {"a_paper_id": r["a_paper_id"], "b_paper_id": r["b_paper_id"],
         "a_text": r["a_text"][:200], "b_text": r["b_text"][:200],
         "similarity": r["similarity"],
         "explanation": r["explanation"][:280]}
        for r in d.get("items", [])[:5]
    ]
    return {"n_contradictions": d.get("n", 0), "examples": examples}


def predictor_check(diet_contradictions: int) -> dict:
    """Diet was chosen against its 0.44 (moderate) predictor score. The
    predictor's implicit prediction: FEWER contradictions than the top-
    ranked domains (LLM-cal 0.818 → measured 0). If diet finds >=3
    confirmed contradictions, reputation beat the predictor."""
    llm_cal_confirmed = 0  # frozen 2026-07 result
    verdict = ("Reputation BEAT predictor: diet-and-mortality's 0.44 "
                 "'moderate' rating understated its actual contradiction "
                 f"yield ({diet_contradictions} confirmed vs LLM-cal's "
                 f"{llm_cal_confirmed} at predictor score 0.818)."
                 if diet_contradictions >= 3 else
                 "Predictor NOT overturned: diet-and-mortality's "
                 f"{diet_contradictions} confirmed contradictions is not "
                 f"materially higher than LLM-cal's {llm_cal_confirmed} "
                 f"despite the different reputation. The 0.44 predictor "
                 f"score is compatible with this yield, and the predictor's "
                 f"one measured failure (over-predicting llm-calibration) "
                 f"remains its only documented directional error.")
    return {
        "predictor_score_diet": 0.44,
        "predictor_score_llm_cal": 0.818,
        "confirmed_llm_cal": llm_cal_confirmed,
        "confirmed_diet": diet_contradictions,
        "verdict": verdict,
    }


def main() -> int:
    out = {"generated_at": None}
    diet_exts = load_extractions("diet-and-mortality")
    fair_exts = load_extractions("ml-fairness")

    out["diet-and-mortality"] = {
        "n_extractions": len(diet_exts),
        "assertion_strength": assertion_strength(diet_exts),
        "gap_type_counts": gap_type_counts(diet_exts),
        "contradiction_summary": contradiction_summary("diet-and-mortality"),
    }
    out["ml-fairness"] = {
        "n_extractions": len(fair_exts),
        "assertion_strength": assertion_strength(fair_exts),
        "gap_type_counts": gap_type_counts(fair_exts),
        "contradiction_summary": contradiction_summary("ml-fairness"),
    }
    # LLM-cal baseline is frozen — not re-computed here. Reference it.
    out["llm-calibration-baseline"] = {
        "assertion_strength": {"firm_share": 0.911, "source": "docs/schema-pressure-test.md §2 (n=56)"},
        "contradictions": {"n_contradictions": 0,
                            "source": "frozen 2026-07 result, docs/findings/corpus-scaling-study.md"},
    }
    diet_contra = out["diet-and-mortality"]["contradiction_summary"]["n_contradictions"]
    out["predictor_check"] = predictor_check(diet_contra)

    import datetime
    out["generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    (REPO_ROOT / "data" / "domains").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "data" / "domains" / "multi_domain_findings.json").write_text(
        json.dumps(out, indent=2)
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
