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
