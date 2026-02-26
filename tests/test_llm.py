"""Offline tests for hal.llm fallback tool-call extraction behavior."""

import json

from hal.llm import VLLMClient


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _mock_chat_payload(content: str, tool_calls: list | None = None) -> dict:
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def test_chat_with_tools_fallback_off_by_default_no_injection(monkeypatch):
    payload = _mock_chat_payload(
        '<tool_call>{"name":"run_command","arguments":{"command":"whoami"}}</tool_call>'
    )

    def _fake_post(*_args, **_kwargs):
        return _FakeResponse(payload)

    monkeypatch.delenv("HAL_EXTRACT_FALLBACK", raising=False)
    monkeypatch.setattr("hal.llm.requests.post", _fake_post)

    client = VLLMClient("http://example", "fake-model")
    result = client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "run_command"}}],
    )

    assert result.get("tool_calls") is None
    assert "<tool_call>" in result["content"]


def test_chat_with_tools_fallback_on_parses_valid_tags(monkeypatch):
    payload = _mock_chat_payload(
        '<tool_call>{"name":"run_command","arguments":{"command":"whoami"}}</tool_call>'
    )

    def _fake_post(*_args, **_kwargs):
        return _FakeResponse(payload)

    monkeypatch.setenv("HAL_EXTRACT_FALLBACK", "1")
    monkeypatch.setattr("hal.llm.requests.post", _fake_post)

    client = VLLMClient("http://example", "fake-model")
    result = client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "run_command"}}],
    )

    assert result["content"] is None
    assert len(result["tool_calls"]) == 1
    call = result["tool_calls"][0]
    assert call["function"]["name"] == "run_command"
    assert json.loads(call["function"]["arguments"]) == {"command": "whoami"}


def test_chat_with_tools_malformed_or_partial_tags_do_not_crash(monkeypatch):
    payload = _mock_chat_payload(
        'prefix <tool_call>{"name":"run_command","arguments":</tool_call>'
    )

    def _fake_post(*_args, **_kwargs):
        return _FakeResponse(payload)

    monkeypatch.setenv("HAL_EXTRACT_FALLBACK", "1")
    monkeypatch.setattr("hal.llm.requests.post", _fake_post)

    client = VLLMClient("http://example", "fake-model")
    result = client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "run_command"}}],
    )

    assert result.get("tool_calls") is None
    assert "prefix" in result["content"]


def test_chat_with_tools_partial_open_tag_does_not_crash_with_or_without_flag(
    monkeypatch,
):
    payload = _mock_chat_payload('here is a literal <tool_call>{"name": "oops"')

    def _fake_post(*_args, **_kwargs):
        return _FakeResponse(payload)

    monkeypatch.setattr("hal.llm.requests.post", _fake_post)
    client = VLLMClient("http://example", "fake-model")

    monkeypatch.delenv("HAL_EXTRACT_FALLBACK", raising=False)
    result_off = client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "run_command"}}],
    )
    assert result_off.get("tool_calls") is None

    monkeypatch.setenv("HAL_EXTRACT_FALLBACK", "1")
    result_on = client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "run_command"}}],
    )
    assert result_on.get("tool_calls") is None
    assert "<tool_call>" in result_on["content"]
