"""Print every flagged disagreement of a library with both claims and both
source abstracts, for the hand audit (genuine | artifact | duplicate).

  .venv/bin/python tools/qa/audit_pairs.py <library-slug> [--unaudited]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    slug = sys.argv[1]
    d = ROOT / "data" / "domains" / slug
    items = json.loads((d / "reasoning" / "contradictions.json").read_text())["items"]
    pre = {f"openalex:{e['wid']}": e for e in json.loads((d / "prelabelled.json").read_text())["entries"]}
    done = set()
    ap = d / "reasoning" / "contradiction_audit.json"
    if ap.exists() and "--unaudited" in sys.argv:
        for v in json.loads(ap.read_text())["verdicts"]:
            done.add((v["a_paper_id"], v["b_paper_id"], v["a_text_starts"][:40]))
    for i, it in enumerate(items, 1):
        if (it["a_paper_id"], it["b_paper_id"], it["a_text"][:40]) in done:
            continue
        a, b = pre.get(it["a_paper_id"], {}), pre.get(it["b_paper_id"], {})
        print(f"=== PAIR {i} (similarity {it.get('similarity', 0):.2f}) ===")
        for side, p, txt in (("A", a, it["a_text"]), ("B", b, it["b_text"])):
            print(f"[{side}] {it[side.lower() + '_paper_id']} | {p.get('title')} ({p.get('year')})")
            print(f"    CLAIM: {txt}")
            print(f"    ABSTRACT: {(p.get('abstract') or '(none)')[:900]}")
        print(f"    CLASSIFIER: {it.get('explanation', '')[:300]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
