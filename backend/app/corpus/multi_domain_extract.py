"""Extraction runner for the multi-domain expansion.

Reads a domain's prelabelled entries + fulltext cache, calls the real
Gemini extractor, and stores results under
`data/domains/<slug>/extractions/{safe_paper_id}.json`. Uses the shared
ExtractionCache too, so a paper cached under any earlier run is reused.

Spend guard: every LLM call goes through GeminiLLMClient.generate() and
is gated by SpendLedger at call time. `set_run_context(stage=..., ...)`
tags the ledger entries for later per-stage reporting.

CLI:
    python -m backend.app.corpus.multi_domain_extract --domain diet            # batch (default)
    python -m backend.app.corpus.multi_domain_extract --domain diet --sync     # full-price sync
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
        # Normalise the prelabel's openalex_id (which may be a full URL
        # https://openalex.org/W…) to the openalex:WID form the cache
        # was keyed under during extraction. Same logic as
        # _paper_from_entry below.
        _raw = e.get("openalex_id", "")
        pid = _raw if _raw.startswith("openalex:") else f"openalex:{e['wid']}"
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
        _raw = e.get("openalex_id", "")
        pid = _raw if _raw.startswith("openalex:") else f"openalex:{e['wid']}"
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


# --------------------------------------------------------------------------
# Batch path (default). 50% of the sync price; every returned result is
# billed to the ledger at batch=True, exactly once per job.
# --------------------------------------------------------------------------

MODEL_ID = "gemini:gemini-3.6-flash"   # cache identity, same as sync path


def _pid(e: dict) -> str:
    raw = e.get("openalex_id", "")
    return raw if raw.startswith("openalex:") else f"openalex:{e['wid']}"


def _batch_state_path(slug: str) -> Path:
    return _extractions_dir(slug) / "batch_state.json"


def _uncached_batch_prompts(slug: str, only_pids: set[str] | None = None):
    """{pid: (prompt, input_source)} for entries not yet cached."""
    from backend.app.corpus.run_batch_corpus import _make_renderer, V11
    cache = ExtractionCache()
    renderers = {s: _make_renderer(s) for s in ("abstract", "fulltext")}
    entries = json.loads(_prelabel_path(DOMAINS[slug]).read_text())["entries"]
    out: dict[str, tuple[str, str]] = {}
    hits = 0
    for e in entries:
        pid = _pid(e)
        if only_pids is not None and pid not in only_pids:
            continue
        src = "fulltext" if e.get("input_source") == "fulltext" else "abstract"
        if (cache.get(pid, MODEL_ID, "fulltext", V11.hash) is not None
                or cache.get(pid, MODEL_ID, "abstract", V11.hash) is not None):
            hits += 1
            continue
        paper = _paper_from_entry(e)
        if src == "fulltext" and not paper.fulltext:
            src = "abstract"   # full text missing from cache: fall back honestly
        out[pid] = (renderers[src]._render(paper), src)
    return out, hits


def batch_submit(slug: str, *, gate_mult: float = 1.5,
                 only_pids: set[str] | None = None, client=None) -> dict:
    """Render uncached prompts, gate (projection × gate_mult must fit the
    ledger headroom at the batch rate), submit ONE batch, save state."""
    from backend.app.extraction.batch_client import GeminiBatchClient
    from backend.app.extraction.rate_limiter import estimate_tokens
    prompts, hits = _uncached_batch_prompts(slug, only_pids)
    if not prompts:
        return {"slug": slug, "cache_hits": hits, "submitted": 0}
    est_in = sum(estimate_tokens(p) for p, _s in prompts.values())
    est_out = sum(OUT_TOKENS_FULLTEXT if s == "fulltext" else OUT_TOKENS_ABSTRACT
                  for _p, s in prompts.values())
    proj_inr = cost(est_in, est_out, batch=True) * 84.0
    SpendLedger.load().check_headroom(
        prompt_tokens_est=int(est_in * gate_mult),
        output_tokens_est=int(est_out * gate_mult),
        batch=True, stage=f"extract_{slug}_batch")
    client = client or GeminiBatchClient(model_name=MODEL_ID.split(":", 1)[1])
    batch_id = client.submit({k: v[0] for k, v in prompts.items()},
                             display_name=f"researchmap-{slug}")
    state = {"batch_id": batch_id, "slug": slug,
             "input_source": {k: v[1] for k, v in prompts.items()},
             "n_submitted": len(prompts), "projected_inr": proj_inr,
             "ledger_recorded": False, "submitted_at": time.time()}
    _extractions_dir(slug).mkdir(parents=True, exist_ok=True)
    _batch_state_path(slug).write_text(json.dumps(state, indent=2))
    return {"slug": slug, "cache_hits": hits, "submitted": len(prompts),
            "batch_id": batch_id, "projected_inr": proj_inr}


def batch_collect(slug: str, *, client=None) -> dict:
    """Poll the saved job; when SUCCEEDED, bill every result to the ledger
    (once), then validate + cache each. Returns status + hard-fail list."""
    from backend.app.corpus.run_batch_corpus import _validate_and_cache
    from backend.app.extraction.batch_client import (
        GeminiBatchClient, record_batch_usage,
    )
    sp = _batch_state_path(slug)
    st = json.loads(sp.read_text())
    client = client or GeminiBatchClient(model_name=MODEL_ID.split(":", 1)[1],
                                         validate_model=False)
    job = client.poll(st["batch_id"])
    if not job.done:
        return {"status": "pending", "state": job.state}
    if not job.succeeded:
        return {"status": "failed", "state": job.state}
    with_usage = client.results_with_usage(job)
    if not st.get("ledger_recorded"):
        inr = record_batch_usage(with_usage, stage=f"extract_{slug}_batch",
                                 model=MODEL_ID.split(":", 1)[1])
        st["ledger_recorded"] = True
        st["recorded_inr"] = inr
        sp.write_text(json.dumps(st, indent=2))
    entries = {_pid(e): e for e in
               json.loads(_prelabel_path(DOMAINS[slug]).read_text())["entries"]}
    cache = ExtractionCache()
    ok, fails = 0, []
    for pid, (text, _u) in with_usage.items():
        e = entries.get(pid)
        if e is None:
            fails.append((pid, "unknown-paper"))
            continue
        paper = _paper_from_entry(e)
        src = st["input_source"].get(pid, "abstract")
        outcome = _validate_and_cache(paper, text, src=src, model=MODEL_ID, cache=cache)
        if outcome == "ok":
            ok += 1
        else:
            fails.append((pid, outcome))
    missing = sorted(set(st["input_source"]) - set(with_usage))
    for pid in missing:
        fails.append((pid, "no-result-returned"))
    return {"status": "collected", "n_submitted": st["n_submitted"],
            "n_returned": len(with_usage), "cached": ok, "hard_fails": fails,
            "recorded_inr": st.get("recorded_inr")}


def run_batch(slug: str, *, poll_interval_s: float = 30.0,
              max_retries: int = 2, client=None) -> dict:
    """Submit → wait → collect. Schema-invalid papers are resubmitted up
    to `max_retries` times, then hard-failed by name."""
    rounds = []
    retry_pids: set[str] | None = None
    for attempt in range(max_retries + 1):
        sub = batch_submit(slug, only_pids=retry_pids, client=client)
        if not sub.get("submitted"):
            rounds.append({"attempt": attempt, **sub})
            break
        print(f"[batch:{slug}] attempt {attempt}: submitted {sub['submitted']} "
              f"(cache hits {sub['cache_hits']}), projected ₹{sub['projected_inr']:.2f}",
              flush=True)
        while True:
            res = batch_collect(slug, client=client)
            if res["status"] != "pending":
                break
            time.sleep(poll_interval_s)
        rounds.append({"attempt": attempt, **sub, **res})
        print(f"[batch:{slug}] attempt {attempt}: {res}", flush=True)
        if res["status"] != "collected" or not res["hard_fails"]:
            break
        retry_pids = {pid for pid, _why in res["hard_fails"]}
    out_dir = _extractions_dir(slug)
    (out_dir / "batch_run_log.json").write_text(json.dumps(rounds, indent=2, default=str))
    return {"slug": slug, "rounds": rounds, "ledger": SpendLedger.load().snapshot()["cumulative_inr"]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domain", choices=sorted(DOMAINS), required=True)
    p.add_argument("--dry-run", action="store_true",
                   help="project spend only; no LLM calls")
    p.add_argument("--sync", action="store_true",
                   help="use the synchronous (full-price) path instead of batch")
    args = p.parse_args()
    if args.dry_run:
        result = dry_run(args.domain)
    elif args.sync:
        result = run(args.domain)
    else:
        result = run_batch(args.domain)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
