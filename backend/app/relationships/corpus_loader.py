"""Load the extracted corpus (200 papers) for the relationship layer.

Reads the expanded corpus manifest for per-paper metadata + input_source,
then pulls each paper's cached PaperExtraction. Everything downstream
(embeddings, shortlist, contradiction, future-work matching) consumes
this in-memory view. Deterministic ordering (sorted by claim id) so runs
are reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.config import REPO_ROOT
from backend.app.extraction.cache import ExtractionCache
from backend.app.extraction.prompt_versions import load as load_prompt
from backend.app.models import Claim, FutureWork, PaperExtraction

MANIFEST = REPO_ROOT / "data" / "live_samples" / "expanded_corpus_manifest.json"
MODEL = "gemini:gemini-3.6-flash"
PROMPT_HASH = load_prompt("v1.1.0").hash


@dataclass
class PaperMeta:
    paper_id: str
    openalex_id: str | None
    title: str | None
    year: int | None
    doi: str | None
    input_source: str
    domain_centrality: str
    provenance: str          # "original" | "snowball"


@dataclass
class LoadedCorpus:
    papers: dict[str, PaperMeta]
    extractions: dict[str, PaperExtraction]
    # claim_id -> paper_id, and claim_id -> input_source (fast lookups).
    claim_paper: dict[str, str] = field(default_factory=dict)
    claim_source: dict[str, str] = field(default_factory=dict)

    def claims(self) -> list[Claim]:
        out: list[Claim] = []
        for pid in sorted(self.extractions):
            out.extend(self.extractions[pid].claims)
        out.sort(key=lambda c: c.id)
        return out

    def future_work(self) -> list[tuple[FutureWork, PaperMeta]]:
        out: list[tuple[FutureWork, PaperMeta]] = []
        for pid in sorted(self.extractions):
            meta = self.papers[pid]
            for fw in self.extractions[pid].future_work:
                out.append((fw, meta))
        out.sort(key=lambda t: t[0].id)
        return out

    @property
    def n_claims(self) -> int:
        return sum(len(e.claims) for e in self.extractions.values())


def load_corpus(
    manifest_path: Path = MANIFEST, cache: ExtractionCache | None = None
) -> LoadedCorpus:
    cache = cache or ExtractionCache()
    manifest = json.loads(manifest_path.read_text())
    papers: dict[str, PaperMeta] = {}
    extractions: dict[str, PaperExtraction] = {}
    claim_paper: dict[str, str] = {}
    claim_source: dict[str, str] = {}

    for rec in manifest["records"]:
        pid = rec["paper_id"]
        src = rec["input_source"]
        ext = cache.get(pid, MODEL, src, PROMPT_HASH)
        if ext is None:
            continue  # not extracted (should not happen at 200/200)
        meta = PaperMeta(
            paper_id=pid,
            openalex_id=rec.get("openalex_id"),
            title=rec.get("title"),
            year=rec.get("year"),
            doi=rec.get("doi"),
            input_source=src,
            domain_centrality=rec.get("domain_centrality", "unknown"),
            provenance=rec.get("provenance", "unknown"),
        )
        papers[pid] = meta
        extractions[pid] = ext
        for c in ext.claims:
            claim_paper[c.id] = pid
            claim_source[c.id] = src

    return LoadedCorpus(papers, extractions, claim_paper, claim_source)


__all__ = ["LoadedCorpus", "PaperMeta", "load_corpus", "MODEL", "PROMPT_HASH"]
