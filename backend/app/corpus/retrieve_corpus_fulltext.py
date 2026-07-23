"""Retrieve arXiv full text for the 30-paper stratified corpus.

Free (arXiv only), no Gemini quota consumed. Produces:
  - data/cache/fulltext/<paper_id>.txt for each recovered paper
  - data/live_samples/fulltext_manifest.json — per-paper: arXiv id,
    recovered?, abstract_only flag, char/token counts, reason.

Papers without recoverable arXiv full text stay in the corpus flagged
`abstract_only` — we measure the difference, we don't drop them.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

from backend.app.ingestion.fulltext import (  # noqa: E402
    estimate_tokens,
    retrieve_fulltext,
)
from backend.app.corpus.run_live_extraction import (  # noqa: E402
    stratify_thirty,
    _load_papers_by_openalex_id,
)

MANIFEST = REPO_ROOT / "data" / "live_samples" / "fulltext_manifest.json"


def main() -> int:
    picks = stratify_thirty()
    papers_by_oid = _load_papers_by_openalex_id()

    records = []
    recovered = abstract_only = 0
    with httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0),
        headers={"User-Agent": "ResearchMap/0.1 fulltext"},
    ) as client:
        for i, r in enumerate(picks, 1):
            oid = r["openalex_id"]
            paper = papers_by_oid.get(oid)
            if paper is None:
                continue
            res = retrieve_fulltext(paper, client=client)
            rec = {
                "openalex_id": oid,
                "paper_id": paper.id,
                "on_domain": r["on_domain"],
                "arxiv_id": res.arxiv_id,
                "abstract_only": res.abstract_only,
                "reason": res.reason,
                "from_cache": res.from_cache,
                "fulltext_chars": len(res.fulltext) if res.fulltext else 0,
                "fulltext_est_tokens": estimate_tokens(res.fulltext) if res.fulltext else 0,
            }
            records.append(rec)
            if res.abstract_only:
                abstract_only += 1
                tag = "ABSTRACT-ONLY"
            else:
                recovered += 1
                tag = f"fulltext {rec['fulltext_est_tokens']} tok"
            print(f"[{i:02d}] {paper.id:<26} {tag:<22} arxiv={res.arxiv_id} ({res.reason})")
            if not res.from_cache:
                time.sleep(1.0)  # be polite to arXiv

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_size": len(records),
        "fulltext_recovered": recovered,
        "abstract_only": abstract_only,
        "coverage_pct": round(100 * recovered / len(records), 1) if records else 0,
        "records": records,
    }, indent=2, ensure_ascii=False))
    print(f"\n[manifest] {MANIFEST.relative_to(REPO_ROOT)}")
    print(f"[coverage] fulltext {recovered}/{len(records)} "
          f"({100*recovered/len(records):.0f}%), "
          f"abstract_only {abstract_only}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
