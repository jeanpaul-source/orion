from __future__ import annotations

from types import SimpleNamespace

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
        "run_conversational",
        lambda *args, **kwargs: "final response",
    )

    old = dict(server._state)
    server._state.clear()
    server._state.update(
        {
            "config": SimpleNamespace(ntopng_url="http://ntopng", tavily_api_key="k"),
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
            "config": _ns(ntopng_url="http://ntopng", tavily_api_key="k"),
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
    """This proves to the user that /chat calls run_health when intent is health."""

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
        "run_health",
        lambda *args, **kwargs: "health check response",
    )

    old = dict(server._state)
    server._state.clear()
    server._state.update(
        {
            "config": _ns(ntopng_url="http://ntopng", tavily_api_key=""),
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
            "config": _ns(ntopng_url="http://ntopng", tavily_api_key="k"),
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
