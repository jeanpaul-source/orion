"""Tests for hal/llm.py — VLLMClient and OllamaClient.

All tests mock ``requests`` so no real network calls happen.
We test the public API: does each method return the right type on success,
and handle errors (HTTP errors, timeouts, connection failures) gracefully?
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from hal.llm import OllamaClient, VLLMClient

# ---------------------------------------------------------------------------
# Helpers — build fake HTTP responses
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Build a fake ``requests.Response`` object.

    ``json_data`` is what ``.json()`` returns.
    ``raise_for_status()`` raises on 4xx/5xx just like real requests.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(
            f"{status_code} Server Error"
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# VLLMClient.chat()
# ---------------------------------------------------------------------------


class TestVLLMChat:
    """Tests for VLLMClient.chat() — plain text responses."""

    def test_chat_returns_content(self):
        """chat() returns the text content from the LLM response."""
        client = VLLMClient("http://fake:8000", "test-model")
        fake_resp = _mock_response(
            200,
            {
                "choices": [{"message": {"content": "Hello from the LLM"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
        with patch("hal.llm.requests.post", return_value=fake_resp):
            result = client.chat([{"role": "user", "content": "hi"}])
        assert result == "Hello from the LLM"
        assert isinstance(result, str)

    def test_chat_with_system_prompt(self):
        """When a system prompt is provided, _messages() prepends it."""
        client = VLLMClient("http://fake:8000", "test-model")
        fake_resp = _mock_response(
            200,
            {"choices": [{"message": {"content": "ok"}}]},
        )
        with patch("hal.llm.requests.post", return_value=fake_resp) as mock_post:
            client.chat([{"role": "user", "content": "hi"}], system="You are HAL.")
        # Verify the system message was included in the payload
        payload = mock_post.call_args[1]["json"]
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "You are HAL."

    def test_chat_http_error_raises(self):
        """chat() re-raises on HTTP 500 (after logging and recording metrics)."""
        client = VLLMClient("http://fake:8000", "test-model")
        fake_resp = _mock_response(500)
        with (
            patch("hal.llm.requests.post", return_value=fake_resp),
            pytest.raises(requests.HTTPError),
        ):
            client.chat([{"role": "user", "content": "hi"}])

    def test_chat_404_raises_runtime_error(self):
        """404 means the model is still loading — chat() raises RuntimeError with a helpful message."""
        client = VLLMClient("http://fake:8000", "test-model")
        fake_resp = _mock_response(404)
        # Override raise_for_status so it doesn't fire before our 404 check
        fake_resp.raise_for_status.side_effect = None
        with (
            patch("hal.llm.requests.post", return_value=fake_resp),
            pytest.raises(RuntimeError, match="still loading"),
        ):
            client.chat([{"role": "user", "content": "hi"}])

    def test_chat_timeout_raises(self):
        """If the HTTP request times out, the exception propagates."""
        client = VLLMClient("http://fake:8000", "test-model")
        with (
            patch("hal.llm.requests.post", side_effect=requests.Timeout("timed out")),
            pytest.raises(requests.Timeout),
        ):
            client.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# VLLMClient.chat_with_tools()
# ---------------------------------------------------------------------------


class TestVLLMChatWithTools:
    """Tests for VLLMClient.chat_with_tools() — tool-calling responses."""

    def test_returns_message_dict_with_tool_calls(self):
        """chat_with_tools() returns the full message dict, including tool_calls."""
        client = VLLMClient("http://fake:8000", "test-model")
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_metrics", "arguments": "{}"},
        }
        fake_resp = _mock_response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call],
                        }
                    }
                ],
            },
        )
        with patch("hal.llm.requests.post", return_value=fake_resp):
            result = client.chat_with_tools(
                [{"role": "user", "content": "check health"}],
                tools=[{"type": "function", "function": {"name": "get_metrics"}}],
            )
        assert isinstance(result, dict)
        assert result["tool_calls"] == [tool_call]

    def test_returns_text_when_no_tool_calls(self):
        """When the LLM responds with text (no tools), tool_calls is None/absent."""
        client = VLLMClient("http://fake:8000", "test-model")
        fake_resp = _mock_response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Everything looks fine.",
                            "tool_calls": None,
                        }
                    }
                ],
            },
        )
        with patch("hal.llm.requests.post", return_value=fake_resp):
            result = client.chat_with_tools(
                [{"role": "user", "content": "is the lab ok?"}],
                tools=[],
            )
        assert result["content"] == "Everything looks fine."

    def test_http_error_raises(self):
        """chat_with_tools() re-raises HTTP errors."""
        client = VLLMClient("http://fake:8000", "test-model")
        fake_resp = _mock_response(500)
        with (
            patch("hal.llm.requests.post", return_value=fake_resp),
            pytest.raises(requests.HTTPError),
        ):
            client.chat_with_tools([{"role": "user", "content": "hi"}], tools=[])

    def test_404_raises_runtime_error(self):
        """404 = model still loading — RuntimeError with clear message."""
        client = VLLMClient("http://fake:8000", "test-model")
        fake_resp = _mock_response(404)
        fake_resp.raise_for_status.side_effect = None
        with (
            patch("hal.llm.requests.post", return_value=fake_resp),
            pytest.raises(RuntimeError, match="still loading"),
        ):
            client.chat_with_tools([{"role": "user", "content": "hi"}], tools=[])


# ---------------------------------------------------------------------------
# VLLMClient.ping()
# ---------------------------------------------------------------------------


class TestVLLMPing:
    """Tests for VLLMClient.ping() — checks if vLLM is ready."""

    def test_ping_healthy(self):
        """ping() returns True when /health returns 200."""
        client = VLLMClient("http://fake:8000", "test-model")
        with patch("hal.llm.requests.get", return_value=_mock_response(200)):
            assert client.ping() is True

    def test_ping_unhealthy(self):
        """ping() returns False when /health returns 503 (model loading)."""
        client = VLLMClient("http://fake:8000", "test-model")
        with patch("hal.llm.requests.get", return_value=_mock_response(503)):
            assert client.ping() is False

    def test_ping_connection_error(self):
        """ping() returns False when the server is unreachable (not an unhandled crash)."""
        client = VLLMClient("http://fake:8000", "test-model")
        with patch(
            "hal.llm.requests.get",
            side_effect=requests.ConnectionError("refused"),
        ):
            assert client.ping() is False


# ---------------------------------------------------------------------------
# OllamaClient.embed()
# ---------------------------------------------------------------------------


class TestOllamaEmbed:
    """Tests for OllamaClient.embed() — text to embedding vector."""

    def test_embed_returns_vector(self):
        """embed() returns a list of floats (the embedding vector)."""
        client = OllamaClient("http://fake:11434", "nomic-embed-text")
        # 768 dimensions is what nomic-embed-text produces
        vector = [0.1] * 768
        fake_resp = _mock_response(200, {"embedding": vector})
        with patch("hal.llm.requests.post", return_value=fake_resp):
            result = client.embed("hello world")
        assert isinstance(result, list)
        assert len(result) == 768
        assert all(isinstance(v, float) for v in result)

    def test_embed_http_error_raises(self):
        """embed() raises on HTTP 500 (Ollama down/overloaded)."""
        client = OllamaClient("http://fake:11434", "nomic-embed-text")
        fake_resp = _mock_response(500)
        with (
            patch("hal.llm.requests.post", return_value=fake_resp),
            pytest.raises(requests.HTTPError),
        ):
            client.embed("hello")


# ---------------------------------------------------------------------------
# OllamaClient.ping()
# ---------------------------------------------------------------------------


class TestOllamaPing:
    """Tests for OllamaClient.ping() — checks if Ollama is reachable."""

    def test_ping_healthy(self):
        """ping() returns True when /api/tags returns 200."""
        client = OllamaClient("http://fake:11434", "nomic-embed-text")
        with patch("hal.llm.requests.get", return_value=_mock_response(200)):
            assert client.ping() is True

    def test_ping_unreachable(self):
        """ping() returns False on ConnectionError (Ollama not running)."""
        client = OllamaClient("http://fake:11434", "nomic-embed-text")
        with patch(
            "hal.llm.requests.get",
            side_effect=requests.ConnectionError("refused"),
        ):
            assert client.ping() is False

    def test_ping_non_200(self):
        """ping() returns False on non-200 status codes."""
        client = OllamaClient("http://fake:11434", "nomic-embed-text")
        with patch("hal.llm.requests.get", return_value=_mock_response(500)):
            assert client.ping() is False
