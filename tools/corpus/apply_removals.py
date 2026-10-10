"""Apply owner-approved paper removals through the normal pipeline (free).

  python tools/corpus/apply_removals.py data/removals/2026-10-10.json

For each {slug, wid, reason} in the spec:
  1. the paper's entry moves from prelabelled.json "entries" to "removed"
     (with the reason, the decision date and the proposal). Nothing is
     deleted: its record, extraction and spend stay on file, and weekly
     growth can never re-add it (core.select / core.collect);
  2. each affected library's disagreement coverage is recomputed from cached
     embeddings (an embedding client that refuses any call: Rs0);
  3. the site data, generated docs and share images are regenerated exactly
     as the weekly run does (tools/grow/run_weekly.regenerate);
  4. results before -> after are accounted with the weekly run's rules
     (every result that left has a stated reason; UNEXPLAINED stops it);
  5. the changelog and docs/releases/<date>-removals.json record it.
The ledger must be byte-identical afterwards.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools" / "grow")]


class _NoCalls:
    """Embedding client for a removal: every vector must already be cached."""

    def embed(self, texts):
        raise RuntimeError(f"a removal must not embed anything ({len(texts)} texts requested)")


def apply(spec_path: Path) -> dict:
    import run_weekly as rw
    from backend.app.corpus import multi_domain_reason as R
    from backend.app.corpus.multi_domain_reason_incremental import write_coverage

    spec = json.loads(spec_path.read_text())
    date, proposal = spec["decided_on"], spec["proposal"]
    ledger = ROOT / "data" / "spend_ledger.json"
    led0 = ledger.read_bytes()
    before = rw.items_snapshot()

    moved: list[dict] = []
    for slug in sorted({r["slug"] for r in spec["removals"]}):
        p = ROOT / "data" / "domains" / slug / "prelabelled.json"
        pre = json.loads(p.read_text())
        pre.setdefault("removed", [])
        done = {r["wid"] for r in pre["removed"]}
        for r in (x for x in spec["removals"] if x["slug"] == slug):
            if r["wid"] in done:
                continue                       # idempotent
            hit = [e for e in pre["entries"] if e["wid"] == r["wid"]]
            if not hit:
                raise SystemExit(f"{slug}: {r['wid']} is not in the library")
            pre["entries"] = [e for e in pre["entries"] if e["wid"] != r["wid"]]
            pre["removed"].append({"wid": r["wid"], "title": hit[0].get("title"), "year": hit[0].get("year"),
                                   "reason": r["reason"], "decided_on": date, "approved_by": "owner",
                                   "proposal": proposal, "entry": hit[0]})
            moved.append({"slug": slug, "wid": r["wid"], "title": hit[0].get("title"), "reason": r["reason"]})
        pre["n_kept"] = len(pre["entries"])
        p.write_text(json.dumps(pre))

    for slug in sorted({m["slug"] for m in moved}):
        exts = R.load_extractions(slug)
        pairs = R.compute_shortlist(exts, use_real_embeddings=True, slug=slug, embed_client=_NoCalls())
        write_coverage(slug, exts, pairs, threshold=R.LIBRARY_THRESHOLD, max_per_claim=R.LIBRARY_MAX_PER_CLAIM,
                       note=f"papers removed by the owner ({date})")

    rw.regenerate()
    diff = {s: d for s, d in rw.diff_items(before, rw.items_snapshot()).items() if s != "llm-calibration"}
    bad = rw.unexplained(diff)
    if bad:
        raise SystemExit(f"UNEXPLAINED result changes: {bad}")
    if ledger.read_bytes() != led0:
        raise SystemExit("the ledger changed during a removal")

    lines = [f"{m['slug']}: paper {m['wid']} removed (owner-approved, {proposal}): {m['reason']}" for m in moved]
    lines += rw.diff_lines(diff)
    rw.changelog(f"{date} (removals)", lines)
    rec = ROOT / "docs" / "releases" / f"{date}-removals.json"
    rec.write_text(json.dumps({"date": date, "proposal": proposal, "removed": moved,
                               "results_changed": {s: {k: d[k] for k in ("shown_before", "shown_after", "new_results",
                                                                          "removed_shown", "removed_not_shown",
                                                                          "verdict_changed")}
                                                   for s, d in diff.items()},
                               "spend_inr": 0.0}, indent=1) + "\n")
    return {"moved": moved, "diff": diff, "lines": lines}


if __name__ == "__main__":
    out = apply(Path(sys.argv[1]))
    print("\n".join(out["lines"]))
