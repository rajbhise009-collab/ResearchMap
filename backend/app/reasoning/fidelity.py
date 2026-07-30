"""Mixed-fidelity correction (opportunity-criteria.md "Mixed-fidelity
corpus bias"). MANDATORY for any scorer that counts independent papers.

Full-text papers surface ~11x more own-work limitations than abstract-only
papers, and full-text availability tracks venue/OA, not merit. So a raw
paper count ranks arXiv/OA-preprint culture. The correction weights each
paper's contribution by `input_source`: abstract-only reports are
UP-weighted (rarer to detect ⇒ stronger evidence of persistence).

`effective_count` with correction ON uses the config weights; with
correction OFF every paper weighs 1.0 (raw count). Both are reported so the
difference is visible. Weights live in config; never LLM-derived.
"""

from __future__ import annotations

from backend.app.config import get_settings
from backend.app.reasoning.corpus_view import PaperInfo


def fidelity_weight(input_source: str, *, corrected: bool = True) -> float:
    if not corrected:
        return 1.0
    s = get_settings()
    return (s.reason_fidelity_weight_abstract if input_source == "abstract"
            else s.reason_fidelity_weight_fulltext)


def effective_count(paper_ids, papers: dict[str, PaperInfo], *, corrected: bool = True) -> float:
    """Fidelity-weighted count of the given papers."""
    return sum(
        fidelity_weight(papers[p].input_source, corrected=corrected)
        for p in paper_ids if p in papers
    )


__all__ = ["fidelity_weight", "effective_count"]
