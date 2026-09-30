"""Score reviewer responses against the diet-contradiction audit key.

Reports:
- Per-item agreement (audit verdict vs reviewer verdict, per reviewer).
- Overall agreement %.
- Over-calling rate on controls: how often the reviewer said
  "genuine disagreement" on pairs that the classifier itself already
  labelled `supports` or `none`. This is the safety-relevant miscall.
- Cohen's kappa when 2+ reviewers respond to the same item.

CLI:
    python -m backend.app.review.score_responses \\
        --responses path/to/response_form.csv [more.csv ...] \\
        --key      docs/review/diet-contradictions/_answer_key_DO_NOT_SHARE/answer_key.json \\
        --out      docs/review/diet-contradictions/scored.md

Never sends anything anywhere.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


# Reviewer verdict → normalised label used in scoring
NORMALISE = {
    "genuine": "genuine_conflict",
    "genuine_conflict": "genuine_conflict",
    "yes": "genuine_conflict",
    "conditions": "not_conflict",
    "differ_in_conditions": "not_conflict",
    "different_conditions": "not_conflict",
    "consistent": "not_conflict",
    "no": "not_conflict",
    "cant_tell": "cant_tell",
    "can't tell": "cant_tell",
    "unsure": "cant_tell",
    "": "blank",
}

# Audit verdict → what a reviewer SHOULD say if they agree with the audit
AUDIT_TO_REVIEWER = {
    "genuine": "genuine_conflict",
    "artifact": "not_conflict",
    # Controls (provenance="control") come from the classifier's
    # supports/none pool; the "should" answer is "not_conflict"
    # regardless of the audit_verdict slot.
}


def _normalise(v: str) -> str:
    return NORMALISE.get((v or "").strip().lower(), (v or "").strip().lower())


def load_responses(paths: List[Path]) -> Dict[str, List[Tuple[str, str, str]]]:
    """Returns item_id → list of (reviewer, verdict, reason) tuples.
    Reviewer defaults to the CSV filename if the reviewer_name column
    is blank/anon."""
    out: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
    for p in paths:
        with p.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                item_id = row.get("item_id", "").strip()
                if not item_id:
                    continue
                verdict = _normalise(row.get("verdict", ""))
                reason = (row.get("one_line_reason") or "").strip()
                reviewer = ((row.get("reviewer_name_or_blank_for_anon") or "").strip()
                            or f"anon:{p.stem}")
                out[item_id].append((reviewer, verdict, reason))
    return out


def _expected_answer(item: dict) -> str:
    """The 'should' answer for scoring against the audit. Controls
    should be 'not_conflict' regardless of the audit slot."""
    if item.get("provenance") == "control":
        return "not_conflict"
    return AUDIT_TO_REVIEWER.get(item.get("audit_verdict"), "not_conflict")


def cohens_kappa(pairs: List[Tuple[str, str]]) -> float | None:
    """Two-rater Cohen's kappa over the same set of items. `pairs` is a
    list of (reviewer1_verdict, reviewer2_verdict). Returns None when
    fewer than 5 pair-observations (kappa on 4 items is noise)."""
    if len(pairs) < 5:
        return None
    labels = sorted({p for pair in pairs for p in pair})
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n
    marg_a = Counter(a for a, _ in pairs)
    marg_b = Counter(b for _, b in pairs)
    pe = sum((marg_a[l] / n) * (marg_b[l] / n) for l in labels)
    return None if pe >= 1.0 else (po - pe) / (1.0 - pe)


def score(responses: Dict[str, List[Tuple[str, str, str]]],
           key_path: Path) -> dict:
    key = json.loads(key_path.read_text())
    by_item = {it["item_id"]: it for it in key["items"]}

    reviewers = set()
    for rs in responses.values():
        for reviewer, _, _ in rs:
            reviewers.add(reviewer)

    per_reviewer: Dict[str, dict] = {r: {
        "agree": 0, "disagree": 0, "blank": 0, "cant_tell": 0,
        "overcall_on_controls": 0, "n_control": 0, "items": {},
    } for r in reviewers}

    overall_agree = overall_answered = 0

    for item_id, item in by_item.items():
        expected = _expected_answer(item)
        for reviewer, verdict, reason in responses.get(item_id, []):
            b = per_reviewer[reviewer]
            b["items"][item_id] = {"reviewer": verdict, "expected": expected,
                                     "reason": reason}
            if verdict == "blank":
                b["blank"] += 1
                continue
            if verdict == "cant_tell":
                b["cant_tell"] += 1
                continue
            overall_answered += 1
            if verdict == expected:
                b["agree"] += 1
                overall_agree += 1
            else:
                b["disagree"] += 1
            if item.get("provenance") == "control":
                b["n_control"] += 1
                if verdict == "genuine_conflict":
                    b["overcall_on_controls"] += 1

    # Cohen's kappa pairwise between reviewers
    kappas = {}
    revs = sorted(reviewers)
    for i, r1 in enumerate(revs):
        for r2 in revs[i + 1:]:
            shared = []
            for item_id in by_item:
                v1 = next((v for rev, v, _ in responses.get(item_id, [])
                            if rev == r1 and v not in ("blank", "cant_tell")), None)
                v2 = next((v for rev, v, _ in responses.get(item_id, [])
                            if rev == r2 and v not in ("blank", "cant_tell")), None)
                if v1 and v2:
                    shared.append((v1, v2))
            k = cohens_kappa(shared)
            kappas[f"{r1} vs {r2}"] = {"n_shared_items": len(shared),
                                          "kappa": k}

    return {
        "n_items": len(by_item),
        "n_reviewers": len(reviewers),
        "overall_agreement":
            (overall_agree / overall_answered) if overall_answered else None,
        "overall_answered": overall_answered,
        "per_reviewer": per_reviewer,
        "cohens_kappa": kappas,
    }


def _render_md(scored: dict) -> str:
    L = ["# Reviewer scoring", ""]
    L.append(f"- Reviewers: **{scored['n_reviewers']}**")
    L.append(f"- Items in packet: **{scored['n_items']}**")
    L.append(f"- Total answered items: {scored['overall_answered']}")
    if scored["overall_agreement"] is not None:
        L.append(f"- Overall agreement with audit: "
                 f"**{scored['overall_agreement']*100:.0f}%**")
    L.append("")
    L.append("## Per reviewer")
    for reviewer, b in scored["per_reviewer"].items():
        answered = b["agree"] + b["disagree"]
        L.append(f"### {reviewer}")
        if answered:
            L.append(f"- agreement: {b['agree']}/{answered} ({b['agree']/answered*100:.0f}%)")
        L.append(f"- can't tell: {b['cant_tell']}, blank: {b['blank']}")
        if b["n_control"]:
            L.append(f"- over-called on controls: {b['overcall_on_controls']}/"
                     f"{b['n_control']} ({b['overcall_on_controls']/b['n_control']*100:.0f}%)")
        L.append("")
    if scored["cohens_kappa"]:
        L.append("## Cohen's kappa (pairwise, when 5+ shared items)")
        for pair, k in scored["cohens_kappa"].items():
            kv = k["kappa"]
            L.append(f"- {pair} — n={k['n_shared_items']} shared items"
                     + (f", kappa = {kv:.2f}" if kv is not None else " (too few for kappa)"))
    return "\n".join(L) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--responses", nargs="+", type=Path, required=True)
    p.add_argument("--key", type=Path, required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    responses = load_responses(args.responses)
    scored = score(responses, args.key)
    md = _render_md(scored)
    if args.out:
        args.out.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
