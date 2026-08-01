"""Arm 3 — v1.1.0 full-text extraction via the Gemini BATCH API (50% off).

Batch is async (target 24h, usually faster). This script:
  --submit   renders the uncached full-text prompts, submits ONE batch,
             saves the batch id to data/live_samples/arm3_batch.json,
             and prints the id.
  --collect  polls the saved batch; when SUCCEEDED, validates + caches
             each result. Schema-invalid results hard-fail that paper by
             name and continue (one bad paper never blocks the arm).
  (default)  submit, then poll up to --wait-min minutes; collect if it
             finishes, else leave it pending for a later --collect.

CRITICAL: batch results are cached under the SAME model identity as the
synchronous arm 2 — `gemini:<model>` — because batch is the same model
(temp 0), only a delivery mechanism. If they were cached under
`gemini-batch:...` the paired comparison would miss them.
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
from backend.app.ingestion.fulltext import load_cached_fulltext  # noqa: E402
from backend.app.models import PaperExtraction  # noqa: E402
from backend.app.corpus.run_live_extraction import (  # noqa: E402
    stratify_thirty,
    _load_papers_by_openalex_id,
)

STATE = REPO_ROOT / "data" / "live_samples" / "arm3_batch.json"
V11 = load("v1.1.0")
INPUT_SOURCE = "fulltext"


def _sync_model_name(model: str) -> str:
    """The synchronous model identity used for the cache key — the same
    one arm 2 used, so the comparison finds these results."""
    return f"gemini:{model}"


def _build_prompts() -> tuple[dict[str, str], dict]:
    """Render v1.1.0 fulltext prompts for uncached papers. Returns
    {paper_id: prompt} and the paper objects for validation."""
    picks = stratify_thirty()
    papers_by_oid = _load_papers_by_openalex_id()
    ex = Extractor.__new__(Extractor)
    ex._prompt = V11
    ex._input_source = INPUT_SOURCE

    settings = get_settings()
    model = _sync_model_name(settings.gemini_model)
    cache = ExtractionCache()

    prompts: dict[str, str] = {}
    papers: dict[str, object] = {}
    for r in picks:
        paper = papers_by_oid.get(r["openalex_id"])
        if paper is None:
            continue
        ft = load_cached_fulltext(paper.id)
        if not ft:
            continue  # abstract_only — not in arm 3
        paper.fulltext = ft
        if cache.get(paper.id, model, INPUT_SOURCE, V11.hash) is not None:
            continue  # already done — never re-pay
        prompts[paper.id] = ex._render(paper)
        papers[paper.id] = paper
    return prompts, papers


def _validate_and_cache(paper, text: str, *, model: str, cache: ExtractionCache) -> str:
    """Parse → validate → augment → cache one batch result. Returns
    'ok' | 'parse-fail' | 'schema-fail' | 'paper-id-mismatch'."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return "parse-fail"
    if data.get("paper_id") != paper.id:
        return "paper-id-mismatch"
    data["extractor"] = model
    data["extracted_at"] = datetime.now(timezone.utc).isoformat()
    try:
        ext = PaperExtraction.model_validate(data)
    except ValidationError:
        return "schema-fail"
    ext = enforce_compound_splitting(ext)
    cache.put(paper.id, model, INPUT_SOURCE, V11.hash, ext)
    return "ok"


def _collect(client: GeminiBatchClient, batch_id: str, papers: dict) -> bool:
    """Poll once; if SUCCEEDED, process results and return True."""
    job = client.poll(batch_id)
    print(f"[batch] state={job.state}")
    if not job.done:
        return False
    if not job.succeeded:
        print(f"[batch] job did not succeed: {job.state}")
        return True  # terminal; nothing to collect
    results = client.results(job)
    settings = get_settings()
    model = _sync_model_name(settings.gemini_model)
    cache = ExtractionCache()
    ok = fails = 0
    for pid, text in results.items():
        paper = papers.get(pid)
        if paper is None:
            print(f"[batch] result for unknown paper {pid} — skipping")
            continue
        outcome = _validate_and_cache(paper, text, model=model, cache=cache)
        if outcome == "ok":
            ok += 1
        else:
            fails += 1
            print(f"[batch] HARD-FAIL {pid}: {outcome} (continuing)")
    print(f"[batch] collected: {ok} cached, {fails} hard-failed")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--wait-min", type=float, default=8.0)
    args = ap.parse_args()

    settings = get_settings()
    if not settings.can_use_gemini:
        print("GEMINI_API_KEY unset.", file=sys.stderr)
        return 2

    prompts, papers = _build_prompts()

    # --collect only: reuse saved batch id + rebuilt papers.
    if args.collect and not args.submit:
        if not STATE.exists():
            print("no saved batch state to collect.", file=sys.stderr)
            return 1
        st = json.loads(STATE.read_text())
        client = GeminiBatchClient(model_name=settings.gemini_model)
        done = _collect(client, st["batch_id"], papers)
        return 0 if done else 3

    print(f"[batch] {len(prompts)} uncached full-text papers to extract")
    if not prompts:
        print("[batch] nothing to do — all full-text papers already cached.")
        return 0

    client = GeminiBatchClient(model_name=settings.gemini_model)
    batch_id = client.submit(prompts, display_name="researchmap-arm3-fulltext")
    STATE.write_text(json.dumps({
        "batch_id": batch_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "paper_ids": sorted(prompts),
    }, indent=2))
    print(f"[batch] submitted id={batch_id}; state saved to "
          f"{STATE.relative_to(REPO_ROOT)}")

    if args.submit and not args.collect:
        print("[batch] --submit only; run --collect later.")
        return 0

    # Poll up to wait-min.
    deadline = time.time() + args.wait_min * 60
    while time.time() < deadline:
        if _collect(client, batch_id, papers):
            return 0
        time.sleep(20)
    print(f"[batch] still pending after {args.wait_min} min — "
          f"run `--collect` later.")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
