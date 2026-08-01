"""Domain-corpus extraction via the Gemini BATCH API (50% off).

Drives entirely off `domain_corpus_manifest.json`: each paper is
extracted ONCE, from full text where the manifest says so, else from its
abstract (abstract_only). Both go through one batch; the per-paper
`input_source` is part of the cache key so they never collide.

Modes:
  --dry-run   MANDATORY before any paid call. Sums estimated input+output
              tokens across every UNCACHED paper, applies batch-discounted
              gemini-3.6-flash rates, prints the projected total. Gate:
              $5 — over that it prints the per-bucket breakdown and exits
              non-zero without spending. Also verifies already-cached
              extractions register as HITS.
  --submit    Renders uncached prompts, submits ONE batch, saves state.
  --collect   Polls saved batch; on SUCCESS validates + caches each result
              under its per-paper input_source. Verifies collected count
              == submitted count (the batch-results-shape guard). Schema-
              invalid results hard-fail by name and continue.

Cached under the synchronous `gemini:<model>` identity (batch == same
model at temp 0), matching arm 2/3 of the comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/corpus/x.py
sys.path.insert(0, str(REPO_ROOT))

from pydantic import ValidationError  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.extraction.batch_client import GeminiBatchClient  # noqa: E402
from backend.app.extraction.cache import ExtractionCache  # noqa: E402
from backend.app.extraction.extractor import Extractor  # noqa: E402
from backend.app.extraction.parse import enforce_compound_splitting  # noqa: E402
from backend.app.extraction.prompt_versions import load  # noqa: E402
from backend.app.extraction.rate_limiter import estimate_tokens  # noqa: E402
from backend.app.ingestion.fulltext import load_cached_fulltext  # noqa: E402
from backend.app.models import Paper, PaperExtraction, Source  # noqa: E402

MANIFEST = REPO_ROOT / "data" / "live_samples" / "expanded_corpus_manifest.json"
STATE = REPO_ROOT / "data" / "live_samples" / "corpus_batch.json"
V11 = load("v1.1.0")

# Verified rates + thinking-inclusive output estimates (see
# backend/app/extraction/pricing.py). The old OUT_ABSTRACT/OUT_FULLTEXT
# omitted thinking tokens, under-projecting the gate.
from backend.app.extraction.pricing import (  # noqa: E402
    IN_PER_M, OUT_PER_M, BATCH_MULT,
    OUT_TOKENS_ABSTRACT as OUT_ABSTRACT, OUT_TOKENS_FULLTEXT as OUT_FULLTEXT,
)
GATE = 6.00


def _sync_model_name(model: str) -> str:
    return f"gemini:{model}"


def _paper_from_record(rec: dict) -> Paper:
    """Build a Paper from a self-contained manifest record. Works for
    both original and snowball papers (no dependency on the raw dump)."""
    return Paper(
        id=rec["paper_id"],
        source=Source.OPENALEX,
        source_id=rec["paper_id"].split(":", 1)[-1],
        doi=rec.get("doi"),
        title=rec.get("title") or "Untitled",
        abstract=rec.get("abstract"),
        year=rec.get("year"),
    )


def _make_renderer(src: str) -> Extractor:
    """A no-client Extractor used only to render prompts for `src`."""
    ex = Extractor.__new__(Extractor)
    ex._prompt = V11
    ex._input_source = src
    return ex


def _prepare():
    """Return (records, papers_by_id, model, cache, renderers)."""
    manifest = json.loads(MANIFEST.read_text())
    records = manifest["records"]
    papers = {rec["paper_id"]: _paper_from_record(rec) for rec in records}
    model = _sync_model_name(get_settings().gemini_model)
    cache = ExtractionCache()
    renderers = {src: _make_renderer(src) for src in ("abstract", "fulltext")}
    return records, papers, model, cache, renderers


def _paper_for(rec, papers):
    """Fetch the prebuilt Paper and attach full text when the record
    uses it."""
    paper = papers.get(rec["paper_id"])
    if paper is None:
        return None
    if rec["input_source"] == "fulltext":
        ft = load_cached_fulltext(paper.id)
        if not ft:
            return None  # manifest says fulltext but cache gone — skip safely
        paper.fulltext = ft
    return paper


def _uncached_prompts(records, papers, model, cache, renderers):
    """{paper_id: (prompt, input_source, paper)} for papers not yet cached
    under their chosen input_source. Also returns hit/miss tallies."""
    out = {}
    hits = {"fulltext": 0, "abstract": 0}
    for rec in records:
        src = rec["input_source"]
        paper = _paper_for(rec, papers)
        if paper is None:
            continue
        if cache.get(paper.id, model, src, V11.hash) is not None:
            hits[src] += 1
            continue
        prompt = renderers[src]._render(paper)
        out[paper.id] = (prompt, src, paper)
    return out, hits


def _validate_and_cache(paper, text, *, src, model, cache) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return "parse-fail"
    if not isinstance(data, dict):
        return "not-json-object"  # e.g. model returned a bare array
    if data.get("paper_id") != paper.id:
        return "paper-id-mismatch"
    data["extractor"] = model
    data["extracted_at"] = datetime.now(timezone.utc).isoformat()
    try:
        ext = PaperExtraction.model_validate(data)
    except ValidationError:
        return "schema-fail"
    ext = enforce_compound_splitting(ext)
    cache.put(paper.id, model, src, V11.hash, ext)
    return "ok"


def _dry_run(records, papers, model, cache, renderers) -> int:
    uncached, hits = _uncached_prompts(records, papers, model, cache, renderers)
    buckets = {"fulltext": {"n": 0, "in": 0, "max": 0},
               "abstract": {"n": 0, "in": 0, "max": 0}}
    for pid, (prompt, src, _p) in uncached.items():
        t = estimate_tokens(prompt)
        b = buckets[src]
        b["n"] += 1
        b["in"] += t
        b["max"] = max(b["max"], t)
    ft, ab = buckets["fulltext"], buckets["abstract"]
    ft_out = ft["n"] * OUT_FULLTEXT
    ab_out = ab["n"] * OUT_ABSTRACT
    ft_cost = (ft["in"] / 1e6 * IN_PER_M + ft_out / 1e6 * OUT_PER_M) * BATCH_MULT
    ab_cost = (ab["in"] / 1e6 * IN_PER_M + ab_out / 1e6 * OUT_PER_M) * BATCH_MULT
    total = ft_cost + ab_cost

    print("=== CORPUS PRE-SPEND DRY RUN (no API calls) ===\n")
    print(f"Rates: in ${IN_PER_M}/1M, out ${OUT_PER_M}/1M; BATCH 50% off")
    print(f"Cache HITS (skip, $0): fulltext={hits['fulltext']}, "
          f"abstract={hits['abstract']} (total {sum(hits.values())})\n")
    print(f"FULL-TEXT bucket  to extract: {ft['n']}")
    print(f"  input tokens:  {ft['in']:>8,}  (largest single: {ft['max']:,})")
    print(f"  output tokens: {ft_out:>8,} (est)   cost ${ft_cost:.4f}\n")
    print(f"ABSTRACT bucket   to extract: {ab['n']}")
    print(f"  input tokens:  {ab['in']:>8,}  (largest single: {ab['max']:,})")
    print(f"  output tokens: {ab_out:>8,} (est)   cost ${ab_cost:.4f}\n")
    print(f"PROJECTED TOTAL (batch): ${total:.4f}   | gate ${GATE:.2f}")
    if total > GATE:
        print(f"\n*** OVER ${GATE:.2f} GATE — STOP. Per-bucket breakdown above. ***")
        return 2
    print(f"\nUnder the ${GATE:.2f} gate — cleared to submit.")
    return 0


def _submit(records, papers, model, cache, renderers) -> int:
    uncached, hits = _uncached_prompts(records, papers, model, cache, renderers)
    print(f"[batch] cache HITS: {sum(hits.values())} "
          f"(fulltext={hits['fulltext']}, abstract={hits['abstract']})")
    print(f"[batch] {len(uncached)} uncached papers to extract")
    if not uncached:
        print("[batch] nothing to do — corpus fully cached.")
        return 0
    prompts = {pid: v[0] for pid, v in uncached.items()}
    client = GeminiBatchClient(model_name=get_settings().gemini_model)
    batch_id = client.submit(prompts, display_name="researchmap-corpus")
    STATE.write_text(json.dumps({
        "batch_id": batch_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "input_source": {pid: v[1] for pid, v in uncached.items()},
        "n_submitted": len(prompts),
    }, indent=2))
    print(f"[batch] submitted id={batch_id}, {len(prompts)} papers; "
          f"state -> {STATE.relative_to(REPO_ROOT)}")
    return 0


def _collect(records, papers, model, cache) -> int:
    if not STATE.exists():
        print("no saved batch state.", file=sys.stderr)
        return 1
    st = json.loads(STATE.read_text())
    src_by_pid = st["input_source"]
    n_submitted = st["n_submitted"]
    client = GeminiBatchClient(model_name=get_settings().gemini_model)
    job = client.poll(st["batch_id"])
    print(f"[batch] state={job.state}")
    if not job.done:
        print("[batch] still pending — run --collect later.")
        return 3
    if not job.succeeded:
        print(f"[batch] job did not succeed: {job.state}")
        return 4
    results = client.results(job)
    # Results-shape guard (the documented batch risk).
    print(f"[batch] results returned: {len(results)} / {n_submitted} submitted")
    if len(results) < n_submitted:
        print("[batch] WARNING: fewer results than submitted — job may be "
              "file-based. NOT trusting partial cache; aborting collect.",
              file=sys.stderr)
        return 5

    by_pid = {p.id: p for p in papers.values()}
    ok = 0
    fails = []
    for pid, text in results.items():
        paper = by_pid.get(pid)
        src = src_by_pid.get(pid, "abstract")
        if paper is None:
            fails.append((pid, "unknown-paper"))
            continue
        if src == "fulltext":
            ft = load_cached_fulltext(paper.id)
            if ft:
                paper.fulltext = ft
        outcome = _validate_and_cache(paper, text, src=src, model=model, cache=cache)
        if outcome == "ok":
            ok += 1
        else:
            fails.append((pid, outcome))
    print(f"[batch] collected: {ok} cached, {len(fails)} hard-failed")
    for pid, why in fails:
        print(f"  HARD-FAIL {pid}: {why}")
    return 0 if not fails else 0  # hard-fails don't fail the run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    args = ap.parse_args()

    if not get_settings().can_use_gemini and not args.dry_run:
        print("GEMINI_API_KEY unset.", file=sys.stderr)
        return 2

    records, papers, model, cache, renderers = _prepare()

    if args.dry_run:
        return _dry_run(records, papers, model, cache, renderers)
    if args.submit:
        return _submit(records, papers, model, cache, renderers)
    if args.collect:
        return _collect(records, papers, model, cache)
    print("specify --dry-run | --submit | --collect", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
