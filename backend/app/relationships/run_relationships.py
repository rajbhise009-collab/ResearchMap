"""Phase 3 orchestrator — build the relationship layer.

  --dry-run  Embed all claims + future-work (real embeddings; cheap,
             cached), shortlist candidate pairs, and report the
             CANDIDATE-PAIR COUNT with a projected contradiction cost.
             Gate: $3 on the contradiction spend. No pairwise LLM call.
  --run      Requires a cleared dry-run. Classifies the shortlist via the
             BATCH API (50% off), assembles ClaimRelationship rows
             (deterministic weight), builds the citation graph, matches
             future-work, and persists everything.

Embeddings are a small prerequisite paid call (reported separately); the
$3 gate governs the combinatorial contradiction spend, which is the real
budget risk.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import REPO_ROOT as RR, get_settings  # noqa: E402
from backend.app.relationships import contradiction as C  # noqa: E402
from backend.app.relationships.citation_graph import (  # noqa: E402
    build_citation_graph, fetch_referenced_works,
)
from backend.app.relationships.corpus_loader import load_corpus  # noqa: E402
from backend.app.relationships.embeddings import (  # noqa: E402
    GeminiEmbeddingClient, MockEmbeddingClient,
)
from backend.app.relationships.future_work_match import match_future_work  # noqa: E402
from backend.app.relationships.shortlist import CandidatePair, shortlist_pairs  # noqa: E402
from backend.app.relationships.store import RelationshipStore  # noqa: E402
from backend.app.models import ClaimEmbedding  # noqa: E402

REL_DIR = RR / "data" / "relationships"
FW_VECS = REL_DIR / "future_work.npy"
FW_META = REL_DIR / "future_work_ids.json"
BATCH_STATE = REL_DIR / "contradiction_batch.json"
EDGES_OUT = REL_DIR / "citation_edges.jsonl"
FW_MATCH_OUT = REL_DIR / "future_work_matches.jsonl"

# Rates from the verified pricing module (includes thinking-token
# correction). OUT_PER_PAIR now reflects observed output INCLUDING the
# heavy thinking tokens a reasoning model spends per pair (~360), not the
# old 40 that under-projected the gate ~9x.
from backend.app.extraction.pricing import (  # noqa: E402
    IN_PER_M, OUT_PER_M, BATCH_MULT, OUT_TOKENS_PAIR as OUT_PER_PAIR, cost,
)
EMBED_PER_M = 0.15
GATE = 3.00


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 3)


def _embedder():
    s = get_settings()
    if s.can_use_gemini:
        return GeminiEmbeddingClient()
    print("[warn] no GEMINI_API_KEY — using MOCK embeddings (not semantic).",
          file=sys.stderr)
    return MockEmbeddingClient(dim=s.embedding_dim)


def _ensure_embeddings(corpus, store: RelationshipStore) -> tuple[list[str], object]:
    """Embed claims (cached) + future-work (cached). Returns (claim_ids,
    claim_vectors)."""
    import numpy as np

    claims = corpus.claims()
    have = store.load_embeddings()
    if len(have) == len(claims) and have:
        cids, cvecs = store.load_vectors()
    else:
        emb = _embedder()
        texts = [c.text for c in claims]
        print(f"[embed] embedding {len(texts)} claims via {emb.name} …", flush=True)
        vecs = emb.embed(texts)
        records = [
            ClaimEmbedding(claim_id=c.id, paper_id=corpus.claim_paper[c.id],
                           input_source=corpus.claim_source[c.id],
                           model=emb.name, dim=len(vecs[i]), embedding=vecs[i])
            for i, c in enumerate(claims)
        ]
        store.save_embeddings(records)
        cids, cvecs = store.load_vectors()

    # Future-work embeddings (cached separately).
    fw = corpus.future_work()
    if not (FW_VECS.exists() and FW_META.exists()
            and len(json.loads(FW_META.read_text())) == len(fw)):
        emb = _embedder()
        fw_texts = [item.text for item, _ in fw]
        print(f"[embed] embedding {len(fw_texts)} future-work items …", flush=True)
        fw_vecs = emb.embed(fw_texts)
        REL_DIR.mkdir(parents=True, exist_ok=True)
        np.save(FW_VECS, np.array(fw_vecs, dtype=np.float32))
        FW_META.write_text(json.dumps([item.id for item, _ in fw]))
    return cids, cvecs


def _shortlist(corpus, cids, cvecs):
    s = get_settings()
    return shortlist_pairs(
        cids, cvecs, corpus.claim_paper,
        threshold=s.rel_similarity_threshold,
        max_per_claim=s.rel_max_candidates_per_claim,
        cross_paper_only=s.rel_cross_paper_only,
    )


def _pair_prompt_tokens(corpus, pair: CandidatePair) -> int:
    ct = {c.id: c.text for c in corpus.claims()}
    prompt = C.build_pair_prompt(
        text_a=ct[pair.from_claim_id], text_b=ct[pair.to_claim_id],
        paper_a=corpus.claim_paper[pair.from_claim_id],
        paper_b=corpus.claim_paper[pair.to_claim_id])
    return _estimate_tokens(prompt)


def dry_run() -> int:
    corpus = load_corpus()
    store = RelationshipStore()
    s = get_settings()
    n_claims = corpus.n_claims
    n_fw = len(corpus.future_work())
    embed_tokens = sum(_estimate_tokens(c.text) for c in corpus.claims())
    embed_tokens += sum(_estimate_tokens(fw.text) for fw, _ in corpus.future_work())
    embed_cost = embed_tokens / 1e6 * EMBED_PER_M

    cids, cvecs = _ensure_embeddings(corpus, store)
    candidates = _shortlist(corpus, cids, cvecs)
    in_tokens = sum(_pair_prompt_tokens(corpus, p) for p in candidates)
    out_tokens = len(candidates) * OUT_PER_PAIR
    contradiction_cost = (in_tokens / 1e6 * IN_PER_M
                          + out_tokens / 1e6 * OUT_PER_M) * BATCH_MULT

    print("\n=== RELATIONSHIP-LAYER DRY RUN ===")
    print(f"claims: {n_claims} | future-work items: {n_fw}")
    print(f"embeddings: {embed_tokens:,} tokens → ${embed_cost:.4f} "
          f"(prerequisite, spent to compute the shortlist)")
    print(f"shortlist: threshold={s.rel_similarity_threshold}, "
          f"cap={s.rel_max_candidates_per_claim}/claim, "
          f"cross_paper_only={s.rel_cross_paper_only}")
    print(f"CANDIDATE PAIRS: {len(candidates)}")
    print(f"contradiction (BATCH 50% off): {in_tokens:,} in + {out_tokens:,} out "
          f"→ ${contradiction_cost:.4f}")
    print(f"PROJECTED contradiction spend: ${contradiction_cost:.4f} | gate ${GATE:.2f}")
    if contradiction_cost > GATE:
        print(f"\n*** OVER ${GATE:.2f} GATE — STOP. Raise the similarity "
              f"threshold or lower the per-claim cap. ***")
        return 2
    print(f"\nUnder the ${GATE:.2f} gate — cleared to --run.")
    return 0


def _batch_classify(corpus, candidates, model_name):
    """Classify the shortlist via the batch API. Returns (rels, stats)."""
    from collections import Counter
    from backend.app.extraction.batch_client import GeminiBatchClient, chunk_requests

    ct = {c.id: c.text for c in corpus.claims()}
    ph = C.prompt_hash()
    reqs = {
        f"{p.from_claim_id}|{p.to_claim_id}": C.build_pair_prompt(
            text_a=ct[p.from_claim_id], text_b=ct[p.to_claim_id],
            paper_a=corpus.claim_paper[p.from_claim_id],
            paper_b=corpus.claim_paper[p.to_claim_id])
        for p in candidates
    }
    pair_by_key = {f"{p.from_claim_id}|{p.to_claim_id}": p for p in candidates}
    client = GeminiBatchClient(model_name=get_settings().gemini_model)

    # Persist batch ids BEFORE waiting so a crash after submission is
    # resumable and never re-pays. Reuse a saved batch if present.
    if BATCH_STATE.exists():
        batch_ids = json.loads(BATCH_STATE.read_text())["batch_ids"]
        print(f"[batch] reusing {len(batch_ids)} saved batch(es)", flush=True)
    else:
        batch_ids = [client.submit(chunk, display_name="researchmap-contradiction")
                     for chunk in chunk_requests(reqs)]
        BATCH_STATE.parent.mkdir(parents=True, exist_ok=True)
        BATCH_STATE.write_text(json.dumps({"batch_ids": batch_ids}))
        print(f"[batch] submitted {len(batch_ids)} batch(es), {len(reqs)} pairs",
              flush=True)

    all_results: dict[str, str] = {}
    for bid in batch_ids:
        job = client.wait(bid, poll_interval_s=30)
        if not job.succeeded:
            print(f"[batch] {bid} did not succeed: {job.state}", file=sys.stderr)
            continue
        res = client.results(job)
        print(f"[batch] {bid} returned {len(res)}", flush=True)
        all_results.update(res)

    rels = []
    counts: Counter = Counter()
    for key, raw in all_results.items():
        counts["classified"] += 1
        verdict = C.parse_verdict(raw)
        if verdict is None:
            counts["malformed"] += 1
            continue
        counts[verdict.relationship] += 1
        rel = C.relationship_from_verdict(pair_by_key[key], verdict, corpus,
                                          model_name=model_name, ph=ph)
        if rel is not None:
            rels.append(rel)
    stats = {"candidates": len(candidates), **dict(counts), "persisted": len(rels),
             "prompt_hash": ph}
    return rels, stats


def run() -> int:
    import numpy as np

    corpus = load_corpus()
    store = RelationshipStore()
    s = get_settings()
    model_name = f"gemini:{s.gemini_model}"

    cids, cvecs = _ensure_embeddings(corpus, store)
    candidates = _shortlist(corpus, cids, cvecs)
    print(f"[run] {len(candidates)} candidate pairs")

    # --- Contradiction / support (LLM perception, batch) ---
    rels, cstats = _batch_classify(corpus, candidates, model_name)
    store.save_relationships(rels)
    BATCH_STATE.unlink(missing_ok=True)   # consumed — don't reuse next run
    print(f"[run] relationships: {cstats}")

    # --- Citation graph (free, OpenAlex) ---
    refs = fetch_referenced_works(corpus)
    edges = build_citation_graph(corpus, refs)
    with EDGES_OUT.open("w") as fh:
        for e in edges:
            fh.write(json.dumps({"from_paper_id": e.from_paper_id,
                                 "to_paper_id": e.to_paper_id}) + "\n")
    print(f"[run] citation edges (intra-corpus): {len(edges)}")

    # --- Future-work matching ---
    fw = corpus.future_work()
    fw_ids = json.loads(FW_META.read_text())
    fw_vecs = np.load(FW_VECS)
    matches = match_future_work(
        corpus, fw_ids, fw_vecs, cids, cvecs,
        threshold=s.rel_futurework_match_threshold,
        topical_threshold=s.rel_futurework_topical_threshold,
        min_near_later=s.rel_futurework_min_near_later,
    )
    with FW_MATCH_OUT.open("w") as fh:
        for m in matches:
            fh.write(json.dumps(m.__dict__) + "\n")
    from collections import Counter
    fw_status = Counter(m.status for m in matches)
    print(f"[run] future-work: {dict(fw_status)}")

    # --- Summary ---
    from backend.app.models import RelationshipType
    by_type = Counter(r.type for r in rels)
    summary = {
        "claims": corpus.n_claims,
        "candidate_pairs": len(candidates),
        "relationships_by_type": {str(k): v for k, v in by_type.items()},
        "contradiction_stats": cstats,
        "citation_edges": len(edges),
        "future_work": dict(fw_status),
        "future_work_total": len(matches),
    }
    (REL_DIR / "relationship_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[summary] {json.dumps(summary, indent=2)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        return dry_run()
    if args.run:
        return run()
    print("specify --dry-run | --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
