"""Tests for hal/web.py — web_search, fetch_url, and query/URL sanitisation.

All tests are offline — Tavily SDK is mocked, HTTP requests are mocked.
No API key or network access needed.

Run with: pytest tests/test_web.py -v
"""

from __future__ import annotations

import socket
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from hal._unlocked.web import (
    _is_private_ip,
    _validate_url,
    fetch_url,
    sanitize_query,
    web_search,
)

# ---------------------------------------------------------------------------
# Tavily mock fixture — injects a fake tavily module so the lazy import works
# ---------------------------------------------------------------------------

_mock_tavily_client_cls = MagicMock()


def _install_mock_tavily():
    """Install a fake 'tavily' module into sys.modules."""
    mod = ModuleType("tavily")
    mod.TavilyClient = _mock_tavily_client_cls  # type: ignore[attr-defined]
    sys.modules["tavily"] = mod
    return _mock_tavily_client_cls


@pytest.fixture(autouse=True)
def _reset_tavily_mock():
    """Reset the mock before each test and clean up after."""
    _mock_tavily_client_cls.reset_mock()
    cls = _install_mock_tavily()
    yield cls
    sys.modules.pop("tavily", None)


# ---------------------------------------------------------------------------
# sanitize_query — privacy guard
# ---------------------------------------------------------------------------


class TestSanitizeQuery:
    """Query sanitisation strips private IPs and hostnames."""

    def test_strips_rfc1918_10(self):
        assert "10.0.0.1" not in sanitize_query("check 10.0.0.1 for updates")

    def test_strips_rfc1918_172(self):
        assert "172.16.5.3" not in sanitize_query("is 172.16.5.3 reachable?")

    def test_strips_rfc1918_192(self):
        assert "192.168.5.10" not in sanitize_query("scan 192.168.5.10 for CVEs")

    def test_strips_loopback(self):
        assert "127.0.0.1" not in sanitize_query("connect to 127.0.0.1:8000")

    def test_strips_tailscale_cgnat(self):
        assert "100.82.66.91" not in sanitize_query("check 100.82.66.91 status")

    def test_strips_localhost(self):
        result = sanitize_query("connect to localhost and check")
        assert "localhost" not in result

    def test_strips_the_lab(self):
        result = sanitize_query("check the-lab for disk usage")
        assert "the-lab" not in result

    def test_strips_dot_local(self):
        result = sanitize_query("resolve myhost.local DNS")
        assert ".local" not in result

    def test_strips_dot_internal(self):
        result = sanitize_query("access .internal service")
        assert ".internal" not in result

    def test_preserves_public_query(self):
        query = "latest version of prometheus"
        assert sanitize_query(query) == query

    def test_collapses_whitespace(self):
        result = sanitize_query("check  192.168.5.10  for updates")
        assert "  " not in result
        assert result == "check for updates"

    def test_empty_after_stripping_raises(self):
        with pytest.raises(ValueError, match="only private"):
            sanitize_query("192.168.5.10")

    def test_only_hostname_raises(self):
        with pytest.raises(ValueError, match="only private"):
            sanitize_query("localhost")

    def test_mixed_private_and_public(self):
        result = sanitize_query("update 192.168.5.10 falco to latest")
        assert "192.168.5.10" not in result
        assert "falco" in result
        assert "latest" in result

    def test_preserves_public_ips(self):
        result = sanitize_query("check 8.8.8.8 DNS resolver")
        assert "8.8.8.8" in result


# ---------------------------------------------------------------------------
# web_search — Tavily integration
# ---------------------------------------------------------------------------


class TestWebSearch:
    """web_search function with mocked Tavily SDK."""

    def test_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="TAVILY_API_KEY"):
            web_search("test query", api_key="")

    def test_returns_formatted_results(self):
        mock_client = MagicMock()
        _mock_tavily_client_cls.return_value = mock_client
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "Prometheus Release",
                    "url": "https://example.com/prom",
                    "content": "Prometheus 2.50 is now available.",
                    "score": 0.95,
                },
                {
                    "title": "Grafana News",
                    "url": "https://example.com/grafana",
                    "content": "Grafana 11 released with new features.",
                    "score": 0.88,
                },
            ]
        }

        results = web_search("latest prometheus version", api_key="test-key")

        assert len(results) == 2
        assert results[0]["title"] == "Prometheus Release"
        assert results[0]["url"] == "https://example.com/prom"
        assert results[0]["score"] == 0.95
        assert "2.50" in results[0]["content"]

    def test_sanitizes_query_before_sending(self):
        mock_client = MagicMock()
        _mock_tavily_client_cls.return_value = mock_client
        mock_client.search.return_value = {"results": []}

        web_search("check 192.168.5.10 falco version", api_key="test-key")

        call_args = mock_client.search.call_args
        sent_query = call_args.kwargs.get("query", call_args[1].get("query", ""))
        assert "192.168.5.10" not in sent_query
        assert "falco" in sent_query

    def test_empty_results(self):
        mock_client = MagicMock()
        _mock_tavily_client_cls.return_value = mock_client
        mock_client.search.return_value = {"results": []}

        results = web_search("obscure query", api_key="test-key")
        assert results == []

    def test_max_results_passed_through(self):
        mock_client = MagicMock()
        _mock_tavily_client_cls.return_value = mock_client
        mock_client.search.return_value = {"results": []}

        web_search("test", api_key="test-key", max_results=3)

        call_args = mock_client.search.call_args
        assert call_args.kwargs.get("max_results", call_args[1].get("max_results")) == 3

    def test_only_private_data_raises(self):
        """Query that is entirely private IPs should fail before reaching Tavily."""
        with pytest.raises(ValueError, match="only private"):
            web_search("192.168.5.10 127.0.0.1 localhost", api_key="test-key")


# ---------------------------------------------------------------------------
# _is_private_ip — low-level IP classification
# ---------------------------------------------------------------------------


class TestIsPrivateIp:
    """_is_private_ip correctly classifies private and public addresses."""

    def test_loopback(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_rfc1918_10(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_rfc1918_172(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_rfc1918_192(self):
        assert _is_private_ip("192.168.5.10") is True

    def test_link_local(self):
        assert _is_private_ip("169.254.1.1") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_public_ip_2(self):
        assert _is_private_ip("151.101.1.140") is False

    def test_invalid_string(self):
        assert _is_private_ip("not-an-ip") is False

    def test_ipv6_loopback(self):
        assert _is_private_ip("::1") is True


# ---------------------------------------------------------------------------
# _validate_url — SSRF protection
# ---------------------------------------------------------------------------


def _fake_addrinfo_public(host, port, **kwargs):
    """Return a fake getaddrinfo result pointing to a public IP."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]


def _fake_addrinfo_private(host, port, **kwargs):
    """Return a fake getaddrinfo result pointing to a private IP (DNS rebinding)."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 443))]


def _fake_addrinfo_rfc1918(host, port, **kwargs):
    """Return a fake getaddrinfo result pointing to 192.168.x (rebinding)."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", port or 443))]


class TestValidateUrl:
    """URL validation blocks SSRF vectors."""

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_public)
    def test_valid_https_url(self, _mock):
        result = _validate_url("https://example.com/page")
        assert result == "https://example.com/page"

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_public)
    def test_valid_http_url(self, _mock):
        result = _validate_url("http://example.com/page")
        assert result == "http://example.com/page"

    def test_blocks_file_scheme(self):
        with pytest.raises(ValueError, match="Blocked scheme"):
            _validate_url("file:///etc/passwd")

    def test_blocks_ftp_scheme(self):
        with pytest.raises(ValueError, match="Blocked scheme"):
            _validate_url("ftp://example.com/file")

    def test_blocks_gopher_scheme(self):
        with pytest.raises(ValueError, match="Blocked scheme"):
            _validate_url("gopher://evil.com/")

    def test_blocks_localhost(self):
        with pytest.raises(ValueError, match="Blocked private hostname"):
            _validate_url("https://localhost/admin")

    def test_blocks_dot_local(self):
        with pytest.raises(ValueError, match="Blocked private hostname"):
            _validate_url("https://myhost.local/api")

    def test_blocks_dot_internal(self):
        with pytest.raises(ValueError, match="Blocked private hostname"):
            _validate_url("https://service.internal/data")

    def test_blocks_dot_onion(self):
        with pytest.raises(ValueError, match="Blocked private hostname"):
            _validate_url("https://something.onion/page")

    def test_blocks_literal_private_ip(self):
        with pytest.raises(ValueError, match="Blocked private"):
            _validate_url("http://192.168.5.10:8000/secret")

    def test_blocks_literal_loopback(self):
        with pytest.raises(ValueError, match="Blocked private"):
            _validate_url("http://127.0.0.1:8000/admin")

    def test_blocks_literal_10_network(self):
        with pytest.raises(ValueError, match="Blocked private"):
            _validate_url("http://10.0.0.1/internal")

    def test_missing_hostname(self):
        with pytest.raises(ValueError, match="no hostname"):
            _validate_url("https:///path-only")

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_private)
    def test_dns_rebinding_to_loopback(self, _mock):
        """DNS rebinding: hostname resolves to 127.0.0.1 — must be blocked."""
        with pytest.raises(ValueError, match="private IP.*rebinding"):
            _validate_url("https://evil-rebind.example.com/steal")

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_rfc1918)
    def test_dns_rebinding_to_rfc1918(self, _mock):
        """DNS rebinding: hostname resolves to 192.168.x — must be blocked."""
        with pytest.raises(ValueError, match="private IP.*rebinding"):
            _validate_url("https://rebind.attacker.com/exfil")

    @patch(
        "hal._unlocked.web.socket.getaddrinfo",
        side_effect=socket.gaierror("DNS failed"),
    )
    def test_dns_failure(self, _mock):
        with pytest.raises(ValueError, match="DNS resolution failed"):
            _validate_url("https://nonexistent.invalid/page")


# ---------------------------------------------------------------------------
# fetch_url — page content extraction
# ---------------------------------------------------------------------------


class TestFetchUrl:
    """fetch_url with mocked HTTP and trafilatura."""

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_public)
    def test_successful_fetch(self, _mock_dns):
        """Happy path: fetch + extract article text."""
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/article"
        mock_resp.iter_content = MagicMock(
            return_value=[
                b"<html><body><p>Important article content here.</p></body></html>"
            ]
        )
        mock_resp.raise_for_status = MagicMock()

        with patch("hal._unlocked.web.requests.get", return_value=mock_resp):
            with patch(
                "hal._unlocked.web.trafilatura.extract",
                return_value="Important article content here.",
            ):
                result = fetch_url("https://example.com/article")

        assert "Important article content here." in result

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_public)
    def test_output_truncation(self, _mock_dns):
        """Output longer than max_chars should be truncated with a marker."""
        long_text = "x" * 20_000
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/long"
        mock_resp.iter_content = MagicMock(return_value=[b"<html>long</html>"])
        mock_resp.raise_for_status = MagicMock()

        with patch("hal._unlocked.web.requests.get", return_value=mock_resp):
            with patch("hal._unlocked.web.trafilatura.extract", return_value=long_text):
                result = fetch_url("https://example.com/long", max_chars=500)

        assert len(result.split("\n\n--- [content truncated")[0]) == 500
        assert "truncated" in result

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_public)
    def test_trafilatura_fallback(self, _mock_dns):
        """When trafilatura returns None, fall back to tag stripping."""
        html = b"<html><body><p>Fallback text for testing.</p></body></html>"
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/fallback"
        mock_resp.iter_content = MagicMock(return_value=[html])
        mock_resp.raise_for_status = MagicMock()

        with patch("hal._unlocked.web.requests.get", return_value=mock_resp):
            with patch("hal._unlocked.web.trafilatura.extract", return_value=None):
                result = fetch_url("https://example.com/fallback")

        assert "Fallback text for testing." in result

    def test_ssrf_blocked_before_fetch(self):
        """SSRF validation runs before any HTTP request is made."""
        with pytest.raises(ValueError, match="Blocked private"):
            fetch_url("http://192.168.5.10:8000/secret")

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_public)
    def test_redirect_to_private_blocked(self, _mock_dns):
        """If a redirect lands on a private IP, re-validation must catch it."""
        mock_resp = MagicMock()
        mock_resp.url = "http://127.0.0.1:8000/admin"  # redirect target
        mock_resp.iter_content = MagicMock(return_value=[b"secret"])
        mock_resp.raise_for_status = MagicMock()

        with patch("hal._unlocked.web.requests.get", return_value=mock_resp):
            with pytest.raises(ValueError, match="Blocked private"):
                fetch_url("https://legit-looking.example.com/redirect")

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_public)
    def test_http_error_raises_runtime(self, _mock_dns):
        """HTTP errors should raise RuntimeError, not leak raw exceptions."""
        import requests as req

        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/404"
        mock_resp.raise_for_status.side_effect = req.HTTPError("404 Not Found")

        with patch("hal._unlocked.web.requests.get", return_value=mock_resp):
            with pytest.raises(req.HTTPError):
                fetch_url("https://example.com/404")

    @patch("hal._unlocked.web.socket.getaddrinfo", side_effect=_fake_addrinfo_public)
    def test_response_size_cap(self, _mock_dns):
        """Responses larger than 1 MB should be truncated during read."""
        # Simulate large response with multiple chunks
        big_chunk = b"x" * 600_000
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/huge"
        mock_resp.iter_content = MagicMock(return_value=[big_chunk, big_chunk])
        mock_resp.raise_for_status = MagicMock()

        with patch("hal._unlocked.web.requests.get", return_value=mock_resp):
            with patch(
                "hal._unlocked.web.trafilatura.extract", return_value="extracted"
            ):
                result = fetch_url("https://example.com/huge")

        # Should succeed — the size cap truncates but doesn't error
        assert result == "extracted"
