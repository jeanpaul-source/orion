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


# ---------------------------------------------------------------------------
# LLM sampling parameter defaults and overrides
# ---------------------------------------------------------------------------


def test_llm_sampling_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM sampling params should use Qwen-recommended defaults when unset."""
    _set_required_env(monkeypatch)
    # Explicitly remove LLM env vars so we hit defaults
    for var in ("LLM_TEMPERATURE", "LLM_TOP_P", "LLM_MIN_P", "LLM_REPETITION_PENALTY"):
        monkeypatch.delenv(var, raising=False)

    config = cfg.load()

    assert config.llm_temperature == 0.7
    assert config.llm_top_p == 0.8
    assert config.llm_min_p == 0.05
    assert config.llm_repetition_penalty == 1.05


def test_llm_sampling_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM sampling params should be overridable via env vars."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LLM_TEMPERATURE", "0.3")
    monkeypatch.setenv("LLM_TOP_P", "0.9")
    monkeypatch.setenv("LLM_MIN_P", "0.10")
    monkeypatch.setenv("LLM_REPETITION_PENALTY", "1.2")

    config = cfg.load()

    assert config.llm_temperature == 0.3
    assert config.llm_top_p == 0.9
    assert config.llm_min_p == 0.10
    assert config.llm_repetition_penalty == 1.2


# ---------------------------------------------------------------------------
# Host registry property tests
# ---------------------------------------------------------------------------


def test_host_registry_default_lab_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty EXTRA_HOSTS → only the 'lab' entry from LAB_HOST/LAB_USER."""
    _set_required_env(monkeypatch)
    monkeypatch.delenv("EXTRA_HOSTS", raising=False)

    config = cfg.load()

    assert config.host_registry == {"lab": ("192.168.5.10", "jp")}


def test_host_registry_with_extra_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Single EXTRA_HOSTS entry adds a second host alongside lab."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("EXTRA_HOSTS", "laptop:jp@192.168.5.20")

    config = cfg.load()

    assert "lab" in config.host_registry
    assert config.host_registry["laptop"] == ("192.168.5.20", "jp")


def test_host_registry_multiple_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple comma-separated EXTRA_HOSTS entries all appear in the registry."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("EXTRA_HOSTS", "laptop:jp@192.168.5.20,nas:admin@192.168.5.30")

    config = cfg.load()

    assert len(config.host_registry) == 3
    assert config.host_registry["laptop"] == ("192.168.5.20", "jp")
    assert config.host_registry["nas"] == ("192.168.5.30", "admin")


def test_host_registry_skips_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed entries are silently skipped; valid entries still parsed."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("EXTRA_HOSTS", "badentry,also bad,ok:jp@10.0.0.1")

    config = cfg.load()

    assert len(config.host_registry) == 2  # lab + ok
    assert config.host_registry["ok"] == ("10.0.0.1", "jp")
    assert "badentry" not in config.host_registry


def test_host_registry_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace around entries and name/user/host is stripped."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("EXTRA_HOSTS", " laptop : jp@192.168.5.20 ")

    config = cfg.load()

    assert config.host_registry["laptop"] == ("192.168.5.20", "jp")
