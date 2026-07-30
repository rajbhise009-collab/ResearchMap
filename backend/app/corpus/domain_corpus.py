"""Canonical DOMAIN corpus selection from the labelled review set.

The abstract-vs-fulltext finding settled that the domain corpus must be
extracted at FULL TEXT where available. This module defines *which*
papers are in the domain corpus and tags each with its
`domain_centrality` — distinct from the earlier `stratify_thirty()`
sample, which deliberately mixed in off-domain controls.

Domain membership (from the hand-labelled `on_domain` column):
  - `on-domain`  -> domain_centrality = "core"
  - `borderline` -> domain_centrality = "peripheral"  (KEPT, not dropped)
  - `off-domain` -> NOT in the domain corpus
Plus the hard-`excluded=1` rows are dropped regardless.

A paper is additionally excluded (and recorded with a reason) if it has
neither a loadable full text nor a recoverable abstract — there is
nothing to extract from.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

from backend.app.corpus.run_live_extraction import (
    CORPUS_CSV,
    _load_papers_by_openalex_id,
)
from backend.app.models import Paper

CENTRALITY = {"on-domain": "core", "borderline": "peripheral"}


@dataclass
class CorpusEntry:
    openalex_id: str
    paper: Paper
    domain_centrality: str  # "core" | "peripheral"
    row: dict               # the raw review row (source, notes, etc.)


def domain_corpus() -> tuple[list[CorpusEntry], list[dict]]:
    """Return (entries, exclusions).

    `entries` — the in-corpus papers (core + peripheral) that have
    something to extract from, deterministically ordered by openalex_id.
    `exclusions` — dropped rows with a machine-readable reason, so the
    manifest can account for every labelled paper.
    """
    rows = list(csv.DictReader(CORPUS_CSV.open(encoding="utf-8")))
    rows.sort(key=lambda r: r["openalex_id"])
    papers = _load_papers_by_openalex_id()

    entries: list[CorpusEntry] = []
    exclusions: list[dict] = []
    for r in rows:
        oid = r["openalex_id"]
        dom = r.get("on_domain")
        if r.get("excluded") == "1":
            exclusions.append({"openalex_id": oid, "reason": "hard_excluded_label"})
            continue
        if dom not in CENTRALITY:
            exclusions.append({"openalex_id": oid, "reason": f"off_domain:{dom}"})
            continue
        paper = papers.get(oid)
        if paper is None or not (paper.abstract or "").strip():
            # No raw record / no recoverable abstract — and (checked by the
            # caller for full text) nothing to extract from.
            exclusions.append({
                "openalex_id": oid,
                "reason": "no_abstract_no_record",
            })
            continue
        entries.append(CorpusEntry(
            openalex_id=oid,
            paper=paper,
            domain_centrality=CENTRALITY[dom],
            row=r,
        ))
    return entries, exclusions


__all__ = ["CorpusEntry", "domain_corpus", "CENTRALITY"]
