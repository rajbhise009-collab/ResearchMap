"""Recover OA full text for the abstract-only papers via Unpaywall +
Europe PMC, and update the expanded corpus manifest in place.

Free (no Gemini spend). Idempotent: cached full text is reused, so
re-runs cost nothing and never re-download. Papers still without full
text keep `abstract_only=true`. Adds a `fulltext_source` field
(arxiv | unpaywall | europepmc) to every full-text record for the
per-source report.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/corpus/x.py
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.ingestion.fulltext import estimate_tokens  # noqa: E402
from backend.app.ingestion.oa_fulltext import retrieve_oa_fulltext  # noqa: E402
from backend.app.models import Paper, Source  # noqa: E402

MANIFEST = REPO_ROOT / "data" / "live_samples" / "expanded_corpus_manifest.json"
EMAIL = "raj.bhise009@gmail.com"


def _paper(rec: dict) -> Paper:
    return Paper(
        id=rec["paper_id"], source=Source.OPENALEX,
        source_id=rec["paper_id"].split(":", 1)[-1],
        doi=rec.get("doi"), title=rec.get("title") or "Untitled",
        year=rec.get("year"),
    )


def _existing_source(rec: dict) -> str:
    """Full-text source for a paper that already had full text (arXiv)."""
    return "arxiv"


def _manifest_hash(records: list[dict]) -> str:
    key = sorted(
        f"{r['paper_id']}|{r['input_source']}|{r['domain_centrality']}|{r['provenance']}"
        for r in records
    )
    return hashlib.sha256("\n".join(key).encode()).hexdigest()[:16]


def main() -> int:
    m = json.loads(MANIFEST.read_text())
    records = m["records"]
    before_ft = sum(1 for r in records if r["input_source"] == "fulltext")

    # Tag existing full-text papers with their source (arXiv).
    for r in records:
        if r["input_source"] == "fulltext" and "fulltext_source" not in r:
            r["fulltext_source"] = _existing_source(r)

    targets = [r for r in records if r["abstract_only"]]
    print(f"[oa] {len(targets)} abstract-only papers to attempt", flush=True)

    recovered = 0
    src_counter: Counter = Counter()
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0),
                      headers={"User-Agent": "ResearchMap/0.1 oa"}) as client:
        for i, r in enumerate(targets, 1):
            res = retrieve_oa_fulltext(_paper(r), email=EMAIL, client=client,
                                       use_cache=True)
            if res.fulltext and res.source:
                r["input_source"] = "fulltext"
                r["abstract_only"] = False
                r["fulltext_source"] = res.source
                r["fulltext_reason"] = res.reason
                r["fulltext_tokens"] = estimate_tokens(res.fulltext)
                recovered += 1
                src_counter[res.source] += 1
            else:
                r["oa_attempted"] = True
            if not res.from_cache:
                time.sleep(0.4)  # politeness across Unpaywall/EPMC/publishers
            if i % 25 == 0:
                print(f"[oa] {i}/{len(targets)} processed, "
                      f"{recovered} recovered", flush=True)

    after_ft = sum(1 for r in records if r["input_source"] == "fulltext")
    ft_source = Counter(r.get("fulltext_source") for r in records
                        if r["input_source"] == "fulltext")

    m["input_source"] = {
        "fulltext": after_ft,
        "abstract_only": sum(1 for r in records if r["abstract_only"]),
    }
    m["fulltext_coverage_pct"] = round(100 * after_ft / len(records), 1)
    m["fulltext_source"] = dict(ft_source)
    m["oa_recovery"] = {
        "before_fulltext": before_ft,
        "after_fulltext": after_ft,
        "recovered": recovered,
        "by_source": dict(src_counter),
        "recovered_at": datetime.now(timezone.utc).isoformat(),
    }
    m["manifest_hash"] = _manifest_hash(records)
    MANIFEST.write_text(json.dumps(m, indent=2))

    print(f"\n[oa] full text: {before_ft} -> {after_ft} "
          f"({m['fulltext_coverage_pct']}%); recovered {recovered}")
    print(f"[oa] recovered by source: {dict(src_counter)}")
    print(f"[oa] full-text source breakdown: {dict(ft_source)}")
    print(f"[oa] still abstract_only: {m['input_source']['abstract_only']}")
    print(f"[oa] manifest_hash: {m['manifest_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
