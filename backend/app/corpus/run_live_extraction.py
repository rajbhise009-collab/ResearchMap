"""Live extraction runner — Gemini 2.5 Flash on a stratified 30 papers.

Spend-gated. Requires GEMINI_API_KEY. Runs a 3-paper smoke first, then
(if the runner is invoked with --continue-after-smoke) the remaining 27.
For an autonomous session pass --auto so a clean smoke rolls straight
into the full run without stopping.

Every raw model response is teed to disk under
`data/live_samples/extraction_attempts/`. Every parsed extraction
lands in the standard cache at `data/cache/extractions/` (via the
Extractor). Per-run stats + per-paper accounting are written to
`data/live_samples/extraction_run_YYYYMMDD_HHMMSS.json`.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.extraction.cache import ExtractionCache  # noqa: E402
from backend.app.extraction.errors import ExtractionError  # noqa: E402
from backend.app.extraction.extractor import Extractor  # noqa: E402
from backend.app.extraction.llm_client import GeminiLLMClient  # noqa: E402
from backend.app.models import Paper, Source  # noqa: E402


CORPUS_CSV = REPO_ROOT / "scratch" / "corpus_review.csv"
RAW_DUMP = REPO_ROOT / "data" / "live_samples" / "phase2_diagnostic_raw.json"
RAW_LOG_DIR = REPO_ROOT / "data" / "live_samples" / "extraction_attempts"

# Free-tier key: cost is not the binding constraint (no card attached).
# We still track tokens; dollar figures are informational only, computed
# against the published gemini-3.6-flash standard-tier rate for reference.
# Source: ai.google.dev/gemini-api/docs/pricing (see PROGRESS.md caveat
# about which figures are independently verified).
PRICE_INPUT_PER_M = 1.50
PRICE_OUTPUT_PER_M = 7.50

SMOKE_IDS = [
    "https://openalex.org/W4388092399",  # #14 Chainpoll (on-domain, compound, prior-work lim)
    "https://openalex.org/W4281690148",  # #15 BIG-Bench (borderline, compound, own-work lim)
    "https://openalex.org/W4415914353",  # #38 FermiEval (on-domain, compound, own-work lim)
]


# --- Paper reconstruction ---------------------------------------------

def _venue(record: dict) -> str | None:
    hv = record.get("host_venue") or record.get("primary_location") or {}
    if isinstance(hv, dict):
        src = hv.get("source") if isinstance(hv.get("source"), dict) else {}
        return (
            (src.get("display_name") if isinstance(src, dict) else None)
            or hv.get("display_name")
        )
    return None


def _openalex_to_paper(record: dict, abstract_override: str | None) -> Paper:
    """Build a Paper object. If OpenAlex's abstract was empty and we
    recovered one from S2/arXiv, `abstract_override` carries it."""
    raw_id = record["id"]
    authors: list[str] = []
    for a in record.get("authorships") or []:
        name = ((a or {}).get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    return Paper(
        id=f"openalex:{raw_id.rsplit('/', 1)[-1]}",
        source=Source.OPENALEX,
        source_id=raw_id.rsplit("/", 1)[-1],
        doi=(record.get("doi") or "").lower().removeprefix("https://doi.org/") or None,
        title=(record.get("title") or "").strip() or "Untitled",
        abstract=abstract_override,
        year=record.get("publication_year"),
        authors=authors,
        venue=_venue(record),
    )


def _load_papers_by_openalex_id() -> dict[str, Paper]:
    """Return openalex-URL → Paper for every paper in the corpus_review,
    substituting recovered abstracts where OpenAlex's was empty."""
    review_rows = list(csv.DictReader(CORPUS_CSV.open(encoding="utf-8")))
    abstracts_by_id: dict[str, str] = {}
    for r in review_rows:
        if r.get("abstract_full"):
            abstracts_by_id[r["openalex_id"]] = r["abstract_full"]

    raw = json.loads(RAW_DUMP.read_text(encoding="utf-8"))
    out: dict[str, Paper] = {}
    for record in raw.get("results") or []:
        oid = record.get("id")
        if not oid:
            continue
        if oid not in abstracts_by_id:
            continue  # not in the 60-paper hand-review sample
        out[oid] = _openalex_to_paper(record, abstracts_by_id[oid])
    return out


# --- Stratified selection ---------------------------------------------

def stratify_thirty() -> list[dict]:
    """Return 30 review rows including the 3 smoke IDs first, then the
    remaining 27 chosen deterministically to meet the composition
    target."""
    rows = list(csv.DictReader(CORPUS_CSV.open(encoding="utf-8")))
    rows = [r for r in rows if r.get("excluded") != "1"]
    # Deterministic order by openalex_id so re-runs pick the same set.
    rows.sort(key=lambda r: r["openalex_id"])

    picked: list[dict] = []
    picked_ids: set[str] = set()

    # 1. Pin the 3 smoke IDs to the front, in order.
    smoke_by_id = {r["openalex_id"]: r for r in rows if r["openalex_id"] in SMOKE_IDS}
    for oid in SMOKE_IDS:
        r = smoke_by_id.get(oid)
        if r is None:
            raise RuntimeError(f"Smoke ID {oid} not found in the review CSV")
        picked.append(r)
        picked_ids.add(oid)

    # 2. Fill the remaining 27 to hit composition targets.
    #    Priorities: on-domain, then borderline, then a few off-domain
    #    controls. Within each bucket, prefer papers that carry
    #    compound_claims=yes and limitation_scope in {prior, own}.
    remaining = [r for r in rows if r["openalex_id"] not in picked_ids]

    def _score(r: dict) -> tuple[int, int, int, str]:
        # Higher-first sort key. Signals we want to preserve.
        d = r.get("on_domain")
        d_rank = {"on-domain": 3, "borderline": 2, "off-domain": 1}.get(d, 0)
        compound = 1 if r.get("compound_claims") == "yes" else 0
        scope = r.get("limitation_scope") or ""
        scope_rank = {"prior": 3, "own": 3, "both": 3, "none": 1, "unknown": 0}.get(scope, 0)
        return (d_rank, compound, scope_rank, r["openalex_id"])

    remaining.sort(key=_score, reverse=True)

    # Composition targets: ~20 on-domain (already 2 smoke), ~7 borderline
    # (already 1 smoke), ~3 off-domain (none smoke).
    quotas = {"on-domain": 20, "borderline": 7, "off-domain": 3}
    already = {
        "on-domain":  sum(1 for r in picked if r["on_domain"] == "on-domain"),
        "borderline": sum(1 for r in picked if r["on_domain"] == "borderline"),
        "off-domain": sum(1 for r in picked if r["on_domain"] == "off-domain"),
    }
    for r in remaining:
        b = r["on_domain"]
        if b in quotas and already.get(b, 0) < quotas[b]:
            picked.append(r)
            already[b] = already.get(b, 0) + 1
        if len(picked) >= 30:
            break

    if len(picked) < 30:
        # Backfill with anything left, retaining sort order.
        for r in remaining:
            if r["openalex_id"] in {p["openalex_id"] for p in picked}:
                continue
            picked.append(r)
            if len(picked) >= 30:
                break

    return picked[:30]


# --- Runner ------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-only", action="store_true",
                        help="Stop after the 3-paper smoke test.")
    parser.add_argument("--auto", action="store_true",
                        help="After a clean smoke, continue to the remaining "
                             "27 without prompting.")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.can_use_gemini:
        print("GEMINI_API_KEY unset — refusing to run.", file=sys.stderr)
        return 2

    picks = stratify_thirty()
    papers_by_id = _load_papers_by_openalex_id()

    # Report composition.
    print(f"[selection] {len(picks)} papers picked")
    dist = {
        "on-domain":  sum(1 for r in picks if r["on_domain"] == "on-domain"),
        "borderline": sum(1 for r in picks if r["on_domain"] == "borderline"),
        "off-domain": sum(1 for r in picks if r["on_domain"] == "off-domain"),
    }
    print(f"  on_domain: {dist}")
    print(f"  compound_claims=yes:      "
          f"{sum(1 for r in picks if r['compound_claims'] == 'yes')}")
    print(f"  limitation_scope=prior:   "
          f"{sum(1 for r in picks if r['limitation_scope'] == 'prior')}")
    print(f"  limitation_scope=own:     "
          f"{sum(1 for r in picks if r['limitation_scope'] == 'own')}")
    print(f"  limitation_scope=both:    "
          f"{sum(1 for r in picks if r['limitation_scope'] == 'both')}")

    # Set up client + extractor.
    llm = GeminiLLMClient(raw_log_dir=RAW_LOG_DIR)
    extractor = Extractor(llm=llm, cache=ExtractionCache())

    run_started = datetime.now(timezone.utc).isoformat()
    per_paper_records: list[dict] = []
    hard_failures: list[dict] = []

    def _run_slice(name: str, start: int, end: int, *, verbose: bool = False) -> None:
        for i, r in enumerate(picks[start:end], start=start + 1):
            oid = r["openalex_id"]
            paper = papers_by_id.get(oid)
            if paper is None:
                print(f"[{name} {i:02d}] ERROR: {oid} not found in raw dump")
                continue
            t0 = time.time()
            # Snapshot LLM stats before this paper.
            calls_before = llm.calls
            in_before = llm.total_prompt_tokens
            out_before = llm.total_output_tokens
            try:
                result = extractor.extract(paper)
                elapsed = time.time() - t0
                attempts = llm.calls - calls_before
                tokens_in = llm.total_prompt_tokens - in_before
                tokens_out = llm.total_output_tokens - out_before
                ex = result.extraction
                per_paper_records.append({
                    "openalex_id": oid,
                    "paper_id": paper.id,
                    "on_domain_label": r["on_domain"],
                    "hand_limitation_scope": r["limitation_scope"],
                    "hand_compound_claims": r["compound_claims"],
                    "hand_has_future_work": r["has_future_work"],
                    "attempts": attempts,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_s": round(elapsed, 3),
                    "from_cache": result.from_cache,
                    "n_claims": len(ex.claims),
                    "n_split_claims": sum(1 for c in ex.claims if c.source_sentence_id),
                    "n_evidence": len(ex.evidence),
                    "n_methodologies": len(ex.methodologies),
                    "n_limitations": len(ex.limitations),
                    "n_this_work_lims": sum(
                        1 for l in ex.limitations if l.source_scope == "this_work"
                    ),
                    "n_prior_work_lims": sum(
                        1 for l in ex.limitations if l.source_scope == "prior_work"
                    ),
                    "n_future_work": len(ex.future_work),
                })
                print(
                    f"[{name} {i:02d}] {paper.id:<32s} "
                    f"attempts={attempts} cached={result.from_cache} "
                    f"tok_in={tokens_in} tok_out={tokens_out} "
                    f"claims={len(ex.claims)} (split={sum(1 for c in ex.claims if c.source_sentence_id)}) "
                    f"lims={len(ex.limitations)} fw={len(ex.future_work)} "
                    f"lat={elapsed:.1f}s"
                )
                if verbose:
                    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", paper.id)
                    raw_files = sorted(RAW_LOG_DIR.glob(f"{safe}.attempt*.txt"))
                    print("  --- RAW MODEL RESPONSE (final attempt) ---")
                    if raw_files:
                        print(raw_files[-1].read_text(encoding="utf-8"))
                    else:
                        print("  (raw log not found on disk)")
                    print("  --- PARSED EXTRACTION (post-validate, post-split) ---")
                    print(ex.model_dump_json(indent=2))
                    print("  --- END ---\n")
            except ExtractionError as e:
                elapsed = time.time() - t0
                hard_failures.append({
                    "openalex_id": oid, "paper_id": paper.id,
                    "attempts": llm.calls - calls_before,
                    "error": type(e).__name__,
                    "message": str(e)[:200],
                    "latency_s": round(elapsed, 3),
                })
                print(f"[{name} {i:02d}] HARD-FAIL {paper.id}: {type(e).__name__}: {e}")
            except Exception as e:  # noqa: BLE001
                # A sustained 429 (rate limit) that exhausts the client's
                # backoff surfaces as httpx.HTTPStatusError, NOT an
                # ExtractionError. Record it as a rate-limit failure and
                # keep going — the paper stays uncached and will be
                # retried on the next run. Never lose the whole run to
                # one paper.
                elapsed = time.time() - t0
                is_429 = "429" in str(e)
                hard_failures.append({
                    "openalex_id": oid, "paper_id": paper.id,
                    "attempts": llm.calls - calls_before,
                    "error": "RateLimitExhausted" if is_429 else type(e).__name__,
                    "message": str(e)[:200],
                    "latency_s": round(elapsed, 3),
                })
                print(f"[{name} {i:02d}] "
                      f"{'RATE-LIMIT' if is_429 else 'ERROR'} {paper.id}: {e}")

    # --- Smoke test.
    print("\n=== SMOKE TEST — 3 papers ===")
    _run_slice("SMOKE", 0, 3, verbose=True)

    if hard_failures:
        print(f"\n[smoke] {len(hard_failures)} hard failure(s) — STOPPING")
        _write_run_report(run_started, per_paper_records, hard_failures, llm)
        return 3

    if args.smoke_only:
        print("\n[smoke-only] complete — not continuing.")
        _write_run_report(run_started, per_paper_records, hard_failures, llm)
        return 0

    # --- Remaining 27.
    print("\n=== CONTINUING — 27 more papers ===")
    _run_slice("RUN", 3, len(picks))

    _write_run_report(run_started, per_paper_records, hard_failures, llm)
    return 0


def _write_run_report(
    run_started: str,
    per_paper: list[dict],
    hard_failures: list[dict],
    llm: GeminiLLMClient,
) -> None:
    tokens_in = llm.total_prompt_tokens
    tokens_out = llm.total_output_tokens
    cost = (tokens_in / 1_000_000) * PRICE_INPUT_PER_M \
        + (tokens_out / 1_000_000) * PRICE_OUTPUT_PER_M
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = (
        REPO_ROOT / "data" / "live_samples"
        / f"extraction_run_{stamp}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_started": run_started,
        "run_finished": datetime.now(timezone.utc).isoformat(),
        "model": llm.name,
        "totals": {
            "papers": len(per_paper),
            "hard_failures": len(hard_failures),
            "rate_limit_hits_429": llm.rate_limit_hits,
            "llm_calls_total": llm.calls,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_s_total": round(llm.total_latency_s, 2),
            "cost_usd_reference_only": round(cost, 4),
            "note": "free-tier key — cost is informational, not billed",
            "price_input_per_1M": PRICE_INPUT_PER_M,
            "price_output_per_1M": PRICE_OUTPUT_PER_M,
        },
        "per_paper": per_paper,
        "hard_failures": hard_failures,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n[report] wrote {out_path.relative_to(REPO_ROOT)}")
    print(f"[report] {len(per_paper)} papers succeeded; "
          f"{len(hard_failures)} hard failed; "
          f"{llm.rate_limit_hits} rate-limit (429) hits; "
          f"{tokens_in} in + {tokens_out} out tokens; "
          f"${cost:.4f} reference cost (free tier — not billed)")


if __name__ == "__main__":
    raise SystemExit(main())
