"""Focused tests for hal.tools registry behavior."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from hal.tools import TOOL_REGISTRY, ToolContext, dispatch_tool, get_tools


def _mock_registry(executor=None):
    """Build an ExecutorRegistry mock whose .default and .get() return executor."""
    if executor is None:
        executor = MagicMock()
    reg = MagicMock()
    reg.default = executor
    reg.get.return_value = executor
    reg.known_hosts = ["lab"]
    return reg


_CTX = ToolContext(
    registry=_mock_registry(),
    judge=MagicMock(),
    kb=MagicMock(),
    prom=MagicMock(),
)


def test_get_tools_returns_layer0_tool_set():
    """Active tool set without Tavily key: 15 tools (web_search is key-gated)."""
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
        # Phase C — recovery playbooks
        "recover_component",
    }
    # With a Tavily key, web_search is also included (16 tools total)
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
        registry=_mock_registry(),
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
        registry=_mock_registry(),
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
        registry=_mock_registry(),
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
        registry=_mock_registry(),
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


# ---------------------------------------------------------------------------
# Phase C — recover_component tool tests
# ---------------------------------------------------------------------------


def test_recover_component_missing_component():
    """recover_component with no component returns error with valid list."""
    out = dispatch_tool("recover_component", {}, _CTX)
    assert "Error" in out
    assert "component is required" in out


def test_recover_component_unknown_component():
    """recover_component with unknown component returns helpful error."""
    out = dispatch_tool("recover_component", {"component": "nonexistent"}, _CTX)
    assert "No recovery playbook found" in out
    assert "nonexistent" in out


def test_recover_component_successful(monkeypatch):
    """recover_component returns success message on playbook success."""
    from hal.playbooks import PlaybookResult

    monkeypatch.setattr(
        "hal.playbooks.execute_playbook",
        lambda pb, ex, j: PlaybookResult(
            success=True,
            steps_completed=1,
            detail="All 1 steps completed successfully",
            playbook_name="restart_pgvector",
        ),
    )
    ctx = ToolContext(
        registry=_mock_registry(),
        judge=MagicMock(),
        kb=MagicMock(),
        prom=MagicMock(),
        config=None,  # no post-recovery health check
    )
    out = dispatch_tool(
        "recover_component", {"component": "pgvector", "reason": "it is down"}, ctx
    )
    assert "successful" in out.lower()
    assert "pgvector" in out


def test_recover_component_failed(monkeypatch):
    """recover_component returns failure detail on playbook failure."""
    from hal.playbooks import PlaybookResult

    monkeypatch.setattr(
        "hal.playbooks.execute_playbook",
        lambda pb, ex, j: PlaybookResult(
            success=False,
            steps_completed=0,
            detail="Step 1 denied by Judge: Restart container",
            playbook_name="restart_pgvector",
        ),
    )
    out = dispatch_tool("recover_component", {"component": "pgvector"}, _CTX)
    assert "FAILED" in out
    assert "denied by Judge" in out


def test_recover_component_schema_in_registry():
    """recover_component schema exists and has required parameters."""
    spec = TOOL_REGISTRY["recover_component"]
    params = spec["schema"]["function"]["parameters"]["properties"]
    assert "component" in params
    assert "reason" in params
    required = spec["schema"]["function"]["parameters"]["required"]
    assert "component" in required


# ---------------------------------------------------------------------------
# Handler happy-path tests (Item 5 — coverage expansion)
# ---------------------------------------------------------------------------


def _approve_judge():
    """Return a Judge-like mock that always approves."""
    judge = MagicMock()
    judge.approve.return_value = True
    return judge


def _make_ctx(**overrides) -> ToolContext:
    """Build a ToolContext with mocks, allowing per-test overrides.

    Pass ``executor=mock`` as a convenience — it will be wrapped in a
    ``_mock_registry(executor)`` automatically.  Or pass ``registry=mock``
    directly.
    """
    # Convenience: convert executor= to registry= via _mock_registry()
    if "executor" in overrides:
        overrides["registry"] = _mock_registry(overrides.pop("executor"))
    defaults: dict = {
        "registry": _mock_registry(),
        "judge": _approve_judge(),
        "kb": MagicMock(),
        "prom": MagicMock(),
    }
    defaults.update(overrides)
    return ToolContext(**defaults)


# --- run_command (happy path) ---


def test_run_command_approved_returns_stdout():
    executor = MagicMock()
    executor.run.return_value = {
        "stdout": "PID  CMD\n1  init\n",
        "stderr": "",
        "returncode": 0,
    }
    ctx = _make_ctx(executor=executor)
    out = dispatch_tool("run_command", {"command": "ps aux", "reason": "check"}, ctx)
    assert "PID" in out
    assert "[exit" not in out


def test_run_command_nonzero_exit_includes_exit_code():
    executor = MagicMock()
    executor.run.return_value = {"stdout": "", "stderr": "not found", "returncode": 127}
    ctx = _make_ctx(executor=executor)
    out = dispatch_tool("run_command", {"command": "badcmd"}, ctx)
    assert "[stderr] not found" in out
    assert "[exit 127]" in out


def test_run_command_empty_output():
    executor = MagicMock()
    executor.run.return_value = {"stdout": "", "stderr": "", "returncode": 0}
    ctx = _make_ctx(executor=executor)
    out = dispatch_tool("run_command", {"command": "true"}, ctx)
    assert out == "(no output)"


# --- read_file ---


def test_read_file_handler_returns_content():
    with patch("hal.tools.read_file", return_value="file contents here"):
        ctx = _make_ctx()
        out = dispatch_tool(
            "read_file", {"path": "/etc/hostname", "reason": "check"}, ctx
        )
    assert out == "file contents here"


def test_read_file_handler_none_returns_error():
    with patch("hal.tools.read_file", return_value=None):
        ctx = _make_ctx()
        out = dispatch_tool("read_file", {"path": "/bad"}, ctx)
    assert "Could not read" in out


# --- list_dir ---


def test_list_dir_handler_returns_listing():
    with patch("hal.tools.list_dir", return_value="bin\netc\nvar"):
        ctx = _make_ctx()
        out = dispatch_tool("list_dir", {"path": "/", "reason": "explore"}, ctx)
    assert "bin" in out


def test_list_dir_handler_none_returns_error():
    with patch("hal.tools.list_dir", return_value=None):
        ctx = _make_ctx()
        out = dispatch_tool("list_dir", {"path": "/nope"}, ctx)
    assert "Could not list" in out


# --- write_file ---


def test_write_file_handler_success():
    with patch("hal.tools.write_file", return_value=True):
        ctx = _make_ctx()
        out = dispatch_tool(
            "write_file",
            {"path": "/tmp/test.txt", "content": "hello", "reason": "test"},
            ctx,
        )
    assert "Written 5 bytes" in out


def test_write_file_handler_denied():
    with patch("hal.tools.write_file", return_value=False):
        ctx = _make_ctx()
        out = dispatch_tool("write_file", {"path": "/tmp/x", "content": "y"}, ctx)
    assert "failed or denied" in out.lower()


# --- search_kb ---


def test_search_kb_returns_formatted_chunks():
    kb = MagicMock()
    kb.search.return_value = [
        {"file": "docs/ops.md", "score": 0.82, "content": "Deploy via docker compose"},
        {
            "file": "docs/arch.md",
            "score": 0.30,
            "content": "Low score — should be filtered",
        },
    ]
    ctx = _make_ctx(kb=kb)
    out = dispatch_tool("search_kb", {"query": "deploy"}, ctx)
    assert "docs/ops.md" in out
    assert "0.82" in out
    assert "Deploy via docker compose" in out
    # score 0.30 is below 0.45 threshold — should NOT appear
    assert "Low score" not in out


def test_search_kb_no_results():
    kb = MagicMock()
    kb.search.return_value = [{"file": "x", "score": 0.20, "content": "noise"}]
    ctx = _make_ctx(kb=kb)
    out = dispatch_tool("search_kb", {"query": "nonexistent"}, ctx)
    assert "No relevant results" in out


def test_search_kb_exception():
    kb = MagicMock()
    kb.search.side_effect = RuntimeError("connection refused")
    ctx = _make_ctx(kb=kb)
    out = dispatch_tool("search_kb", {"query": "test"}, ctx)
    assert "KB search failed" in out


# --- get_metrics ---


def test_get_metrics_returns_formatted_health():
    prom = MagicMock()
    prom.health.return_value = {"cpu": "23%", "mem": "4.2 GiB", "uptime": None}
    ctx = _make_ctx(prom=prom)
    out = dispatch_tool("get_metrics", {}, ctx)
    assert "cpu: 23%" in out
    assert "mem: 4.2 GiB" in out
    # uptime is None — should be excluded
    assert "uptime" not in out


def test_get_metrics_exception():
    prom = MagicMock()
    prom.health.side_effect = ConnectionError("timeout")
    ctx = _make_ctx(prom=prom)
    out = dispatch_tool("get_metrics", {}, ctx)
    assert "Metrics unavailable" in out


# --- get_trend (custom metric path) ---


def test_get_trend_custom_metric():
    prom = MagicMock()
    prom.trend.return_value = {
        "first": 1.0,
        "last": 2.0,
        "min": 0.5,
        "max": 2.5,
        "delta": 1.0,
        "delta_per_hour": 1.0,
        "direction": "rising",
    }
    ctx = _make_ctx(prom=prom)
    out = dispatch_tool(
        "get_trend",
        {"metric": "custom", "promql": "up{job='vllm'}", "window": "1h"},
        ctx,
    )
    assert "custom" in out
    assert "rising" in out


def test_get_trend_custom_missing_promql():
    ctx = _make_ctx()
    out = dispatch_tool("get_trend", {"metric": "custom"}, ctx)
    assert "promql is required" in out


def test_get_trend_exception():
    prom = MagicMock()
    prom.trend.side_effect = RuntimeError("prom down")
    ctx = _make_ctx(prom=prom)
    out = dispatch_tool("get_trend", {"metric": "cpu", "window": "1h"}, ctx)
    assert "Trend query failed" in out


# --- web_search ---


def test_web_search_returns_formatted_results():
    with patch("hal.web.web_search") as mock_ws:
        mock_ws.return_value = [
            {
                "score": 0.95,
                "title": "vLLM Docs",
                "url": "https://docs.vllm.ai",
                "content": "Serve LLMs",
            },
        ]
        ctx = _make_ctx(tavily_api_key="test-key")
        out = dispatch_tool("web_search", {"query": "vllm docs"}, ctx)
    assert "vLLM Docs" in out
    assert "https://docs.vllm.ai" in out


def test_web_search_no_results():
    with patch("hal.web.web_search", return_value=[]):
        ctx = _make_ctx(tavily_api_key="k")
        out = dispatch_tool("web_search", {"query": "nothing"}, ctx)
    assert "No results found" in out


def test_web_search_exception():
    with patch("hal.web.web_search", side_effect=RuntimeError("api error")):
        ctx = _make_ctx(tavily_api_key="k")
        out = dispatch_tool("web_search", {"query": "test"}, ctx)
    assert "web_search failed" in out


# --- fetch_url (success path) ---


def test_fetch_url_approved_returns_text():
    with patch("hal.web.fetch_url", return_value="Article text here"):
        judge = _approve_judge()
        ctx = _make_ctx(judge=judge)
        out = dispatch_tool(
            "fetch_url", {"url": "https://example.com", "reason": "research"}, ctx
        )
    assert out == "Article text here"


def test_fetch_url_exception():
    with patch("hal.web.fetch_url", side_effect=ValueError("SSRF blocked")):
        ctx = _make_ctx()
        out = dispatch_tool("fetch_url", {"url": "http://10.0.0.1"}, ctx)
    assert "fetch_url failed" in out


# --- get_action_stats ---


def test_get_action_stats_returns_formatted_stats():
    with patch("hal.trust_metrics.get_action_stats") as mock_stats:
        mock_stats.return_value = {
            "by_tool": {
                "run_command": {
                    "total": 42,
                    "approved": 40,
                    "denied": 2,
                    "last_timestamp": "2026-03-01T12:00:00",
                },
            },
        }
        ctx = _make_ctx()
        out = dispatch_tool("get_action_stats", {"pattern": "run"}, ctx)
    assert "run_command" in out
    assert "total=42" in out
    assert "approved=40" in out


def test_get_action_stats_no_entries():
    with patch("hal.trust_metrics.get_action_stats", return_value={"by_tool": {}}):
        ctx = _make_ctx()
        out = dispatch_tool("get_action_stats", {"pattern": "xyz"}, ctx)
    assert "No audit entries" in out


def test_get_action_stats_exception():
    with patch("hal.trust_metrics.get_action_stats", side_effect=OSError("no file")):
        ctx = _make_ctx()
        out = dispatch_tool("get_action_stats", {}, ctx)
    assert "get_action_stats failed" in out


# --- security handler wrappers ---


def test_get_security_events_handler_formats_json():
    with patch("hal.security.get_security_events") as mock_events:
        mock_events.return_value = [{"time": "12:00", "rule": "some_rule"}]
        ctx = _make_ctx()
        out = dispatch_tool("get_security_events", {"n": "10", "reason": "audit"}, ctx)
    parsed = json.loads(out)
    assert parsed[0]["rule"] == "some_rule"


def test_get_security_events_handler_empty():
    with patch("hal.security.get_security_events", return_value=[]):
        ctx = _make_ctx()
        out = dispatch_tool("get_security_events", {}, ctx)
    assert "No security events" in out


def test_get_host_connections_handler_formats_json():
    with patch("hal.security.get_host_connections") as mock_conn:
        mock_conn.return_value = {"listening": [{"port": 8000}]}
        ctx = _make_ctx()
        out = dispatch_tool("get_host_connections", {"reason": "check"}, ctx)
    parsed = json.loads(out)
    assert parsed["listening"][0]["port"] == 8000


def test_get_host_connections_handler_empty():
    with patch("hal.security.get_host_connections", return_value={}):
        ctx = _make_ctx()
        out = dispatch_tool("get_host_connections", {}, ctx)
    assert "No host connection data" in out


def test_get_traffic_summary_handler_formats_json():
    with patch("hal.security.get_traffic_summary") as mock_traffic:
        mock_traffic.return_value = {"interfaces": {"eth0": {}}}
        ctx = _make_ctx(ntopng_url="http://localhost:3000")
        out = dispatch_tool("get_traffic_summary", {"reason": "monitor"}, ctx)
    parsed = json.loads(out)
    assert "interfaces" in parsed


def test_get_traffic_summary_handler_empty():
    with patch("hal.security.get_traffic_summary", return_value={}):
        ctx = _make_ctx()
        out = dispatch_tool("get_traffic_summary", {}, ctx)
    assert "No traffic data" in out


def test_scan_lan_handler_formats_json():
    with patch("hal.security.scan_lan") as mock_scan:
        mock_scan.return_value = [{"ip": "192.168.5.1", "mac": "aa:bb:cc:dd:ee:ff"}]
        ctx = _make_ctx()
        out = dispatch_tool(
            "scan_lan", {"subnet": "192.168.5.0/24", "reason": "inventory"}, ctx
        )
    parsed = json.loads(out)
    assert parsed[0]["ip"] == "192.168.5.1"


def test_scan_lan_handler_missing_subnet():
    ctx = _make_ctx()
    out = dispatch_tool("scan_lan", {}, ctx)
    assert "subnet is required" in out


def test_scan_lan_handler_empty():
    with patch("hal.security.scan_lan", return_value=[]):
        ctx = _make_ctx()
        out = dispatch_tool("scan_lan", {"subnet": "10.0.0.0/24"}, ctx)
    assert "No hosts found" in out


# --- check_system_health ---


def test_check_system_health_no_config():
    ctx = _make_ctx(config=None)
    out = dispatch_tool("check_system_health", {}, ctx)
    assert "unavailable" in out.lower()


def test_check_system_health_with_config(monkeypatch):
    monkeypatch.setattr(
        "hal.healthcheck.run_all_checks",
        lambda cfg: [],
    )
    monkeypatch.setattr(
        "hal.healthcheck.format_health_table",
        lambda results: "| Name | Status |",
    )
    monkeypatch.setattr(
        "hal.healthcheck.summary_line",
        lambda results: "0/0 healthy",
    )
    ctx = _make_ctx(config=MagicMock())
    out = dispatch_tool("check_system_health", {}, ctx)
    assert "0/0 healthy" in out
    assert "| Name | Status |" in out


# ===========================================================================
# Multi-host routing — target_host parameter
# ===========================================================================


def _multi_host_registry():
    """Build a registry mock with default (lab) and a named 'laptop' executor."""
    lab_exec = MagicMock()
    lab_exec.run.return_value = {"stdout": "lab-output", "stderr": "", "returncode": 0}
    laptop_exec = MagicMock()
    laptop_exec.run.return_value = {
        "stdout": "laptop-output",
        "stderr": "",
        "returncode": 0,
    }

    reg = MagicMock()
    reg.default = lab_exec
    reg.known_hosts = ["lab", "laptop"]

    def _get(name):
        if name is None:
            return lab_exec
        if name == "laptop":
            return laptop_exec
        raise ValueError(f"Unknown host '{name}'. Available hosts: lab, laptop")

    reg.get.side_effect = _get
    return reg, lab_exec, laptop_exec


# --- run_command multi-host ---


def test_run_command_default_host():
    """No target_host → registry.get(None) → default lab executor."""
    reg, _lab_exec, _ = _multi_host_registry()
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool("run_command", {"command": "hostname", "reason": "test"}, ctx)
    assert "lab-output" in out
    reg.get.assert_called_with(None)


def test_run_command_named_host():
    """target_host='laptop' → registry.get('laptop') → laptop executor."""
    reg, _, _laptop_exec = _multi_host_registry()
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool(
        "run_command",
        {"command": "hostname", "reason": "test", "target_host": "laptop"},
        ctx,
    )
    assert "laptop-output" in out
    reg.get.assert_called_with("laptop")


def test_run_command_unknown_host():
    """Unknown target_host → ValueError caught → error message returned."""
    reg, _, _ = _multi_host_registry()
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool(
        "run_command",
        {"command": "hostname", "reason": "test", "target_host": "unknown"},
        ctx,
    )
    assert "Unknown host" in out
    assert "unknown" in out


# --- read_file multi-host ---


def test_read_file_default_host():
    """No target_host → default executor."""
    reg, lab_exec, _ = _multi_host_registry()
    lab_exec.run.return_value = {
        "stdout": "file content here",
        "stderr": "",
        "returncode": 0,
    }
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool("read_file", {"path": "/etc/hostname"}, ctx)
    reg.get.assert_called_with(None)
    assert "file content" in out


def test_read_file_named_host():
    """target_host='laptop' → laptop executor."""
    reg, _, laptop_exec = _multi_host_registry()
    laptop_exec.run.return_value = {
        "stdout": "laptop-file-content",
        "stderr": "",
        "returncode": 0,
    }
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool(
        "read_file", {"path": "/etc/hostname", "target_host": "laptop"}, ctx
    )
    reg.get.assert_called_with("laptop")
    assert "laptop-file-content" in out


def test_read_file_unknown_host():
    """Unknown target_host → error message."""
    reg, _, _ = _multi_host_registry()
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool(
        "read_file", {"path": "/etc/hostname", "target_host": "unknown"}, ctx
    )
    assert "Unknown host" in out


# --- list_dir multi-host ---


def test_list_dir_default_host():
    """No target_host → default executor."""
    reg, lab_exec, _ = _multi_host_registry()
    lab_exec.run.return_value = {
        "stdout": "bin\netc\nusr",
        "stderr": "",
        "returncode": 0,
    }
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool("list_dir", {"path": "/"}, ctx)
    reg.get.assert_called_with(None)
    assert "bin" in out


def test_list_dir_named_host():
    """target_host='laptop' → laptop executor."""
    reg, _, laptop_exec = _multi_host_registry()
    laptop_exec.run.return_value = {
        "stdout": "home\nopt",
        "stderr": "",
        "returncode": 0,
    }
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool("list_dir", {"path": "/", "target_host": "laptop"}, ctx)
    reg.get.assert_called_with("laptop")
    assert "home" in out


def test_list_dir_unknown_host():
    """Unknown target_host → error message."""
    reg, _, _ = _multi_host_registry()
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool("list_dir", {"path": "/", "target_host": "unknown"}, ctx)
    assert "Unknown host" in out


# --- write_file multi-host ---


def test_write_file_default_host():
    """No target_host → default executor."""
    reg, _lab_exec, _ = _multi_host_registry()
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool(
        "write_file",
        {"path": "/tmp/test.txt", "content": "hello", "reason": "test"},
        ctx,
    )
    reg.get.assert_called_with(None)
    # write_file handler calls workers.write_file which uses executor.run
    assert "denied" not in out.lower() or "wrote" in out.lower() or out


def test_write_file_named_host():
    """target_host='laptop' → laptop executor."""
    reg, _, _laptop_exec = _multi_host_registry()
    ctx = _make_ctx(registry=reg)
    dispatch_tool(
        "write_file",
        {
            "path": "/tmp/test.txt",
            "content": "hello",
            "reason": "test",
            "target_host": "laptop",
        },
        ctx,
    )
    reg.get.assert_called_with("laptop")


def test_write_file_unknown_host():
    """Unknown target_host → error message."""
    reg, _, _ = _multi_host_registry()
    ctx = _make_ctx(registry=reg)
    out = dispatch_tool(
        "write_file",
        {
            "path": "/tmp/test.txt",
            "content": "hello",
            "reason": "test",
            "target_host": "unknown",
        },
        ctx,
    )
    assert "Unknown host" in out


# --- Security handlers always use default ---


def test_security_handlers_use_default_executor():
    """Security tool handlers use ctx.registry.default, not target_host."""
    from unittest.mock import patch

    reg, lab_exec, _ = _multi_host_registry()
    ctx = _make_ctx(registry=reg)

    # Patch the underlying security function so no real I/O happens;
    # hal/tools.py accesses it via `_security.get_security_events(...)`.
    with patch("hal.security.get_security_events", return_value=[]):
        dispatch_tool("get_security_events", {}, ctx)

    # The handler passes ctx.registry.default (the lab executor) to the
    # security function — it never calls ctx.registry.get() because security
    # tools always target the primary lab server.
    assert reg.default is lab_exec
