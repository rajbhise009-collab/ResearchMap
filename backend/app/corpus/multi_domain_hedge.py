"""LLM-based firm-vs-hedged classifier for extracted claims.

Replaces the lexical `is_hedged` marker list (which came in at 99.7%
firm on diet-and-mortality — flagging classifier bluntness, not a real
domain result). One-shot per claim; Gemini-3.6-flash at temperature 0.
Every call gates through SpendLedger like the extraction and
contradiction paths.

CLI:
    python -m backend.app.corpus.multi_domain_hedge --dry-run
    python -m backend.app.corpus.multi_domain_hedge --domain diet-and-mortality
    python -m backend.app.corpus.multi_domain_hedge --domain ml-fairness
    python -m backend.app.corpus.multi_domain_hedge --domain llm-calibration
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.corpus.multi_domain_reason import load_extractions  # noqa: E402
from backend.app.extraction.llm_client import (  # noqa: E402
    DailyQuotaError,
    GeminiLLMClient,
)
from backend.app.extraction.pricing import cost  # noqa: E402
from backend.app.extraction.spend_ledger import (  # noqa: E402
    SpendCapExceededError,
    SpendLedger,
)

HEDGE_PROMPT = """\
You are classifying a scientific claim as firm or hedged. This is a
simple binary judgment on the sentence's assertion strength, not on
the truth or importance of the claim.

- "firm": the sentence asserts something definitely (e.g. "X reduces Y",
  "X is Y", "results demonstrate X").
- "hedged": the sentence softens the assertion with qualifiers
  (e.g. "may reduce", "appears to", "suggests", "is likely to", "we
  hypothesize", "remains unclear", "possibly", "further work needed").

Return STRICT JSON, no prose:
{"label": "firm" | "hedged"}

Claim: <<<{claim}>>>
"""

# Small per-call token budget — this is a single-token classification.
EST_INPUT_TOKENS = 200
EST_OUTPUT_TOKENS = 60  # includes thinking; task is simple


def _hedge_dir(slug: str) -> Path:
    return REPO_ROOT / "data" / "domains" / slug / "hedge"


def _llm_cal_extractions():
    """Load LLM-cal extractions from the frozen manifest. Reuses the
    reasoning-corpus loader which reads data/reasoning/."""
    from backend.app.reasoning.corpus_view import load_reasoning_corpus
    corpus = load_reasoning_corpus()
    # Extractions are on `corpus._loaded.extractions` (dict paper_id ->
    # PaperExtraction).
    return list(corpus._loaded.extractions.values())


def _extractions_for(slug: str):
    if slug == "llm-calibration":
        return _llm_cal_extractions()
    return load_extractions(slug)


def all_claims_for(slug: str):
    """Yield (paper_id, claim_id, claim_text) for every claim in a
    domain's extractions."""
    for ext in _extractions_for(slug):
        for c in (ext.claims or []):
            if c.text and c.text.strip():
                yield (ext.paper_id, c.id, c.text.strip())


def dry_run(slug: str) -> dict:
    """Project hedge-classification cost for a domain."""
    claims = list(all_claims_for(slug))
    n = len(claims)
    proj_in = n * EST_INPUT_TOKENS
    proj_out = n * EST_OUTPUT_TOKENS
    proj_usd = cost(proj_in, proj_out, batch=False)
    return {
        "slug": slug, "n_claims": n,
        "est_input_tokens_per_call": EST_INPUT_TOKENS,
        "est_output_tokens_per_call": EST_OUTPUT_TOKENS,
        "proj_cost_usd": proj_usd,
        "proj_cost_inr": proj_usd * 84.0,
    }


def combined_dry_run(slugs: list[str]) -> dict:
    projections = [dry_run(s) for s in slugs]
    total_inr = sum(p["proj_cost_inr"] for p in projections)
    return {
        "per_domain": projections,
        "total_cost_inr": total_inr,
        "total_cost_usd": total_inr / 84.0,
        "gate_inr": 150.0,
        "fits": total_inr <= 150.0,
    }


def run(slug: str) -> dict:
    """Classify every claim. Persist labels incrementally to
    `data/domains/<slug>/hedge/labels.json`; halt cleanly on SpendCap or
    DailyQuota."""
    claims = list(all_claims_for(slug))
    out_dir = _hedge_dir(slug)
    out_dir.mkdir(parents=True, exist_ok=True)

    llm = GeminiLLMClient(validate_model=False)
    llm.set_run_context(stage=f"hedge_{slug}", est_output_tokens=EST_OUTPUT_TOKENS)
    labels: list[dict] = []
    counter = Counter()
    fails = 0
    t0 = time.time()
    for i, (pid, cid, text) in enumerate(claims, 1):
        prompt = HEDGE_PROMPT.replace("{claim}", text[:600])
        try:
            raw = llm.generate(prompt)
        except SpendCapExceededError as e:
            print(f"[hedge:{slug}] HALT — spend cap at claim {i}/{len(claims)}: {e}",
                  flush=True)
            break
        except DailyQuotaError:
            print(f"[hedge:{slug}] HALT — daily quota", flush=True)
            break
        except Exception as ex:  # noqa: BLE001
            fails += 1
            counter["error"] += 1
            labels.append({"claim_id": cid, "paper_id": pid,
                            "text": text[:200], "label": None,
                            "error": type(ex).__name__})
            continue
        try:
            data = json.loads(raw)
            label = str(data.get("label", "")).strip().lower()
        except json.JSONDecodeError:
            fails += 1
            counter["error"] += 1
            labels.append({"claim_id": cid, "paper_id": pid,
                            "text": text[:200], "label": None,
                            "error": "json_decode"})
            continue
        if label not in ("firm", "hedged"):
            counter["unknown"] += 1
            label = "unknown"
        counter[label] += 1
        labels.append({"claim_id": cid, "paper_id": pid,
                        "text": text[:200], "label": label})
        if i % 50 == 0 or i == len(claims):
            snap = SpendLedger.load().snapshot()
            print(f"[hedge:{slug}] [{i}/{len(claims)}] firm={counter['firm']} "
                  f"hedged={counter['hedged']} err={fails} — cum "
                  f"₹{snap['cumulative_inr']:.2f}/₹{snap['cap_inr']:.0f}",
                  flush=True)

    total = counter["firm"] + counter["hedged"]
    result = {
        "slug": slug,
        "elapsed_s": time.time() - t0,
        "n_classified": total,
        "n_total_claims": len(claims),
        "firm": counter["firm"], "hedged": counter["hedged"],
        "firm_share": counter["firm"] / total if total else 0.0,
        "hedged_share": counter["hedged"] / total if total else 0.0,
        "errors": fails, "unknown": counter["unknown"],
    }
    (out_dir / "labels.json").write_text(json.dumps({
        "summary": result, "items": labels,
    }, indent=2))
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domain", choices=("diet-and-mortality", "ml-fairness",
                                          "llm-calibration", "all"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.dry_run:
        slugs = ["diet-and-mortality", "ml-fairness", "llm-calibration"]
        print(json.dumps(combined_dry_run(slugs), indent=2))
        return 0

    if args.domain == "all" or args.domain is None:
        for s in ("diet-and-mortality", "ml-fairness", "llm-calibration"):
            print(json.dumps(run(s), indent=2))
    else:
        print(json.dumps(run(args.domain), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
