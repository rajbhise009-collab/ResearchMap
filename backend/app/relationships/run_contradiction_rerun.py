"""Re-run contradiction detection on the corrected corpus with SIBLING
CLAIM CONTEXT (regime-aware v1.1 prompt). Cheap partial for the missing
Claim.condition field: no schema change, no re-extraction.

  --dry-run  shortlist + projected cost (thinking-inclusive), gate $1.
  --run      batch-classify with sibling context, rebuild claim_relationships.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.extraction import pricing  # noqa: E402
from backend.app.relationships import contradiction as C  # noqa: E402
from backend.app.relationships.corpus_loader import load_corpus  # noqa: E402
from backend.app.relationships.shortlist import shortlist_pairs  # noqa: E402
from backend.app.relationships.store import RelationshipStore  # noqa: E402

REL = REPO_ROOT / "data" / "relationships"
STATE = REL / "contradiction_rerun_batch.json"
GATE = 1.00
MAX_SIB = 4


def _prep():
    corpus = load_corpus()
    store = RelationshipStore()
    cids, cvecs = store.load_vectors()
    s = get_settings()
    pairs = shortlist_pairs(cids, cvecs, corpus.claim_paper,
                            threshold=s.rel_similarity_threshold,
                            max_per_claim=s.rel_max_candidates_per_claim,
                            cross_paper_only=s.rel_cross_paper_only)
    ctext = {c.id: c.text for c in corpus.claims()}
    # sibling claims per paper
    sibs: dict[str, list[str]] = {}
    for pid, ext in corpus.extractions.items():
        sibs[pid] = [c.text for c in ext.claims]

    def sib_of(claim_id, paper_id):
        others = [t for t in sibs.get(paper_id, []) if t != ctext.get(claim_id)]
        return " | ".join(others[:MAX_SIB])

    return corpus, store, pairs, ctext, sib_of


def _prompt_for(pair, corpus, ctext, sib_of):
    a, b = pair.from_claim_id, pair.to_claim_id
    pa, pb = corpus.claim_paper[a], corpus.claim_paper[b]
    return C.build_pair_prompt_ctx(
        text_a=ctext[a], text_b=ctext[b], paper_a=pa, paper_b=pb,
        sib_a=sib_of(a, pa), sib_b=sib_of(b, pb))


def dry_run() -> int:
    corpus, store, pairs, ctext, sib_of = _prep()
    in_tok = sum(len(_prompt_for(p, corpus, ctext, sib_of)) // 3 for p in pairs)
    out_tok = len(pairs) * pricing.OUT_TOKENS_PAIR
    cost = pricing.cost(in_tok, out_tok, batch=True)
    print("=== CONTRADICTION RE-RUN DRY RUN (corrected corpus, sibling context) ===")
    print(f"claims: {corpus.n_claims} | candidate pairs (0.78 shortlist): {len(pairs)}")
    print(f"projected (BATCH, thinking-corrected): {in_tok:,} in + {out_tok:,} out "
          f"-> ${cost:.4f} | gate ${GATE:.2f}")
    if cost > GATE:
        print(f"\n*** OVER ${GATE:.2f} GATE — STOP. ***")
        return 2
    print(f"\nUnder ${GATE:.2f} gate — cleared to --run.")
    return 0


def run() -> int:
    from backend.app.extraction.batch_client import GeminiBatchClient, chunk_requests
    corpus, store, pairs, ctext, sib_of = _prep()
    model_name = f"gemini:{get_settings().gemini_model}"
    ph = C.prompt_hash_v11()
    reqs = {f"{p.from_claim_id}|{p.to_claim_id}": _prompt_for(p, corpus, ctext, sib_of)
            for p in pairs}
    by_key = {f"{p.from_claim_id}|{p.to_claim_id}": p for p in pairs}
    client = GeminiBatchClient(model_name=get_settings().gemini_model)
    if STATE.exists():
        batch_ids = json.loads(STATE.read_text())["batch_ids"]
        print(f"[batch] reusing {len(batch_ids)} saved batch(es)")
    else:
        batch_ids = [client.submit(ch, display_name="researchmap-contradiction-rerun")
                     for ch in chunk_requests(reqs)]
        STATE.write_text(json.dumps({"batch_ids": batch_ids}))
        print(f"[batch] submitted {len(reqs)} pairs")
    results: dict[str, str] = {}
    for bid in batch_ids:
        job = client.wait(bid, poll_interval_s=30)
        if job.succeeded:
            results.update(client.results(job))
    rels, counts = [], Counter()
    for key, raw in results.items():
        counts["classified"] += 1
        v = C.parse_verdict(raw)
        if v is None:
            counts["malformed"] += 1
            continue
        counts[v.relationship] += 1
        rel = C.relationship_from_verdict(by_key[key], v, corpus,
                                          model_name=model_name, ph=ph)
        if rel is not None:
            rels.append(rel)
    store.save_relationships(rels)
    STATE.unlink(missing_ok=True)
    print(f"[run] verdicts: {dict(counts)}")
    print(f"[run] persisted relationships: {len(rels)} "
          f"(contradicts={counts['contradicts']}, supports={counts['supports']})")
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
