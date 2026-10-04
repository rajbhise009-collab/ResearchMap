"""Second diet expert-review packet: v1's 12 items unchanged + items 13-14.

Output: docs/review/diet-contradictions-v2/ (packet.md, packet.html,
response_form.csv, recruitment-message.md). The frozen v1 packet in
docs/review/diet-contradictions/ is READ, never written.

- Items 01-12 are copied byte-for-byte from the v1 packet.md (same text,
  same neutral IDs, same order).
- Items 13-14 are two additional pairs taken from reasoning/audit_doubts.json,
  rendered with v1's own item formatter. Which earlier item each repeats,
  and their seeded order, are recorded only in the private key.
- The answer key goes OUTSIDE the repo, to a NEW file
  (default ~/ResearchMap-private/answer_key_v2.json, override with
  --key-out / PACKET_KEY_DIR). v1's answer_key.json and README.md are
  never written. This module never calls v1's build_packet() (which would
  overwrite them).

    python -m backend.app.review.build_diet_packet_v2
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.api.contradiction_audit import attach_verdicts  # noqa: E402
from backend.app.review.build_diet_packet import (  # noqa: E402
    DIET_REASONING, RESPONSE_OPTIONS, _html_packet, _load_papers_index, _md_item,
    _pair_to_item, _response_form_csv,
)

V1_DIR = REPO_ROOT / "docs" / "review" / "diet-contradictions"
OUT_DIR = REPO_ROOT / "docs" / "review" / "diet-contradictions-v2"
SEED_V2 = int(os.environ.get("PACKET_SEED_V2", "20261004"))
_DEFAULT_PRIVATE = Path(os.environ.get("PACKET_KEY_DIR",
                                       str(Path.home() / "ResearchMap-private")))
KEY_NAME = "answer_key_v2.json"


def v1_item_blocks(md: str | None = None) -> list[str]:
    """The 12 '## Item NN' blocks of the frozen v1 packet, verbatim."""
    md = md if md is not None else (V1_DIR / "packet.md").read_text()
    starts = [m.start() for m in re.finditer(r"^## Item \d\d$", md, flags=re.M)]
    return [md[s:e] for s, e in zip(starts, starts[1:] + [len(md)])]


def doubted_items() -> list[dict]:
    """Audit rows 1 and 5 as packet items (same shape as v1 items)."""
    doubts = json.loads((DIET_REASONING / "audit_doubts.json").read_text())["items"]
    raw = json.loads((DIET_REASONING / "contradictions.json").read_text())["items"]
    audited = attach_verdicts("diet-and-mortality", raw)
    papers = _load_papers_index()
    out = []
    for d in doubts:
        match = [c for c in audited
                 if {c["a_paper_id"], c["b_paper_id"]} == {d["a_paper_id"], d["b_paper_id"]}
                 and c["audit"]["verdict"] == "genuine"]
        if len(match) != 1:
            raise RuntimeError(f"audit pair {d['audit_pair']}: {len(match)} matching flags")
        it = _pair_to_item(match[0], papers, provenance="genuine-doubted")
        it["audit_pair"] = d["audit_pair"]
        it["doubt"] = d["text"]
        out.append(it)
    return out


def _header() -> str:
    return "\n".join([
        "# ResearchMap — diet-and-mortality contradiction review (second packet)",
        "",
        "**Target time:** 35 minutes or less. **What we're asking:** for "
        "each of the 14 item pairs below, does the pair genuinely conflict "
        "(same kind of people, exposure, outcome, and comparable study "
        "design), or is the apparent conflict an artifact of different "
        "conditions?",
        "",
        "## What ResearchMap is",
        "",
        "ResearchMap is a prototype tool that reads a small collection of "
        "papers on one subject and flags pairs whose primary findings look "
        "like they disagree. It is not peer review, not clinical guidance, "
        "and not a settled resolution of anything — it is a discovery aid "
        "that shortlists candidate disagreements a human still has to check.",
        "",
        "The items below are a mix of pairs the tool flagged as "
        "contradictions AND controls (pairs it marked as consistent or "
        "orthogonal on the same topics). Items 01–12 are the same as in our "
        "first packet. Items 13 and 14 repeat two of the earlier pairs; "
        "please judge every item on its own, without looking back at your "
        "earlier answer.",
        "",
        "## How to respond",
        "",
        "Fill the `response_form.csv` template with one row per item. Or "
        "reply inline in this markdown. Either way, please note whether "
        "you want acknowledgement by name in the write-up, or prefer to "
        "stay anonymous.",
        "",
        "---",
        "",
        "",
    ])


def _recruitment() -> str:
    return (
        "Subject: 35-minute blind review of AI-flagged research disagreements\n\n"
        "Hi [FIRST_NAME],\n\n"
        "I've been building a prototype tool that reads a collection of "
        "papers on one subject and flags pairs whose primary findings "
        "look like they disagree. It's not peer review, not clinical "
        "guidance — it's a discovery aid whose output still needs a "
        "human to check.\n\n"
        "I have 14 pairs from a small library on diet and mortality "
        "(red meat, alcohol and related questions). Some are pairs the "
        "tool flagged as contradictions; others are controls it marked as "
        "consistent or orthogonal on the same topics. You wouldn't be told "
        "which is which. Two pairs appear twice.\n\n"
        "The ask: for each pair, tell me whether the two findings "
        "genuinely conflict (comparable people, exposure, outcome, and "
        "study design) or whether the apparent conflict is an artifact "
        "of different conditions. Target time is 35 minutes or less, "
        "with a small CSV response form.\n\n"
        "If you'd like to see the packet, reply and I'll send it as an "
        "attachment. You can respond by name or anonymously — please "
        "say which you prefer.\n\n"
        "[YOUR_NAME]\n"
        "[YOUR_AFFILIATION]\n"
    )


def build(out_dir: Path = OUT_DIR, key_out_dir: Path = _DEFAULT_PRIVATE,
          seed: int = SEED_V2, v1_key_path: Path | None = None) -> dict:
    blocks = v1_item_blocks()
    assert len(blocks) == 12, f"v1 packet has {len(blocks)} items, expected 12"
    extra = doubted_items()
    random.Random(seed).shuffle(extra)
    v1_key_path = v1_key_path or (key_out_dir / "answer_key.json")
    v1_items = json.loads(v1_key_path.read_text())["items"]
    # Blind-ordering rule added for repeats: an item may not sit directly
    # after its own twin (item 13 must not repeat item 12). If the seeded
    # order breaks that, swap 13 and 14.
    def _twin(it):
        return [k["item_id"] for k in v1_items
                if {k["a_paper_id"], k["b_paper_id"]} == {it["a_paper_id"], it["b_paper_id"]}]
    if "item-12" in _twin(extra[0]):
        extra.reverse()
    md = _header() + "".join(blocks)
    if not md.endswith("\n"):
        md += "\n"
    md += "".join(_md_item(13 + i, it) for i, it in enumerate(extra))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "packet.md").write_text(md)
    (out_dir / "packet.html").write_text(
        _html_packet(md).replace("diet contradictions review", "diet contradictions review (second packet)"))
    (out_dir / "response_form.csv").write_text(_response_form_csv([None] * 14))
    (out_dir / "recruitment-message.md").write_text(_recruitment())

    key_items = [dict(it) for it in v1_items]
    for i, it in enumerate(extra):
        repeats = [k["item_id"] for k in v1_items
                   if {k["a_paper_id"], k["b_paper_id"]} == {it["a_paper_id"], it["b_paper_id"]}]
        key_items.append({
            "item_id": f"item-{13 + i:02d}", "provenance": it["provenance"],
            "audit_verdict": it["audit_verdict"], "audit_reason": it["audit_reason"],
            "a_paper_id": it["a_paper_id"], "b_paper_id": it["b_paper_id"],
            "audit_pair": it["audit_pair"], "doubt": it["doubt"],
            "repeats_v1_item": repeats[0] if len(repeats) == 1 else repeats,
        })
    key = {"DO_NOT_SHARE_WITH_REVIEWERS": True, "packet": "diet-contradictions-v2",
           "seed_v2": seed, "items_01_12": "copied from answer_key.json (v1), unchanged",
           "items": key_items}
    key_out_dir.mkdir(parents=True, exist_ok=True)
    (key_out_dir / KEY_NAME).write_text(json.dumps(key, indent=2))
    readme = key_out_dir / "README_v2.md"
    readme.write_text(
        "# DO NOT SHARE — answer key for the SECOND diet review packet\n\n"
        "answer_key_v2.json maps docs/review/diet-contradictions-v2/ items to\n"
        "their provenance. Items 01-12 are identical to v1 (answer_key.json);\n"
        "items 13-14 repeat two v1 items (see repeats_v1_item).\n\n"
        "    python -m backend.app.review.score_responses \\\n"
        "        --responses path/to/response.csv \\\n"
        "        --key ~/ResearchMap-private/answer_key_v2.json\n")
    return {"n_items": 14, "out_dir": str(out_dir),
            "key": str(key_out_dir / KEY_NAME)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=SEED_V2)
    p.add_argument("--key-out", type=Path, default=_DEFAULT_PRIVATE)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    a = p.parse_args()
    print(json.dumps(build(out_dir=a.out_dir, key_out_dir=a.key_out, seed=a.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
