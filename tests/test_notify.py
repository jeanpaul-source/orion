"""Tests for hal/notify.py — ntfy push notification sender.

All tests mock ``requests.post`` so no real HTTP calls happen.
We test: success, no-URL no-op, HTTP errors, connection errors, and custom params.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from hal.notify import send_ntfy_simple


def _mock_response(status_code: int = 200) -> MagicMock:
    """Build a fake requests.Response with the given status code."""
    resp = MagicMock()
    resp.status_code = status_code
    return resp


class TestSendNtfySimple:
    """Tests for send_ntfy_simple() — the shared notification function."""

    def test_success_returns_true(self):
        """A 200 response means the notification was delivered — returns True."""
        with patch(
            "hal.notify.requests.post", return_value=_mock_response(200)
        ) as mock_post:
            result = send_ntfy_simple("https://ntfy.sh/test-topic", ["Server is down"])
        assert result is True
        # Verify the right URL was called
        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == "https://ntfy.sh/test-topic"

    def test_no_url_returns_false(self):
        """When ntfy_url is empty, no HTTP call happens — returns False."""
        with patch("hal.notify.requests.post") as mock_post:
            result = send_ntfy_simple("", ["alert message"])
        assert result is False
        mock_post.assert_not_called()

    def test_none_url_returns_false(self):
        """None url is treated like empty — no crash, returns False."""
        with patch("hal.notify.requests.post") as mock_post:
            # The type hint says str, but callers may pass None from config
            result = send_ntfy_simple(None, ["alert message"])  # type: ignore[arg-type]
        assert result is False
        mock_post.assert_not_called()

    def test_http_error_returns_false(self):
        """HTTP 500 from ntfy server — returns False (doesn't crash)."""
        with patch("hal.notify.requests.post", return_value=_mock_response(500)):
            result = send_ntfy_simple("https://ntfy.sh/test-topic", ["alert"])
        assert result is False

    def test_connection_error_returns_false(self):
        """Network unreachable — returns False (doesn't crash)."""
        with patch(
            "hal.notify.requests.post",
            side_effect=requests.ConnectionError("refused"),
        ):
            result = send_ntfy_simple("https://ntfy.sh/test-topic", ["alert"])
        assert result is False

    def test_custom_title_and_tags(self):
        """Custom title, urgency, and tags are forwarded as HTTP headers."""
        with patch(
            "hal.notify.requests.post", return_value=_mock_response(200)
        ) as mock_post:
            send_ntfy_simple(
                "https://ntfy.sh/test-topic",
                ["line 1", "line 2"],
                urgency="urgent",
                title="Recovery Alert",
                tags="check,resolved",
            )
        # Check the headers include our custom values
        call_kwargs = mock_post.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["Title"] == "Recovery Alert"
        assert headers["Priority"] == "urgent"
        assert headers["Tags"] == "check,resolved"

    def test_messages_joined_as_body(self):
        """Multiple message lines are joined with newlines into the POST body."""
        with patch(
            "hal.notify.requests.post", return_value=_mock_response(200)
        ) as mock_post:
            send_ntfy_simple(
                "https://ntfy.sh/test-topic",
                ["line 1", "line 2", "line 3"],
            )
        # The body is the data= kwarg, encoded
        call_kwargs = mock_post.call_args[1]
        body = call_kwargs["data"]
        assert body == b"line 1\nline 2\nline 3"
