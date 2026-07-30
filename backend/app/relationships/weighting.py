"""Deterministic relationship weighting.

THE LLM BOUNDARY LIVES HERE. An LLM perceives a single pair's
relationship *type* (contradicts / supports / none); this module turns
that perception into a NUMBER using only inspectable, deterministic
inputs. No LLM output feeds the weight, and — per
docs/confidence-policy.md — `Claim.confidence` (an LLM self-assessment)
must never enter a score, so it is deliberately not an input here.

Inputs used (all deterministic):
  - `similarity`: cosine of the two claim embeddings (the shortlist
    signal); higher = the pair is more clearly about the same thing.
  - input_source fidelity: a relationship between two full-text-derived
    claims is higher-fidelity than one resting on abstract-only claims
    (mixed-fidelity bias, docs/opportunity-criteria.md). Full text is
    where own-work claims actually live.
"""

from __future__ import annotations

# Fidelity multiplier by the pair of input sources. Full text is the
# higher-fidelity signal; two abstract-only claims get the largest
# discount. Tunable and documented; not learned, not LLM-derived.
_FIDELITY = {
    frozenset({"fulltext"}): 1.00,             # both full text
    frozenset({"fulltext", "abstract"}): 0.90,  # mixed
    frozenset({"abstract"}): 0.80,             # both abstract-only
}


def fidelity_factor(source_a: str, source_b: str) -> float:
    return _FIDELITY.get(frozenset({source_a, source_b}), 0.80)


def relationship_weight(
    *, similarity: float, source_a: str, source_b: str
) -> float:
    """Deterministic weight in [0, 1]. weight = similarity × fidelity,
    clamped. Pure function of code-visible inputs."""
    sim = max(0.0, min(1.0, similarity))
    w = sim * fidelity_factor(source_a, source_b)
    return max(0.0, min(1.0, w))


__all__ = ["relationship_weight", "fidelity_factor"]
