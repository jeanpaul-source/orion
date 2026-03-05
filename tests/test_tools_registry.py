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
    """Active tool set without Tavily key: 14 tools (web_search is key-gated)."""
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
        # Phase B — structured health checks
        "check_system_health",
    }
    # With a Tavily key, web_search is also included (15 tools total)
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


# ---------------------------------------------------------------------------
# Denial message quality tests (F2)
# ---------------------------------------------------------------------------


def _deny_judge():
    """Return a Judge-like mock that always denies."""
    judge = MagicMock()
    judge.approve.return_value = False
    return judge


def test_run_command_denial_includes_tier_and_alternatives():
    """Denied run_command must report the tier and suggest read-only alternatives."""
    ctx = ToolContext(
        executor=MagicMock(),
        judge=_deny_judge(),
        kb=MagicMock(),
        prom=MagicMock(),
    )
    out = TOOL_REGISTRY["run_command"]["handler"](
        {"command": "systemctl restart prometheus", "reason": "health check"},
        ctx,
    )
    assert "denied" in out.lower()
    assert "tier" in out.lower()
    # Must suggest at least some safe alternatives
    assert "systemctl status" in out or "docker ps" in out or "ps" in out
    # Must NOT contain the old opaque message
    assert "Action denied by user" not in out


def test_run_command_denial_tier_matches_command():
    """The tier in the denial message should reflect the actual command classification."""
    ctx = ToolContext(
        executor=MagicMock(),
        judge=_deny_judge(),
        kb=MagicMock(),
        prom=MagicMock(),
    )
    # systemctl restart → tier 1
    out = TOOL_REGISTRY["run_command"]["handler"](
        {"command": "systemctl restart prometheus"},
        ctx,
    )
    assert "tier 1" in out

    # rm -rf → tier 3
    out = TOOL_REGISTRY["run_command"]["handler"](
        {"command": "rm -rf /"},
        ctx,
    )
    assert "tier 3" in out


def test_fetch_url_denial_suggests_web_search():
    """Denied fetch_url must suggest web_search as an alternative."""
    ctx = ToolContext(
        executor=MagicMock(),
        judge=_deny_judge(),
        kb=MagicMock(),
        prom=MagicMock(),
    )
    out = TOOL_REGISTRY["fetch_url"]["handler"](
        {"url": "https://example.com", "reason": "test"},
        ctx,
    )
    assert "denied" in out.lower()
    assert "web_search" in out
    assert "Action denied by user" not in out


# ---------------------------------------------------------------------------
# Tool description quality tests (F3)
# ---------------------------------------------------------------------------


def test_run_command_description_lists_safe_commands():
    """run_command tool description must list auto-approved commands so the LLM
    knows what to use instead of guessing commands that will be denied."""
    desc = TOOL_REGISTRY["run_command"]["schema"]["function"]["description"]
    # Must mention key safe commands
    for keyword in [
        "systemctl status",
        "docker ps",
        "journalctl",
        "nvidia-smi",
        "tier 0",
    ]:
        assert keyword in desc, f"run_command description missing '{keyword}'"
    # Must warn about denial in HTTP mode
    assert "DENIED" in desc or "denied" in desc


# ---------------------------------------------------------------------------
# Tool description quality tests (F5)
# ---------------------------------------------------------------------------


def test_web_search_description_lists_trigger_examples():
    """web_search description must include CVE, version, and release keywords
    so the LLM knows when to prefer web search over KB search."""
    desc = TOOL_REGISTRY["web_search"]["schema"]["function"]["description"]
    for keyword in ["CVE", "latest release", "changelog", "version"]:
        assert keyword in desc, f"web_search description missing '{keyword}'"
