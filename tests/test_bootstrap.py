"""Tests for hal/bootstrap.py — shared init used by REPL and HTTP server.

Tests get_system_prompt(), _connect(), _handle_conversational(), and
dispatch_intent(). setup_clients() is excluded (it connects to real services).
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from rich.console import Console

from hal import bootstrap
from hal.agent import AgentResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides: object) -> object:
    """Build a minimal Config-like namespace for get_system_prompt()."""
    defaults = {
        "vllm_url": "http://localhost:8000",
        "ollama_host": "http://localhost:11434",
        "prometheus_url": "http://localhost:9091",
        "ntopng_url": "http://localhost:3000",
        "lab_host": "192.168.5.10",
        "lab_user": "jp",
        "lab_hostname": "the-lab",
        "lab_hardware_summary": "",
        "chat_model": "Qwen/Qwen2.5-32B-Instruct-AWQ",
        "host_registry": {"lab": ("192.168.5.10", "jp")},
        "infra_base": "/opt/homelab-infrastructure",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _quiet_console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, no_color=True, width=120)


class _ScriptedLLM:
    """Minimal LLM stub for _handle_conversational."""

    def __init__(self, response: dict | Exception):
        self._response = response

    def chat_with_tools(self, messages, tools, system=""):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


# =========================================================================
# get_system_prompt()
# =========================================================================


class TestGetSystemPrompt:
    def test_contains_date(self):
        """The system prompt should include today's date."""
        config = _make_config()
        prompt = bootstrap.get_system_prompt(config)
        # Should contain a date string like "Friday, March 07, 2026"
        assert "2026" in prompt or "202" in prompt

    def test_contains_hal_identity(self):
        config = _make_config()
        prompt = bootstrap.get_system_prompt(config)
        assert "You are HAL" in prompt

    def test_contains_port_numbers_from_config(self):
        config = _make_config(
            vllm_url="http://localhost:8000",
            ollama_host="http://localhost:11434",
            prometheus_url="http://localhost:9091",
        )
        prompt = bootstrap.get_system_prompt(config)
        assert ":8000" in prompt
        assert ":11434" in prompt
        assert ":9091" in prompt

    def test_includes_hardware_when_configured(self):
        config = _make_config(
            lab_hardware_summary="RTX 3090 Ti, 64GB RAM, Ryzen 9 7950X"
        )
        prompt = bootstrap.get_system_prompt(config)
        assert "RTX 3090 Ti" in prompt

    def test_omits_hardware_when_not_configured(self):
        config = _make_config(lab_hardware_summary="")
        prompt = bootstrap.get_system_prompt(config)
        assert "Hardware:" not in prompt

    def test_includes_hostname_and_ip(self):
        config = _make_config(lab_hostname="the-lab", lab_host="192.168.5.10")
        prompt = bootstrap.get_system_prompt(config)
        assert "the-lab" in prompt
        assert "192.168.5.10" in prompt

    def test_shows_ip_only_when_no_hostname(self):
        config = _make_config(lab_hostname="", lab_host="192.168.5.10")
        prompt = bootstrap.get_system_prompt(config)
        assert "192.168.5.10" in prompt


# =========================================================================
# _connect()
# =========================================================================


class TestConnect:
    def test_returns_url_when_port_is_open(self, monkeypatch):
        """If the port is reachable, _connect returns the original URL with no tunnel."""
        monkeypatch.setattr(bootstrap, "port_open", lambda h, p: True)
        url, tunnel = bootstrap._connect(
            "vLLM", "http://localhost:8000", "jp", "192.168.5.10", 8000
        )
        assert url == "http://localhost:8000"
        assert tunnel is None

    def test_exits_when_localhost_port_closed(self, monkeypatch):
        """If the URL is localhost and the port is closed, sys.exit is called."""
        monkeypatch.setattr(bootstrap, "port_open", lambda h, p: False)
        with pytest.raises(SystemExit):
            bootstrap._connect(
                "vLLM", "http://localhost:8000", "jp", "192.168.5.10", 8000
            )

    def test_exits_when_lab_host_is_localhost_and_port_closed(self, monkeypatch):
        """If lab_host is localhost, tunnelling can't help -- exits."""
        monkeypatch.setattr(bootstrap, "port_open", lambda h, p: False)
        with pytest.raises(SystemExit):
            bootstrap._connect(
                "vLLM", "http://192.168.5.10:8000", "jp", "localhost", 8000
            )

    def test_tries_tunnel_when_remote_port_closed(self, monkeypatch):
        """If the port is closed but lab_host is remote, tries SSH tunnel."""
        call_count = 0

        def port_open_returns_false_then_true(host, port):
            nonlocal call_count
            call_count += 1
            return call_count > 1  # first call: closed, subsequent: open

        monkeypatch.setattr(bootstrap, "port_open", port_open_returns_false_then_true)

        tunnel_started = []

        class FakeTunnel:
            def __init__(self, *args):
                self.local_port = 8000

            def start(self):
                tunnel_started.append(True)

        monkeypatch.setattr(bootstrap, "SSHTunnel", FakeTunnel)

        _url, tunnel = bootstrap._connect(
            "vLLM", "http://192.168.5.10:8000", "jp", "192.168.5.10", 8000
        )
        assert tunnel is not None
        assert tunnel_started

    def test_exits_when_tunnel_fails(self, monkeypatch):
        """If the SSH tunnel fails to start, sys.exit is called."""
        monkeypatch.setattr(bootstrap, "port_open", lambda h, p: False)

        class FailingTunnel:
            def __init__(self, *args):
                pass

            def start(self):
                raise RuntimeError("tunnel failed")

            def stop(self):
                pass

        monkeypatch.setattr(bootstrap, "SSHTunnel", FailingTunnel)

        with pytest.raises(SystemExit):
            bootstrap._connect(
                "vLLM", "http://192.168.5.10:8000", "jp", "192.168.5.10", 8000
            )


# =========================================================================
# _handle_conversational()
# =========================================================================


class TestHandleConversational:
    def test_returns_response(self, memory_store):
        llm = _ScriptedLLM(
            {"role": "assistant", "content": "Hello there!", "tool_calls": None}
        )
        console = _quiet_console()
        sid = memory_store.new_session()
        history: list[dict] = []
        result = bootstrap._handle_conversational(
            "hello", history, llm, memory_store, sid, "system prompt", console
        )
        assert isinstance(result, AgentResult)
        assert "Hello there!" in result.response

    def test_saves_turns_to_memory(self, memory_store):
        llm = _ScriptedLLM({"role": "assistant", "content": "Hi!", "tool_calls": None})
        console = _quiet_console()
        sid = memory_store.new_session()
        history: list[dict] = []
        bootstrap._handle_conversational(
            "hello", history, llm, memory_store, sid, "system prompt", console
        )
        turns = memory_store.load_turns(sid)
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"

    def test_trims_history_to_40(self, memory_store):
        """If history exceeds 40 entries, it should be trimmed to the last 40."""
        llm = _ScriptedLLM({"role": "assistant", "content": "ok", "tool_calls": None})
        console = _quiet_console()
        sid = memory_store.new_session()
        # Pre-fill history with 42 entries (will be 44 after the call adds 2)
        history: list[dict] = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(42)
        ]
        bootstrap._handle_conversational(
            "hello", history, llm, memory_store, sid, "system prompt", console
        )
        # After appending 2 more entries (44 total), it should trim to 40
        assert len(history) == 40

    def test_handles_llm_error(self, memory_store):
        """When LLM raises, the error is returned and history is not modified."""
        llm = _ScriptedLLM(ConnectionError("vLLM is down"))
        console = _quiet_console()
        sid = memory_store.new_session()
        history: list[dict] = []
        result = bootstrap._handle_conversational(
            "hello", history, llm, memory_store, sid, "system prompt", console
        )
        assert "unavailable" in result.response.lower()
        # History should NOT be modified on error
        assert len(history) == 0


# =========================================================================
# dispatch_intent()
# =========================================================================


class TestDispatchIntent:
    def test_routes_conversational_to_handle_conversational(
        self, memory_store, monkeypatch
    ):
        """When classifier returns 'conversational', dispatch goes to _handle_conversational."""
        llm = _ScriptedLLM({"role": "assistant", "content": "Hi!", "tool_calls": None})
        console = _quiet_console()
        sid = memory_store.new_session()

        class FakeClassifier:
            def classify(self, text):
                return ("conversational", 0.95)

        # We don't need run_agent for this path
        result = bootstrap.dispatch_intent(
            "hello",
            [],
            llm,
            SimpleNamespace(health=dict),  # prom
            SimpleNamespace(search=lambda *a, **kw: []),  # kb
            SimpleNamespace(
                default=SimpleNamespace(), get=lambda *a: SimpleNamespace()
            ),  # registry
            SimpleNamespace(approve=lambda *a, **kw: True),  # judge
            memory_store,
            sid,
            "system prompt",
            console,
            classifier=FakeClassifier(),
        )
        assert "Hi!" in str(result)

    def test_routes_health_to_run_agent(self, memory_store, monkeypatch):
        """Non-conversational intents (health, fact, agentic) go to run_agent."""
        called_run_agent = []

        def fake_run_agent(*args, **kwargs):
            called_run_agent.append(True)
            return AgentResult(response="All systems nominal.")

        monkeypatch.setattr(bootstrap, "run_agent", fake_run_agent)
        console = _quiet_console()
        sid = memory_store.new_session()

        class FakeClassifier:
            def classify(self, text):
                return ("health", 0.90)

        result = bootstrap.dispatch_intent(
            "how's the lab?",
            [],
            SimpleNamespace(chat_with_tools=lambda *a, **kw: {}),
            SimpleNamespace(health=dict),
            SimpleNamespace(search=lambda *a, **kw: []),
            SimpleNamespace(
                default=SimpleNamespace(), get=lambda *a: SimpleNamespace()
            ),
            SimpleNamespace(approve=lambda *a, **kw: True),
            memory_store,
            sid,
            "system prompt",
            console,
            classifier=FakeClassifier(),
        )
        assert called_run_agent
        assert "nominal" in str(result)

    def test_routes_to_run_agent_when_no_classifier(self, memory_store, monkeypatch):
        """When classifier=None, everything goes to run_agent."""
        called_run_agent = []

        def fake_run_agent(*args, **kwargs):
            called_run_agent.append(True)
            return AgentResult(response="Agent response.")

        monkeypatch.setattr(bootstrap, "run_agent", fake_run_agent)
        console = _quiet_console()
        sid = memory_store.new_session()

        bootstrap.dispatch_intent(
            "what is docker?",
            [],
            SimpleNamespace(chat_with_tools=lambda *a, **kw: {}),
            SimpleNamespace(health=dict),
            SimpleNamespace(search=lambda *a, **kw: []),
            SimpleNamespace(
                default=SimpleNamespace(), get=lambda *a: SimpleNamespace()
            ),
            SimpleNamespace(approve=lambda *a, **kw: True),
            memory_store,
            sid,
            "system prompt",
            console,
            classifier=None,
        )
        assert called_run_agent
