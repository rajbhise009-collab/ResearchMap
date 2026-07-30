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
    # `neural text generation` dropped after Phase 2 diagnostic showed
    # it matched 0/200 papers — dead term inflating query length.
)

TOPIC_TERMS: tuple[str, ...] = (
    "calibration",
    "uncertainty quantification",
    "abstention",
    "selective prediction",
    "hallucination detection",
    "hallucination",         # broader match for the noun on its own
    "hallucinations",        # plural — very common in titles/abstracts
    "confidence estimation",
    "epistemic uncertainty",
)

# High-precision, unambiguously in-domain terms. Unlike TOPIC_TERMS (which
# require an LLM anchor to co-occur), a STRONG term alone marks a paper
# on-domain — so FOUNDATIONAL pre-LLM work (conformal / selective
# prediction / calibration) is kept even though it never says "LLM".
# Deliberately specific to avoid false includes (bare "calibration" is
# NOT here; it collides across fields).
STRONG_TOPIC_TERMS: tuple[str, ...] = (
    "conformal prediction",
    "set-valued classifier",
    "set-valued classification",
    "selective prediction",
    "selective classification",
    "prediction set",
    "expected calibration error",
    "calibration error",
    "uncertainty quantification",
    "epistemic uncertainty",
    "aleatoric uncertainty",
    "hallucination detection",
    "abstention",
    "semantic entropy",
    # Foundational calibration/uncertainty terminology (pre-LLM classics
    # like Platt scaling, isotonic regression, deep-ensembles, OOD
    # detection). Same rationale as #14: legitimate in-domain work that
    # never says "LLM". Kept high-precision to avoid re-admitting noise.
    "probability estimates",
    "well-calibrated",
    "well calibrated",
    "uncertainty estimation",
    "out-of-distribution detection",
    "distributional shift",
    "predictive uncertainty",
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
    # NOTE: "arxiv" was REMOVED — arXiv is a preprint server for all of
    # CS/ML, not a domain signal. Auto-including any arXiv paper as
    # on-domain wrongly cleared off-topic work (e.g. BoolQ). A paper on
    # arXiv must earn on-domain via anchor+topic, strong-topic, or a real
    # venue — not the host.
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


CO_OCCURRENCE_WINDOW = 30  # tokens between anchor and topic (abstract)
TITLE_CO_OCCURRENCE_WINDOW = 12  # tighter window for the title rescue


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
    title = record.get("title") or ""
    text = " ".join(filter(None, [title, abstract_text or ""]))

    # Title-level on-domain rescue. When the property co-occurs with an
    # LLM anchor IN THE TITLE (tight window), the paper is ABOUT the
    # property — that is the rubric's contribution test — so a
    # mis-assigned OpenAlex `primary_field` must not hard-drop it. This
    # is failure mode #3 (the field gate dropping legitimate off-subfield
    # papers, e.g. a hallucination survey OpenAlex tagged 'neuroscience',
    # or a Nature semantic-entropy paper). It overrides the FIELD
    # denylist, not the venue denylist (a chemistry-journal venue is a
    # deliberate, reliable off-domain signal).
    title_on_domain = _co_occurs_within(title, ANCHOR_TERMS, TOPIC_TERMS,
                                        window=TITLE_CO_OCCURRENCE_WINDOW)

    # Off-domain gates (strongest signals first).
    if _venue_hit(venue_name, VENUE_DENYLIST):
        return "off-domain", f"venue in denylist: {venue_name!r}"
    if field and any(f in field for f in DENYLIST_FIELDS) and not title_on_domain:
        return "off-domain", f"primary field is off-domain: {field!r}"

    # On-domain gates.
    if title_on_domain:
        return "on-domain", "property + LLM anchor co-occur in title"
    if _venue_hit(venue_name, VENUE_ALLOWLIST):
        return "on-domain", f"venue in allowlist: {venue_name!r}"
    if _co_occurs_within(text, ANCHOR_TERMS, TOPIC_TERMS, CO_OCCURRENCE_WINDOW):
        return (
            "on-domain",
            f"anchor+topic co-occur within {CO_OCCURRENCE_WINDOW} tokens",
        )
    # Strong-topic-alone: a high-precision in-domain term with NO anchor
    # required — keeps foundational pre-LLM work (conformal / selective
    # prediction, e.g. "Least Ambiguous Set-Valued Classifiers").
    strong = [t for t in STRONG_TOPIC_TERMS if t in text.lower()]
    if strong:
        return "on-domain", f"strong in-domain term: {strong[0]!r}"

    # No signal → EXCLUDE. The old default kept these as 'borderline',
    # which let citation-neighbourhood contamination (text matching, QA
    # benchmarks, summarization datasets) into the corpus. A paper with no
    # positive domain signal is off-domain until proven otherwise.
    return "off-domain", "no domain signal (default-exclude)"


__all__ = [
    "ANCHOR_TERMS",
    "STRONG_TOPIC_TERMS",
    "CO_OCCURRENCE_WINDOW",
    "DENYLIST_FIELDS",
    "TOPIC_TERMS",
    "VENUE_ALLOWLIST",
    "VENUE_DENYLIST",
    "classify",
]
