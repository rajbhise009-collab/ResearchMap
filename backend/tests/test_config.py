"""Settings resolution + capability flags."""

from __future__ import annotations


def test_settings_default_environment_is_test_in_this_process():
    from backend.app.config import get_settings
    settings = get_settings()
    assert settings.environment.value == "test"


def test_capability_flags_false_when_env_is_empty():
    from backend.app.config import get_settings
    settings = get_settings()
    assert settings.can_use_openalex_live is False
    assert settings.can_use_gemini is False
    assert settings.can_use_anthropic is False
    assert settings.has_database is False


def test_capability_flags_flip_when_env_set(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "oa-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-XYZ")
    from backend.app import config as cfg
    cfg.get_settings.cache_clear()
    settings = cfg.get_settings()
    assert settings.can_use_openalex_live is True
    assert settings.can_use_gemini is True


def test_settings_repr_does_not_leak_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-SUPER-SECRET-VALUE")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@host/db")
    from backend.app import config as cfg
    cfg.get_settings.cache_clear()
    repr_str = repr(cfg.get_settings())
    assert "SUPER-SECRET-VALUE" not in repr_str
    assert "pw" not in repr_str
