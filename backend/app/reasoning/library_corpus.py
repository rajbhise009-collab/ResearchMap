"""ReasoningCorpus for a multi-domain library (diet-and-mortality,
ml-fairness), so the same Phase-4 scorers that run on LLM calibration can
run on it. Nothing here calls an LLM.

Built from local files only:
  papers           data/domains/<slug>/prelabelled.json (merges applied)
  extractions      the shared extraction cache (merged losers unioned)
  first authors    raw OpenAlex records in snowball.json (authorships)
  citation edges   snowball.json `referenced_works`, kept when both ends are
                   in the library (a merged loser's id maps to its survivor)
  claim vectors    reasoning/claim_embeddings.json (cache from the
                   disagreement check; refuses to embed anything)
  fw vectors       reasoning/fw_embeddings.json — the only paid input;
                   `embed_future_work()` fills it (cached, gated, ledgered)
  addressals       reasoning/fw_addressals.jsonl (two-stage matcher output)

Contradictions are left empty on purpose: the library's disagreement cards
and their hand audit are produced elsewhere and must not change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from backend.app.config import REPO_ROOT
from backend.app.models import FutureWorkAddressal
from backend.app.reasoning.corpus_view import PaperInfo, ReasoningCorpus
from backend.app.relationships.corpus_loader import LoadedCorpus, PaperMeta

DOMAINS = REPO_ROOT / "data" / "domains"


def _dir(slug: str) -> Path:
    return DOMAINS / slug / "reasoning"


def fw_cache_path(slug: str) -> Path:
    return _dir(slug) / "fw_embeddings.json"


def addressals_path(slug: str) -> Path:
    return _dir(slug) / "fw_addressals.jsonl"


def _fw_key(fw_id: str, text: str) -> str:
    return f"{fw_id}|{hashlib.sha256(text.encode()).hexdigest()[:12]}"


def _wid(x: str) -> str:
    return (x or "").rsplit("/", 1)[-1].split(":")[-1]


def load_loaded_corpus(slug: str) -> LoadedCorpus:
    from backend.app.corpus import multi_domain_reason as R
    pre = json.loads((DOMAINS / slug / "prelabelled.json").read_text())
    papers: dict[str, PaperMeta] = {}
    for e in pre["entries"]:
        pid = f"openalex:{e['wid']}"
        papers[pid] = PaperMeta(
            paper_id=pid, openalex_id=e.get("openalex_id"), title=e.get("title"),
            year=e.get("year"), doi=e.get("doi"),
            input_source="fulltext" if e.get("input_source") == "fulltext" else "abstract",
            domain_centrality=e.get("domain_centrality", "core"), provenance="snowball")
    exts = {x.paper_id: x for x in R.load_extractions(slug) if x.paper_id in papers}
    lc = LoadedCorpus(papers=papers, extractions=exts)
    for pid, ext in exts.items():
        for c in ext.claims:
            lc.claim_paper[c.id] = pid
            lc.claim_source[c.id] = papers[pid].input_source
    return lc


def _authors_and_edges(slug: str, lc: LoadedCorpus):
    pre = json.loads((DOMAINS / slug / "prelabelled.json").read_text())
    alias = {}
    for e in pre["entries"]:
        alias[e["wid"]] = e["wid"]
        for m in e.get("merged_from", []):
            alias[_wid(m)] = e["wid"]
    snow = json.loads((DOMAINS / slug / "snowball.json").read_text())
    first: dict[str, str | None] = {}
    edges: set[tuple[str, str]] = set()
    for r in snow["records"] + snow.get("rejected_records", []):
        w = _wid(r.get("id", ""))
        if w not in alias:
            continue
        src = f"openalex:{alias[w]}"
        auth = r.get("authorships") or []
        if src not in first and auth:
            first[src] = ((auth[0] or {}).get("author") or {}).get("display_name")
        for ref in r.get("referenced_works") or []:
            t = alias.get(_wid(ref))
            if t and t != alias[w]:
                edges.add((src, f"openalex:{t}"))
    return first, edges


def claim_vectors(slug: str, lc: LoadedCorpus) -> tuple[list[str], np.ndarray]:
    from backend.app.corpus import multi_domain_reason as R
    cache = json.loads(R._embedding_cache_path(slug).read_text())
    ids, vecs, missing = [], [], 0
    for pid in sorted(lc.extractions):
        for c in lc.extractions[pid].claims:
            k = R._claim_seed(c.id, c.text)
            if k not in cache:
                missing += 1
                continue
            ids.append(c.id)
            vecs.append(cache[k])
    if missing:
        raise RuntimeError(f"{missing} claims have no cached embedding in {slug}; "
                           "refusing to embed here (free builder)")
    v = np.asarray(vecs, dtype=np.float32)
    v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
    return ids, v


def future_work_texts(lc: LoadedCorpus) -> list[tuple[str, str]]:
    return [(fw.id, fw.text) for fw, _m in lc.future_work()]


def embed_future_work(slug: str, *, dry_run: bool, client=None) -> dict:
    """Embed future-work items not yet cached. Projection x1.5 gated; every
    chunk is ledgered by the embedding client; cache written after each
    chunk so a restart never re-pays."""
    from backend.app.extraction.rate_limiter import estimate_tokens
    from backend.app.extraction.spend_gate import EXTRACTION_GATE_MULT, preflight
    from backend.app.extraction.spend_ledger import EMBED_IN_PER_M, FX_USD_TO_INR
    lc = load_loaded_corpus(slug)
    items = future_work_texts(lc)
    p = fw_cache_path(slug)
    cache = json.loads(p.read_text()) if p.exists() else {}
    todo = [(i, t) for i, t in items if _fw_key(i, t) not in cache]
    est = sum(estimate_tokens(t) for _i, t in todo)
    proj = est * EMBED_IN_PER_M / 1e6 * FX_USD_TO_INR
    out = {"slug": slug, "items": len(items), "cached": len(items) - len(todo),
           "to_embed": len(todo), "est_tokens": est, "projected_inr": round(proj, 4)}
    if dry_run or not todo:
        return out
    preflight(stage=f"embed_fw_{slug}", projected_inr=proj, n_calls=len(todo),
              multiplier=EXTRACTION_GATE_MULT)
    if client is None:
        from backend.app.relationships.embeddings import GeminiEmbeddingClient
        client = GeminiEmbeddingClient(stage=f"embed_fw_{slug}")
    step = getattr(client, "BATCH", 100)
    for k in range(0, len(todo), step):
        chunk = todo[k:k + step]
        vecs = client.embed([t for _i, t in chunk])
        for (i, t), v in zip(chunk, vecs):
            cache[_fw_key(i, t)] = [round(float(x), 6) for x in v]
        p.write_text(json.dumps(cache))          # saved as it returns
    out["embedded"] = len(todo)
    return out


def fw_vectors(slug: str, lc: LoadedCorpus) -> tuple[list[str], np.ndarray | None]:
    p = fw_cache_path(slug)
    if not p.exists():
        return [], None
    cache = json.loads(p.read_text())
    ids, vecs = [], []
    for i, t in future_work_texts(lc):
        k = _fw_key(i, t)
        if k in cache:
            ids.append(i)
            vecs.append(cache[k])
    if not vecs:
        return [], None
    v = np.asarray(vecs, dtype=np.float32)
    v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
    return ids, v


def load_addressals(slug: str) -> list[FutureWorkAddressal]:
    p = addressals_path(slug)
    if not p.exists():
        return []
    return [FutureWorkAddressal.model_validate_json(l) for l in p.read_text().splitlines() if l.strip()]


def load_library_corpus(slug: str) -> ReasoningCorpus:
    lc = load_loaded_corpus(slug)
    first, edges = _authors_and_edges(slug, lc)
    papers = {pid: PaperInfo(id=pid, openalex_id=m.openalex_id, title=m.title, year=m.year,
                             input_source=m.input_source, domain_centrality=m.domain_centrality,
                             first_author=first.get(pid))
              for pid, m in lc.papers.items() if pid in lc.extractions}
    cids, cvecs = claim_vectors(slug, lc)
    by_paper: dict[str, list] = {}
    for i, cid in enumerate(cids):
        by_paper.setdefault(lc.claim_paper[cid], []).append(cvecs[i])
    paper_vecs = {pid: np.mean(vs, axis=0) for pid, vs in by_paper.items()}
    own = [(l, pid) for pid, ext in lc.extractions.items()
           for l in ext.limitations if l.source_scope == "this_work"]
    fids, fvecs = fw_vectors(slug, lc)
    return ReasoningCorpus(
        papers=papers, own_limitations=own, future_work=lc.future_work(),
        addressals=load_addressals(slug), contradictions=[], citation_edges=edges,
        claim_ids=cids, claim_vectors=cvecs, paper_vectors=paper_vecs,
        fw_ids=fids, fw_vectors=fvecs, claim_paper=lc.claim_paper, _loaded=lc)


__all__ = ["load_library_corpus", "load_loaded_corpus", "embed_future_work",
           "load_addressals", "addressals_path", "fw_cache_path"]
