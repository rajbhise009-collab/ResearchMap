"""Rebuild the hand-review artifact from the Phase-2 raw dump.

Consumes `data/live_samples/phase2_diagnostic_raw.json` (gitignored),
draws the same deterministic 60-paper sample used by
`diagnose_v3.py` (RNG seed 20260723), and emits two review files
under `scratch/`:

  scratch/corpus_review.csv  — one row per paper, first five columns
                                prefilled (openalex_id, title, venue,
                                year, abstract_full — FULL untruncated
                                abstract), remaining columns blank for
                                hand labelling.
  scratch/corpus_review.md   — same content in readable markdown, one
                                paper per section, so the reviewer can
                                upload it for discussion.

Blank columns (see docs/labelling-rubric.md and the schema pressure-
test the reviewer runs in the same reading pass):

  on_domain         on-domain | borderline | off-domain
  has_limitation    yes | no  — does the ABSTRACT state a limitation?
  claim_hedged      firm | hedged | mixed — how strongly are the main
                    claims asserted?
  has_future_work   explicit | implied | none
  compound_claims   yes | no  — does any single sentence carry two
                    claims needing separate evidence?
  notes             free-form
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

from backend.app.ingestion.normalizer import _reconstruct_abstract  # noqa: E402


RAW_PATH   = REPO_ROOT / "data" / "live_samples" / "phase2_diagnostic_raw.json"
CSV_PATH   = REPO_ROOT / "scratch" / "corpus_review.csv"
MD_PATH    = REPO_ROOT / "scratch" / "corpus_review.md"
SAMPLE_N   = 60
RNG_SEED   = 20260723  # SAME seed as diagnose_v3, so the sample is stable


BLANK_COLUMNS = [
    "on_domain",
    "has_limitation",
    "claim_hedged",
    "has_future_work",
    "compound_claims",
    "notes",
]


def _venue(record: dict) -> str:
    hv = record.get("host_venue") or record.get("primary_location") or {}
    if isinstance(hv, dict):
        src = hv.get("source") if isinstance(hv.get("source"), dict) else {}
        return (
            (src.get("display_name") if isinstance(src, dict) else None)
            or hv.get("display_name")
            or ""
        )
    return ""


def main() -> int:
    if not RAW_PATH.exists():
        print(
            f"ERROR: {RAW_PATH} not found. Re-run the Phase-2 diagnostic first "
            "(backend.app.corpus.diagnose_v3) to regenerate it.",
            file=sys.stderr,
        )
        return 1

    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    results = raw.get("results") or []

    # Reproduce the diagnose_v3 sample deterministically.
    rng = random.Random(RNG_SEED)
    idx = list(range(len(results)))
    rng.shuffle(idx)
    sample_records = [results[i] for i in idx[:SAMPLE_N]]

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    # --- CSV ----------------------------------------------------------
    fieldnames = ["openalex_id", "title", "venue", "year", "abstract_full"] \
                 + BLANK_COLUMNS
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sample_records:
            abstract = _reconstruct_abstract(r.get("abstract_inverted_index")) or ""
            row = {
                "openalex_id": r.get("id", ""),
                "title": (r.get("title") or "").strip(),
                "venue": _venue(r),
                "year": r.get("publication_year", ""),
                "abstract_full": abstract,
            }
            for col in BLANK_COLUMNS:
                row[col] = ""
            w.writerow(row)

    # --- Markdown -----------------------------------------------------
    lines: list[str] = []
    lines.append("# Corpus review — 60-paper hand-label sample")
    lines.append("")
    lines.append(
        "Deterministic sample from the Phase-2 raw pull. Full untruncated "
        "abstracts. Labelling rubric: see `docs/labelling-rubric.md`. Each "
        "paper carries seven blank fields the reviewer fills in the same "
        "reading pass; the last six pressure-test the extraction schema at "
        "the same time as they measure precision."
    )
    lines.append("")
    lines.append(f"- Source: `data/live_samples/phase2_diagnostic_raw.json`")
    lines.append(f"- Sample size: **{len(sample_records)}**")
    lines.append(f"- RNG seed (frozen): `{RNG_SEED}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    for i, r in enumerate(sample_records, 1):
        title = (r.get("title") or "").strip() or "(untitled)"
        year = r.get("publication_year", "?")
        venue = _venue(r) or "(no venue)"
        oaid = r.get("id", "")
        abstract = _reconstruct_abstract(r.get("abstract_inverted_index")) or \
                   "_(no abstract in response)_"
        lines.append(f"## {i:02d}. {title}")
        lines.append("")
        lines.append(f"- **openalex_id:** [{oaid}]({oaid})")
        lines.append(f"- **venue:** {venue}")
        lines.append(f"- **year:** {year}")
        lines.append("")
        lines.append("**Abstract**")
        lines.append("")
        lines.append(abstract)
        lines.append("")
        lines.append("**Fields to fill**")
        lines.append("")
        for col in BLANK_COLUMNS:
            lines.append(f"- {col}:")
        lines.append("")
        lines.append("---")
        lines.append("")
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {CSV_PATH.relative_to(REPO_ROOT)}")
    print(f"Wrote {MD_PATH.relative_to(REPO_ROOT)}")
    print(f"Sample size: {len(sample_records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
