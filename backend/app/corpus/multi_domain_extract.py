"""Extraction runner for the multi-domain expansion.

Reads a domain's prelabelled entries + fulltext cache, calls the real
Gemini extractor, and stores results under
`data/domains/<slug>/extractions/{safe_paper_id}.json`. Uses the shared
ExtractionCache too, so a paper cached under any earlier run is reused.

Spend guard: every LLM call goes through GeminiLLMClient.generate() and
is gated by SpendLedger at call time. `set_run_context(stage=..., ...)`
tags the ledger entries for later per-stage reporting.

CLI:
    python -m backend.app.corpus.multi_domain_extract --domain diet
    python -m backend.app.corpus.multi_domain_extract --domain fairness --dry-run
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

from backend.app.corpus.multi_domain import DOMAINS, _prelabel_path  # noqa: E402
from backend.app.extraction.cache import ExtractionCache  # noqa: E402
from backend.app.extraction.errors import (  # noqa: E402
    ExtractionParseError,
    ExtractionValidationError,
)
from backend.app.extraction.extractor import Extractor  # noqa: E402
from backend.app.extraction.llm_client import (  # noqa: E402
    DailyQuotaError,
    GeminiLLMClient,
)
from backend.app.extraction.pricing import (  # noqa: E402
    OUT_TOKENS_ABSTRACT,
    OUT_TOKENS_FULLTEXT,
    cost,
)
from backend.app.extraction.spend_ledger import (  # noqa: E402
    SpendCapExceededError,
    SpendLedger,
)
from backend.app.ingestion.fulltext import load_cached_fulltext  # noqa: E402
from backend.app.models import Paper, Source  # noqa: E402


def _paper_from_entry(e: dict) -> Paper:
    """Build a Paper for the Extractor from a prelabelled entry.
    Attaches fulltext from the shared cache if the entry has it."""
    pid = e["openalex_id"] if e.get("openalex_id", "").startswith("openalex:") \
        else f"openalex:{e['wid']}"
    fulltext = None
    if e.get("input_source") == "fulltext":
        fulltext = load_cached_fulltext(pid) or load_cached_fulltext(e["wid"])
    return Paper(
        id=pid,
        source=Source.OPENALEX,
        source_id=e["wid"],
        doi=e.get("doi"),
        title=e.get("title") or "Untitled",
        year=e.get("year"),
        venue=e.get("venue"),
        authors=e.get("authors") or [],
        abstract=e.get("abstract"),
        fulltext=fulltext,
    )


def _extractions_dir(slug: str) -> Path:
    return REPO_ROOT / "data" / "domains" / slug / "extractions"


def dry_run(slug: str) -> dict:
    """Project extraction cost for a domain WITHOUT calling the LLM.

    Uses observed per-paper token averages (from pricing.py). Reports
    projected input/output tokens, USD, INR. Skips already-cached papers.
    """
    from backend.app.extraction.prompt_versions import latest_version, load
    prompt_hash = load(latest_version()).hash
    cache = ExtractionCache()
    payload = json.loads(_prelabel_path(DOMAINS[slug]).read_text())
    entries = payload["entries"]

    n_full = n_abs = 0
    n_cached = 0
    for e in entries:
        pid = e.get("openalex_id") or f"openalex:{e['wid']}"
        # Both possible input_source keys are checked for cache hit
        cached_ft = cache.get(pid, "gemini:gemini-3.6-flash", "fulltext", prompt_hash)
        cached_ab = cache.get(pid, "gemini:gemini-3.6-flash", "abstract", prompt_hash)
        if cached_ft is not None or cached_ab is not None:
            n_cached += 1
            continue
        if e.get("input_source") == "fulltext":
            n_full += 1
        else:
            n_abs += 1

    # Observed averages for gemini-3.6-flash. Padded upward (per pricing.py
    # docstring — a gate must never under-project).
    IN_FULL = 15_000
    IN_ABS = 500
    OUT_FULL = OUT_TOKENS_FULLTEXT
    OUT_ABS = OUT_TOKENS_ABSTRACT
    proj_in = n_full * IN_FULL + n_abs * IN_ABS
    proj_out = n_full * OUT_FULL + n_abs * OUT_ABS
    proj_usd = cost(proj_in, proj_out, batch=False)
    return {
        "slug": slug,
        "n_entries": len(entries),
        "n_cache_hits_projected": n_cached,
        "n_full_new": n_full,
        "n_abstract_new": n_abs,
        "proj_input_tokens": proj_in,
        "proj_output_tokens_incl_thoughts": proj_out,
        "proj_cost_usd": proj_usd,
        "proj_cost_inr": proj_usd * 84.0,
    }


def run(slug: str, *, batch: bool = False, halt_on_first_fail: bool = False) -> dict:
    """Extract every prelabelled entry for a domain. Iterates in
    top-cited-desc order (already sorted by prelabel). Cache-first;
    cached papers make no LLM call and never hit the ledger.

    Halts on:
      - DailyQuotaError (per-day 429) — must resume after reset
      - SpendCapExceededError (guard trip) — must resume after cap raise
    """
    cache = ExtractionCache()
    llm = GeminiLLMClient(validate_model=False, raw_log_dir=None)
    est_out = OUT_TOKENS_FULLTEXT  # over-project for either kind
    llm.set_run_context(stage=f"extract_{slug}", est_output_tokens=est_out)

    payload = json.loads(_prelabel_path(DOMAINS[slug]).read_text())
    entries = payload["entries"]

    stats = Counter()
    per_paper: list[dict] = []
    t0 = time.time()
    for i, e in enumerate(entries, 1):
        pid = e.get("openalex_id") or f"openalex:{e['wid']}"
        input_source = "fulltext" if e.get("input_source") == "fulltext" else "abstract"
        extractor = Extractor(llm=llm, cache=cache, input_source=input_source)
        paper = _paper_from_entry(e)
        try:
            result = extractor.extract(paper)
            if result.from_cache:
                stats["cache_hit"] += 1
            else:
                stats["extracted"] += 1
            per_paper.append({
                "wid": e["wid"], "input_source": input_source,
                "from_cache": result.from_cache, "ok": True,
            })
        except SpendCapExceededError as e_cap:
            stats["halted_spend_cap"] += 1
            per_paper.append({"wid": e["wid"], "ok": False, "reason": "spend_cap"})
            print(f"[extract:{slug}] HALT — spend cap reached at "
                  f"paper {i}/{len(entries)}: {e_cap}", flush=True)
            break
        except DailyQuotaError as e_day:
            stats["halted_daily_quota"] += 1
            per_paper.append({"wid": e["wid"], "ok": False, "reason": "daily_quota"})
            print(f"[extract:{slug}] HALT — daily quota: {e_day}", flush=True)
            break
        except (ExtractionParseError, ExtractionValidationError) as e_ex:
            stats["extraction_failed"] += 1
            per_paper.append({"wid": e["wid"], "ok": False,
                              "reason": type(e_ex).__name__, "detail": str(e_ex)[:200]})
            if halt_on_first_fail:
                break
        if i % 10 == 0 or i == len(entries):
            snap = SpendLedger.load().snapshot()
            print(f"[extract:{slug}] [{i}/{len(entries)}] cached={stats['cache_hit']} "
                  f"extracted={stats['extracted']} fail={stats['extraction_failed']} "
                  f"— cum ₹{snap['cumulative_inr']:.2f} / ₹{snap['cap_inr']:.0f}",
                  flush=True)

    out_dir = _extractions_dir(slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run_log.json").write_text(json.dumps({
        "slug": slug,
        "elapsed_s": time.time() - t0,
        "stats": dict(stats),
        "per_paper": per_paper,
    }, indent=2))
    return {"slug": slug, "stats": dict(stats),
            "ledger": SpendLedger.load().snapshot()}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domain", choices=sorted(DOMAINS), required=True)
    p.add_argument("--dry-run", action="store_true",
                   help="project spend only; no LLM calls")
    args = p.parse_args()
    if args.dry_run:
        result = dry_run(args.domain)
    else:
        result = run(args.domain)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
