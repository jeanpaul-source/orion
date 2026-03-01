"""Tests for hal/config.py required environment variable validation."""

import pytest

import hal.config as cfg


@pytest.fixture(autouse=True)
def _disable_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "load_dotenv", lambda: None)


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv(
        "PGVECTOR_DSN", "postgresql://kb_user:pw@localhost:5432/knowledge_base"
    )
    monkeypatch.setenv("PROMETHEUS_URL", "http://localhost:9091")
    monkeypatch.setenv("LAB_HOST", "192.168.5.10")
    monkeypatch.setenv("LAB_USER", "jp")


@pytest.mark.parametrize(
    "missing", ["OLLAMA_HOST", "PGVECTOR_DSN", "PROMETHEUS_URL", "LAB_HOST", "LAB_USER"]
)
def test_load_raises_when_required_env_var_missing(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.delenv(missing, raising=False)

    with pytest.raises(RuntimeError, match=rf"{missing}.*\.env\.example"):
        cfg.load()


def test_load_succeeds_when_required_vars_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    config = cfg.load()

    assert config.ollama_host == "http://localhost:11434"
    assert (
        config.pgvector_dsn == "postgresql://kb_user:pw@localhost:5432/knowledge_base"
    )
    assert config.prometheus_url == "http://localhost:9091"


def test_load_does_not_raise_when_optional_vars_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_URL", raising=False)

    config = cfg.load()

    assert config.tavily_api_key == ""
    assert config.telegram_bot_token == ""
    assert config.ntfy_url == ""
