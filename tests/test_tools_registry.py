"""Focused tests for hal.tools registry behavior."""

from unittest.mock import MagicMock

from hal.tools import TOOL_REGISTRY, ToolContext, dispatch_tool, get_tools

_CTX = ToolContext(
    executor=MagicMock(),
    judge=MagicMock(),
    kb=MagicMock(),
    prom=MagicMock(),
)


def test_get_tools_registry_parity_with_and_without_tavily_key():
    """web_search is key-gated; fetch_url is always available."""
    names_no_key = [tool["function"]["name"] for tool in get_tools()]
    names_with_key = [
        tool["function"]["name"] for tool in get_tools(tavily_api_key="k")
    ]

    assert "fetch_url" in names_no_key
    assert "fetch_url" in names_with_key
    assert "web_search" not in names_no_key
    assert "web_search" in names_with_key


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
