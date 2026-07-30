"""Two-stage future-work matcher runner.

  --dry-run  Shortlist candidates, report the count, project the LLM cost
             with CORRECTED thinking-token pricing. Gate: $1.
  --run      Batch-classify each candidate, persist FutureWorkAddressal
             rows with provenance + citation prior, and report the new
             addressed / partial / unaddressed / indeterminate distribution
             (with the small-corpus guard + corpus-relative caveat).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.extraction import pricing  # noqa: E402
from backend.app.relationships import future_work_llm as F  # noqa: E402
from backend.app.relationships.citation_graph import CitationEdge  # noqa: E402
from backend.app.relationships.corpus_loader import load_corpus  # noqa: E402
from backend.app.relationships.store import RelationshipStore  # noqa: E402

REL_DIR = REPO_ROOT / "data" / "relationships"
BATCH_STATE = REL_DIR / "fw_addr_batch.json"
GATE = 1.00


def _load_inputs():
    corpus = load_corpus()
    store = RelationshipStore()
    cids, cvecs = store.load_vectors()
    fw_ids = json.loads((store.root / "future_work_ids.json").read_text())
    fw_vecs = np.load(store.root / "future_work.npy")
    edges = [CitationEdge(**json.loads(l)) for l in
             (store.root / "citation_edges.jsonl").read_text().splitlines() if l.strip()]
    return corpus, store, cids, cvecs, fw_ids, fw_vecs, edges


def _candidates(corpus, cids, cvecs, fw_ids, fw_vecs, edges):
    s = get_settings()
    return F.shortlist_candidates(
        corpus, fw_ids, fw_vecs, cids, cvecs, edges,
        shortlist_threshold=0.70, max_papers_per_fw=4,
    )


def dry_run() -> int:
    corpus, store, cids, cvecs, fw_ids, fw_vecs, edges = _load_inputs()
    cands = _candidates(corpus, cids, cvecs, fw_ids, fw_vecs, edges)
    fw_text = {fw.id: fw.text for fw, _ in corpus.future_work()}
    in_tok = sum(len(F.build_prompt(c, fw_text[c.fw_id])) // 3 for c in cands)
    out_tok = len(cands) * pricing.OUT_TOKENS_PAIR
    cost = pricing.cost(in_tok, out_tok, batch=True)
    fws_with_cands = len({c.fw_id for c in cands})
    cites = sum(1 for c in cands if c.cites_source)
    print("=== FUTURE-WORK TWO-STAGE DRY RUN ===")
    print(f"future-work items: {len(fw_ids)} | with >=1 candidate: {fws_with_cands}")
    print(f"candidate pairs (shortlist 0.70, cap 4/item): {len(cands)}")
    print(f"  of which the later paper cites the source (citation prior): {cites}")
    print(f"projected LLM cost (BATCH, thinking-token corrected): "
          f"{in_tok:,} in + {out_tok:,} out -> ${cost:.4f} | gate ${GATE:.2f}")
    if cost > GATE:
        print(f"\n*** OVER ${GATE:.2f} GATE — lower max_papers_per_fw. ***")
        return 2
    print(f"\nUnder the ${GATE:.2f} gate — cleared to --run.")
    return 0


def _classify(cands, fw_text, model_name):
    from backend.app.extraction.batch_client import GeminiBatchClient, chunk_requests
    reqs = {f"{c.fw_id}||{c.to_paper_id}": F.build_prompt(c, fw_text[c.fw_id])
            for c in cands}
    by_key = {f"{c.fw_id}||{c.to_paper_id}": c for c in cands}
    client = GeminiBatchClient(model_name=get_settings().gemini_model)
    if BATCH_STATE.exists():
        batch_ids = json.loads(BATCH_STATE.read_text())["batch_ids"]
        print(f"[batch] reusing {len(batch_ids)} saved batch(es)", flush=True)
    else:
        batch_ids = [client.submit(ch, display_name="researchmap-fw-addr")
                     for ch in chunk_requests(reqs)]
        BATCH_STATE.write_text(json.dumps({"batch_ids": batch_ids}))
        print(f"[batch] submitted {len(reqs)} pairs", flush=True)
    results: dict[str, str] = {}
    for bid in batch_ids:
        job = client.wait(bid, poll_interval_s=30)
        if job.succeeded:
            results.update(client.results(job))
        else:
            print(f"[batch] {bid} failed: {job.state}", file=sys.stderr)
    ph = F.prompt_hash()
    rows, counts = [], Counter()
    for key, raw in results.items():
        c = by_key[key]
        v = F.parse_verdict(raw)
        counts["classified"] += 1
        if v is None:
            counts["malformed"] += 1
            continue
        label, just, elem = v
        counts[label] += 1
        rows.append(F.to_addressal(c, label, just, elem, model_name=model_name, ph=ph))
    return rows, counts


def _distribution(corpus, store, fw_ids, fw_vecs, cids, cvecs, addressals):
    """Per-item label combining LLM verdicts with the small-corpus guard."""
    s = get_settings()
    paper_year = {pid: m.year for pid, m in corpus.papers.items()}
    claim_year = np.array([paper_year.get(corpus.claim_paper.get(c)) or -1 for c in cids])
    cvec = np.asarray(cvecs, dtype=np.float32)
    fw_meta = {fw.id: meta for fw, meta in corpus.future_work()}
    by_fw: dict[str, set[str]] = {}
    for a in addressals:
        by_fw.setdefault(a.future_work_id, set()).add(a.label)

    dist = Counter()
    for i, fw_id in enumerate(fw_ids):
        meta = fw_meta[fw_id]
        labels = by_fw.get(fw_id, set())
        if "addressed" in labels:
            dist["addressed"] += 1
            continue
        if "partial" in labels:
            dist["partial"] += 1
            continue
        # No (full/partial) address -> small-corpus guard decides.
        sy = meta.year
        near = 0
        if sy is not None:
            sims = cvec @ np.asarray(fw_vecs[i], dtype=np.float32)
            later = claim_year > sy
            if later.any():
                idx = np.where(later)[0]
                near = len({corpus.claim_paper.get(cids[int(k)])
                            for k in idx if sims[k] >= s.rel_futurework_topical_threshold})
        dist["unaddressed" if near >= s.rel_futurework_min_near_later
             else "indeterminate_small_corpus"] += 1
    return dist


def run() -> int:
    corpus, store, cids, cvecs, fw_ids, fw_vecs, edges = _load_inputs()
    cands = _candidates(corpus, cids, cvecs, fw_ids, fw_vecs, edges)
    fw_text = {fw.id: fw.text for fw, _ in corpus.future_work()}
    model_name = f"gemini:{get_settings().gemini_model}"
    print(f"[run] {len(cands)} candidate pairs")

    addressals, counts = _classify(cands, fw_text, model_name)
    store.save_addressals(addressals)
    BATCH_STATE.unlink(missing_ok=True)
    print(f"[run] verdicts: {dict(counts)}")

    dist = _distribution(corpus, store, fw_ids, fw_vecs, cids, cvecs, addressals)
    n = len(fw_ids)
    print(f"[run] item distribution (n={n}): {dict(dist)}")
    summary = {
        "future_work_items": n,
        "candidate_pairs": len(cands),
        "verdict_counts": dict(counts),
        "item_distribution": dict(dist),
        "citation_prior_candidates": sum(1 for c in cands if c.cites_source),
        "matcher": "two-stage (cosine 0.70 shortlist -> LLM classify) + citation prior",
    }
    (REL_DIR / "future_work_addressal_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
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
