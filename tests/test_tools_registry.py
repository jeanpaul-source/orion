"""Focused tests for hal.tools registry behavior."""

from unittest.mock import MagicMock

from hal.tools import TOOL_REGISTRY, ToolContext, dispatch_tool, get_tools

_CTX = ToolContext(
    executor=MagicMock(),
    judge=MagicMock(),
    kb=MagicMock(),
    prom=MagicMock(),
)


def test_get_tools_returns_layer0_tool_set():
    """Active tool set without Tavily key: 13 tools (web_search is key-gated)."""
    names = [tool["function"]["name"] for tool in get_tools()]
    assert set(names) == {
        "search_kb",
        "get_metrics",
        "get_trend",
        "run_command",
        "read_file",
        "list_dir",
        "write_file",
        "fetch_url",
        "get_action_stats",
        # Layer 3 security tools (Stage 3b)
        "get_security_events",
        "get_host_connections",
        "get_traffic_summary",
        "scan_lan",
    }
    # With a Tavily key, web_search is also included (14 tools total)
    names_with_key = [
        tool["function"]["name"] for tool in get_tools(tavily_api_key="k")
    ]
    assert set(names_with_key) == set(names) | {"web_search"}


def test_dispatch_tool_unknown_name_returns_clear_error():
    """Unknown tool names keep the existing string contract."""
    out = dispatch_tool(
        name="does_not_exist",
        args={},
        ctx=_CTX,
    )
    assert out == "Unknown tool: does_not_exist"


def test_dispatch_tool_uses_registry_handler():
    """dispatch_tool must route through TOOL_REGISTRY handler lookup."""
    handler = MagicMock(return_value="registry-ok")
    original = TOOL_REGISTRY["search_kb"]
    TOOL_REGISTRY["search_kb"] = {
        "schema": original["schema"],
        "handler": handler,
        "enabled": original["enabled"],
    }
    try:
        out = dispatch_tool(
            name="search_kb",
            args={"query": "x"},
            ctx=_CTX,
        )
    finally:
        TOOL_REGISTRY["search_kb"] = original

    assert out == "registry-ok"
    handler.assert_called_once()


# ---------------------------------------------------------------------------
# get_trend tool handler tests
# ---------------------------------------------------------------------------


def _ctx_with_trend(trend_return):
    """Build a ToolContext whose prom.trend() returns the given value."""
    prom_stub = MagicMock()
    prom_stub.trend.return_value = trend_return
    return ToolContext(
        executor=MagicMock(),
        judge=MagicMock(),
        kb=MagicMock(),
        prom=prom_stub,
    )


def test_get_trend_named_metric_rising():
    """Handler returns a one-line summary containing the metric name and 'rising'."""
    summary = {
        "first": 32.5,
        "last": 34.1,
        "min": 31.2,
        "max": 35.0,
        "delta": 1.60,
        "delta_per_hour": 1.60,
        "direction": "rising",
    }
    ctx = _ctx_with_trend(summary)
    out = TOOL_REGISTRY["get_trend"]["handler"](
        {"metric": "cpu", "window": "1h", "reason": "test"},
        ctx,
    )
    assert "cpu" in out
    assert "rising" in out
    assert "32.5" in out
    assert "34.1" in out


def test_get_trend_unknown_metric():
    """Unknown metric name returns an error string."""
    ctx = _ctx_with_trend(None)
    out = TOOL_REGISTRY["get_trend"]["handler"](
        {"metric": "not_a_real_metric", "reason": "test"},
        ctx,
    )
    assert out.startswith("Error:")
    assert "not_a_real_metric" in out


def test_get_trend_no_data():
    """When trend() returns None the handler reports no data available."""
    ctx = _ctx_with_trend(None)
    out = TOOL_REGISTRY["get_trend"]["handler"](
        {"metric": "mem", "window": "6h", "reason": "test"},
        ctx,
    )
    assert "No data" in out
