"""Parse-time enforcement of the compound-splitting contract.

Called by the extractor orchestrator on every `PaperExtraction` before
persistence. The rule: `Claim.text` must be a single atomic assertion.
If the model returns a compound sentence (multiple assertions joined
in one Claim), we split it into separate `Claim` records with a shared
`source_sentence_id` so the evidence chain stays traceable.

Splitting rules (conservative — we'd rather leave a compound whole
than split a fluent single claim):

  1. Enumeration markers: "1)", "(1)", "1.", "1:" at word boundaries.
  2. Semicolons that separate two independent-looking clauses (each
     clause has a verb-like token).

We deliberately DO NOT split on sentence-ending periods — many valid
single claims contain multiple sentences of context ("X is true.
Specifically, Y."). Trusting sentence boundaries loses too much
signal.

Rationale documented in `docs/schema-pressure-test.md` decision #2.
"""

from __future__ import annotations

import re
from typing import Iterable

from backend.app.models import Claim, PaperExtraction


# --- Detection ----------------------------------------------------------

# Numeric enumeration markers.
# Matches:  "1)" "(1)" "1." "1:" "(a)" "a)" — as long as they appear at
# a word boundary and are followed by a space.
_ENUM_PATTERN = re.compile(
    r"(?:^|(?<=[\s,;]))"
    r"(?:\(?\d+[.):]|\(?[a-z][.):])"
    r"\s+",
    flags=re.IGNORECASE,
)

# A rough "clause has a verb" check — presence of a common verb token
# indicates the fragment could stand alone as a claim. Small closed
# vocabulary; deliberately conservative.
_VERB_TOKENS = {
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had",
    "does", "do", "did", "done",
    "shows", "show", "showed",
    "demonstrates", "demonstrate", "demonstrated",
    "improves", "improve", "improved",
    "reduces", "reduce", "reduced",
    "increases", "increase", "increased",
    "outperforms", "outperform", "outperformed",
    "achieves", "achieve", "achieved",
    "propose", "proposes", "proposed",
    "reports", "reported",
    "finds", "found", "find",
    "requires", "required", "require",
    "generalises", "generalises", "generalizes",
    "provides", "provide", "provided",
    "makes", "make", "made",
    "gives", "give", "given",
    "yields", "yield", "yielded",
    "suffers", "suffer", "suffered",
    "fails", "fail", "failed",
}


def _has_verblike_token(text: str) -> bool:
    tokens = re.findall(r"[a-z]+", text.lower())
    return any(t in _VERB_TOKENS for t in tokens)


def is_compound(text: str) -> bool:
    """True iff we can detect two or more atomic assertions in `text`."""
    return len(_split_compound_text(text)) > 1


def _split_compound_text(text: str) -> list[str]:
    """Return the list of atomic claim-text substrings implied by
    the compound-splitting rules. If `text` is atomic, returns
    `[text]`."""
    # --- Enumeration split.
    # Only accept when we detected at least TWO enumeration markers.
    # Atoms are the text that appears AFTER each marker, up to the
    # next marker (or end of text). Preamble (text before the first
    # marker) is discarded — it's typically framing like "Our
    # contributions are" rather than an atomic claim on its own.
    # We deliberately DO NOT require a verb on each atom — nominal
    # contribution lists ("1) X, 2) Y, 3) Z") are compounds even
    # though the atoms are noun phrases.
    matches = list(_ENUM_PATTERN.finditer(text))
    if len(matches) >= 2:
        atoms = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            atom = text[start:end].strip().rstrip(",").strip()
            atoms.append(atom)
        long_enough = [a for a in atoms if len(a.split()) >= 3]
        if len(long_enough) >= 2:
            return long_enough

    # --- Semicolon split.
    # More ambiguous — many valid single claims use semicolons for
    # trailing lists ("three benchmarks were used; ETTh1, ETTh2, and
    # Weather"). Require that every half have both a verb-like token
    # AND enough tokens to stand alone.
    semi = [p.strip() for p in text.split(";") if p.strip()]
    if len(semi) >= 2:
        with_verbs = [p for p in semi if _has_verblike_token(p) and len(p.split()) >= 3]
        if len(with_verbs) == len(semi):
            return semi

    return [text]


# --- Splitter -----------------------------------------------------------


def split_compound_claims(claims: Iterable[Claim]) -> list[Claim]:
    """Rewrite a claim list so no `Claim.text` carries a compound.

    Each split emission:
      - inherits `paper_id`, `type`, `confidence` from the parent;
      - gets a deterministic new id: `<parent.id>:s1`, `<parent.id>:s2`;
      - carries the parent's `id` as `source_sentence_id` so the
        evidence chain can reconstruct which claims came from the
        same sentence.

    Idempotent: running the splitter on already-atomic claims returns
    them unchanged.
    """
    out: list[Claim] = []
    for claim in claims:
        atoms = _split_compound_text(claim.text)
        if len(atoms) == 1:
            out.append(claim)
            continue
        parent_id = claim.id
        for i, atom_text in enumerate(atoms, start=1):
            new_id = f"{parent_id}:s{i}"
            out.append(Claim(
                id=new_id,
                paper_id=claim.paper_id,
                text=atom_text,
                type=claim.type,
                confidence=claim.confidence,
                source_sentence_id=parent_id,
            ))
    return out


def enforce_compound_splitting(extraction: PaperExtraction) -> PaperExtraction:
    """Apply `split_compound_claims` in place on a PaperExtraction
    bundle. Preserves every other field."""
    if not extraction.claims:
        return extraction
    split = split_compound_claims(extraction.claims)
    if len(split) == len(extraction.claims):
        # No-op — bundle already atomic.
        return extraction
    return PaperExtraction.model_validate({
        **extraction.model_dump(),
        "claims": [c.model_dump() for c in split],
    })


__all__ = [
    "enforce_compound_splitting",
    "is_compound",
    "split_compound_claims",
]
