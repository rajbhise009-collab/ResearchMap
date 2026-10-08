"""Raw OpenAlex records for a multi-domain library.

The full fetch (`snowball.json`, ~15-18 MB per library) stays local and
gitignored. `records.slim.json` is the committed subset: only the fields
the pipeline reads (ids, title, year, DOI, venue, field, first-author
names, references, OA locations, abstract index), so a fresh checkout —
including the weekly growth workflow — can rebuild every library.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.config import REPO_ROOT

DOMAINS = REPO_ROOT / "data" / "domains"
_KEEP = ("id", "doi", "title", "display_name", "publication_year", "publication_date",
         "cited_by_count", "is_retracted", "is_paratext", "type", "referenced_works",
         "abstract_inverted_index", "ids")


def slim(r: dict) -> dict:
    out = {k: r[k] for k in _KEEP if k in r}
    out["authorships"] = [{"author": {"display_name": ((a or {}).get("author") or {}).get("display_name")}}
                          for a in (r.get("authorships") or [])]
    src = ((r.get("primary_location") or {}).get("source") or {})
    out["primary_location"] = {"source": {"display_name": src.get("display_name")}} if src else None
    pt = r.get("primary_topic") or {}
    out["primary_topic"] = ({"display_name": pt.get("display_name"),
                             "field": {"display_name": (pt.get("field") or {}).get("display_name")}}
                            if pt else None)
    out["locations"] = [{"landing_page_url": l.get("landing_page_url"), "pdf_url": l.get("pdf_url"),
                         "source": {"display_name": ((l.get("source") or {}).get("display_name"))}}
                        for l in (r.get("locations") or [])]
    return out


def full_path(slug: str) -> Path:
    return DOMAINS / slug / "snowball.json"


def slim_path(slug: str) -> Path:
    return DOMAINS / slug / "records.slim.json"


def load(slug: str) -> dict:
    """{"records": [...], "rejected_records": [...]} — the full local fetch
    when present, else the committed slim copy."""
    p = full_path(slug) if full_path(slug).exists() else slim_path(slug)
    d = json.loads(p.read_text())
    return {"records": d["records"], "rejected_records": d.get("rejected_records", [])}


def write_slim(slug: str) -> dict:
    d = json.loads(full_path(slug).read_text())
    out = {"note": "Subset of snowball.json (backend/app/corpus/records.py).",
           "records": [slim(r) for r in d["records"]],
           "rejected_records": [slim(r) for r in d.get("rejected_records", [])]}
    slim_path(slug).write_text(json.dumps(out, separators=(",", ":")))
    return {"slug": slug, "records": len(out["records"]), "rejected": len(out["rejected_records"])}


def append(slug: str, recs: list[dict]) -> None:
    """Add newly accepted records to the slim copy and, if present, the full fetch."""
    for p, conv in ((slim_path(slug), slim), (full_path(slug), lambda r: r)):
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        have = {r.get("id") for r in d["records"]}
        d["records"] += [conv(r) for r in recs if r.get("id") not in have]
        p.write_text(json.dumps(d, separators=(",", ":")) if p == slim_path(slug) else json.dumps(d))


if __name__ == "__main__":
    for s in ("diet-and-mortality", "ml-fairness"):
        print(write_slim(s))
