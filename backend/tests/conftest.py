"""Shared test fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make sure the tests import from THIS checkout regardless of installed
# packages of the same name.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    """Every test starts with a clean env — no live network by accident.

    We SET each secret to empty rather than DELETE it, because
    pydantic-settings falls back to `.env` on the developer's machine
    when the env var is absent. Setting an empty string wins over any
    file value.
    """
    for var in (
        "OPENALEX_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
        "DATABASE_URL",
    ):
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("RESEARCHMAP_ENV", "test")

    # Reset the cached Settings singleton so env changes are picked up.
    from backend.app import config as cfg
    cfg.get_settings.cache_clear()
    yield
    cfg.get_settings.cache_clear()


@pytest.fixture
def seed_dir() -> Path:
    return REPO_ROOT / "data" / "seed"
