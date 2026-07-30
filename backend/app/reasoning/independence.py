"""Independence check (opportunity-criteria.md criterion 1).

Independent supporting papers means:
  - distinct Paper.id (guaranteed by the corpus keys);
  - not present in each other's merged_from (dedup ran at ingestion, so
    the corpus already holds one row per work — merged_from collapses are
    upstream; noted, not re-checked here);
  - identical FIRST authors on >= 2 papers count as ONE.

This returns the deduped independent set, collapsing papers that share a
first author. Papers with unknown first author are treated as distinct
(we do not merge on missing data).
"""

from __future__ import annotations

from backend.app.reasoning.corpus_view import PaperInfo


def independent_set(paper_ids, papers: dict[str, PaperInfo]) -> list[str]:
    """Collapse papers sharing a first author to one representative
    (deterministic: keep the lexicographically smallest paper id)."""
    seen_author: dict[str, str] = {}
    out: list[str] = []
    for pid in sorted(paper_ids):
        info = papers.get(pid)
        fa = (info.first_author or "").strip().lower() if info else ""
        if fa and fa in seen_author:
            continue  # same first author already counted
        if fa:
            seen_author[fa] = pid
        out.append(pid)
    return out


def independent_count(paper_ids, papers: dict[str, PaperInfo]) -> int:
    return len(independent_set(paper_ids, papers))


__all__ = ["independent_set", "independent_count"]
