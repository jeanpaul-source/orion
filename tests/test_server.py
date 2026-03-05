from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import hal.bootstrap as bootstrap
import hal.server as server
from hal.sanitize import strip_tool_call_artifacts

_ns = SimpleNamespace  # short alias used by /chat routing tests


def test_health_ok_when_startup_healthy() -> None:
    """This proves to the user that /health reports healthy startup state."""
    old = dict(server._state)
    server._state.clear()
    server._state.update({"config": object()})
    try:
        client = TestClient(server.app)
        resp = client.get("/health")
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_degraded_with_startup_error_detail() -> None:
    """This proves to the user that /health surfaces degraded startup error details."""
    old = dict(server._state)
    server._state.clear()
    server._state["_startup_error"] = "Services unavailable"
    try:
        client = TestClient(server.app)
        resp = client.get("/health")
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "degraded",
        "detail": "Services unavailable",
    }


def test_chat_returns_503_when_startup_degraded() -> None:
    """This proves to the user that /chat blocks requests while startup is degraded."""
    old = dict(server._state)
    server._state.clear()
    server._state["_startup_error"] = "Services unavailable"
    try:
        client = TestClient(server.app)
        resp = client.post("/chat", json={"message": "hello"})
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Services unavailable"


def test_chat_returns_503_when_server_uninitialized() -> None:
    """This proves to the user that /chat rejects requests before state initialization."""
    old = dict(server._state)
    server._state.clear()
    try:
        client = TestClient(server.app)
        resp = client.post("/chat", json={"message": "hello"})
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Server not yet initialised"


def test_strip_tool_call_blocks_strips_hallucinated_tool_call_json_fences() -> None:
    """Hallucinated tool-call JSON fences are removed by strip_tool_call_artifacts."""
    text = (
        "Before\n"
        "```json\n"
        '{"name":"web_search","arguments":{"query":"latest"}}\n'
        "```\n"
        "After"
    )

    out = strip_tool_call_artifacts(text)

    assert out == "Before\n\nAfter"


def test_strip_tool_call_blocks_preserves_normal_json_fences() -> None:
    """Ordinary JSON code fences are preserved unchanged by strip_tool_call_artifacts."""
    text = 'Payload:\n```json\n{"cpu_pct":35.5,"status":"ok"}\n```'

    out = strip_tool_call_artifacts(text)

    assert out == text


def test_chat_happy_path_returns_response_session_and_intent(monkeypatch) -> None:
    """This proves to the user that /chat returns the stable response/session_id/intent contract."""

    class _Mem:
        def session_exists(self, _sid: str) -> bool:
            return True

        def create_session(self, _sid: str) -> None:
            return None

        def last_session_id(self) -> str:
            return "sess-1"

        def new_session(self) -> str:
            return "sess-new"

        def load_turns(self, _sid: str) -> list[dict[str, str]]:
            return [{"role": "user", "content": "old"}]

        def close(self) -> None:
            return None

    class _Classifier:
        def classify(self, _msg: str) -> tuple[str, float]:
            return "conversational", 0.9

    async def _fake_to_thread(fn):
        return fn()

    monkeypatch.setattr(server.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(server, "MemoryStore", _Mem)
    monkeypatch.setattr(
        bootstrap,
        "run_agent",
        lambda *args, **kwargs: "final response",
    )

    old = dict(server._state)
    server._state.clear()
    server._state.update(
        {
            "config": SimpleNamespace(
                ntopng_url="http://ntopng",
                tavily_api_key="k",
                vllm_url="http://localhost:8000",
                ollama_host="http://localhost:11434",
                prometheus_url="http://localhost:9091",
                chat_model="test-model",
                infra_base="/opt/infra",
                lab_hostname="test-lab",
                lab_hardware_summary="",
                lab_host="127.0.0.1",
            ),
            "classifier": _Classifier(),
            "llm": object(),
            "kb": object(),
            "prom": object(),
            "executor": object(),
            "judge": object(),
        }
    )
    try:
        client = TestClient(server.app)
        resp = client.post("/chat", json={"message": "hi", "session_id": "sess-1"})
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    assert resp.json() == {
        "response": "final response",
        "session_id": "sess-1",
        "intent": "conversational",
    }


def test_chat_routes_agentic_intent_and_returns_response(monkeypatch) -> None:
    """This proves to the user that /chat calls run_agent when intent is agentic."""

    class _Mem:
        def session_exists(self, _sid: str) -> bool:
            return False

        def create_session(self, _sid: str) -> None:
            return None

        def last_session_id(self) -> str:
            return "sess-a"

        def new_session(self) -> str:
            return "sess-a"

        def load_turns(self, _sid: str) -> list[dict[str, str]]:
            return []

        def close(self) -> None:
            return None

    class _Classifier:
        def classify(self, _msg: str) -> tuple[str, float]:
            return "agentic", 0.78

    async def _fake_to_thread(fn):
        return fn()

    monkeypatch.setattr(server.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(server, "MemoryStore", _Mem)
    monkeypatch.setattr(
        bootstrap,
        "run_agent",
        lambda *args, **kwargs: "agentic response text",
    )

    old = dict(server._state)
    server._state.clear()
    server._state.update(
        {
            "config": _ns(
                ntopng_url="http://ntopng",
                tavily_api_key="k",
                vllm_url="http://localhost:8000",
                ollama_host="http://localhost:11434",
                prometheus_url="http://localhost:9091",
                chat_model="test-model",
                infra_base="/opt/infra",
                lab_hostname="test-lab",
                lab_hardware_summary="",
                lab_host="127.0.0.1",
            ),
            "classifier": _Classifier(),
            "llm": object(),
            "kb": object(),
            "prom": object(),
            "executor": object(),
            "judge": object(),
        }
    )
    try:
        client = TestClient(server.app)
        resp = client.post("/chat", json={"message": "check lab for issues"})
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "agentic response text"
    assert body["intent"] == "agentic"


def test_chat_routes_health_intent_and_returns_response(monkeypatch) -> None:
    """This proves to the user that /chat calls run_agent for all intents (Layer 0)."""

    class _Mem:
        def session_exists(self, _sid: str) -> bool:
            return False

        def create_session(self, _sid: str) -> None:
            return None

        def last_session_id(self) -> str:
            return "sess-h"

        def new_session(self) -> str:
            return "sess-h"

        def load_turns(self, _sid: str) -> list[dict[str, str]]:
            return []

        def close(self) -> None:
            return None

    class _Classifier:
        def classify(self, _msg: str) -> tuple[str, float]:
            return "health", 0.91

    async def _fake_to_thread(fn):
        return fn()

    monkeypatch.setattr(server.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(server, "MemoryStore", _Mem)
    monkeypatch.setattr(
        bootstrap,
        "run_agent",
        lambda *args, **kwargs: "health check response",
    )

    old = dict(server._state)
    server._state.clear()
    server._state.update(
        {
            "config": _ns(
                ntopng_url="http://ntopng",
                tavily_api_key="",
                vllm_url="http://localhost:8000",
                ollama_host="http://localhost:11434",
                prometheus_url="http://localhost:9091",
                chat_model="test-model",
                infra_base="/opt/infra",
                lab_hostname="test-lab",
                lab_hardware_summary="",
                lab_host="127.0.0.1",
            ),
            "classifier": _Classifier(),
            "llm": object(),
            "kb": object(),
            "prom": object(),
            "executor": object(),
            "judge": object(),
        }
    )
    try:
        client = TestClient(server.app)
        resp = client.post("/chat", json={"message": "how is the server?"})
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "health check response"
    assert body["intent"] == "health"


def test_chat_strips_fenced_tool_call_blocks_from_agentic_response(monkeypatch) -> None:
    """This proves that the server strips fenced ```json tool-call blocks from run_agent output."""

    class _Mem:
        def session_exists(self, _sid: str) -> bool:
            return False

        def create_session(self, _sid: str) -> None:
            return None

        def last_session_id(self) -> str:
            return "sess-strip"

        def new_session(self) -> str:
            return "sess-strip"

        def load_turns(self, _sid: str) -> list[dict[str, str]]:
            return []

        def close(self) -> None:
            return None

    class _Classifier:
        def classify(self, _msg: str) -> tuple[str, float]:
            return "agentic", 0.80

    # Fenced tool-call block — handled by server._strip_tool_call_blocks
    fenced_artifact = (
        "Clean prose.\n"
        "```json\n"
        '{"name": "run_command", "arguments": {"command": "ls"}}\n'
        "```"
    )

    async def _fake_to_thread(fn):
        return fn()

    monkeypatch.setattr(server.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(server, "MemoryStore", _Mem)
    monkeypatch.setattr(
        bootstrap,
        "run_agent",
        lambda *args, **kwargs: fenced_artifact,
    )

    old = dict(server._state)
    server._state.clear()
    server._state.update(
        {
            "config": _ns(
                ntopng_url="http://ntopng",
                tavily_api_key="k",
                vllm_url="http://localhost:8000",
                ollama_host="http://localhost:11434",
                prometheus_url="http://localhost:9091",
                chat_model="test-model",
                infra_base="/opt/infra",
                lab_hostname="test-lab",
                lab_hardware_summary="",
                lab_host="127.0.0.1",
            ),
            "classifier": _Classifier(),
            "llm": object(),
            "kb": object(),
            "prom": object(),
            "executor": object(),
            "judge": object(),
        }
    )
    try:
        client = TestClient(server.app)
        resp = client.post("/chat", json={"message": "run a health check"})
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    response_text = resp.json()["response"]
    # The fenced block must be stripped by the server
    assert "```json" not in response_text
    assert "run_command" not in response_text
    assert "Clean prose." in response_text


# ---------------------------------------------------------------------------
# Boot-order retry mechanism tests
# ---------------------------------------------------------------------------


def test_populate_state_sets_clients_and_clears_error() -> None:
    """_populate_state fills _state with clients and removes degraded markers."""
    old = dict(server._state)
    server._state.clear()
    server._state["_startup_error"] = "fail"
    server._state["_retry_task"] = "dummy"
    try:
        config = _ns(
            pgvector_dsn="postgresql://localhost/test",
            prometheus_url="http://localhost:9091",
            lab_host="127.0.0.1",
            lab_user="jp",
            judge_extra_sensitive_paths="",
        )
        llm = MagicMock()
        embed = MagicMock()
        with (
            patch.object(server, "KnowledgeBase"),
            patch.object(server, "PrometheusClient"),
            patch.object(server, "SSHExecutor"),
            patch.object(server, "IntentClassifier"),
        ):
            server._populate_state(config, llm, embed, [])

        assert "_startup_error" not in server._state
        assert "_retry_task" not in server._state
        assert server._state["llm"] is llm
        assert server._state["embed"] is embed
    finally:
        server._state.clear()
        server._state.update(old)


def test_retry_init_succeeds_after_failures() -> None:
    """_retry_init retries and populates state when backends eventually come up."""
    old = dict(server._state)
    server._state.clear()
    server._state["_startup_error"] = "fail"

    call_count = 0

    def fake_setup(cfg):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise SystemExit(1)
        return MagicMock(), MagicMock(), []

    try:
        with (
            patch.object(server, "setup_clients", side_effect=fake_setup),
            patch.object(server, "_populate_state") as mock_pop,
            patch.object(server, "_RETRY_DELAY", 0),
            patch.object(server, "_MAX_RETRIES", 5),
        ):
            asyncio.run(server._retry_init(_ns()))

        assert call_count == 3
        assert mock_pop.called
    finally:
        server._state.clear()
        server._state.update(old)


def test_retry_init_gives_up_after_max_retries() -> None:
    """_retry_init stops after _MAX_RETRIES without populating state."""
    old = dict(server._state)
    server._state.clear()
    server._state["_startup_error"] = "fail"

    try:
        with (
            patch.object(server, "setup_clients", side_effect=SystemExit(1)),
            patch.object(server, "_populate_state") as mock_pop,
            patch.object(server, "_RETRY_DELAY", 0),
            patch.object(server, "_MAX_RETRIES", 3),
        ):
            asyncio.run(server._retry_init(_ns()))

        assert not mock_pop.called
        assert "_startup_error" in server._state
    finally:
        server._state.clear()
        server._state.update(old)


def test_health_degraded_shows_retry_message() -> None:
    """Health endpoint shows 'Retrying in background' when retry is active."""
    old = dict(server._state)
    server._state.clear()
    server._state["_startup_error"] = (
        "Services unavailable (exit 1). Retrying in background..."
    )
    try:
        client = TestClient(server.app)
        resp = client.get("/health")
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert "Retrying" in body["detail"]


def test_server_service_unit_has_vllm_after_dependency() -> None:
    """The systemd unit file orders server.service after vllm.service."""
    from pathlib import Path

    unit = Path(__file__).parent.parent / "ops" / "server.service"
    content = unit.read_text()
    assert "After=" in content
    assert "vllm.service" in content


def test_retry_constants_sensible() -> None:
    """Retry constants allow at least 5 minutes of retry time."""
    total = server._RETRY_DELAY * server._MAX_RETRIES
    assert total >= 300, f"Total retry window {total}s < 300s"
    assert server._RETRY_DELAY >= 10, "Retry delay too aggressive"


def test_log_recovery_event_writes_audit_entry(tmp_path) -> None:
    """_log_recovery_event writes a structured JSON-lines entry to the audit log."""
    import json

    fake_log = tmp_path / "audit.log"
    with patch.object(server, "AUDIT_LOG", fake_log):
        server._log_recovery_event(attempt=3, elapsed_seconds=45)

    lines = fake_log.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action"] == "system"
    assert entry["detail"] == "recovered_from_degraded_start"
    assert entry["status"] == "auto"
    assert entry["tier"] == 0
    assert "attempt 3" in entry["reason"]
    assert "45s" in entry["reason"]
    assert "ts" in entry


def test_health_includes_recovery_metadata_after_degraded_start() -> None:
    """After recovery from degraded start, /health includes last_recovery and recovery_attempts."""
    old = dict(server._state)
    server._state.clear()
    server._state.update(
        {
            "config": object(),
            "_last_recovery": "2026-03-04T20:15:00+00:00",
            "_recovery_attempts": 3,
        }
    )
    try:
        client = TestClient(server.app)
        resp = client.get("/health")
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["last_recovery"] == "2026-03-04T20:15:00+00:00"
    assert body["recovery_attempts"] == 3


def test_health_omits_recovery_metadata_on_clean_start() -> None:
    """On clean start (no recovery), /health returns only status: ok."""
    old = dict(server._state)
    server._state.clear()
    server._state.update({"config": object()})
    try:
        client = TestClient(server.app)
        resp = client.get("/health")
    finally:
        server._state.clear()
        server._state.update(old)

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}
    assert "last_recovery" not in body
    assert "recovery_attempts" not in body


def test_retry_init_sends_ntfy_on_recovery() -> None:
    """_retry_init sends an ntfy notification when recovery succeeds."""
    import asyncio
    from types import SimpleNamespace as NS

    fake_config = NS(
        pgvector_dsn="postgresql://x",
        prometheus_url="http://x:9090",
        lab_host="localhost",
        lab_user="jp",
        judge_extra_sensitive_paths="",
        ntfy_url="https://ntfy.example.com/test",
    )

    fake_llm = MagicMock()
    fake_embed = MagicMock()

    with (
        patch.object(server, "_RETRY_DELAY", 0),
        patch.object(server, "_MAX_RETRIES", 2),
        patch("hal.server.setup_clients", return_value=(fake_llm, fake_embed, [])),
        patch("hal.server._populate_state"),
        patch("hal.server._log_recovery_event"),
        patch("hal.server.send_ntfy_simple") as mock_ntfy,
    ):
        asyncio.run(server._retry_init(fake_config))

    mock_ntfy.assert_called_once()
    call_args = mock_ntfy.call_args
    assert call_args[0][0] == "https://ntfy.example.com/test"
    assert "recover" in call_args[0][1][0].lower()
    assert call_args[1]["title"] == "Orion Recovery — the-lab"
    assert "white_check_mark" in call_args[1]["tags"]


def test_retry_init_skips_ntfy_when_url_empty() -> None:
    """_retry_init does not send ntfy when ntfy_url is empty."""
    import asyncio
    from types import SimpleNamespace as NS

    fake_config = NS(
        pgvector_dsn="postgresql://x",
        prometheus_url="http://x:9090",
        lab_host="localhost",
        lab_user="jp",
        judge_extra_sensitive_paths="",
        ntfy_url="",
    )

    fake_llm = MagicMock()
    fake_embed = MagicMock()

    with (
        patch.object(server, "_RETRY_DELAY", 0),
        patch.object(server, "_MAX_RETRIES", 2),
        patch("hal.server.setup_clients", return_value=(fake_llm, fake_embed, [])),
        patch("hal.server._populate_state"),
        patch("hal.server._log_recovery_event"),
        patch("hal.server.send_ntfy_simple") as mock_ntfy,
    ):
        asyncio.run(server._retry_init(fake_config))

    mock_ntfy.assert_not_called()
