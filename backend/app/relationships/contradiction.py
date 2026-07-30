"""Pairwise contradiction / support detection over the shortlist.

THE LLM BOUNDARY: the LLM classifies ONE pair — "do these two claims
contradict, support, or neither?" — plus a short explanation. That is
perception of a relationship, the same class of task as extraction. The
LLM never ranks pairs, never weights them, never scores. The weight is
computed by deterministic Python (relationships/weighting.py); the LLM's
text goes only into `type` and `evidence_note`.

One `generate` call per shortlisted pair. Malformed output for a pair is
counted and skipped (a single bad pair never aborts the run).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass

from backend.app.extraction.llm_client import LLMClient
from backend.app.models import ClaimRelationship, RelationshipType
from backend.app.relationships.corpus_loader import LoadedCorpus
from backend.app.relationships.shortlist import CandidatePair
from backend.app.relationships.weighting import relationship_weight

PAIR_PROMPT_VERSION = "pair-c1.0.0"

PAIR_PROMPT = """\
You are comparing two scientific claims, each from a different paper on \
LLM calibration / uncertainty / hallucination. Decide the relationship \
between them. Judge ONLY these two claims — do not rank, score, or rate \
importance.

Return STRICT JSON, no prose:
{"relationship": "contradicts" | "supports" | "none", "explanation": "<one sentence>"}

Definitions:
- "contradicts": the two claims cannot both be true about the same \
construct (e.g. one says a method improves calibration, the other says \
the same method does not).
- "supports": the two claims independently assert the same or a \
mutually reinforcing finding.
- "none": same topic but neither contradicting nor supporting (different \
constructs, orthogonal findings, or a mere terminological overlap).

Beware terminology collisions: the same word (e.g. "calibration") can \
mean different constructs in different papers — that is "none", not a \
contradiction.

Claim A (paper <<PAPER_A>>): <<TEXT_A>>
Claim B (paper <<PAPER_B>>): <<TEXT_B>>
"""


def prompt_hash() -> str:
    return hashlib.sha256(PAIR_PROMPT.encode()).hexdigest()[:12]


# v1.1 — regime/experimental-context aware. Feeds each claim's SIBLING
# claims (same paper) so the model can infer the experimental regime and
# avoid calling claims contradictory when they hold under different regimes
# (e.g. general generation vs adversarial/clinical prompting). This is the
# cheap partial for the missing Claim.condition field (docs/reasoning-engine.md).
PAIR_PROMPT_V11 = """\
You are comparing two scientific claims, each from a different paper on \
LLM calibration / uncertainty / hallucination. Decide the relationship. \
Judge ONLY these two claims — do not rank, score, or rate importance.

CRITICAL — experimental regime. Two claims are NOT contradictory if they \
hold under DIFFERENT conditions (general open-ended generation vs. \
adversarial or clinical prompting; different datasets; different \
definitions of the measured property). Use each claim's sibling claims \
(same paper, given below) to infer its regime. Call it "contradicts" ONLY \
if the two claims are incompatible about the SAME construct UNDER THE SAME \
REGIME.

Return STRICT JSON, no prose:
{"relationship": "contradicts" | "supports" | "none", "same_regime": true | false, "explanation": "<one sentence naming the regime of each claim>"}

Beware terminology collisions: the same word (e.g. "calibration") can mean \
different constructs — that is "none".

Claim A (paper <<PAPER_A>>): <<TEXT_A>>
Other claims from paper <<PAPER_A>> (context): <<SIB_A>>

Claim B (paper <<PAPER_B>>): <<TEXT_B>>
Other claims from paper <<PAPER_B>> (context): <<SIB_B>>
"""


def prompt_hash_v11() -> str:
    return hashlib.sha256(PAIR_PROMPT_V11.encode()).hexdigest()[:12]


def build_pair_prompt_ctx(*, text_a, text_b, paper_a, paper_b, sib_a, sib_b) -> str:
    return (PAIR_PROMPT_V11
            .replace("<<TEXT_A>>", text_a).replace("<<TEXT_B>>", text_b)
            .replace("<<PAPER_A>>", paper_a).replace("<<PAPER_B>>", paper_b)
            .replace("<<SIB_A>>", sib_a or "(none)")
            .replace("<<SIB_B>>", sib_b or "(none)"))


_REL_MAP = {
    "contradicts": RelationshipType.CONTRADICTS,
    "supports": RelationshipType.SUPPORTS,
}


@dataclass
class PairVerdict:
    relationship: str            # "contradicts" | "supports" | "none"
    explanation: str


def build_pair_prompt(*, text_a: str, text_b: str,
                      paper_a: str, paper_b: str) -> str:
    return (PAIR_PROMPT
            .replace("<<TEXT_A>>", text_a).replace("<<TEXT_B>>", text_b)
            .replace("<<PAPER_A>>", paper_a).replace("<<PAPER_B>>", paper_b))


def parse_verdict(raw: str) -> PairVerdict | None:
    """Parse a pair-classification response. None on any malformed output
    (the caller counts and skips — one bad pair never aborts the run)."""
    try:
        data = json.loads(raw)
        rel = str(data["relationship"]).strip().lower()
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if rel not in ("contradicts", "supports", "none"):
        return None
    return PairVerdict(rel, str(data.get("explanation", "")).strip())


def relationship_from_verdict(
    pair: CandidatePair, verdict: PairVerdict, corpus: LoadedCorpus,
    *, model_name: str, ph: str,
) -> ClaimRelationship | None:
    """Assemble a ClaimRelationship from a parsed verdict. The weight is
    DETERMINISTIC (relationships/weighting.py); the LLM's text only names
    the type and fills evidence_note. Returns None for 'none'."""
    rel_type = _REL_MAP.get(verdict.relationship)
    if rel_type is None:
        return None
    a, b = pair.from_claim_id, pair.to_claim_id
    pa, pb = corpus.claim_paper[a], corpus.claim_paper[b]
    weight = relationship_weight(
        similarity=pair.similarity,
        source_a=corpus.claim_source[a], source_b=corpus.claim_source[b],
    )
    return ClaimRelationship(
        id=f"rel:{a}__{rel_type.value}__{b}",
        from_claim_id=a, to_claim_id=b,
        type=rel_type, weight=weight,
        evidence_note=verdict.explanation or None,
        from_paper_id=pa, to_paper_id=pb,
        detector_model=model_name, prompt_hash=ph,
        similarity=pair.similarity,
    )


class PairClassifier:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def classify(self, *, text_a: str, text_b: str,
                 paper_a: str, paper_b: str) -> PairVerdict | None:
        raw = self._llm.generate(build_pair_prompt(
            text_a=text_a, text_b=text_b, paper_a=paper_a, paper_b=paper_b))
        return parse_verdict(raw)


def detect_relationships(
    corpus: LoadedCorpus,
    candidates: list[CandidatePair],
    llm: LLMClient,
    *,
    model_name: str,
) -> tuple[list[ClaimRelationship], dict]:
    """Classify every shortlisted pair; persist contradicts/supports as
    ClaimRelationship rows with deterministic weight + full provenance."""
    classifier = PairClassifier(llm)
    claim_text = {c.id: c.text for c in corpus.claims()}
    ph = prompt_hash()

    rels: list[ClaimRelationship] = []
    counts: Counter = Counter()
    for pair in candidates:
        a, b = pair.from_claim_id, pair.to_claim_id
        pa, pb = corpus.claim_paper[a], corpus.claim_paper[b]
        verdict = classifier.classify(
            text_a=claim_text[a], text_b=claim_text[b], paper_a=pa, paper_b=pb
        )
        counts["classified"] += 1
        if verdict is None:
            counts["malformed"] += 1
            continue
        counts[verdict.relationship] += 1
        rel = relationship_from_verdict(pair, verdict, corpus,
                                        model_name=model_name, ph=ph)
        if rel is not None:
            rels.append(rel)
    stats = {
        "candidates": len(candidates),
        "classified": counts["classified"],
        "malformed": counts["malformed"],
        "contradicts": counts["contradicts"],
        "supports": counts["supports"],
        "none": counts["none"],
        "persisted": len(rels),
        "prompt_hash": ph,
    }
    return rels, stats


__all__ = ["PairClassifier", "PairVerdict", "detect_relationships",
           "prompt_hash", "PAIR_PROMPT_VERSION"]
