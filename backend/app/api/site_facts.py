"""Facts the public trust pages and library headers show — from data only.

  python -m backend.app.api.site_facts     # writes frontend/public/data/site-facts.json

Per library: build date (and what it means), papers, claims read, full text
vs abstract only, gap cards, and the disagreement check with its hand audit.
Free; reads files only. Anything not measured is written as null and the
site prints "not measured".

"Built" = the date the library's current results were produced:
  - diet-and-mortality, ml-fairness: `date` in reasoning/coverage.json (the
    disagreement check's last run over the final corpus);
  - llm-calibration: the file date of data/reasoning/opportunities.jsonl
    (its frozen gap list). That source is gitignored, so the value is kept
    in data/library_builds.json and reused when the source is absent.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

DATA = REPO_ROOT / "data"
PUB = REPO_ROOT / "frontend" / "public" / "data"
OUT = PUB / "site-facts.json"
BUILDS = DATA / "library_builds.json"


def _j(p: Path):
    return json.loads(p.read_text())


def _lib_dir(snapshot_path: str) -> Path:
    return PUB if snapshot_path == "/data" else PUB / snapshot_path.removeprefix("/data/")


def _builds() -> dict:
    known = _j(BUILDS) if BUILDS.exists() else {}
    opp = DATA / "reasoning" / "opportunities.jsonl"
    if opp.exists():
        known["llm-calibration"] = {
            "date": datetime.fromtimestamp(opp.stat().st_mtime).date().isoformat(),
            "basis": "file date of the library's frozen gap list (data/reasoning/opportunities.jsonl)"}
    for slug in ("diet-and-mortality", "ml-fairness"):
        cov = DATA / "domains" / slug / "reasoning" / "coverage.json"
        if cov.exists():
            known[slug] = {"date": _j(cov)["date"],
                           "basis": "last run of the disagreement check over the final corpus"}
    BUILDS.write_text(json.dumps(known, indent=2) + "\n")
    return known


def _disagreement(slug: str) -> dict | None:
    if slug == "llm-calibration":
        rel = _j(DATA / "relationships" / "relationship_summary.json")["contradiction_stats"] \
            if (DATA / "relationships" / "relationship_summary.json").exists() else None
        if rel is None:
            return None
        return {"shortlisted": rel["candidates"], "classified": rel["classified"],
                "flagged": rel["contradicts"], "hand_checked": None,
                "confirmed": 0, "set_aside": rel["contradicts"],
                "checked_how": ("both flags set aside after a regime-context re-check "
                                "(different experimental conditions)")}
    rd = DATA / "domains" / slug / "reasoning"
    cov = _j(rd / "coverage.json")
    flagged = _j(rd / "contradictions.json")["n"]
    audit = _j(rd / "contradiction_audit.json")["verdicts"] if (rd / "contradiction_audit.json").exists() else []
    v = [a["verdict"] for a in audit]
    return {"shortlisted": cov["shortlist_pairs"], "classified": cov["classified_pairs"],
            "flagged": flagged, "hand_checked": len(v), "confirmed": v.count("genuine"),
            "set_aside": v.count("artifact") + v.count("duplicate"),
            "checked_how": ("by hand, by the project's builder, against the two papers' "
                            "abstracts; not independent expert review") if v else None}


def build() -> dict:
    manifest = _j(PUB / "libraries.json")
    builds = _builds()
    libs = []
    for lib in manifest["libraries"]:
        d = _lib_dir(lib["snapshot_path"])
        st = _j(d / "stats.json")
        opps = _j(d / "opportunities.json")
        n_gaps = opps.get("total", len(opps.get("items", [])))
        audit = opps.get("audit") or {}
        visible = audit.get("confirmed", n_gaps) if audit else n_gaps
        libs.append({
            "slug": lib["slug"], "name": lib["name"], "short_name": lib["short_name"],
            "blurb": lib["blurb"],
            "built": builds.get(lib["slug"], {}).get("date"),
            "built_basis": builds.get(lib["slug"], {}).get("basis"),
            "papers": st["papers"],
            "claims_read": st.get("n_extractions"),
            "full_text": st["full_text"], "abstract_only": st["abstract_only"],
            "gap_cards": visible,
            "disagreement_check": _disagreement(lib["slug"]),
            "audit_doubts": st.get("audit_doubts", []),
            "not_advice": bool(lib.get("not_advice_note")),
        })
    out = {"generated_by": "backend/app/api/site_facts.py", "libraries": libs}
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    return out


def main() -> int:
    for lib in build()["libraries"]:
        print(f"{lib['slug']}: built {lib['built']} · {lib['papers']} papers · claims read "
              f"{lib['claims_read']} of {lib['papers']} · {lib['gap_cards']} gap cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
