"""ReasoningCorpus — the single structured view every Phase-4 scorer
consumes. Assembled from the extraction cache + Phase-3 relationship
outputs; nothing here calls an LLM.

Provides: papers (with input_source, year, first author for the
independence check), own-work limitations, future-work items, the
two-stage future-work addressals, contradiction relationships, the
intra-corpus citation edges, and cached embeddings (claim vectors + mean
paper vectors) for the clustering / semantic-match scorers.

First-author data is fetched once from OpenAlex (free) and cached, so the
opportunity-criteria independence rule can be applied for real.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from backend.app.config import REPO_ROOT
from backend.app.models import ClaimRelationship, FutureWork, FutureWorkAddressal, Limitation
from backend.app.relationships.corpus_loader import LoadedCorpus, load_corpus
from backend.app.relationships.store import RelationshipStore

AUTHORS_CACHE = REPO_ROOT / "data" / "reasoning" / "authors.json"


@dataclass
class PaperInfo:
    id: str
    openalex_id: str | None
    title: str | None
    year: int | None
    input_source: str
    domain_centrality: str
    first_author: str | None


@dataclass
class ReasoningCorpus:
    papers: dict[str, PaperInfo]
    own_limitations: list[tuple[Limitation, str]]     # (limitation, paper_id), this_work only
    future_work: list[tuple[FutureWork, str]]
    addressals: list[FutureWorkAddressal]
    contradictions: list[ClaimRelationship]
    citation_edges: set[tuple[str, str]]              # (citing, cited)
    claim_ids: list[str]
    claim_vectors: np.ndarray
    paper_vectors: dict[str, np.ndarray]              # mean claim vector per paper
    fw_ids: list[str] = field(default_factory=list)
    fw_vectors: np.ndarray = None
    claim_paper: dict[str, str] = field(default_factory=dict)
    _loaded: LoadedCorpus = field(repr=False, default=None)

    def year(self, pid: str) -> int | None:
        p = self.papers.get(pid)
        return p.year if p else None


def _fetch_authors(oa_ids: list[str]) -> dict[str, str | None]:
    """openalex_native_id -> first-author display name. Cached (free)."""
    if AUTHORS_CACHE.exists():
        return json.loads(AUTHORS_CACHE.read_text())
    from backend.app.ingestion.openalex import OpenAlexClient

    natives = [i.rsplit("/", 1)[-1] for i in oa_ids if i]
    out: dict[str, str | None] = {}
    with OpenAlexClient() as client:
        for i in range(0, len(natives), 50):
            chunk = natives[i:i + 50]
            filt = "ids.openalex:" + "|".join(chunk)
            for rec in client.raw_works(filter=filt, limit=len(chunk), per_page=50):
                nid = (rec.get("id") or "").rsplit("/", 1)[-1]
                auth = rec.get("authorships") or []
                first = None
                for a in auth:
                    if (a or {}).get("author_position") == "first" or a is auth[0]:
                        first = ((a or {}).get("author") or {}).get("display_name")
                        break
                out[nid] = first
    AUTHORS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    AUTHORS_CACHE.write_text(json.dumps(out, indent=2))
    return out


def load_reasoning_corpus() -> ReasoningCorpus:
    lc = load_corpus()
    store = RelationshipStore()
    cids, cvecs = store.load_vectors()
    cvecs = np.asarray(cvecs, dtype=np.float32)

    oa_ids = [m.openalex_id for m in lc.papers.values() if m.openalex_id]
    authors = _fetch_authors(oa_ids)

    papers: dict[str, PaperInfo] = {}
    for pid, m in lc.papers.items():
        nid = (m.openalex_id or "").rsplit("/", 1)[-1]
        papers[pid] = PaperInfo(
            id=pid, openalex_id=m.openalex_id, title=m.title, year=m.year,
            input_source=m.input_source, domain_centrality=m.domain_centrality,
            first_author=authors.get(nid),
        )

    own_lims = [(l, pid) for pid, ext in lc.extractions.items()
                for l in ext.limitations if l.source_scope == "this_work"]
    fw = lc.future_work()

    rels = store.load_relationships()
    contradictions = [r for r in rels if r.type == "contradicts"]
    addressals = store.load_addressals()

    edges_path = store.root / "citation_edges.jsonl"
    edges: set[tuple[str, str]] = set()
    if edges_path.exists():
        for line in edges_path.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                edges.add((d["from_paper_id"], d["to_paper_id"]))

    # Mean claim vector per paper (topic vector) for clustering / matching.
    by_paper: dict[str, list[np.ndarray]] = {}
    for i, cid in enumerate(cids):
        pid = lc.claim_paper.get(cid)
        if pid:
            by_paper.setdefault(pid, []).append(cvecs[i])
    paper_vecs = {pid: np.mean(vs, axis=0) for pid, vs in by_paper.items()}

    fw_ids, fw_vecs = [], None
    fwv_path = store.root / "future_work.npy"
    fwi_path = store.root / "future_work_ids.json"
    if fwv_path.exists() and fwi_path.exists():
        fw_ids = json.loads(fwi_path.read_text())
        fw_vecs = np.load(fwv_path).astype(np.float32)

    return ReasoningCorpus(
        papers=papers, own_limitations=own_lims, future_work=fw,
        addressals=addressals, contradictions=contradictions,
        citation_edges=edges, claim_ids=cids, claim_vectors=cvecs,
        paper_vectors=paper_vecs, fw_ids=fw_ids, fw_vectors=fw_vecs,
        claim_paper=lc.claim_paper, _loaded=lc,
    )


__all__ = ["ReasoningCorpus", "PaperInfo", "load_reasoning_corpus"]
