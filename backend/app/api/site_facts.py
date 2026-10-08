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
    # LLM calibration is frozen: its recorded date stands. A file's mtime is
    # only a fallback for a first record (a fresh checkout resets mtimes).
    if opp.exists() and "llm-calibration" not in known:
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


# Result types in plain words, in the order the site lists them.
RESULT_TYPES = [
    ("unresolved_contradictions", "disagreement between papers", "disagreements between papers"),
    ("persistent_limitations", "recurring limitation", "recurring limitations"),
    ("structural_holes", "unexplored connection", "unexplored connections"),
    ("orphaned_future_work", "open question", "open questions"),
]
ZERO_NOTE = ("none were found among the papers read, which is not the same as "
             "none existing")
DISJOINT_NOTE = ("A fifth, experimental check (papers linked only through a third "
                 "paper) is switched off in every library until it can be validated.")


KIND_TO_TYPE = {"disagreement": "unresolved_contradictions",
                "unaddressed_limitation": "persistent_limitations",
                "method_transfer": "structural_holes",
                "unfollowed_future_work": "orphaned_future_work"}


def _results(st: dict, items: list[dict]) -> tuple[list[dict], int, int]:
    """Counts come from the cards themselves: visible = nothing set it
    aside. (rows, visible total, set-aside total)."""
    from backend.app.api.language import is_visible
    skipped = st.get("scorers_skipped") or {}
    vis: dict[str, int] = {}
    aside = 0
    for it in items:
        if is_visible(it):
            t = KIND_TO_TYPE.get(it["consumer"].get("kind_id"), "other")
            vis[t] = vis.get(t, 0) + 1
        else:
            aside += 1
    if "other" in vis:
        raise ValueError(f"unknown result kind in cards: {vis}")
    rows = []
    for key, one, many in RESULT_TYPES:
        if key in skipped:
            rows.append({"type": key, "count": None, "label": many,
                         "note": f"not checked: {skipped[key]}"})
            continue
        n = vis.get(key, 0)
        rows.append({"type": key, "count": n, "label": one if n == 1 else many,
                     "note": ZERO_NOTE if n == 0 else None})
    return rows, sum(vis.values()), aside


def _check_line(dc: dict | None) -> str | None:
    if not dc:
        return None
    if dc["classified"] == dc["shortlisted"]:
        return (f"The disagreement check compared every pair of closely similar claims from "
                f"different papers ({dc['shortlisted']} pairs); pairs worded differently are "
                "never compared.")
    return (f"The disagreement check has compared {dc['classified']} of {dc['shortlisted']} "
            "pairs of closely similar claims so far.")


def _growth(slug: str) -> dict:
    """What the weekly growth run has actually added (counted from the
    library's entries, never assumed)."""
    from backend.app.grow.core import grow_slugs
    if slug not in grow_slugs():
        return {"grows": False, "added": 0, "last_added": None}
    pre = DATA / "domains" / slug / "prelabelled.json"
    entries = _j(pre)["entries"] if pre.exists() else []
    added = [e.get("added_on") for e in entries if e.get("added_by") == "weekly-grow"]
    return {"grows": True, "added": len(added), "last_added": max(added) if added else None}


def build() -> dict:
    manifest = _j(PUB / "libraries.json")
    builds = _builds()
    libs = []
    for lib in manifest["libraries"]:
        d = _lib_dir(lib["snapshot_path"])
        st = _j(d / "stats.json")
        opps = _j(d / "opportunities.json")
        results, total, aside = _results(st, opps.get("items", []))
        visible = total
        dc = _disagreement(lib["slug"])
        libs.append({
            "slug": lib["slug"], "name": lib["name"], "short_name": lib["short_name"],
            "blurb": lib["blurb"],
            "built": builds.get(lib["slug"], {}).get("date"),
            "built_basis": builds.get(lib["slug"], {}).get("basis"),
            "papers": st["papers"],
            "claims_read": st.get("n_extractions"),
            "full_text": st["full_text"], "abstract_only": st["abstract_only"],
            "gap_cards": visible,
            "results": results,
            "results_total": total,
            "set_aside_total": aside,
            "growth": _growth(lib["slug"]),
            "check_line": _check_line(dc),
            "not_run": DISJOINT_NOTE,
            "disagreement_check": dc,
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
