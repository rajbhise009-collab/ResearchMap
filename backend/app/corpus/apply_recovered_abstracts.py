"""Merge recovered abstracts from the manifest into scratch/corpus_review.csv.

Reads `data/labelled/abstract_recovery_manifest.json`, updates the
`abstract_full` column for each recovered paper, and appends an
`abstract_source` column so it's obvious which abstracts came from
OpenAlex vs. S2 recovery vs. arXiv recovery.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/corpus/x.py
sys.path.insert(0, str(REPO_ROOT))

MANIFEST = REPO_ROOT / "data" / "labelled" / "abstract_recovery_manifest.json"
CSV_PATH = REPO_ROOT / "scratch" / "corpus_review.csv"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    recovered: dict[str, dict] = {r["openalex_id"]: r for r in manifest["records"]}

    rows = list(csv.DictReader(CSV_PATH.open("r", encoding="utf-8")))

    updated = 0
    excluded = 0
    for row in rows:
        oid = row["openalex_id"]
        rec = recovered.get(oid)
        if rec is None:
            row["abstract_source"] = "openalex"
            row["excluded"] = ""
            continue
        if rec["recovered_abstract"]:
            row["abstract_full"] = rec["recovered_abstract"]
            row["abstract_source"] = rec["recovered_from"]
            row["excluded"] = ""
            updated += 1
        else:
            row["abstract_source"] = "unrecovered"
            row["excluded"] = "1"
            excluded += 1

    fieldnames = list(rows[0].keys())
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Rows: {len(rows)}")
    print(f"  updated with recovered abstract: {updated}")
    print(f"  marked excluded (no recovery):   {excluded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
