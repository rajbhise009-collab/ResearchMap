"""Recover missing abstracts for corpus members OpenAlex didn't have.

Data-quality bug from Phase 2: 4/60 of the hand-review sample came back
from OpenAlex without an abstract. A paper we cannot read is not a
corpus member. Rule (from the labelling brief): attempt Semantic
Scholar first, then arXiv, then exclude.

APIs used (both free, both allowed under the autonomy policy):
  - Semantic Scholar `paper/DOI:{doi}` (unauth OK; rate-limited)
  - arXiv `export.arxiv.org/api/query` (unauth, always free)

Outputs:
  data/labelled/abstract_recovery_manifest.json — per-paper record of
  what was tried, what worked, and (for exclusions) the reason.

Corpus consequence: papers with no recovered abstract are excluded
from the extraction corpus by manifest. The persistent-limitations
scorer never sees them.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402


RAW_PATH = REPO_ROOT / "data" / "live_samples" / "phase2_diagnostic_raw.json"
MANIFEST_PATH = REPO_ROOT / "data" / "labelled" / "abstract_recovery_manifest.json"
CORPUS_REVIEW_CSV = REPO_ROOT / "scratch" / "corpus_review.csv"

S2_BASE = "https://api.semanticscholar.org/graph/v1"
ARXIV_BASE = "https://export.arxiv.org/api/query"


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    v = doi.strip().lower()
    for pfx in ("https://doi.org/", "http://doi.org/", "doi:"):
        if v.startswith(pfx):
            v = v[len(pfx):]
    return v or None


def _reconstruct_abstract(inv: dict[str, list[int]] | None) -> str | None:
    if not inv:
        return None
    pos: dict[int, str] = {}
    for tok, ixs in inv.items():
        for i in ixs:
            pos[i] = tok
    if not pos:
        return None
    return " ".join(pos[i] for i in sorted(pos)).strip() or None


def try_semantic_scholar(doi: str, client: httpx.Client) -> Optional[str]:
    """Look up a paper by DOI on Semantic Scholar; return abstract if any."""
    url = f"{S2_BASE}/paper/DOI:{doi}"
    try:
        r = client.get(url, params={"fields": "abstract,title"})
        if r.status_code == 404:
            return None
        if r.status_code == 429:
            # Rate-limited unauth. Back off once and retry.
            time.sleep(2.0)
            r = client.get(url, params={"fields": "abstract,title"})
        r.raise_for_status()
        body = r.json()
        abs_text = (body.get("abstract") or "").strip()
        return abs_text or None
    except httpx.HTTPError:
        return None


def try_arxiv(title: str, client: httpx.Client) -> Optional[str]:
    """Search arXiv by title; return the summary of the best-matching
    hit if the title is a strong match, else None."""
    # arXiv's search is fuzzy; require a strong title overlap before
    # accepting the match.
    query_title = re.sub(r"[^A-Za-z0-9 ]+", " ", title)[:200]
    try:
        r = client.get(ARXIV_BASE, params={
            "search_query": f"ti:{query_title}",
            "start": "0",
            "max_results": "3",
        })
        r.raise_for_status()
    except httpx.HTTPError:
        return None

    text = r.text
    # Parse the atom feed with a minimal regex — avoid pulling in feedparser.
    entries = re.split(r"<entry>", text)[1:]
    norm_want = _norm_title(title)
    for entry in entries:
        m_title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        m_sum = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        if not m_title or not m_sum:
            continue
        got_title = re.sub(r"\s+", " ", m_title.group(1)).strip()
        if _norm_title(got_title) != norm_want:
            continue
        summary = re.sub(r"\s+", " ", m_sum.group(1)).strip()
        return summary or None
    return None


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm_title(t: str) -> str:
    return _NON_ALNUM.sub(" ", t.lower()).strip()


def main() -> int:
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))

    # Identify papers whose abstract_inverted_index is empty in the
    # OpenAlex response.
    missing: list[dict] = []
    for w in raw.get("results", []):
        inv = w.get("abstract_inverted_index")
        if _reconstruct_abstract(inv):
            continue
        missing.append(w)

    print(f"[audit] {len(missing)}/{len(raw['results'])} papers missing abstract in OpenAlex response")

    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(raw["results"]),
        "openalex_missing_abstracts": len(missing),
        "records": [],
    }

    with httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={"User-Agent": "ResearchMap/0.1 abstract-recovery"},
    ) as client:
        for w in missing:
            openalex_id = w.get("id")
            title = (w.get("title") or "").strip()
            doi = normalize_doi(w.get("doi"))

            record = {
                "openalex_id": openalex_id,
                "title": title,
                "doi": doi,
                "attempts": {},
                "recovered_from": None,
                "recovered_abstract": None,
                "excluded": False,
                "exclusion_reason": None,
            }

            # --- Semantic Scholar
            if doi:
                s2 = try_semantic_scholar(doi, client)
                record["attempts"]["semantic_scholar"] = "hit" if s2 else "miss"
                if s2:
                    record["recovered_from"] = "semantic_scholar"
                    record["recovered_abstract"] = s2
            else:
                record["attempts"]["semantic_scholar"] = "skipped (no doi)"

            # --- arXiv (only if S2 miss)
            if not record["recovered_abstract"]:
                arx = try_arxiv(title, client)
                record["attempts"]["arxiv"] = "hit" if arx else "miss"
                if arx:
                    record["recovered_from"] = "arxiv"
                    record["recovered_abstract"] = arx

            if not record["recovered_abstract"]:
                record["excluded"] = True
                record["exclusion_reason"] = (
                    "no abstract in OpenAlex; not recovered from Semantic "
                    "Scholar or arXiv"
                )
                print(f"  EXCLUDED  {openalex_id}  {title[:60]}")
            else:
                print(f"  recovered {openalex_id} via {record['recovered_from']}  "
                      f"({len(record['recovered_abstract'])} chars)")

            manifest["records"].append(record)

            # Be a good citizen — light rate throttling.
            time.sleep(0.5)

    recovered = sum(1 for r in manifest["records"] if r["recovered_abstract"])
    excluded = sum(1 for r in manifest["records"] if r["excluded"])
    manifest["summary"] = {
        "recovered": recovered,
        "excluded": excluded,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print()
    print(f"Recovered: {recovered}/{len(missing)}")
    print(f"Excluded:  {excluded}/{len(missing)}")
    print(f"Manifest:  {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
