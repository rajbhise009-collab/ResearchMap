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


REAL_SPEND_FILES = (REPO_ROOT / "data" / "spend_ledger.json",
                    REPO_ROOT / "data" / "spend_projections.jsonl")


def _fingerprint(paths) -> dict:
    import hashlib
    return {str(p): (hashlib.sha256(p.read_bytes()).hexdigest()
                     if p.exists() else None) for p in paths}


@pytest.fixture(autouse=True, scope="session")
def _real_ledger_guard():
    """Fail the session if any test changed the real ledger or projection
    log. (Mock-transport client tests once leaked 200 5-token "unknown"
    entries into data/spend_ledger.json — see
    docs/findings/ledger-unknown-entries.md.)"""
    before = _fingerprint(REAL_SPEND_FILES)
    yield
    after = _fingerprint(REAL_SPEND_FILES)
    assert before == after, f"a test modified a real spend file: {before} -> {after}"


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    """Never let a test write to the real data/spend_ledger.json or
    data/spend_projections.jsonl: every default path points into tmp."""
    from backend.app.extraction import spend_ledger as sl
    monkeypatch.setenv("SPEND_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setenv("SPEND_PROJECTIONS_PATH", str(tmp_path / "projections.jsonl"))
    monkeypatch.setattr(sl.SpendLedger, "_instance",
                        sl.SpendLedger(path=tmp_path / "ledger.json"))
    yield
    sl.SpendLedger._instance = None


@pytest.fixture
def seed_dir() -> Path:
    return REPO_ROOT / "data" / "seed"


@pytest.fixture(autouse=True)
def _no_inherited_money_config(monkeypatch):
    """Tests are hermetic: a MONEY_CONFIG_PATH inherited from the caller (the
    weekly workflow's own end-to-end test sets one) must not apply the money
    rule to the temporary ledgers the spend tests create. A test that needs
    it sets it itself."""
    monkeypatch.delenv("MONEY_CONFIG_PATH", raising=False)
