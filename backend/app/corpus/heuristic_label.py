"""Heuristic on-domain labeller for the corpus-quality diagnostic.

Two-part heuristic. A paper is labelled:

  on-domain    — venue is in the NLP/ML allowlist OR the abstract
                 shows tight (≤ N-token) co-occurrence of an anchor
                 term and a topic term.
  off-domain   — venue is in the denylist OR the primary OpenAlex
                 topic is clearly outside AI (chemistry, materials,
                 medicine, biology, geoscience).
  borderline   — everything else (mostly AI-adjacent papers that
                 mention our terms but not centrally).

This is deliberately conservative on both sides — the whole point of
having the user hand-label a sample in parallel is to measure where
the heuristic disagrees.

Nothing here is used by ranking; this is a diagnostic tool only.
"""

from __future__ import annotations

import re
from typing import Iterable

# --- Query terms (must match the v3 query used at pull time) ------------

ANCHOR_TERMS: tuple[str, ...] = (
    "language model",
    "language models",
    "llm",
    "llms",
    "large language model",
    "large language models",
    "neural text generation",
)

TOPIC_TERMS: tuple[str, ...] = (
    "calibration",
    "uncertainty quantification",
    "abstention",
    "selective prediction",
    "hallucination detection",
    "hallucination",         # broader match for the noun on its own
    "confidence estimation",
    "epistemic uncertainty",
)

# --- Venue allow / denylists --------------------------------------------

# NLP / ML venues where a paper mentioning our terms is almost certainly
# on-domain. Lowercased; matched by substring.
VENUE_ALLOWLIST: tuple[str, ...] = (
    "neural information processing systems",
    "neurips",
    "international conference on machine learning",
    "icml",
    "international conference on learning representations",
    "iclr",
    "association for computational linguistics",
    "annual meeting of the association for computational linguistics",
    "acl",
    "empirical methods in natural language processing",
    "emnlp",
    "north american chapter of the association for computational linguistics",
    "naacl",
    "european chapter of the association for computational linguistics",
    "eacl",
    "coling",
    "conference on computational natural language learning",
    "conll",
    "transactions of the association for computational linguistics",
    "tacl",
    "journal of machine learning research",
    "jmlr",
    "transactions on machine learning research",
    "tmlr",
    "aaai conference on artificial intelligence",
    "international joint conference on artificial intelligence",
    "ijcai",
    "findings of the association for computational linguistics",
    "findings of acl",
    "findings of emnlp",
    "arxiv",   # accepted here — arXiv preprints are common on-domain
)

# Venues where a "language model + X" mention is almost certainly a
# cross-domain application paper. Substring match, lowercased.
VENUE_DENYLIST: tuple[str, ...] = (
    "journal of chemical",
    "chemistry of materials",
    "chemical reviews",
    "nature chemistry",
    "nature materials",
    "advanced materials",
    "chem catalysis",
    "acs catal",
    "acs applied materials",
    "journal of physical chemistry",
    "chemical science",
    "chemcomm",
    "green chemistry",
    "the lancet",
    "new england journal of medicine",
    "nejm",
    "jama ",
    "british medical journal",
    "bmj",
    "radiology",
    "geoscience",
    "geochemistry",
    "biophysical",
    "biochim",
    "biochemistry",
    "photonics",
    "supercomputing",
    "high performance computing",
)

# OpenAlex primary_topic.field.display_name values that are safe
# assumptions of on-domain research.
ALLOWLIST_FIELDS: tuple[str, ...] = (
    "computer science",
)

# OpenAlex primary_topic.field.display_name values that are almost
# never NLP calibration research even if the term shows up.
DENYLIST_FIELDS: tuple[str, ...] = (
    "chemistry",
    "materials science",
    "medicine",
    "pharmacology, toxicology and pharmaceutics",
    "biochemistry, genetics and molecular biology",
    "physics and astronomy",
    "earth and planetary sciences",
    "chemical engineering",
    "environmental science",
    "energy",
    "agricultural and biological sciences",
    "veterinary",
    "immunology and microbiology",
    "neuroscience",
    "dentistry",
    "nursing",
)

# --- Tokenization + matching --------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _spans_of(needle: str, tokens: list[str]) -> list[tuple[int, int]]:
    """Return (start, end_exclusive) token indices where `needle` (a
    multi-word phrase) occurs in `tokens`."""
    parts = needle.lower().split()
    if not parts:
        return []
    n = len(parts)
    out: list[tuple[int, int]] = []
    for i in range(len(tokens) - n + 1):
        if tokens[i:i + n] == parts:
            out.append((i, i + n))
    return out


def _co_occurs_within(text: str, a_terms: Iterable[str],
                       b_terms: Iterable[str], window: int) -> bool:
    """True if any a-term and any b-term have token spans within `window`
    tokens of each other in `text`."""
    tokens = _tokens(text)
    a_spans = [s for term in a_terms for s in _spans_of(term, tokens)]
    if not a_spans:
        return False
    b_spans = [s for term in b_terms for s in _spans_of(term, tokens)]
    if not b_spans:
        return False
    for (a_start, a_end) in a_spans:
        for (b_start, b_end) in b_spans:
            gap = min(abs(a_start - b_end), abs(b_start - a_end))
            if gap <= window:
                return True
    return False


# --- The heuristic itself ----------------------------------------------


CO_OCCURRENCE_WINDOW = 30  # tokens between anchor and topic


def _venue_hit(venue: str | None, hitlist: Iterable[str]) -> bool:
    if not venue:
        return False
    v = venue.lower()
    return any(t in v for t in hitlist)


def _field_display_name(record: dict) -> str | None:
    pt = record.get("primary_topic") or {}
    field = (pt.get("field") or {}) if isinstance(pt, dict) else {}
    name = field.get("display_name")
    return name.lower() if isinstance(name, str) else None


def classify(record: dict, *, abstract_text: str | None) -> tuple[str, str]:
    """Return (label, one-line rationale).

    label ∈ {"on-domain", "off-domain", "borderline"}.
    """
    venue_name = None
    hv = record.get("host_venue") or record.get("primary_location") or {}
    if isinstance(hv, dict):
        src = hv.get("source") if isinstance(hv.get("source"), dict) else {}
        venue_name = (src.get("display_name") if isinstance(src, dict) else None) \
                     or hv.get("display_name")

    field = _field_display_name(record)
    text = " ".join(filter(None, [record.get("title") or "", abstract_text or ""]))

    # Off-domain gates (strongest signals first).
    if _venue_hit(venue_name, VENUE_DENYLIST):
        return "off-domain", f"venue in denylist: {venue_name!r}"
    if field and any(f in field for f in DENYLIST_FIELDS):
        return "off-domain", f"primary field is off-domain: {field!r}"

    # On-domain gates.
    if _venue_hit(venue_name, VENUE_ALLOWLIST):
        return "on-domain", f"venue in allowlist: {venue_name!r}"
    if _co_occurs_within(text, ANCHOR_TERMS, TOPIC_TERMS, CO_OCCURRENCE_WINDOW):
        return (
            "on-domain",
            f"anchor+topic co-occur within {CO_OCCURRENCE_WINDOW} tokens",
        )

    # Neither — borderline. Includes AI-field papers whose abstract
    # mentions the terms but not tightly, or papers with no venue/field
    # information.
    return "borderline", "no strong signal in either direction"


__all__ = [
    "ANCHOR_TERMS",
    "CO_OCCURRENCE_WINDOW",
    "DENYLIST_FIELDS",
    "TOPIC_TERMS",
    "VENUE_ALLOWLIST",
    "VENUE_DENYLIST",
    "classify",
]
