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
    monkeypatch.delenv("RUN_CAP_LEDGER_INR", raising=False)



_RUN_CONTROLS_AND_SECRETS = (
    # the weekly run's controls: a test must never inherit a SCHEDULED event
    # (or a manual run's inputs) from the run whose preflight is executing it
    "GROW_EVENT", "GROW_RUN_BUDGET_INR", "GROW_BUILD_QUEUED", "GROW_GATES_ONLY", "GROW_ISSUE_MARKER",
    "GROW_FAIL_GATE", "GROW_STEPS", "WEEKLY_BUDGET_INR",
    # GitHub credentials (the API keys are BLANKED by _isolated_env above,
    # which beats .env; deleting them would let .env show through)
    "GH_TOKEN", "GITHUB_TOKEN",
)


@pytest.fixture(autouse=True)
def _no_run_controls_or_secrets(monkeypatch):
    """Tests are hermetic: weekly-grow's preflight runs this suite inside a
    scheduled run, whose environment holds GROW_EVENT=schedule and the API
    keys. A test calling run_weekly.main() must never take the live path
    with them (it once could have: a gates_only test fell through to a full
    run inside pytest)."""
    for k in _RUN_CONTROLS_AND_SECRETS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _no_github_output_files(monkeypatch):
    """Tests never write to the workflow's own output files. On the runner
    GITHUB_STEP_SUMMARY etc. point at the live job: a test that exercises
    the summary writer (with deliberately failing fake gates) once put a
    fake 'smoke: FAIL' table into the real gates_only run's summary."""
    for k in ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_PATH", "GITHUB_STATE"):
        monkeypatch.delenv(k, raising=False)


# On the workflow runner (CI=1) the safety checks must RUN, never skip: a
# skip there would let a publish through unchecked. Any skip in these
# modules becomes a failure with the skip reason.
_NEVER_SKIP_ON_RUNNER = (
    "backend/tests/api/test_safety_queries.py",      # distress handling
    "backend/tests/api/test_rendered_output.py",     # banned phrases in the built site
    "backend/tests/api/test_public_claims.py",       # banned phrases / public claims
    "backend/tests/api/test_language.py",
    "backend/tests/api/test_consistency.py",         # cross-surface consistency
    "backend/tests/api/test_hardening.py",           # incl. no full text shipped
    "backend/tests/extraction/test_money.py",        # the money rule
    "backend/tests/extraction/test_spend_ledger.py",
    "backend/tests/extraction/test_spend_gate.py",
)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if (rep.skipped and os.environ.get("CI")
            and any(item.nodeid.startswith(m) for m in _NEVER_SKIP_ON_RUNNER)):
        rep.outcome = "failed"
        rep.longrepr = f"safety test skipped on the runner (CI=1): {rep.longrepr}"
