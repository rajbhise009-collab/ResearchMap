"""Intra-corpus citation graph from OpenAlex `referenced_works`.

For each corpus paper we fetch its OpenAlex reference list and keep the
edges that land on ANOTHER corpus paper (citing -> cited). This is the
deterministic backbone the reasoning engine will later walk (a
future-work item "addressed by" a paper that cites it, a limitation
inherited along a citation chain, etc.). Pure OpenAlex data — free, no
LLM, no scoring.

Fetched reference lists are cached to disk so the graph rebuilds
offline. Edges are directed: `from_paper_id` cites `to_paper_id`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import REPO_ROOT
from backend.app.relationships.corpus_loader import LoadedCorpus

REFS_CACHE = REPO_ROOT / "data" / "relationships" / "referenced_works.json"


@dataclass(frozen=True)
class CitationEdge:
    from_paper_id: str   # the citing paper (corpus id, e.g. openalex:W..)
    to_paper_id: str     # the cited paper (corpus id)


def _native(oid: str) -> str:
    return (oid or "").rsplit("/", 1)[-1]


def fetch_referenced_works(
    corpus: LoadedCorpus, *, client=None, cache_path: Path = REFS_CACHE
) -> dict[str, list[str]]:
    """Return {paper_id: [referenced openalex native ids]}, cached. Uses
    OpenAlex raw records (free, 1 credit / 50 ids)."""
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    from backend.app.ingestion.openalex import OpenAlexClient

    natives = [_native(m.openalex_id) for m in corpus.papers.values()
               if m.openalex_id]
    owns = client is None
    client = client or OpenAlexClient()
    refs: dict[str, list[str]] = {}
    try:
        for i in range(0, len(natives), 50):
            chunk = natives[i:i + 50]
            filt = "ids.openalex:" + "|".join(chunk)
            for rec in client.raw_works(filter=filt, limit=len(chunk), per_page=50):
                pid = f"openalex:{_native(rec.get('id') or '')}"
                refs[pid] = [_native(r) for r in rec.get("referenced_works", [])]
    finally:
        if owns:
            client.close()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(refs, indent=2))
    return refs


def build_citation_graph(
    corpus: LoadedCorpus, refs: dict[str, list[str]]
) -> list[CitationEdge]:
    """Keep only edges whose target is also a corpus paper."""
    corpus_native = {_native(m.openalex_id): pid
                     for pid, m in corpus.papers.items() if m.openalex_id}
    edges: list[CitationEdge] = []
    seen: set[tuple[str, str]] = set()
    for citing_pid, ref_ids in refs.items():
        if citing_pid not in corpus.papers:
            continue
        for rn in ref_ids:
            cited_pid = corpus_native.get(rn)
            if cited_pid and cited_pid != citing_pid:
                key = (citing_pid, cited_pid)
                if key not in seen:
                    seen.add(key)
                    edges.append(CitationEdge(citing_pid, cited_pid))
    edges.sort(key=lambda e: (e.from_paper_id, e.to_paper_id))
    return edges


__all__ = ["CitationEdge", "fetch_referenced_works", "build_citation_graph",
           "REFS_CACHE"]
