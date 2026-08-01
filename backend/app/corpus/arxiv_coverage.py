"""Measure arXiv full-text coverage of the 60-paper hand-review sample.

Purpose: revise the Phase 1.5 "OA full text is expensive" recommendation
if this corpus (AI/ML) has near-universal arXiv coverage. Cheaper than
we assumed makes the decision to ingest full text much easier.

Detection strategy (deterministic, free — arXiv API is unauthenticated):
  1. If OpenAlex's DOI matches the arXiv prefix `10.48550/arxiv.` →
     definite arXiv hit; record the arXiv id.
  2. Else if OpenAlex's `primary_location.landing_page_url` points
     to arxiv.org → hit.
  3. Else search arXiv's Atom API by title; require an exact
     normalized-title match to accept.

No PDF fetch — this is a feasibility check, not the ingest itself.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/corpus/x.py
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402


RAW_PATH = REPO_ROOT / "data" / "live_samples" / "phase2_diagnostic_raw.json"
REPORT_PATH = REPO_ROOT / "data" / "labelled" / "arxiv_coverage_report.json"
SAMPLE_SIZE = 60
RNG_SEED = 20260723  # same seed the hand-review used

ARXIV_BASE = "https://export.arxiv.org/api/query"
ARXIV_DOI_PREFIX = "10.48550/arxiv."


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _openalex_arxiv_from_doi(doi: str | None) -> Optional[str]:
    if not doi:
        return None
    v = doi.strip().lower()
    for pfx in ("https://doi.org/", "http://doi.org/", "doi:"):
        if v.startswith(pfx):
            v = v[len(pfx):]
    if v.startswith(ARXIV_DOI_PREFIX):
        return v[len(ARXIV_DOI_PREFIX):]
    return None


def _openalex_arxiv_from_landing(record: dict) -> Optional[str]:
    """Extract arXiv ID from OpenAlex `primary_location.landing_page_url`
    or `locations[].landing_page_url` if any."""
    locations = [record.get("primary_location") or {}]
    locations += record.get("locations") or []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        url = loc.get("landing_page_url") or loc.get("pdf_url") or ""
        m = re.search(r"arxiv\.org/abs/([0-9]{4}\.[0-9]{4,6})", url)
        if m:
            return m.group(1)
        m = re.search(r"arxiv\.org/pdf/([0-9]{4}\.[0-9]{4,6})", url)
        if m:
            return m.group(1)
    return None


def _arxiv_search_by_title(title: str, client: httpx.Client) -> Optional[str]:
    """Search arXiv Atom API for a title; return arXiv id iff the
    top-hit title normalizes to the same key as our query."""
    query = re.sub(r"[^A-Za-z0-9 ]+", " ", title)[:220]
    if not query.strip():
        return None
    try:
        r = client.get(ARXIV_BASE, params={
            "search_query": f"ti:{query}",
            "start": "0",
            "max_results": "3",
        })
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    text = r.text
    want = _norm_title(title)
    entries = re.split(r"<entry>", text)[1:]
    for entry in entries:
        m_title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        m_id = re.search(r"<id>http[s]?://arxiv\.org/abs/([0-9]{4}\.[0-9]{4,6})", entry)
        if not m_title or not m_id:
            continue
        got_title = re.sub(r"\s+", " ", m_title.group(1)).strip()
        if _norm_title(got_title) == want:
            return m_id.group(1)
    return None


def main() -> int:
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    results = raw.get("results") or []

    # Reproduce the diagnose_v3 60-paper sample deterministically.
    import random
    rng = random.Random(RNG_SEED)
    idx = list(range(len(results)))
    rng.shuffle(idx)
    sample_records = [results[i] for i in idx[:SAMPLE_SIZE]]

    per_paper = []
    hits_doi = 0
    hits_landing = 0
    hits_search = 0

    with httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={"User-Agent": "ResearchMap/0.1 arxiv-coverage"},
    ) as client:
        for w in sample_records:
            oid = w.get("id")
            title = (w.get("title") or "").strip()
            doi = w.get("doi")
            venue = ((w.get("host_venue") or {}).get("display_name") or "").lower()

            arxiv_id = _openalex_arxiv_from_doi(doi)
            method = None
            if arxiv_id:
                method = "openalex_doi"
                hits_doi += 1
            else:
                arxiv_id = _openalex_arxiv_from_landing(w)
                if arxiv_id:
                    method = "openalex_landing"
                    hits_landing += 1
                else:
                    arxiv_id = _arxiv_search_by_title(title, client)
                    if arxiv_id:
                        method = "arxiv_title_search"
                        hits_search += 1
                    time.sleep(0.4)  # be polite

            per_paper.append({
                "openalex_id": oid,
                "title": title,
                "openalex_venue": venue,
                "arxiv_id": arxiv_id,
                "method": method,
            })

    n = len(sample_records)
    hits_total = hits_doi + hits_landing + hits_search
    misses = n - hits_total

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": n,
        "hits_total": hits_total,
        "hit_breakdown": {
            "openalex_doi (arxiv DOI prefix)": hits_doi,
            "openalex_landing_page (arxiv.org URL)": hits_landing,
            "arxiv_title_search (fuzzy match on title)": hits_search,
        },
        "misses": misses,
        "coverage_percent": round(100.0 * hits_total / n, 1),
        "per_paper": per_paper,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"arXiv coverage of the 60-paper sample")
    print(f"  hits total          : {hits_total} / {n} = {100*hits_total/n:.1f}%")
    print(f"    via OpenAlex DOI (arXiv prefix)          : {hits_doi}")
    print(f"    via OpenAlex landing page (arxiv.org)    : {hits_landing}")
    print(f"    via arXiv title search                   : {hits_search}")
    print(f"  misses              : {misses}")
    print(f"  report              : {REPORT_PATH.relative_to(REPO_ROOT)}")

    if misses:
        print()
        print("Non-arXiv papers:")
        for r in per_paper:
            if not r["arxiv_id"]:
                print(f"  {r['openalex_id']}  ({r['openalex_venue']!r:35s}) {r['title'][:70]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
