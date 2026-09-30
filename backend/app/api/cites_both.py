"""'Who has tried to settle this' — OpenAlex query for works that cite
BOTH sides of a confirmed contradiction.

Free-tier OpenAlex only. One credit per pair. Runs at BUILD TIME (not
live from the browser), and the top-N results are baked into the
snapshot at `data/domains/<slug>/reasoning/cites_both.json`.

The UI presents this as "later papers that cite both sides" — the
copy must NOT imply the papers resolved or settled the disagreement.
Citing both = discussing, not deciding.

OpenAlex `cites:` filter syntax verified 2026-09-30 against the live
free tier: `filter=cites:W_A,cites:W_B` is AND across two `cites`
filters; single call returns works citing BOTH. `merged_from` support
would fold preprint/published pairs into one side but that requires
knowing the merged siblings up front; skipped in v1.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import httpx

from backend.app.api.contradiction_audit import (
    attach_verdicts, audit_summary,
)
from backend.app.config import REPO_ROOT, get_settings

OA_BASE = "https://api.openalex.org"


def _wid(pid: str) -> str:
    """openalex:W123 or https://openalex.org/W123 -> W123."""
    return (pid or "").rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def query_cites_both(
    a_id: str, b_id: str, *,
    api_key: str,
    top_n: int = 10,
    client: httpx.Client | None = None,
) -> dict:
    """Return {total: int, items: [top-N by cited_by_count]}. Excludes A
    and B themselves — they cite each other but that isn't 'a third
    paper discussing the disagreement'."""
    a_wid, b_wid = _wid(a_id), _wid(b_id)
    params = {
        "filter": f"cites:{a_wid},cites:{b_wid}",
        "per-page": str(min(50, max(top_n + 2, 12))),   # +2 for A/B exclusion
        "sort": "cited_by_count:desc",
        "select": ("id,doi,display_name,publication_year,cited_by_count,"
                    "primary_location"),
        "api_key": api_key,
    }
    close = False
    if client is None:
        client = httpx.Client(timeout=30.0)
        close = True
    try:
        r = client.get(f"{OA_BASE}/works", params=params)
        r.raise_for_status()
        payload = r.json()
    finally:
        if close:
            client.close()

    total = int((payload.get("meta") or {}).get("count") or 0)
    results = payload.get("results") or []
    # Exclude A and B themselves — they cite each other, but "cites both"
    # is meant to name third-party papers discussing the disagreement.
    filtered = []
    for w in results:
        wid = _wid(w.get("id", ""))
        if wid in (a_wid, b_wid):
            continue
        filtered.append({
            "wid": wid,
            "openalex_id": w.get("id"),
            "doi": w.get("doi"),
            "title": w.get("display_name"),
            "year": w.get("publication_year"),
            "cited_by_count": w.get("cited_by_count"),
            "venue": (((w.get("primary_location") or {}).get("source") or {})
                       .get("display_name")),
        })
    return {"total_cites_both": total, "top": filtered[:top_n]}


def compute_cites_both_for_domain(
    slug: str, *, top_n: int = 10, api_key: str | None = None,
) -> dict:
    """For every GENUINE contradiction in a domain, fetch the cites-both
    list. Writes `data/domains/<slug>/reasoning/cites_both.json` with a
    record per pair, plus the run's query_date."""
    contra_path = REPO_ROOT / "data" / "domains" / slug / "reasoning" / "contradictions.json"
    if not contra_path.exists():
        return {"slug": slug, "n_pairs": 0, "n_queried": 0, "credits_used": 0}
    raw = json.loads(contra_path.read_text()).get("items", [])
    audited = attach_verdicts(slug, raw)
    genuine = [c for c in audited if c["audit"]["verdict"] == "genuine"]

    settings = get_settings()
    key = api_key or (settings.openalex_api_key.get_secret_value()
                        if settings.openalex_api_key else None)
    if not key:
        raise RuntimeError(
            "OPENALEX_API_KEY not set; needed for cites-both queries."
        )

    query_date = datetime.date.today().isoformat()
    records = []
    credits_used = 0
    with httpx.Client(timeout=30.0) as client:
        for c in genuine:
            r = client.get(f"{OA_BASE}/works", params={
                "filter": f"cites:{_wid(c['a_paper_id'])},cites:{_wid(c['b_paper_id'])}",
                "per-page": str(min(50, max(top_n + 2, 12))),
                "sort": "cited_by_count:desc",
                "select": ("id,doi,display_name,publication_year,"
                            "cited_by_count,primary_location"),
                "api_key": key,
            })
            credits_used += int(r.headers.get("X-RateLimit-Credits-Used") or 0)
            r.raise_for_status()
            payload = r.json()
            total = int((payload.get("meta") or {}).get("count") or 0)
            top = []
            a_wid, b_wid = _wid(c["a_paper_id"]), _wid(c["b_paper_id"])
            for w in payload.get("results") or []:
                wid = _wid(w.get("id", ""))
                if wid in (a_wid, b_wid):
                    continue
                top.append({
                    "wid": wid, "openalex_id": w.get("id"),
                    "doi": w.get("doi"), "title": w.get("display_name"),
                    "year": w.get("publication_year"),
                    "cited_by_count": w.get("cited_by_count"),
                    "venue": (((w.get("primary_location") or {}).get("source")
                                or {}).get("display_name")),
                })
                if len(top) >= top_n:
                    break
            records.append({
                "a_paper_id": c["a_paper_id"],
                "b_paper_id": c["b_paper_id"],
                "verdict_topic": c["audit"].get("topic"),
                "total_cites_both": total,
                "top": top,
            })

    out = {
        "slug": slug,
        "query_date": query_date,
        "n_genuine_pairs_queried": len(genuine),
        "credits_used": credits_used,
        "note": ("Papers listed here cite both sides of the disagreement — "
                  "this means they discuss it, not that they resolved it."),
        "records": records,
    }
    out_path = REPO_ROOT / "data" / "domains" / slug / "reasoning" / "cites_both.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    return {
        "slug": slug, "n_pairs": len(audited),
        "n_queried": len(genuine), "credits_used": credits_used,
    }


def load_cites_both(slug: str) -> dict | None:
    p = REPO_ROOT / "data" / "domains" / slug / "reasoning" / "cites_both.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


__all__ = ["query_cites_both", "compute_cites_both_for_domain",
            "load_cites_both", "_wid"]
