"""Tool registry for the agent loop — Layer 0.

Layer 0 tools (always available, no external API keys required):
  search_kb     — pgvector semantic search
  get_metrics   — live Prometheus metrics
  get_trend     — Prometheus range-query trend analysis
  run_command   — shell command execution (Judge-gated)
  read_file     — file read (Judge-gated)
  list_dir      — directory listing (Judge-gated)
  write_file    — file write (Judge-gated)

Locked tools (moved to hal/_unlocked/ — returns with their layer):
  Layer 3: get_action_stats, get_security_events, get_host_connections,
           get_traffic_summary, scan_lan, fetch_url, web_search,
           patch_file, git_status, git_diff
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple, TypedDict

from hal.executor import SSHExecutor
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.prometheus import PrometheusClient
from hal.workers import list_dir, read_file, write_file


class ToolContext(NamedTuple):
    """Shared runtime dependencies threaded through every tool handler.

    Construct once per agent turn at the ``dispatch_tool`` / ``run_agent``
    boundary.  Adding a new shared dependency only requires changing this class
    and its single construction site — not every handler signature.
    """

    executor: "SSHExecutor"
    judge: "Judge"
    kb: "KnowledgeBase"
    prom: "PrometheusClient"
    ntopng_url: str = "http://localhost:3000"
    tavily_api_key: str = ""


class ToolSpec(TypedDict):
    schema: dict
    handler: Callable[[dict, ToolContext], str]
    enabled: Callable[[str], bool]


def _always_enabled(_: str) -> bool:
    return True


def _handle_run_command(args: dict, ctx: ToolContext) -> str:
    command = args.get("command") or ""
    reason = args.get("reason") or ""
    if not ctx.judge.approve("run_command", command, reason=reason):
        return "Action denied by user."
    result = ctx.executor.run(command)
    parts = []
    if result["stdout"].strip():
        parts.append(result["stdout"].strip())
    if result["stderr"].strip():
        parts.append(f"[stderr] {result['stderr'].strip()}")
    if result["returncode"] != 0:
        parts.append(f"[exit {result['returncode']}]")
    return "\n".join(parts) or "(no output)"


def _handle_read_file(args: dict, ctx: ToolContext) -> str:
    path = args.get("path") or ""
    reason = args.get("reason") or ""
    content = read_file(path, ctx.executor, ctx.judge, reason=reason)
    return content if content is not None else f"Could not read {path}"


def _handle_list_dir(args: dict, ctx: ToolContext) -> str:
    path = args.get("path") or ""
    reason = args.get("reason") or ""
    output = list_dir(path, ctx.executor, ctx.judge, reason=reason)
    return output if output is not None else f"Could not list {path}"


def _handle_write_file(args: dict, ctx: ToolContext) -> str:
    path = args.get("path") or ""
    content = args.get("content") or ""
    reason = args.get("reason") or ""
    ok = write_file(path, content, ctx.executor, ctx.judge, reason=reason)
    return (
        f"Written {len(content)} bytes to {path}"
        if ok
        else f"Write failed or denied for {path}"
    )


def _handle_search_kb(args: dict, ctx: ToolContext) -> str:
    query = args.get("query") or ""
    try:
        chunks = ctx.kb.search(query, top_k=8)
        lines = []
        for c in chunks:
            if c["score"] < 0.45:
                continue
            lines.append(f"[{c['file']} | score={c['score']:.2f}]")
            lines.append(c["content"].strip())
            lines.append("")
        return "\n".join(lines) if lines else "No relevant results found."
    except Exception as e:
        return f"KB search failed: {e}"


def _handle_get_metrics(args: dict, ctx: ToolContext) -> str:
    _ = args
    try:
        h = ctx.prom.health()
        return "\n".join(f"{k}: {v}" for k, v in h.items() if v is not None)
    except Exception as e:
        return f"Metrics unavailable: {e}"


# PromQL expressions for each named metric — mirrors health() exactly.
_METRIC_PROMQL: dict[str, str] = {
    "cpu": '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
    "mem": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
    "disk_root": (
        '(1 - node_filesystem_avail_bytes{mountpoint="/"}'
        ' / node_filesystem_size_bytes{mountpoint="/"}) * 100'
    ),
    "disk_docker": (
        '(1 - node_filesystem_avail_bytes{mountpoint="/docker"}'
        ' / node_filesystem_size_bytes{mountpoint="/docker"}) * 100'
    ),
    "disk_data": (
        '(1 - node_filesystem_avail_bytes{mountpoint="/data/projects"}'
        ' / node_filesystem_size_bytes{mountpoint="/data/projects"}) * 100'
    ),
    "swap": "(1 - node_memory_SwapFree_bytes / node_memory_SwapTotal_bytes) * 100",
    "load": "node_load1",
    "gpu_vram": 'node_gpu_vram_usage_percent{gpu="0"}',
    "gpu_temp": 'node_gpu_temperature_celsius{gpu="0"}',
}


def _handle_get_trend(args: dict, ctx: ToolContext) -> str:
    metric = args.get("metric") or ""
    window = args.get("window") or "1h"
    if metric == "custom":
        promql = args.get("promql") or ""
        if not promql:
            return 'Error: promql is required when metric="custom".'
    else:
        promql = _METRIC_PROMQL.get(metric, "")
        if not promql:
            valid = ", ".join(sorted(_METRIC_PROMQL)) + ", custom"
            return f"Error: unknown metric '{metric}'. Valid values: {valid}"
    try:
        summary = ctx.prom.trend(promql, window)
    except Exception as e:
        return f"Trend query failed: {e}"
    if summary is None:
        return f"No data returned for '{metric}' over window '{window}'."
    return (
        f"{metric} over {window}: "
        f"{summary['first']} → {summary['last']} "
        f"(min={summary['min']}, max={summary['max']}, "
        f"delta={summary['delta']:+.2f}, "
        f"{summary['delta_per_hour']:+.2f}/h, "
        f"{summary['direction']})"
    )


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "search_kb": {
        "schema": {
            "type": "function",
            "function": {
                "name": "search_kb",
                "description": (
                    "Search the homelab knowledge base for documentation, configs, "
                    "and infrastructure facts. Use this for questions about ports, "
                    "service configuration, file paths, or any documented fact. "
                    "Prefer this over run_command when the answer may already be documented."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        "handler": _handle_search_kb,
        "enabled": _always_enabled,
    },
    "get_metrics": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_metrics",
                "description": (
                    "Get live Prometheus metrics: CPU %, memory %, disk usage "
                    "(root /, /docker, /data/projects), swap %, 1-min load average, "
                    "GPU VRAM %, and GPU temperature. Returns None for any metric "
                    "that is temporarily unavailable."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        "handler": _handle_get_metrics,
        "enabled": _always_enabled,
    },
    "get_trend": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_trend",
                "description": (
                    "Analyse how a Prometheus metric has changed over a recent time window. "
                    "Use this when asked whether a metric is growing, stable, or shrinking — "
                    "e.g. 'is /docker disk filling up?', 'show me CPU trend over 6h'. "
                    "Returns first/last/min/max values, delta, rate per hour, and direction "
                    "(rising/falling/stable). Prefer this over get_metrics for trend questions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": [
                                "cpu",
                                "mem",
                                "disk_root",
                                "disk_docker",
                                "disk_data",
                                "swap",
                                "load",
                                "gpu_vram",
                                "gpu_temp",
                                "custom",
                            ],
                            "description": (
                                "Which metric to trend. Use 'custom' with the 'promql' field "
                                "for an arbitrary PromQL expression."
                            ),
                        },
                        "window": {
                            "type": "string",
                            "description": (
                                "Lookback window, e.g. '1h', '6h', '24h'. Defaults to '1h'. "
                                "Maximum is '24h'."
                            ),
                        },
                        "promql": {
                            "type": "string",
                            "description": "Raw PromQL expression — only used when metric='custom'.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need this trend.",
                        },
                    },
                    "required": ["metric", "reason"],
                },
            },
        },
        "handler": _handle_get_trend,
        "enabled": _always_enabled,
    },
    "run_command": {
        "schema": {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": (
                    "Run a shell command on the lab server. "
                    "Use ONLY for live state: checking processes, service status, logs, "
                    "disk usage, network. Do NOT use for questions answerable from the KB."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to run",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need to run this command",
                        },
                    },
                    "required": ["command"],
                },
            },
        },
        "handler": _handle_run_command,
        "enabled": _always_enabled,
    },
    "read_file": {
        "schema": {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file on the lab server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path to the file",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need to read this file",
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        "handler": _handle_read_file,
        "enabled": _always_enabled,
    },
    "list_dir": {
        "schema": {
            "type": "function",
            "function": {
                "name": "list_dir",
                "description": "List the contents of a directory on the lab server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path to the directory",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need to list this directory",
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        "handler": _handle_list_dir,
        "enabled": _always_enabled,
    },
    "write_file": {
        "schema": {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "Write content to a file on the lab server (creates or overwrites). "
                    "Requires approval. Use only when explicitly asked to create or modify a file."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path to the file to write",
                        },
                        "content": {
                            "type": "string",
                            "description": "The full content to write to the file",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need to write this file",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        },
        "handler": _handle_write_file,
        "enabled": _always_enabled,
    },
}


def get_tools(*, tavily_api_key: str = "") -> list[dict]:
    """Return active tools exposed to the LLM for this request."""
    tools: list[dict] = []
    for spec in TOOL_REGISTRY.values():
        if spec["enabled"](tavily_api_key):
            tools.append(spec["schema"])
    return tools


def dispatch_tool(
    name: str,
    args: dict,
    ctx: ToolContext,
) -> str:
    """Dispatch a tool by registry lookup, preserving legacy error contract."""
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return f"Unknown tool: {name}"
    return spec["handler"](args, ctx)
