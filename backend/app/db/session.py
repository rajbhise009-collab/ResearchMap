"""Database session factory.

Lazily constructs a SQLAlchemy engine from `Settings.database_url`. If
DATABASE_URL is unset, `get_engine()` raises rather than silently
returning something usable — the offline seed pipeline does not touch
the DB, so needing one always indicates real-work intent.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import REPO_ROOT, get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine

    settings = get_settings()
    if not settings.has_database:
        raise RuntimeError(
            "DATABASE_URL is not set. Configure it in .env before using the DB. "
            "The offline seed pipeline does not require a database."
        )

    url = settings.database_url.get_secret_value()  # type: ignore[union-attr]
    _engine = create_engine(url, pool_pre_ping=True, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session() -> Session:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def list_migrations() -> list[Path]:
    """Return migration SQL files in lexical order."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def reset_for_tests() -> None:
    """Drop the cached engine — used by tests that swap DATABASE_URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


__all__ = [
    "MIGRATIONS_DIR",
    "REPO_ROOT",
    "get_engine",
    "get_session",
    "list_migrations",
    "reset_for_tests",
]
