"""Two-stage future-work matching: cosine shortlist -> LLM classification.

Raw cosine cannot express the "addresses" relation (precision caps ~0.57).
This applies the SAME architecture validated for contradictions: a wide
cosine shortlist (recall-first) feeds an LLM that classifies each
(future-work, later-paper) pair as addressed / partial / not_addressed.
Classification only — the LLM never scores or ranks (standing boundary).

A deterministic CITATION PRIOR is recorded per candidate: whether the
later paper cites the source paper (a later citing + topical paper is far
more likely to address the source's future work). It is a code-computed
FEATURE stored alongside the verdict — never fed to the LLM to weight.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from backend.app.models import FutureWorkAddressal, FutureWorkLabel
from backend.app.relationships.citation_graph import CitationEdge
from backend.app.relationships.corpus_loader import LoadedCorpus

PROMPT_VERSION = "fw-addr-c1.0.0"

PROMPT = """\
You are checking whether a LATER paper addresses a FUTURE-WORK direction \
proposed by an EARLIER paper. Judge only this pair. Classification only — \
do not rank, score, or rate importance.

Return STRICT JSON, no prose:
{"label": "addressed" | "partial" | "not_addressed", "justification": "<one sentence>", "addressing_element": "<the specific claim or method in the later paper that addresses it, or empty>"}

- "addressed": the later paper does substantive work that carries out or \
directly investigates the proposed direction.
- "partial": the later paper takes up a related sub-problem or a different \
setting but does not fully carry out the direction.
- "not_addressed": same broad topic only — the later paper does not take \
up this direction (mere topical adjacency).

Future-work item (proposed by paper <<SRC>>): <<FW>>
Later paper <<DST>> (<<YEAR>>) — title: <<TITLE>>
Most relevant claim from the later paper: <<CLAIM>>
"""


def prompt_hash() -> str:
    return hashlib.sha256(PROMPT.encode()).hexdigest()[:12]


@dataclass
class AddressalCandidate:
    fw_id: str
    from_paper_id: str          # source (raised the future work)
    to_paper_id: str            # later candidate paper
    to_year: int | None
    to_title: str | None
    best_claim_id: str
    best_claim_text: str
    similarity: float
    cites_source: bool          # citation prior (deterministic)


def shortlist_candidates(
    corpus: LoadedCorpus,
    fw_ids: list[str],
    fw_vectors,
    claim_ids: list[str],
    claim_vectors,
    citation_edges: list[CitationEdge],
    *,
    shortlist_threshold: float = 0.70,
    max_papers_per_fw: int = 4,
) -> list[AddressalCandidate]:
    """Recall-first stage: for each future-work item, later papers with a
    claim cosine >= threshold; keep the top-`max_papers_per_fw` papers by
    best claim cosine. Records the citation prior per candidate."""
    import numpy as np

    fw_lookup = {fw.id: (fw, meta) for fw, meta in corpus.future_work()}
    claim_text = {c.id: c.text for c in corpus.claims()}
    claim_paper = corpus.claim_paper
    paper_year = {pid: m.year for pid, m in corpus.papers.items()}
    paper_title = {pid: m.title for pid, m in corpus.papers.items()}
    cvec = np.asarray(claim_vectors, dtype=np.float32)
    claim_year = np.array([paper_year.get(claim_paper.get(c)) or -1 for c in claim_ids])
    # citation edge (citing -> cited): to_paper cites from_paper?
    cites = {(e.from_paper_id, e.to_paper_id) for e in citation_edges}

    out: list[AddressalCandidate] = []
    for i, fw_id in enumerate(fw_ids):
        fw, meta = fw_lookup[fw_id]
        src, src_year = meta.paper_id, meta.year
        if src_year is None:
            continue
        sims = cvec @ np.asarray(fw_vectors[i], dtype=np.float32)
        later = claim_year > src_year
        # best claim per later paper, above the shortlist threshold
        best_per_paper: dict[str, tuple[float, str]] = {}
        for k in np.where(later)[0]:
            if sims[k] < shortlist_threshold:
                continue
            pid = claim_paper.get(claim_ids[int(k)])
            if pid is None or pid == src:
                continue
            s = float(min(1.0, max(-1.0, sims[int(k)])))
            if pid not in best_per_paper or s > best_per_paper[pid][0]:
                best_per_paper[pid] = (s, claim_ids[int(k)])
        top = sorted(best_per_paper.items(), key=lambda kv: kv[1][0], reverse=True)[:max_papers_per_fw]
        for pid, (s, cid) in top:
            out.append(AddressalCandidate(
                fw_id=fw_id, from_paper_id=src, to_paper_id=pid,
                to_year=paper_year.get(pid), to_title=paper_title.get(pid),
                best_claim_id=cid, best_claim_text=claim_text[cid],
                similarity=s, cites_source=(pid, src) in cites,
            ))
    return out


def build_prompt(c: AddressalCandidate, fw_text: str) -> str:
    return (PROMPT
            .replace("<<SRC>>", c.from_paper_id.split(":")[-1])
            .replace("<<FW>>", fw_text)
            .replace("<<DST>>", c.to_paper_id.split(":")[-1])
            .replace("<<YEAR>>", str(c.to_year or ""))
            .replace("<<TITLE>>", c.to_title or "")
            .replace("<<CLAIM>>", c.best_claim_text))


_LABELS = {"addressed", "partial", "not_addressed"}


def parse_verdict(raw: str) -> tuple[str, str, str] | None:
    """Return (label, justification, addressing_element) or None if bad."""
    try:
        d = json.loads(raw)
        label = str(d["label"]).strip().lower()
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if label not in _LABELS:
        return None
    return label, str(d.get("justification", "")).strip(), str(d.get("addressing_element", "")).strip()


def to_addressal(c: AddressalCandidate, label: str, justification: str,
                 element: str, *, model_name: str, ph: str) -> FutureWorkAddressal:
    return FutureWorkAddressal(
        id=f"fwa:{c.fw_id}__{c.to_paper_id}",
        future_work_id=c.fw_id, from_paper_id=c.from_paper_id, to_paper_id=c.to_paper_id,
        label=FutureWorkLabel(label), justification=justification or None,
        addressing_element=element or None, similarity=c.similarity,
        cites_source=c.cites_source, detector_model=model_name, prompt_hash=ph,
    )


__all__ = [
    "AddressalCandidate", "shortlist_candidates", "build_prompt",
    "parse_verdict", "to_addressal", "prompt_hash", "PROMPT_VERSION",
]
