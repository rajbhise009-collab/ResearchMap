"""Compute the PAIRED abstract-vs-fulltext comparison from cached
v1.1.0 extractions. No API calls — reads disk only.

Runs after both extraction sets exist. Emits the paired table (21
papers with both) plus the 30-paper abstract context and the
v1.0.0->v1.1.0 diff. Prints a fill-in block for
docs/abstract-vs-fulltext.md and writes the raw numbers to
data/live_samples/abstract_vs_fulltext_numbers.json.

Refuses to emit a paired comparison unless BOTH extractions exist for
every paired paper — a partial comparison is confident noise.
"""

from __future__ import annotations

import csv
import json
import statistics as st
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/corpus/x.py
sys.path.insert(0, str(REPO_ROOT))

from backend.app.extraction.cache import ExtractionCache  # noqa: E402
from backend.app.extraction.prompt_versions import load  # noqa: E402
from backend.app.models import PaperExtraction  # noqa: E402

MANIFEST = REPO_ROOT / "data" / "live_samples" / "fulltext_manifest.json"
CORPUS_CSV = REPO_ROOT / "scratch" / "corpus_review.csv"
RAW_DUMP = REPO_ROOT / "data" / "live_samples" / "phase2_diagnostic_raw.json"
OUT = REPO_ROOT / "data" / "live_samples" / "abstract_vs_fulltext_numbers.json"

MODEL = "gemini:gemini-3.6-flash"


def _counts(e: PaperExtraction) -> dict:
    return {
        "claims": len(e.claims),
        "limitations": len(e.limitations),
        "this_work_lims": sum(1 for l in e.limitations if l.source_scope == "this_work"),
        "prior_work_lims": sum(1 for l in e.limitations if l.source_scope == "prior_work"),
        "future_work": len(e.future_work),
        "methodologies": len(e.methodologies),
    }


def _mean(rows: list[dict], key: str) -> float:
    return round(st.mean(r[key] for r in rows), 2) if rows else 0.0


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    paired_ids = [r["paper_id"] for r in manifest["records"] if not r["abstract_only"]]
    all30_ids = [r["paper_id"] for r in manifest["records"]]

    cache = ExtractionCache()
    v11 = load("v1.1.0").hash
    v10 = load("v1.0.0").hash

    def get(pid, source, phash):
        return cache.get(pid, MODEL, source, phash)

    # --- Availability check.
    missing = []
    for pid in paired_ids:
        if get(pid, "abstract", v11) is None:
            missing.append((pid, "abstract/v1.1.0"))
        if get(pid, "fulltext", v11) is None:
            missing.append((pid, "fulltext/v1.1.0"))
    if missing:
        print(f"NOT READY — {len(missing)} paired extractions missing:")
        for pid, what in missing[:40]:
            print(f"  {pid}  {what}")
        print("\nRun both extractions first:")
        print("  python -m backend.app.corpus.run_live_extraction")
        print("  python -m backend.app.corpus.run_live_extraction --input-source fulltext")
        return 1

    # --- Paired (21): abstract vs fulltext, v1.1.0.
    abs_rows = [{**_counts(get(pid, "abstract", v11)), "pid": pid} for pid in paired_ids]
    ful_rows = [{**_counts(get(pid, "fulltext", v11)), "pid": pid} for pid in paired_ids]

    metrics = ["claims", "limitations", "this_work_lims", "prior_work_lims",
               "future_work", "methodologies"]
    paired = {m: {"abstract": _mean(abs_rows, m), "fulltext": _mean(ful_rows, m)} for m in metrics}

    # --- 30-paper abstract context (only those that exist).
    all30 = [get(pid, "abstract", v11) for pid in all30_ids]
    all30 = [e for e in all30 if e is not None]
    all30_rows = [_counts(e) for e in all30]

    # --- v1.0.0 abstract for the same 30 (baseline diff).
    v10_rows = [_counts(e) for pid in all30_ids
                if (e := get(pid, "abstract", v10)) is not None]

    out = {
        "model": MODEL,
        "paired_n": len(paired_ids),
        "paired_v11_abstract_vs_fulltext": paired,
        "all30_v11_abstract": {m: _mean(all30_rows, m) for m in metrics} if all30_rows else {},
        "all30_v10_abstract": {m: _mean(v10_rows, m) for m in metrics} if v10_rows else {},
        "counts": {"all30_v11": len(all30_rows), "v10": len(v10_rows)},
    }
    OUT.write_text(json.dumps(out, indent=2))

    # --- Print the fill-in table.
    print(f"=== PAIRED (n={len(paired_ids)}) — v1.1.0 abstract vs fulltext ===\n")
    print(f"{'metric':<26} {'abstract':>10} {'fulltext':>10} {'ratio':>8}")
    for m in metrics:
        a = paired[m]["abstract"]; f = paired[m]["fulltext"]
        ratio = f"{f/a:.1f}x" if a else "-"
        print(f"{m:<26} {a:>10} {f:>10} {ratio:>8}")

    print("\n=== VERDICT INPUTS ===")
    ow_a = paired["this_work_lims"]["abstract"]; ow_f = paired["this_work_lims"]["fulltext"]
    fw_a = paired["future_work"]["abstract"]; fw_f = paired["future_work"]["fulltext"]
    print(f"own-work limitations/paper: {ow_a} -> {ow_f}")
    print(f"future-work items/paper:    {fw_a} -> {fw_f}")
    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
