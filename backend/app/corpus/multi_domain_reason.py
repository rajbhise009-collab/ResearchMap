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
                    [--dry-run] [--max-per-claim 2] [--threshold 0.80]
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
from backend.app.extraction.spend_gate import (  # noqa: E402
    CLASSIFICATION_GATE_MULT,
    OVERRUN_FACTOR,
    OverrunMonitor,
    SpendGateRefused,
    preflight,
)
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


def _embedding_cache_path(slug: str) -> Path:
    return _reason_dir(slug) / "claim_embeddings.json"


# Documented shortlist settings for the multi-domain libraries
# (docs/findings/multi-domain.md §7: tightened from 0.72/4 to 0.80/2).
# The single source for every runner in this package.
LIBRARY_THRESHOLD = 0.80
LIBRARY_MAX_PER_CLAIM = 2

# Classification projection per pair (input tokens observed ~250-350; output
# incl. thinking from pricing.OUT_TOKENS_PAIR).
IN_TOKENS_PAIR = 300


def projected_inr_per_pair() -> float:
    return cost(IN_TOKENS_PAIR, OUT_TOKENS_PAIR, batch=False) * 84.0


# Number of claims embedded by the API in the most recent compute_shortlist
# call (cache misses). Embedding calls are ledgered by GeminiEmbeddingClient.
LAST_EMBED_STATS: dict = {}


def compute_shortlist(exts: list[PaperExtraction], *,
                       threshold: float = LIBRARY_THRESHOLD,
                       max_per_claim: int = LIBRARY_MAX_PER_CLAIM,
                       use_real_embeddings: bool = True,
                       slug: str | None = None,
                       embed_client=None) -> list:
    """Embed claims → cosine shortlist. With `slug`, real vectors are
    cached per claim (keyed by claim id + text hash) under the library's
    reasoning dir so only NEW claims hit the embedding API. If the real
    client fails we raise rather than silently fall back to mock vectors —
    a mock shortlist would look like a real one."""
    ids, texts, paper = _flat_claims(exts)
    if not ids:
        return []
    import numpy as np
    if not use_real_embeddings:
        vecs = MockEmbeddingClient().embed(texts)
        LAST_EMBED_STATS.update({"embedded": 0, "cached": 0, "mock": len(ids)})
    else:
        cache: dict[str, list[float]] = {}
        cp = _embedding_cache_path(slug) if slug else None
        if cp and cp.exists():
            cache = json.loads(cp.read_text())
        keys = [_claim_seed(i, t) for i, t in zip(ids, texts)]
        missing = [k for k in dict.fromkeys(keys) if k not in cache]
        if missing:
            text_by_key = dict(zip(keys, texts))
            client = embed_client or GeminiEmbeddingClient(
                stage=f"embed_{slug or 'claims'}")
            new = client.embed([text_by_key[k] for k in missing])
            cache.update({k: [round(x, 6) for x in v] for k, v in zip(missing, new)})
            if cp:
                cp.parent.mkdir(parents=True, exist_ok=True)
                cp.write_text(json.dumps(cache))
        LAST_EMBED_STATS.update({"embedded": len(missing),
                                 "cached": len(set(keys)) - len(missing), "mock": 0})
        vecs = [cache[k] for k in keys]
    arr = np.asarray(vecs, dtype=np.float32)
    return shortlist_pairs(ids, arr, paper,
                            threshold=threshold, max_per_claim=max_per_claim,
                            cross_paper_only=True)


def dry_run(slug: str, *, threshold: float = LIBRARY_THRESHOLD,
             max_per_claim: int = LIBRARY_MAX_PER_CLAIM) -> dict:
    """Project contradiction-pass cost without any LLM call."""
    exts = load_extractions(slug)
    pairs = compute_shortlist(exts, threshold=threshold,
                                max_per_claim=max_per_claim,
                                use_real_embeddings=False)  # mock in dry-run
    # Real embeddings are cheaper than the mock hash version's spread; a
    # dry-run projection using MockEmbeddingClient over-projects pair
    # count (typical), so cost projection is upper-bound rather than
    # exact. The real run will produce fewer / more relevant pairs.
    proj_in = len(pairs) * IN_TOKENS_PAIR
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


_VERDICT_FILES = {"contradicts": "contradictions.json",
                  "supports": "supports.json", "none": "nones.json"}


def _verdict_log_path(slug: str) -> Path:
    return _reason_dir(slug) / "verdicts.jsonl"


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b)


def load_classified_keys(slug: str) -> set[tuple[str, str]]:
    """Every pair that has already been paid for: the three verdict files,
    failures.json, and the append-only verdict log."""
    d = _reason_dir(slug)
    keys: set[tuple[str, str]] = set()
    for name in list(_VERDICT_FILES.values()):
        p = d / name
        if p.exists():
            for it in json.loads(p.read_text()).get("items", []):
                keys.add(_pair_key(it.get("from_claim_id"), it.get("to_claim_id")))
    lp = _verdict_log_path(slug)
    if lp.exists():
        for line in lp.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                keys.add(_pair_key(r["from_claim_id"], r["to_claim_id"]))
    return keys


def _append_verdict(slug: str, rec: dict) -> None:
    """Durably append one verdict the moment it is returned."""
    import os
    lp = _verdict_log_path(slug)
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def materialize_verdicts(slug: str) -> dict:
    """Fold the verdict log into contradictions/supports/nones/failures
    JSON. Existing items are kept first and never overwritten; dedup by
    pair key. Idempotent."""
    d = _reason_dir(slug)
    files = {rel: d / name for rel, name in _VERDICT_FILES.items()}
    files["fail"] = d / "failures.json"
    current: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for rel, p in files.items():
        items = json.loads(p.read_text()).get("items", []) if p.exists() else []
        current[rel] = items
        for it in items:
            if "from_claim_id" in it:
                seen.add(_pair_key(it["from_claim_id"], it["to_claim_id"]))
            elif "pair" in it:
                seen.add(_pair_key(*it["pair"]))
    lp = _verdict_log_path(slug)
    if lp.exists():
        for line in lp.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            k = _pair_key(r["from_claim_id"], r["to_claim_id"])
            if k in seen:
                continue
            seen.add(k)
            rel = r.get("relationship", "none")
            item = {kk: vv for kk, vv in r.items() if kk not in ("relationship", "ts")}
            current["fail" if rel == "fail" else (rel if rel in _VERDICT_FILES else "none")].append(item)
    for rel, p in files.items():
        p.write_text(json.dumps({"n": len(current[rel]), "items": current[rel]}, indent=2))
    return {rel: len(v) for rel, v in current.items()}


def classify_pairs(slug: str, exts: list[PaperExtraction], pairs: list,
                    *, halt_on_first_fail: bool = False, llm=None,
                    max_inr: float | None = None,
                    projected_inr_per_call: float | None = None,
                    overrun_factor: float = OVERRUN_FACTOR,
                    gate: bool = True) -> dict:
    """Classify each NOT-yet-classified pair once. Every verdict (and every
    paid failure) is appended to verdicts.jsonl as soon as it returns, so a
    crash or kill loses at most the in-flight call and a restart never
    re-pays for a saved pair.

    Before any call (when `gate`): the projection for the unseen pairs is
    recorded and the stage is refused if projection x2 exceeds the ledger's
    remaining ceiling (spend_gate.preflight). Halts on: spend cap, daily
    quota, `max_inr` of new spend in this call, or running cost per call
    exceeding projection x overrun_factor."""
    domain_name = DOMAINS[slug].name
    if llm is None:
        llm = GeminiLLMClient(validate_model=False)
        llm.set_run_context(stage=f"contradiction_{slug}",
                            est_output_tokens=OUT_TOKENS_PAIR)
    text_by_id: dict[str, tuple[str, str]] = {}
    for e in exts:
        for c in (e.claims or []):
            text_by_id[c.id] = (e.paper_id, c.text)

    done = load_classified_keys(slug)
    todo = [p for p in pairs if _pair_key(p.from_claim_id, p.to_claim_id) not in done]
    stats = Counter({"skipped_already_classified": len(pairs) - len(todo)})
    per_call = projected_inr_per_call or projected_inr_per_pair()
    t0 = time.time()
    if gate and todo:
        try:
            preflight(stage=f"contradiction_{slug}",
                      projected_inr=per_call * len(todo), n_calls=len(todo),
                      multiplier=CLASSIFICATION_GATE_MULT)
        except SpendGateRefused as refused:
            print(f"[reason:{slug}] REFUSED — {refused}", flush=True)
            return {"slug": slug, "elapsed_s": 0.0, "stats": dict(stats),
                    "n_todo": len(todo), "halted": f"gate refused: {refused}",
                    "run_inr": 0.0, "file_counts": None}
    ledger = SpendLedger.load()
    start_inr = ledger.snapshot()["cumulative_inr"]
    monitor = OverrunMonitor(per_call, factor=overrun_factor, ledger=ledger)
    halted = None
    try:
        for i, p in enumerate(todo, 1):
            spent = ledger.snapshot()["cumulative_inr"] - start_inr
            if max_inr is not None and spent >= max_inr:
                halted = f"run budget ₹{max_inr:.2f} reached"
                break
            over = monitor.check(stats["calls"])
            if over:
                halted = over
                break
            a_pid, a_text = text_by_id[p.from_claim_id]
            b_pid, b_text = text_by_id[p.to_claim_id]
            prompt = PAIR_PROMPT_MULTI.format(
                domain_name=domain_name,
                a_paper_id=a_pid, a_text=a_text,
                b_paper_id=b_pid, b_text=b_text,
            )
            base = {"from_claim_id": p.from_claim_id, "to_claim_id": p.to_claim_id,
                    "similarity": p.similarity,
                    "a_paper_id": a_pid, "a_text": a_text,
                    "b_paper_id": b_pid, "b_text": b_text, "ts": time.time()}
            try:
                raw = llm.generate(prompt)
            except SpendCapExceededError as e_cap:
                halted = f"spend cap: {e_cap}"
                break
            except DailyQuotaError:
                halted = "daily quota"
                break
            except Exception as e_pair:  # noqa: BLE001
                # Not logged: no response was received, so nothing paid is
                # being thrown away; a restart may retry it.
                stats["call_error"] += 1
                if halt_on_first_fail:
                    halted = f"call error: {type(e_pair).__name__}"
                    break
                continue
            stats["calls"] += 1
            try:
                data = json.loads(raw)
                rel = str(data.get("relationship", "")).lower()
                explanation = str(data.get("explanation", ""))[:400]
            except (json.JSONDecodeError, AttributeError):
                _append_verdict(slug, {**base, "relationship": "fail",
                                       "reason": "json_decode", "detail": raw[:200]})
                stats["fail"] += 1
                continue
            rel = rel if rel in _VERDICT_FILES else "none"
            _append_verdict(slug, {**base, "relationship": rel,
                                   "explanation": explanation})
            stats[rel] += 1
            if i % 25 == 0:
                print(f"[reason:{slug}] [{i}/{len(todo)}] "
                      f"contra={stats['contradicts']} sup={stats['supports']} "
                      f"none={stats['none']} fail={stats['fail']} — "
                      f"run ₹{ledger.snapshot()['cumulative_inr'] - start_inr:.2f}",
                      flush=True)
    finally:
        counts = materialize_verdicts(slug)
    spent = ledger.snapshot()["cumulative_inr"] - start_inr
    if halted:
        print(f"[reason:{slug}] HALT — {halted}", flush=True)
    return {"slug": slug, "elapsed_s": time.time() - t0, "stats": dict(stats),
            "n_todo": len(todo), "halted": halted, "run_inr": spent,
            "file_counts": counts}


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
    p.add_argument("--threshold", type=float, default=LIBRARY_THRESHOLD)
    p.add_argument("--max-per-claim", type=int, default=LIBRARY_MAX_PER_CLAIM)
    p.add_argument("--mock-embeddings", action="store_true",
                   help="use MockEmbeddingClient (free, deterministic; not "
                        "semantic — for smoke tests)")
    args = p.parse_args()

    if args.dry_run:
        print(json.dumps(dry_run(args.domain, threshold=args.threshold,
                                   max_per_claim=args.max_per_claim),
                         indent=2))
        return 0

    args.domain = DOMAINS[args.domain].slug   # normalise short slug -> full
    exts = load_extractions(args.domain)
    if not exts:
        print(f"[reason:{args.domain}] no extractions found — "
              f"run extraction first")
        return 1
    pairs = compute_shortlist(exts, threshold=args.threshold,
                                max_per_claim=args.max_per_claim,
                                use_real_embeddings=not args.mock_embeddings,
                                slug=args.domain)
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
