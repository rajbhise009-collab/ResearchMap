"""Runtime configuration.

All secrets are read from environment variables (or a `.env` file at repo
root). Nothing here is ever logged in cleartext — `Settings` overrides
`__repr__` so accidental prints don't leak keys.

The offline seed pipeline runs with every one of these unset. Live
ingestion requires OPENALEX_API_KEY (mandatory since 2026-02-13; the
old polite-pool mailto convention was retired); live extraction
requires GEMINI_API_KEY; live synthesis (Phase 4+) requires
ANTHROPIC_API_KEY.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]


def _secret_truthy(v: SecretStr | None) -> bool:
    """A SecretStr("") is not None but should count as unset — we treat
    an empty value the same as a missing one."""
    if v is None:
        return False
    return bool(v.get_secret_value().strip())


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Central config. Do NOT read env vars anywhere else in the codebase."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    environment: Environment = Field(
        default=Environment.DEVELOPMENT, alias="RESEARCHMAP_ENV"
    )

    database_url: SecretStr | None = Field(default=None, alias="DATABASE_URL")

    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    # Model names are volatile — gemini-2.5-flash was deprecated out from
    # under us mid-development. Keep the model in config, not hardcoded,
    # and validate it against models.list at client startup.
    gemini_model: str = Field(default="gemini-flash-latest", alias="GEMINI_MODEL")
    # Client-side rate limiting (never trip an avoidable 429).
    # RPM: requests/minute. TPM: input tokens/minute (set under the
    # 250k API ceiling to leave headroom). Both configurable.
    gemini_max_rpm: int = Field(default=8, alias="GEMINI_MAX_RPM", gt=0)
    gemini_max_tpm: int = Field(default=200_000, alias="GEMINI_MAX_TPM", gt=0)
    # Embedding model for the Phase-3 claim shortlist. 768-dim to match
    # the pgvector schema (migration 002). Kept in config, not hardcoded.
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001", alias="GEMINI_EMBEDDING_MODEL"
    )
    embedding_dim: int = Field(default=768, alias="EMBEDDING_DIM", gt=0)

    # --- Phase 3 relationship layer (config-driven shortlist knobs) ---
    # Only claim pairs with cosine similarity >= threshold become
    # contradiction-check candidates; each claim keeps at most
    # `rel_max_candidates_per_claim` neighbours. Both bound the
    # combinatorial budget — see docs/relationship-layer.md.
    # 0.78 calibrated on the 200-paper corpus (see docs/relationship-layer.md):
    # above ~0.9 pairs are near-duplicate restatements (support), while
    # genuine same-construct/opposite-conclusion pairs sit lower, so a high
    # threshold sacrifices contradiction recall. 0.78 -> ~440 candidates
    # (~$0.20 batch), well under the $3 gate. The shortlist optimizes
    # recall; the pairwise LLM provides precision.
    rel_similarity_threshold: float = Field(
        default=0.78, alias="REL_SIMILARITY_THRESHOLD", ge=0.0, le=1.0
    )
    rel_max_candidates_per_claim: int = Field(
        default=10, alias="REL_MAX_CANDIDATES_PER_CLAIM", gt=0
    )
    # A paper does not meaningfully contradict itself; cross-paper only.
    rel_cross_paper_only: bool = Field(
        default=True, alias="REL_CROSS_PAPER_ONLY"
    )
    # Future-work "addressed_by" match threshold (cosine). PINNED at 0.74
    # by hand-labelling 40 items in the sensitive [0.70,0.80) band: 0.74 is
    # the F1-optimum (P=0.41, R=0.70) and favors recall, which is the right
    # bias for an orphan scorer (a missed real match = a FALSE orphan, the
    # costly error). NOTE: precision peaks at ~0.57 anywhere — the
    # future-work↔claim cosine is a weak signal; "addressed" is noisy and
    # Phase 4 must treat it as such. See docs/relationship-layer.md +
    # scratch/futurework_audit.md.
    rel_futurework_match_threshold: float = Field(
        default=0.74, alias="REL_FUTUREWORK_MATCH_THRESHOLD", ge=0.0, le=1.0
    )
    # Orphan (unaddressed) is corpus-relative: only callable when the
    # corpus holds enough LATER, TOPICALLY-NEAR papers that the addressing
    # work would plausibly have been seen. Below that -> indeterminate.
    # See docs/relationship-layer.md "Orphan judgments are corpus-relative".
    rel_futurework_topical_threshold: float = Field(
        default=0.65, alias="REL_FUTUREWORK_TOPICAL_THRESHOLD", ge=0.0, le=1.0
    )
    rel_futurework_min_near_later: int = Field(
        default=5, alias="REL_FUTUREWORK_MIN_NEAR_LATER", ge=1
    )

    # --- Phase 4 reasoning-engine weights (deterministic, NEVER LLM) ---
    # All chosen by hand with reasoning in docs/reasoning-engine.md. Every
    # scorer maps its raw signal to [0,1] and records named component_scores.
    reason_min_independent_papers: int = Field(
        default=3, alias="REASON_MIN_INDEPENDENT_PAPERS", ge=1
    )  # opportunity-criteria.md criterion 1 — the 3-paper floor.

    # Mixed-fidelity correction. A paper's evidence weight when COUNTING
    # independent papers. Full text over-detects own-work limitations ~11x
    # (docs/findings), so raw counts rank full-text/arXiv work. `abstract`
    # is up-weighted so an abstract-only report counts for more. Default 3.0
    # is a DAMPENED inverse-propensity: the full ~11x lets a single noisy
    # abstract paper dominate and defeats the 3-paper robustness intent, so
    # it is dampened. 1.0 = correction OFF (reported alongside). See
    # docs/reasoning-engine.md "Mixed-fidelity correction".
    reason_fidelity_weight_abstract: float = Field(
        default=3.0, alias="REASON_FIDELITY_WEIGHT_ABSTRACT", ge=1.0
    )
    reason_fidelity_weight_fulltext: float = Field(
        default=1.0, alias="REASON_FIDELITY_WEIGHT_FULLTEXT", ge=0.0
    )

    # Persistent-limitations component weights (sum used in a documented
    # blend, then squashed to [0,1]).
    reason_persist_w_count: float = Field(default=0.55, alias="REASON_PERSIST_W_COUNT")
    reason_persist_w_diversity: float = Field(default=0.25, alias="REASON_PERSIST_W_DIVERSITY")
    reason_persist_w_timespan: float = Field(default=0.20, alias="REASON_PERSIST_W_TIMESPAN")

    # Orphaned-future-work: minimum years unfollowed to be non-trivial
    # (opportunity-criteria.md non-triviality #3; defensible default 2).
    reason_orphan_min_years: int = Field(default=2, alias="REASON_ORPHAN_MIN_YEARS", ge=0)

    # Structural holes: number of paper clusters (k-means on mean claim
    # vectors) and the max citation edges between two clusters for them to
    # count as "weakly bridged".
    reason_n_clusters: int = Field(default=8, alias="REASON_N_CLUSTERS", ge=2)
    reason_weak_bridge_max_edges: int = Field(default=2, alias="REASON_WEAK_BRIDGE_MAX_EDGES", ge=0)
    reason_method_addresses_threshold: float = Field(
        default=0.72, alias="REASON_METHOD_ADDRESSES_THRESHOLD", ge=0.0, le=1.0
    )

    # Disjoint bridging (Swanson ABC): OFF by default — mostly noise until
    # validated (docs/reasoning-engine.md).
    reason_enable_disjoint_bridging: bool = Field(
        default=False, alias="REASON_ENABLE_DISJOINT_BRIDGING"
    )

    # Same-construct gate: for these OVERLOADED limitation categories, two
    # limitations must share a more-specific sub-construct before they
    # count toward the same persistent-limitations cluster. Measured:
    # "computational-cost" pools >=4 constructs (evaluation/training/
    # inference/sampling). Config list so more can be added when found.
    reason_gated_categories: list[str] = Field(
        default=["computational-cost", "high-computational-cost",
                 "computational-efficiency"],
        alias="REASON_GATED_CATEGORIES",
    )

    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    openalex_api_key: SecretStr | None = Field(default=None, alias="OPENALEX_API_KEY")
    semantic_scholar_api_key: SecretStr | None = Field(
        default=None, alias="SEMANTIC_SCHOLAR_API_KEY"
    )

    seed_dir: Path = Field(default=REPO_ROOT / "data" / "seed", alias="SEED_DIR")
    cache_dir: Path = Field(default=REPO_ROOT / "data" / "cache", alias="CACHE_DIR")

    @field_validator("seed_dir", "cache_dir", mode="before")
    @classmethod
    def _resolve_path(cls, v):
        p = Path(v) if not isinstance(v, Path) else v
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    # --- Capability flags — check these before making real network calls ---

    @property
    def can_use_openalex_live(self) -> bool:
        """OpenAlex mandates an API key per request since 2026-02-13.
        Unauthenticated traffic is capped at 100 credits/day and returns
        409 once exhausted. We refuse to make live calls without a key
        so ingestion never accidentally spends the shared daily quota."""
        return _secret_truthy(self.openalex_api_key)

    @property
    def can_use_gemini(self) -> bool:
        return _secret_truthy(self.gemini_api_key)

    @property
    def can_use_anthropic(self) -> bool:
        return _secret_truthy(self.anthropic_api_key)

    @property
    def has_database(self) -> bool:
        return _secret_truthy(self.database_url)

    def __repr__(self) -> str:
        return (
            f"Settings(environment={self.environment.value}, "
            f"openalex={'set' if self.can_use_openalex_live else 'unset'}, "
            f"gemini={'set' if self.can_use_gemini else 'unset'}, "
            f"anthropic={'set' if self.can_use_anthropic else 'unset'}, "
            f"database={'set' if self.has_database else 'unset'})"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Call this everywhere; do not construct
    Settings() directly."""
    return Settings()


__all__ = ["Environment", "Settings", "get_settings", "REPO_ROOT"]
