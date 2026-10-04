"""Paper merges inside a multi-domain library — free, files only.

A merge is recorded in `data/domains/<slug>/merges.json`:

    {"merges": [{"survivor": "W…", "losers": ["W…"], "rule": "...",
                 "date": "...", "evidence": "docs/findings/..."}]}

Applying it (`python -m backend.app.corpus.merges --slug ml-fairness --apply`):
  - picks the survivor with the normalizer's own `_pick_survivor` (the
    survivor rule in docs/merge-policy.md) and refuses if the recorded
    survivor disagrees;
  - removes each loser from `prelabelled.json` and writes the merged entry
    (field-level policy: survivor-only identity/title, fill-in doi/year/
    venue/full text, max citations, transitive `merged_from`);
  - moves classifier verdicts whose two claims now belong to the same paper
    out of the verdict files into `reasoning/dropped_by_merge.json` (with
    the reason), so a self-"supports" never counts;
  - writes before/after counts to `data/domains/<slug>/merge_log.json`.

Extractions are never rewritten. `union_extraction()` folds a loser's
cached extraction onto its survivor at load time using the Phase-2 entity
keys in docs/merge-policy.md, so nothing attached to the loser is lost.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

DOMAINS_DIR = REPO_ROOT / "data" / "domains"


def merges_path(slug: str) -> Path:
    return DOMAINS_DIR / slug / "merges.json"


def load_merges(slug: str) -> list[dict]:
    p = merges_path(slug)
    return json.loads(p.read_text())["merges"] if p.exists() else []


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def union_extraction(survivor, losers: list):
    """Fold loser extractions onto the survivor (policy keys):
    claims (paper_id, normalized text); evidence by id; methodologies
    (paper_id, normalized name); limitations (paper_id, normalized
    category); future work by id. Loser items are re-attributed to the
    survivor paper; their ids are kept, so provenance stays readable."""
    pid = survivor.paper_id
    keys = {
        "claims": lambda x: (pid, _norm(x.text)),
        "evidence": lambda x: x.id,
        "methodologies": lambda x: (pid, _norm(x.name)),
        "limitations": lambda x: (pid, _norm(x.normalized_category)),
        "future_work": lambda x: x.id,
    }
    update = {}
    for field, key in keys.items():
        items = list(getattr(survivor, field))
        seen = {key(x) for x in items}
        for lo in losers:
            for x in getattr(lo, field):
                if hasattr(x, "paper_id"):
                    x = x.model_copy(update={"paper_id": pid})
                k = key(x)
                if k not in seen:
                    seen.add(k)
                    items.append(x)
        update[field] = items
    return survivor.model_copy(update=update)


# ---- counts ----------------------------------------------------------------

def library_counts(slug: str) -> dict:
    from backend.app.corpus import multi_domain_reason as R

    class _Refuse:
        def embed(self, texts):
            raise RuntimeError(f"would embed {len(texts)} claims; refusing (free script)")

    pre = json.loads((DOMAINS_DIR / slug / "prelabelled.json").read_text())
    exts = R.load_extractions(slug)
    cov = json.loads((DOMAINS_DIR / slug / "reasoning" / "coverage.json").read_text())
    st = cov["shortlist_settings"]
    pairs = R.compute_shortlist(exts, threshold=st["threshold"],
                                max_per_claim=st["max_per_claim"], slug=slug,
                                embed_client=_Refuse())
    done = R.load_classified_keys(slug)
    rd = DOMAINS_DIR / slug / "reasoning"
    n = lambda f: json.loads((rd / f).read_text())["n"] if (rd / f).exists() else 0  # noqa: E731
    return {
        "papers": len(pre["entries"]),
        "full_text": sum(1 for e in pre["entries"] if e.get("input_source") == "fulltext"),
        "extractions": len(exts),
        "claims": sum(len(e.claims) for e in exts),
        "shortlist_pairs": len(pairs),
        "shortlist_classified": sum((p.from_claim_id, p.to_claim_id) in done for p in pairs),
        "flagged_contradictions": n("contradictions.json"),
        "supports_verdicts": n("supports.json"),
        "none_verdicts": n("nones.json"),
    }


# ---- apply -----------------------------------------------------------------

def _paper(entry: dict, snowball: dict):
    from backend.app.ingestion.normalizer import from_openalex
    return from_openalex(snowball[entry["wid"]])


def apply(slug: str) -> dict:
    from backend.app.corpus import multi_domain_reason as R
    from backend.app.ingestion.normalizer import _pick_survivor

    merges = load_merges(slug)
    pre_p = DOMAINS_DIR / slug / "prelabelled.json"
    pre = json.loads(pre_p.read_text())
    by_wid = {e["wid"]: e for e in pre["entries"]}
    todo = [m for m in merges if any(lo in by_wid for lo in m["losers"])]
    if not todo:
        return {"slug": slug, "applied": 0, "note": "already applied"}
    before = library_counts(slug)
    snow = {r["id"].rsplit("/", 1)[-1]: r
            for r in json.loads((DOMAINS_DIR / slug / "snowball.json").read_text())["records"]}

    for m in todo:
        s_ent = by_wid[m["survivor"]]
        for lo in m["losers"]:
            l_ent = by_wid[lo]
            surv, _loser = _pick_survivor(_paper(s_ent, snow), _paper(l_ent, snow))
            if surv.id.split(":")[-1] != m["survivor"]:
                raise RuntimeError(f"merge-policy survivor is {surv.id}, merges.json says "
                                   f"{m['survivor']}; refusing")
            merged = dict(s_ent)
            for f in ("doi", "year", "venue", "abstract"):
                merged[f] = s_ent.get(f) or l_ent.get(f)
            merged["cited_by_count"] = max(s_ent.get("cited_by_count") or 0,
                                           l_ent.get("cited_by_count") or 0)
            if s_ent.get("input_source") != "fulltext" and l_ent.get("input_source") == "fulltext":
                merged.update({"input_source": "fulltext", "abstract_only": False,
                               "fulltext_source": f"merged:openalex:{lo}"})
            merged["merged_from"] = sorted(set(s_ent.get("merged_from", []))
                                           | {f"openalex:{lo}"}
                                           | set(l_ent.get("merged_from", [])))
            by_wid[m["survivor"]] = s_ent = merged
            del by_wid[lo]
    pre["entries"] = [by_wid[e["wid"]] for e in pre["entries"] if e["wid"] in by_wid]
    pre["n_kept"] = len(pre["entries"])
    pre["merges_applied"] = [{"survivor": m["survivor"], "losers": m["losers"]} for m in merges]
    pre_p.write_text(json.dumps(pre))

    # Verdicts whose two claims now belong to one paper are not cross-paper
    # evidence: move them aside, recorded.
    paper_of = {c.id: e.paper_id for e in R.load_extractions(slug) for c in e.claims}
    rd = DOMAINS_DIR / slug / "reasoning"
    dropped_p = rd / "dropped_by_merge.json"
    dropped = json.loads(dropped_p.read_text())["items"] if dropped_p.exists() else []
    for fname in ("contradictions.json", "supports.json", "nones.json", "failures.json"):
        p = rd / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        keep = []
        for it in d.get("items", []):
            a, b = it.get("from_claim_id"), it.get("to_claim_id")
            if a in paper_of and b in paper_of and paper_of[a] == paper_of[b]:
                dropped.append({**it, "dropped_from": fname,
                                "reason": f"both claims belong to {paper_of[a]} after merge"})
            else:
                keep.append(it)
        p.write_text(json.dumps({"n": len(keep), "items": keep}, indent=2))
    dropped_p.write_text(json.dumps({"n": len(dropped), "items": dropped}, indent=2))

    after = library_counts(slug)
    log = {"slug": slug, "date": date.today().isoformat(), "merges": merges,
           "before": before, "after": after,
           "verdicts_dropped_by_merge": len(dropped)}
    (DOMAINS_DIR / slug / "merge_log.json").write_text(json.dumps(log, indent=2) + "\n")
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.apply:
        print(json.dumps(apply(a.slug), indent=2))
    else:
        print(json.dumps({"slug": a.slug, "counts": library_counts(a.slug),
                          "merges": load_merges(a.slug)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
