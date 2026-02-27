"""Unit tests for hal/telegram.py — all offline, no real Telegram API needed.

Run with: pytest tests/test_telegram.py -v
"""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hal._unlocked.telegram import (
    _get_session_id,
    _sanitize,
    _sessions,
    cmd_new,
    cmd_start,
    handle_message,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_update(user_id: int = 123, chat_id: int = 123, text: str = "hi"):
    """Build a minimal mock Update with the fields the handlers read."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    thinking = AsyncMock()
    thinking.edit_text = AsyncMock()
    update.message.reply_text.return_value = thinking
    return update, thinking


# ---------------------------------------------------------------------------
# _sanitize
# ---------------------------------------------------------------------------


class TestSanitize:
    def test_short_text_unchanged(self):
        assert _sanitize("hello") == "hello"

    def test_truncates_long_text(self):
        long = "x" * 5000
        result = _sanitize(long)
        assert len(result) <= 4096
        assert result.endswith("\n[…]")

    def test_redacts_secret_paths(self):
        text = "Loaded /run/homelab-secrets/monitoring-stack.env into memory"
        result = _sanitize(text)
        assert "/run/homelab-secrets/" not in result
        assert "[redacted]" in result

    def test_multiple_secret_paths(self):
        text = "Read /run/homelab-secrets/a.env and /run/homelab-secrets/b.env"
        result = _sanitize(text)
        assert result.count("[redacted]") == 2

    def test_normal_paths_untouched(self):
        text = "Config at /opt/homelab-infrastructure/monitoring-stack/"
        assert _sanitize(text) == text


# ---------------------------------------------------------------------------
# _get_session_id
# ---------------------------------------------------------------------------


class TestSessionId:
    def setup_method(self):
        _sessions.clear()

    def test_default_session_id(self):
        assert _get_session_id(12345) == "tg-12345"

    def test_override_session_id(self):
        _sessions[12345] = "tg-12345-1700000000"
        assert _get_session_id(12345) == "tg-12345-1700000000"

    def test_fallback_after_clear(self):
        _sessions[12345] = "tg-12345-1700000000"
        del _sessions[12345]
        assert _get_session_id(12345) == "tg-12345"


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class TestAuth:
    """Auth checks — handlers must silently ignore unauthorized users."""

    @pytest.fixture(autouse=True)
    def _set_allowed_user(self):
        import hal._unlocked.telegram as mod

        original = mod.ALLOWED_USER_ID
        mod.ALLOWED_USER_ID = 999
        yield
        mod.ALLOWED_USER_ID = original

    def test_authorized_user_gets_reply(self):
        update, _ = _make_update(user_id=999)
        asyncio.run(cmd_start(update, None))
        update.message.reply_text.assert_called_once()

    def test_unauthorized_user_ignored(self):
        update, _ = _make_update(user_id=666)
        asyncio.run(cmd_start(update, None))
        update.message.reply_text.assert_not_called()

    def test_none_user_ignored(self):
        update, _ = _make_update(user_id=999)
        update.effective_user = None
        asyncio.run(cmd_start(update, None))
        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# /new command
# ---------------------------------------------------------------------------


class TestCmdNew:
    @pytest.fixture(autouse=True)
    def _set_allowed_user(self):
        import hal._unlocked.telegram as mod

        original = mod.ALLOWED_USER_ID
        mod.ALLOWED_USER_ID = 999
        _sessions.clear()
        yield
        mod.ALLOWED_USER_ID = original
        _sessions.clear()

    def test_new_resets_session(self):
        update, _ = _make_update(user_id=999, chat_id=42)
        asyncio.run(cmd_new(update, None))
        sid = _sessions[42]
        assert sid.startswith("tg-42-")
        assert re.match(r"tg-42-\d+$", sid)

    def test_new_replies_confirmation(self):
        update, _ = _make_update(user_id=999, chat_id=42)
        asyncio.run(cmd_new(update, None))
        update.message.reply_text.assert_called_once_with("Session reset.")


# ---------------------------------------------------------------------------
# handle_message — integration (mocked HTTP)
# ---------------------------------------------------------------------------


class TestHandleMessage:
    @pytest.fixture(autouse=True)
    def _set_allowed_user(self):
        import hal._unlocked.telegram as mod

        original = mod.ALLOWED_USER_ID
        mod.ALLOWED_USER_ID = 999
        _sessions.clear()
        yield
        mod.ALLOWED_USER_ID = original
        _sessions.clear()

    def test_successful_response(self):
        update, thinking = _make_update(user_id=999, text="what is CPU usage?")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": "CPU is at 35%.",
            "session_id": "tg-123",
            "intent": "health",
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("hal._unlocked.telegram.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(handle_message(update, None))

        thinking.edit_text.assert_called_once_with("CPU is at 35%.")

    def test_connect_error_shows_offline(self):
        update, thinking = _make_update(user_id=999, text="hello")

        with patch("hal._unlocked.telegram.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=__import__("httpx").ConnectError("refused")
            )
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(handle_message(update, None))

        thinking.edit_text.assert_called_once()
        assert "offline" in thinking.edit_text.call_args[0][0].lower()

    def test_503_shows_starting_up(self):
        update, thinking = _make_update(user_id=999, text="hello")

        import httpx as httpx_mod

        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch("hal._unlocked.telegram.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx_mod.HTTPStatusError(
                    "503", request=MagicMock(), response=mock_response
                )
            )
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(handle_message(update, None))

        thinking.edit_text.assert_called_once()
        assert "starting up" in thinking.edit_text.call_args[0][0].lower()

    def test_unauthorized_message_ignored(self):
        update, thinking = _make_update(user_id=666, text="hello")
        asyncio.run(handle_message(update, None))
        # No "thinking..." sent, no edit
        update.message.reply_text.assert_not_called()
