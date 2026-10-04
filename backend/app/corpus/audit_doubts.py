"""Audit doubts — recorded, plain-language, never a verdict change.

  python -m backend.app.corpus.audit_doubts      # writes reasoning/audit_doubts.json per library

Diet: two hand-audit verdicts the builder now doubts (iteration 4). They
stay "genuine" on the site; they are sent to a second expert packet.
ML fairness: classifier verdicts made at iteration 3's looser shortlist
settings; counted from data (verdicts whose pair is not in the current
shortlist). Free; never embeds (cache only).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

DOMAINS = REPO_ROOT / "data" / "domains"

# Audit row numbers (1-based, contradiction_audit.json order) + reason.
DIET_DOUBTS = {
    1: ("one paper reports no link while the other gives a risk per 100 g a "
        "day — the same kind of difference in how results were measured that "
        "got the triglyceride pair set aside."),
    5: ("one paper is about unprocessed red meat and the other about red meat "
        "in general, which may not be the same exposure."),
}


def diet() -> dict:
    a = json.loads((DOMAINS / "diet-and-mortality" / "reasoning"
                    / "contradiction_audit.json").read_text())["verdicts"]
    items = []
    for n, reason in DIET_DOUBTS.items():
        v = a[n - 1]
        items.append({"audit_pair": n, "topic": v["topic"], "verdict": v["verdict"],
                      "a_paper_id": v["a_paper_id"], "b_paper_id": v["b_paper_id"],
                      "text": (f"We doubt our own \"disagreement\" verdict on {v['topic']}: "
                               f"{reason} The verdict is unchanged and the pair has been "
                               "sent for expert review.")})
    return {"slug": "diet-and-mortality", "items": items}


def fairness() -> dict:
    from backend.app.corpus import multi_domain_reason as R

    class _Refuse:
        def embed(self, texts):
            raise RuntimeError("would embed; refusing (free script)")

    slug = "ml-fairness"
    exts = R.load_extractions(slug)
    pairs = R.compute_shortlist(exts, slug=slug, embed_client=_Refuse())
    shortlist = {(p.from_claim_id, p.to_claim_id) for p in pairs}
    rd = DOMAINS / slug / "reasoning"
    outside = {"contradicts": 0, "supports": 0, "none": 0}
    looser = 0
    for rel, f in (("contradicts", "contradictions.json"), ("supports", "supports.json"),
                   ("none", "nones.json")):
        for it in json.loads((rd / f).read_text())["items"]:
            if (it["from_claim_id"], it["to_claim_id"]) not in shortlist:
                outside[rel] += 1
                looser += (it.get("similarity") or 0) < R.LIBRARY_THRESHOLD
    n = sum(outside.values())
    rest = n - looser
    dis = ("none of them is a disagreement" if outside["contradicts"] == 0
           else f"{outside['contradicts']} of them are disagreements")
    return {"slug": slug, "outside_shortlist": outside, "below_threshold": looser, "items": [{
        "n_verdicts": n,
        "text": (f"{n} of this library's classifier verdicts are for pairs outside the ones "
                 f"we report: {looser} were made with a looser matching setting than the "
                 "library's documented one (similarity below 0.80; iteration 3 ran at 0.72 "
                 f"with up to 4 matches per claim), and {rest} no longer rank among each "
                 f"claim's top 2 matches. {dis[0].upper() + dis[1:]}, and none is counted."),
    }]}


def main() -> int:
    for d in (diet(), fairness()):
        p = DOMAINS / d["slug"] / "reasoning" / "audit_doubts.json"
        p.write_text(json.dumps(d, indent=2) + "\n")
        for it in d["items"]:
            print(f"{d['slug']}: {it['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
