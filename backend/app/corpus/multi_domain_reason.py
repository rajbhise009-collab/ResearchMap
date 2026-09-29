"""Multi-domain reasoning — the minimum pipeline that answers the
per-domain findings questions from CLAUDE.md § "How you work":

  1. Load a domain's extractions (from data/domains/<slug>/extractions/).
  2. Compute claim embeddings (Gemini text-embedding-004; free-tier is
     tiny — kept off the ledger since it's a different model with
     different pricing and negligible cost, see docstring below).
  3. Shortlist cross-paper claim pairs by cosine (reuses the LLM-cal
     shortlist code) with a domain-configurable per-claim cap.
  4. LLM-classify each shortlisted pair as contradicts / supports / none
     using the same PAIR_PROMPT the LLM-cal library used. Every call is
     GATED BY THE SPEND LEDGER.
  5. Report per-domain: confirmed contradictions (count + examples),
     supports count, none count. Also compute assertion-strength
     firm/hedged distribution from the extractions (no LLM call).
  6. Persist `data/domains/<slug>/reasoning/{contradictions,supports,
     none,summary}.json`.

CLI:
    python -m backend.app.corpus.multi_domain_reason --domain diet
                    [--dry-run] [--max-per-claim 4] [--threshold 0.72]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.corpus.multi_domain import DOMAINS as _DOMAINS_SHORT  # noqa: E402

# The multi_domain module keys the DOMAINS dict by short slug (`diet`,
# `fairness`) with the full slug in the config. This module accepts
# either form for convenience.
DOMAINS = dict(_DOMAINS_SHORT)
DOMAINS.update({cfg.slug: cfg for cfg in _DOMAINS_SHORT.values()})
from backend.app.extraction.cache import ExtractionCache  # noqa: E402
from backend.app.extraction.llm_client import (  # noqa: E402
    DailyQuotaError,
    GeminiLLMClient,
)
from backend.app.extraction.pricing import OUT_TOKENS_PAIR, cost  # noqa: E402
from backend.app.extraction.prompt_versions import latest_version, load  # noqa: E402
from backend.app.extraction.spend_ledger import (  # noqa: E402
    SpendCapExceededError,
    SpendLedger,
)
from backend.app.models import PaperExtraction  # noqa: E402
from backend.app.relationships.embeddings import (  # noqa: E402
    GeminiEmbeddingClient,
    MockEmbeddingClient,
)
from backend.app.relationships.shortlist import shortlist_pairs  # noqa: E402


PAIR_PROMPT_MULTI = """\
You are comparing two scientific claims, each from a different paper on \
{domain_name}. Decide the relationship between them. Judge ONLY these \
two claims — do not rank, score, or rate importance.

Return STRICT JSON, no prose:
{{"relationship": "contradicts" | "supports" | "none", "explanation": "<one sentence>"}}

Definitions:
- "contradicts": the two claims cannot both be true about the same \
construct.
- "supports": the two claims independently assert the same or a \
mutually reinforcing finding.
- "none": same topic but neither contradicting nor supporting.

Beware terminology collisions: the same word can mean different \
constructs in different papers — that is "none", not a contradiction.

---

Claim A (from paper {a_paper_id}): {a_text}
Claim B (from paper {b_paper_id}): {b_text}
"""


def _extractions_dir(slug: str) -> Path:
    return REPO_ROOT / "data" / "domains" / slug / "extractions"


def _reason_dir(slug: str) -> Path:
    return REPO_ROOT / "data" / "domains" / slug / "reasoning"


def load_extractions(slug: str) -> list[PaperExtraction]:
    """Load every extraction for a domain from the shared cache. Uses
    the domain's prelabelled entries to know which paper ids to look up.
    Skips papers without cached extractions."""
    from backend.app.corpus.multi_domain import _prelabel_path
    cache = ExtractionCache()
    prompt_hash = load(latest_version()).hash
    payload = json.loads(_prelabel_path(DOMAINS[slug]).read_text())
    out = []
    for e in payload["entries"]:
        # Cache key uses `openalex:W...`; prelabelled entries store
        # openalex_id as the URL form `https://openalex.org/W...` which
        # would hash to a different directory.
        pid = f"openalex:{e['wid']}"
        for src in ("fulltext", "abstract"):
            ext = cache.get(pid, "gemini:gemini-3.6-flash", src, prompt_hash)
            if ext is not None:
                out.append(ext)
                break
    return out


def _claim_seed(claim_id: str, text: str) -> str:
    """Stable key for embedding cache lookups within a run (unused now
    — reserved for future disk caching of vectors)."""
    return hashlib.sha1(f"{claim_id}|{text}".encode()).hexdigest()[:16]


def _flat_claims(exts: list[PaperExtraction]) -> tuple[list[str], list[str], dict[str, str]]:
    """(claim_ids, claim_texts, claim_paper) — one row per claim, order-
    stable. Skips empty-text claims."""
    ids: list[str] = []
    texts: list[str] = []
    paper: dict[str, str] = {}
    for e in exts:
        for c in (e.claims or []):
            if not c.text or not c.text.strip():
                continue
            ids.append(c.id)
            texts.append(c.text)
            paper[c.id] = e.paper_id
    return ids, texts, paper


def compute_shortlist(exts: list[PaperExtraction], *,
                       threshold: float = 0.72,
                       max_per_claim: int = 4,
                       use_real_embeddings: bool = True) -> list:
    """Embed all claims → cosine shortlist. Free (real embeddings ~$0.02
    for 100 papers) or offline (Mock, deterministic hashes)."""
    ids, texts, paper = _flat_claims(exts)
    if not ids:
        return []
    import numpy as np
    if use_real_embeddings:
        try:
            embed = GeminiEmbeddingClient()
            vecs = embed.embed(texts)
        except Exception as e:  # noqa: BLE001
            print(f"[reason] embedding failed ({e}); falling back to Mock",
                  flush=True)
            embed = MockEmbeddingClient()
            vecs = embed.embed(texts)
    else:
        embed = MockEmbeddingClient()
        vecs = embed.embed(texts)
    arr = np.asarray(vecs, dtype=np.float32)
    return shortlist_pairs(ids, arr, paper,
                            threshold=threshold, max_per_claim=max_per_claim,
                            cross_paper_only=True)


def dry_run(slug: str, *, threshold: float = 0.72,
             max_per_claim: int = 4) -> dict:
    """Project contradiction-pass cost without any LLM call."""
    exts = load_extractions(slug)
    pairs = compute_shortlist(exts, threshold=threshold,
                                max_per_claim=max_per_claim,
                                use_real_embeddings=False)  # mock in dry-run
    # Real embeddings are cheaper than the mock hash version's spread; a
    # dry-run projection using MockEmbeddingClient over-projects pair
    # count (typical), so cost projection is upper-bound rather than
    # exact. The real run will produce fewer / more relevant pairs.
    IN_PAIR = 300     # observed ~250-350 tokens per pair prompt
    proj_in = len(pairs) * IN_PAIR
    proj_out = len(pairs) * OUT_TOKENS_PAIR
    proj_usd = cost(proj_in, proj_out, batch=False)
    return {
        "slug": slug,
        "n_extractions": len(exts),
        "n_claims": sum(len(e.claims or []) for e in exts),
        "n_pair_candidates_estimate": len(pairs),
        "proj_input_tokens": proj_in,
        "proj_output_tokens": proj_out,
        "proj_cost_usd": proj_usd,
        "proj_cost_inr": proj_usd * 84.0,
        "shortlist_settings": {"threshold": threshold,
                                 "max_per_claim": max_per_claim},
    }


def classify_pairs(slug: str, exts: list[PaperExtraction], pairs: list,
                    *, halt_on_first_fail: bool = False) -> dict:
    """Call the LLM once per pair. Gated by SpendLedger at call time.
    Persists results incrementally so a halt keeps partial output."""
    domain_name = DOMAINS[slug].name
    llm = GeminiLLMClient(validate_model=False)
    llm.set_run_context(stage=f"contradiction_{slug}", est_output_tokens=OUT_TOKENS_PAIR)
    text_by_id: dict[str, tuple[str, str]] = {}
    for e in exts:
        for c in (e.claims or []):
            text_by_id[c.id] = (e.paper_id, c.text)

    out_dir = _reason_dir(slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    contradictions: list[dict] = []
    supports: list[dict] = []
    nones: list[dict] = []
    fails: list[dict] = []
    stats = Counter()
    t0 = time.time()
    for i, p in enumerate(pairs, 1):
        a_pid, a_text = text_by_id[p.from_claim_id]
        b_pid, b_text = text_by_id[p.to_claim_id]
        prompt = PAIR_PROMPT_MULTI.format(
            domain_name=domain_name,
            a_paper_id=a_pid, a_text=a_text,
            b_paper_id=b_pid, b_text=b_text,
        )
        try:
            raw = llm.generate(prompt)
        except SpendCapExceededError as e_cap:
            stats["halted_spend_cap"] += 1
            print(f"[reason:{slug}] HALT — spend cap at pair {i}/{len(pairs)}: "
                  f"{e_cap}", flush=True)
            break
        except DailyQuotaError:
            stats["halted_daily_quota"] += 1
            print(f"[reason:{slug}] HALT — daily quota", flush=True)
            break
        except Exception as e_pair:  # noqa: BLE001
            fails.append({"pair": (p.from_claim_id, p.to_claim_id),
                          "reason": type(e_pair).__name__,
                          "detail": str(e_pair)[:200]})
            stats["fail"] += 1
            if halt_on_first_fail:
                break
            continue
        try:
            data = json.loads(raw)
            rel = data.get("relationship", "").lower()
            explanation = str(data.get("explanation", ""))[:400]
        except json.JSONDecodeError:
            fails.append({"pair": (p.from_claim_id, p.to_claim_id),
                          "reason": "json_decode", "detail": raw[:200]})
            stats["fail"] += 1
            continue
        rec = {
            "from_claim_id": p.from_claim_id, "to_claim_id": p.to_claim_id,
            "similarity": p.similarity,
            "a_paper_id": a_pid, "a_text": a_text,
            "b_paper_id": b_pid, "b_text": b_text,
            "explanation": explanation,
        }
        if rel == "contradicts":
            contradictions.append(rec); stats["contradicts"] += 1
        elif rel == "supports":
            supports.append(rec); stats["supports"] += 1
        else:
            nones.append(rec); stats["none"] += 1
        if i % 25 == 0 or i == len(pairs):
            snap = SpendLedger.load().snapshot()
            print(f"[reason:{slug}] [{i}/{len(pairs)}] contra={stats['contradicts']} "
                  f"sup={stats['supports']} none={stats['none']} fail={stats['fail']} "
                  f"— cum ₹{snap['cumulative_inr']:.2f}/₹{snap['cap_inr']:.0f}",
                  flush=True)

    (out_dir / "contradictions.json").write_text(json.dumps({
        "n": len(contradictions), "items": contradictions}, indent=2))
    (out_dir / "supports.json").write_text(json.dumps({
        "n": len(supports), "items": supports}, indent=2))
    (out_dir / "nones.json").write_text(json.dumps({
        "n": len(nones), "items": nones}, indent=2))
    (out_dir / "failures.json").write_text(json.dumps({
        "n": len(fails), "items": fails}, indent=2))
    return {"slug": slug, "elapsed_s": time.time() - t0,
            "stats": dict(stats),
            "contradiction_examples": contradictions[:5]}


def assertion_strength_distribution(exts: list[PaperExtraction]) -> dict:
    """Count firm vs hedged claims across a domain's extractions. Uses
    the lexical hedge classifier from `multi_domain_findings.is_hedged`
    — the v1.1.0 prompt doesn't emit an assertion_strength field, so
    this is a post-hoc heuristic aligned with the schema-pressure-test
    91% baseline (docs/schema-pressure-test.md §2)."""
    from backend.app.corpus.multi_domain_findings import is_hedged
    counter = Counter()
    for e in exts:
        for c in (e.claims or []):
            counter["hedged" if is_hedged(c.text) else "firm"] += 1
    total = sum(counter.values())
    return {"total_claims": total, "distribution": dict(counter),
            "firm_share": counter.get("firm", 0) / total if total else 0.0,
            "hedged_share": counter.get("hedged", 0) / total if total else 0.0}


def gap_type_counts(exts: list[PaperExtraction]) -> dict:
    """Deterministic counts of the raw signal each Phase-4 scorer builds
    from — no LLM. Persistent-limitations reads limitations grouped by
    normalized_category; orphaned-future-work is total future-work items
    unresolved (a full Phase-4 scorer needs a citation graph — see
    docs — but the raw counts give an honest per-domain summary)."""
    limitations_by_cat = defaultdict(set)
    fw_items = 0
    for e in exts:
        for l in (e.limitations or []):
            cat = getattr(l, "normalized_category", None) or "uncategorized"
            limitations_by_cat[cat].add(e.paper_id)
        fw_items += len(e.future_work or [])
    return {
        "n_papers": len(exts),
        "n_limitations": sum(len(v) for v in limitations_by_cat.values()),
        "limitation_categories": {
            k: len(v) for k, v in sorted(
                limitations_by_cat.items(), key=lambda x: -len(x[1])
            )
        },
        "n_future_work_items": fw_items,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domain", choices=sorted(DOMAINS), required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--threshold", type=float, default=0.72)
    p.add_argument("--max-per-claim", type=int, default=4)
    p.add_argument("--mock-embeddings", action="store_true",
                   help="use MockEmbeddingClient (free, deterministic; not "
                        "semantic — for smoke tests)")
    args = p.parse_args()

    if args.dry_run:
        print(json.dumps(dry_run(args.domain, threshold=args.threshold,
                                   max_per_claim=args.max_per_claim),
                         indent=2))
        return 0

    exts = load_extractions(args.domain)
    if not exts:
        print(f"[reason:{args.domain}] no extractions found — "
              f"run extraction first")
        return 1
    pairs = compute_shortlist(exts, threshold=args.threshold,
                                max_per_claim=args.max_per_claim,
                                use_real_embeddings=not args.mock_embeddings)
    result = classify_pairs(args.domain, exts, pairs)
    stats = assertion_strength_distribution(exts)
    gap = gap_type_counts(exts)
    summary = {"contradiction_run": result,
               "assertion_strength": stats,
               "gap_type_counts": gap,
               "ledger": SpendLedger.load().snapshot()}
    (_reason_dir(args.domain) / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
