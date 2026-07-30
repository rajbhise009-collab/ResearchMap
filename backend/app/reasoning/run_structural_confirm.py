"""LLM-confirm the structural-hole leads (bounded, ~12 calls).

For each lead: does cluster-A's method plausibly ADDRESS cluster-B's stated
limitation, and is the resulting direction NON-TRIVIAL? Classification only
— no scoring, no ranking. Leads that reduce to "run a larger evaluation" or
"apply method X to dataset Y" are flagged `trivial` (valid pairing, fails
the actionability/non-triviality bars in docs/opportunity-criteria.md).

  --dry-run  count leads + projected cost, gate $0.25.
  --run      batch-classify, write confirmations, print survivors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.extraction import pricing  # noqa: E402
from backend.app.reasoning import scorers as S  # noqa: E402
from backend.app.reasoning.corpus_view import load_reasoning_corpus  # noqa: E402

OUT = REPO_ROOT / "data" / "reasoning" / "structural_hole_confirmations.json"
GATE = 0.25

PROMPT = """\
You are judging a proposed method-transfer research direction. Paper A uses \
a method; Paper B — a different, weakly-connected line of work — states an \
open own-work limitation. Decide whether A's method plausibly ADDRESSES B's \
limitation and whether the resulting direction is NON-TRIVIAL and \
ACTIONABLE. Classification only; do not rank or score.

Return STRICT JSON:
{"verdict": "substantive" | "trivial" | "not_addressing", "reason": "<one sentence>"}

- "substantive": A's method plausibly addresses B's limitation AND the \
direction is non-trivial (names a specific object of study; not merely \
"evaluate on more data" or "apply an existing method to another dataset").
- "trivial": the pairing is valid but reduces to "run a larger/broader \
evaluation" or "apply method X to dataset/task Y" — fails actionability / \
non-triviality.
- "not_addressing": A's method does not actually address B's limitation \
(topical adjacency only, or different construct).

Paper A ("<<A_TITLE>>") method: <<METHOD>> — <<METHOD_CLAIMS>>
Paper B ("<<B_TITLE>>") limitation: <<LIMITATION>>
"""


def _prompt_hash() -> str:
    return hashlib.sha256(PROMPT.encode()).hexdigest()[:12]


def _leads():
    corpus = load_reasoning_corpus()
    opps = S.score_structural_holes(corpus)   # default k=8, capped 12
    lim_by_id = {l.id: l for l, _p in corpus.own_limitations}
    title = {p: corpus.papers[p].title for p in corpus.papers}
    rows = []
    for o in opps:
        a_pid, b_pid, lim_id = o.evidence_trail[0], o.evidence_trail[1], o.evidence_trail[2]
        method = o.title.split("'")[1] if "'" in o.title else "(method)"
        mclaims = [c.text for c in corpus._loaded.extractions[a_pid].claims
                   if c.type == "method"][:3]
        lim = lim_by_id.get(lim_id)
        rows.append({
            "id": o.id, "a_pid": a_pid, "b_pid": b_pid,
            "a_title": title.get(a_pid, "?"), "b_title": title.get(b_pid, "?"),
            "method": method, "method_claims": " | ".join(mclaims),
            "limitation": lim.text if lim else "?", "sim": o.component_scores["semantic_similarity"],
        })
    return rows


def _prompt(r):
    return (PROMPT.replace("<<A_TITLE>>", r["a_title"][:80])
            .replace("<<B_TITLE>>", r["b_title"][:80])
            .replace("<<METHOD>>", r["method"])
            .replace("<<METHOD_CLAIMS>>", r["method_claims"][:400])
            .replace("<<LIMITATION>>", r["limitation"][:300]))


def dry_run() -> int:
    rows = _leads()
    in_tok = sum(len(_prompt(r)) // 3 for r in rows)
    out_tok = len(rows) * pricing.OUT_TOKENS_PAIR
    cost = pricing.cost(in_tok, out_tok, batch=True)
    print(f"structural-hole leads to confirm: {len(rows)}")
    print(f"projected (BATCH, thinking-corrected): {in_tok:,} in + {out_tok:,} out "
          f"-> ${cost:.4f} | gate ${GATE:.2f}")
    print("Under gate — cleared to --run." if cost <= GATE else "*** OVER GATE ***")
    return 0 if cost <= GATE else 2


def run() -> int:
    from backend.app.extraction.batch_client import GeminiBatchClient
    rows = _leads()
    reqs = {r["id"]: _prompt(r) for r in rows}
    client = GeminiBatchClient(model_name=get_settings().gemini_model)
    bid = client.submit(reqs, display_name="researchmap-hole-confirm")
    print(f"[batch] submitted {len(reqs)} leads id={bid}", flush=True)
    job = client.wait(bid, poll_interval_s=20)
    if not job.succeeded:
        print(f"[batch] failed: {job.state}", file=sys.stderr)
        return 1
    results = client.results(job)
    conf = {}
    counts = Counter()
    ph = _prompt_hash()
    by_id = {r["id"]: r for r in rows}
    for oid, raw in results.items():
        try:
            d = json.loads(raw)
            v = str(d["verdict"]).strip().lower()
            reason = str(d.get("reason", "")).strip()
        except Exception:
            v, reason = "malformed", ""
        if v not in ("substantive", "trivial", "not_addressing"):
            v = "malformed"
        counts[v] += 1
        conf[oid] = {"verdict": v, "reason": reason, "prompt_hash": ph,
                     "detector_model": f"gemini:{get_settings().gemini_model}",
                     "a_pid": by_id[oid]["a_pid"], "b_pid": by_id[oid]["b_pid"],
                     "method": by_id[oid]["method"], "limitation": by_id[oid]["limitation"]}
    OUT.write_text(json.dumps(conf, indent=2))
    print(f"[confirm] {dict(counts)}")
    print(f"[confirm] SUBSTANTIVE survivors: {counts['substantive']}/{len(rows)}")
    for oid, c in conf.items():
        if c["verdict"] == "substantive":
            print(f"  ✓ {c['method']} -> {c['limitation'][:70]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.dry_run:
        return dry_run()
    if a.run:
        return run()
    print("specify --dry-run | --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
