"""Shared test fixtures for the HAL test suite.

conftest.py is a special pytest file — fixtures defined here are automatically
available to all test files in this directory without needing to import them.
"""

from __future__ import annotations

import os

import pytest

from hal.intent import IntentClassifier  # why: intent.py graduated to Layer 1
from hal.judge import Judge
from hal.llm import OllamaClient

# Read Ollama URL from environment, defaulting to server-local address.
# On the laptop, set OLLAMA_HOST=http://192.168.5.10:11434 before running tests.
_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text:latest")


# ---------------------------------------------------------------------------
# Integration test doubles — used by tests/test_integration.py
# ---------------------------------------------------------------------------


class ScriptedLLM:
    """Replays pre-defined LLM responses in order.

    LLM response format (matches VLLMClient.chat_with_tools output):
        {"role": "assistant", "content": "text", "tool_calls": None}
        or
        {"role": "assistant", "content": None, "tool_calls": [...]}
    """

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self._index = 0
        self.call_count = 0
        self.calls: list[dict] = []  # record every call for assertions

    def chat_with_tools(
        self, messages: list[dict], tools: list[dict], system: str = ""
    ) -> dict:
        self.call_count += 1
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "system": system,
            }
        )
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        # Exhausted — return a safe text-only fallback
        return {"role": "assistant", "content": "Done.", "tool_calls": None}

    def ping(self) -> bool:
        return True

    def chat(self, messages, system="", timeout=30):
        """Used by Judge._llm_reason — return a stub."""
        return "Routine operation, low risk."


class ScriptedExecutor:
    """Returns pre-defined outputs for shell commands.

    Usage:
        executor = ScriptedExecutor({
            "ps aux": {"stdout": "PID ...", "stderr": "", "returncode": 0},
        })
    """

    def __init__(self, responses: dict[str, dict] | None = None):
        self._responses = responses or {}
        self.commands_run: list[str] = []  # track what was executed

    def run(self, command: str) -> dict:
        self.commands_run.append(command)
        # Exact match first
        if command in self._responses:
            return self._responses[command]
        # Prefix match (e.g. "ps" matches "ps aux")
        for pattern, result in self._responses.items():
            if command.startswith(pattern):
                return result
        # Default: command not configured
        return {
            "stdout": f"[scripted: no output configured for '{command}']",
            "stderr": "",
            "returncode": 0,
        }


class FakeClassifier:
    """Returns a fixed intent classification for any input."""

    def __init__(self, intent: str, confidence: float = 0.95):
        self._intent = intent
        self._confidence = confidence

    def classify(self, text: str) -> tuple[str, float]:
        return (self._intent, self._confidence)


class StubKB:
    """Knowledge base stub with canned search results."""

    def __init__(self, results: list[dict] | None = None):
        self._results = results or []

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        return self._results[:top_k]


class StubProm:
    """Prometheus client stub with canned health data."""

    def __init__(self, health_data: dict | None = None):
        self._health = health_data or {
            "cpu_pct": 12.5,
            "mem_pct": 45.0,
            "disk_root_pct": 38.0,
            "disk_docker_pct": None,
            "disk_data_pct": None,
            "swap_pct": 2.0,
            "load1": 0.5,
            "gpu_vram_pct": 60.0,
            "gpu_temp_c": 55,
        }

    def health(self) -> dict:
        return self._health

    def trend(self, promql: str, window: str = "1h") -> dict | None:
        return {
            "first": 10.0,
            "last": 12.0,
            "min": 9.5,
            "max": 13.0,
            "delta": 2.0,
            "delta_per_hour": 2.0,
            "direction": "rising",
        }


# ---------------------------------------------------------------------------
# Integration test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_audit_log(tmp_path):
    """Temporary audit log path for Judge tests."""
    return tmp_path / "audit.log"


@pytest.fixture
def real_judge(tmp_audit_log):
    """Real Judge instance with temporary audit log, auto-deny mode."""

    class AutoDenyJudge(Judge):
        """Judge that auto-denies any tier > 0 (like ServerJudge)."""

        def _request_approval(self, action_type, detail, tier, reason):
            return False

    return AutoDenyJudge(audit_log=tmp_audit_log)


@pytest.fixture
def auto_approve_judge(tmp_audit_log):
    """Real Judge that auto-approves everything (for tests that need it)."""

    class AutoApproveJudge(Judge):
        def _request_approval(self, action_type, detail, tier, reason):
            return True

    return AutoApproveJudge(audit_log=tmp_audit_log)


@pytest.fixture
def scripted_executor():
    """ScriptedExecutor with no pre-configured responses."""
    return ScriptedExecutor()


@pytest.fixture
def stub_kb():
    """Empty KB stub."""
    return StubKB()


@pytest.fixture
def stub_prom():
    """Prometheus stub with default healthy metrics."""
    return StubProm()


@pytest.fixture
def memory_store(tmp_path, monkeypatch):
    """Real MemoryStore backed by a temporary SQLite database."""
    import hal.memory as _mem

    monkeypatch.setattr(_mem, "DB_PATH", tmp_path / "memory.db")
    store = _mem.MemoryStore()
    yield store
    store.close()


@pytest.fixture
def quiet_console():
    """Silent Rich console for tests."""
    from rich.console import Console

    return Console(quiet=True)


# ---------------------------------------------------------------------------
# Ollama-dependent fixtures (existing)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def classifier():
    """
    Real IntentClassifier built with the live embedding model.

    scope="session" means this is created ONCE for the entire test run —
    all 39 example sentences are embedded at startup, then reused for every test.
    This keeps the test suite fast (one batch of embed calls, not one per test).

    Requires Ollama to be running. If unreachable, tests are skipped via the
    autouse fixture below.
    """
    ollama = OllamaClient(
        base_url=_OLLAMA_HOST,
        embed_model=_EMBED_MODEL,
    )
    return IntentClassifier(ollama)


@pytest.fixture(scope="session")
def require_ollama(classifier):
    """
    Skip Ollama-dependent tests when the embedding model is unreachable.

    NOT autouse — only tests that explicitly request this fixture (or modules
    that declare pytestmark = pytest.mark.usefixtures("require_ollama")) will
    be skipped.  Pure unit tests (judge, memory) must not be affected by
    Ollama availability.
    """
    if not classifier._ready:
        pytest.skip(
            f"Ollama not reachable at {_OLLAMA_HOST} — "
            "intent classifier could not build embeddings. "
            "Start Ollama and re-run, or set OLLAMA_HOST to the correct URL."
        )
