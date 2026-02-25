"""Tests for hal/web.py — web_search tool and query sanitisation.

All tests are offline — Tavily SDK is mocked. No API key needed.

Run with: pytest tests/test_web.py -v
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from hal.web import sanitize_query, web_search

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
# get_tools — tool registry
# ---------------------------------------------------------------------------


class TestGetTools:
    """get_tools() returns the right tool set based on config."""

    def test_base_tools_always_present(self):
        from hal.agent import get_tools

        tools = get_tools()
        names = [t["function"]["name"] for t in tools]
        assert "search_kb" in names
        assert "run_command" in names
        assert "get_metrics" in names

    def test_web_search_excluded_without_key(self):
        from hal.agent import get_tools

        tools = get_tools()
        names = [t["function"]["name"] for t in tools]
        assert "web_search" not in names

    def test_web_search_included_with_key(self):
        from hal.agent import get_tools

        tools = get_tools(tavily_api_key="sk-test-123")
        names = [t["function"]["name"] for t in tools]
        assert "web_search" in names

    def test_empty_key_excludes_web_search(self):
        from hal.agent import get_tools

        tools = get_tools(tavily_api_key="")
        names = [t["function"]["name"] for t in tools]
        assert "web_search" not in names

    def test_returns_new_list_each_call(self):
        """Ensure get_tools() doesn't mutate _BASE_TOOLS."""
        from hal.agent import get_tools

        tools_a = get_tools()
        tools_b = get_tools(tavily_api_key="key")
        assert len(tools_b) == len(tools_a) + 1
        # Call again without key — should still be the base length
        tools_c = get_tools()
        assert len(tools_c) == len(tools_a)
