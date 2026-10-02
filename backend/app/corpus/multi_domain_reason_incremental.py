"""Incremental contradiction classifier: classify ONLY unseen pairs.

Loads existing contradictions.json / supports.json / nones.json for the
slug, computes the shortlist on the current (possibly larger) extraction
set, filters out pairs already classified, calls the LLM on the
remainder only, and merges the new verdicts back into the JSONs.

Preserves every existing verdict exactly. Never re-classifies an audited
pair.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.app.corpus.multi_domain_reason import (
    _reason_dir, compute_shortlist, load_extractions, classify_pairs,
)


def _load_seen_pairs(slug: str) -> set[tuple[str, str]]:
    """Pair key = (from_claim_id, to_claim_id), order-stable. Union of
    all three verdict files."""
    seen: set[tuple[str, str]] = set()
    d = _reason_dir(slug)
    for name in ("contradictions.json", "supports.json", "nones.json"):
        p = d / name
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        for item in data.get("items", []):
            k = (item.get("from_claim_id"), item.get("to_claim_id"))
            seen.add(k)
    return seen


def _merge_results(slug: str, new_result: dict) -> None:
    """Union new verdicts into the three on-disk JSON files. Existing
    entries are kept — never overwritten by this incremental pass."""
    out_dir = _reason_dir(slug)
    for name in ("contradictions.json", "supports.json", "nones.json"):
        p = out_dir / name
        existing = json.loads(p.read_text()) if p.exists() else {"items": []}
        existing_keys = {(it.get("from_claim_id"), it.get("to_claim_id"))
                         for it in existing.get("items", [])}
        # Pull the matching new items. classify_pairs wrote its own
        # files already — load them, filter to not-already-present, append.
        new_file = out_dir / name
        new_data = json.loads(new_file.read_text()) if new_file.exists() else {"items": []}
        appended = 0
        for it in new_data.get("items", []):
            k = (it.get("from_claim_id"), it.get("to_claim_id"))
            if k in existing_keys:
                continue
            existing.setdefault("items", []).append(it)
            existing_keys.add(k)
            appended += 1
        existing["n"] = len(existing["items"])
        p.write_text(json.dumps(existing, indent=2))


def run(slug: str, *, threshold: float = 0.72,
         max_per_claim: int = 4) -> dict:
    """Return summary dict with counts."""
    exts = load_extractions(slug)
    all_pairs = compute_shortlist(
        exts, threshold=threshold, max_per_claim=max_per_claim,
        use_real_embeddings=True)
    seen = _load_seen_pairs(slug)
    new_pairs = [p for p in all_pairs
                 if (p.from_claim_id, p.to_claim_id) not in seen]
    stats = {
        "slug": slug,
        "n_extractions": len(exts),
        "n_total_shortlist_pairs": len(all_pairs),
        "n_already_classified_pairs": len(all_pairs) - len(new_pairs),
        "n_new_pairs_to_classify": len(new_pairs),
    }
    if not new_pairs:
        print(f"[reason-incr:{slug}] no new pairs — nothing to classify.")
        return stats
    print(f"[reason-incr:{slug}] {len(new_pairs)} new pairs "
          f"(of {len(all_pairs)} total)")

    # Backup existing files so we can restore after classify_pairs
    # (which overwrites with ONLY the new-pair results).
    d = _reason_dir(slug)
    backup = {}
    for name in ("contradictions.json", "supports.json", "nones.json",
                  "failures.json"):
        p = d / name
        if p.exists():
            backup[name] = json.loads(p.read_text())

    cls_result = classify_pairs(slug, exts, new_pairs)
    # classify_pairs wrote the NEW pair results — merge with backups.
    for name, old in backup.items():
        if name == "failures.json":
            # append new failures
            new = json.loads((d / name).read_text()) if (d / name).exists() else {"items": []}
            merged_items = old.get("items", []) + new.get("items", [])
            (d / name).write_text(json.dumps({
                "n": len(merged_items), "items": merged_items}, indent=2))
            continue
        new = json.loads((d / name).read_text()) if (d / name).exists() else {"items": []}
        merged_items = old.get("items", []) + new.get("items", [])
        (d / name).write_text(json.dumps({
            "n": len(merged_items), "items": merged_items}, indent=2))

    stats.update(cls_result)
    return stats


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--slug", choices=["diet-and-mortality", "ml-fairness"],
                    required=True)
    p.add_argument("--threshold", type=float, default=0.72)
    p.add_argument("--max-per-claim", type=int, default=4)
    args = p.parse_args()
    r = run(args.slug, threshold=args.threshold,
             max_per_claim=args.max_per_claim)
    print(json.dumps(r, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
