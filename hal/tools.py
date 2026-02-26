"""Tool registry for the agent loop.

Each tool is defined once with:
- OpenAI function-call schema exposed to the model
- runtime handler implementation
- optional availability predicate
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import NamedTuple, TypedDict

from hal.executor import SSHExecutor
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.prometheus import PrometheusClient
from hal.security import (
    get_host_connections,
    get_security_events,
    get_traffic_summary,
    scan_lan,
)
from hal.trust_metrics import get_action_stats as tm_get_action_stats
from hal.web import fetch_url as _fetch_url
from hal.web import web_search as _web_search
from hal.workers import (
    git_diff,
    git_status,
    list_dir,
    patch_file,
    read_file,
    write_file,
)


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


def _tavily_enabled(tavily_api_key: str) -> bool:
    return bool(tavily_api_key)


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


def _handle_patch_file(args: dict, ctx: ToolContext) -> str:
    path = args.get("path") or ""
    old_str = args.get("old_str") or ""
    new_str = args.get("new_str") or ""
    reason = args.get("reason") or ""
    return patch_file(path, old_str, new_str, ctx.executor, ctx.judge, reason=reason)


def _handle_git_status(args: dict, ctx: ToolContext) -> str:
    repo_path = args.get("repo_path") or ""
    reason = args.get("reason") or ""
    return git_status(repo_path, ctx.executor, ctx.judge, reason=reason)


def _handle_git_diff(args: dict, ctx: ToolContext) -> str:
    repo_path = args.get("repo_path") or ""
    ref = args.get("ref") or "HEAD"
    reason = args.get("reason") or ""
    return git_diff(repo_path, ctx.executor, ctx.judge, ref=ref, reason=reason)


def _handle_get_metrics(args: dict, ctx: ToolContext) -> str:
    _ = args
    try:
        h = ctx.prom.health()
        return "\n".join(f"{k}: {v}" for k, v in h.items() if v is not None)
    except Exception as e:
        return f"Metrics unavailable: {e}"


def _handle_get_action_stats(args: dict, ctx: ToolContext) -> str:
    pattern = args.get("action_pattern") or ""
    if not pattern:
        return "Error: action_pattern is required."
    try:
        data = tm_get_action_stats(pattern)
        return json.dumps(data, indent=2)
    except Exception as e:
        return f"get_action_stats failed: {e}"


def _handle_get_security_events(args: dict, ctx: ToolContext) -> str:
    n = int(args.get("n", 50))
    reason = args.get("reason") or ""
    events = get_security_events(ctx.executor, ctx.judge, n=n, reason=reason)
    return json.dumps(events, indent=2)


def _handle_get_host_connections(args: dict, ctx: ToolContext) -> str:
    reason = args.get("reason") or ""
    data = get_host_connections(ctx.executor, ctx.judge, reason=reason)
    return json.dumps(data, indent=2) if data else "Denied."


def _handle_get_traffic_summary(args: dict, ctx: ToolContext) -> str:
    top_flows = int(args.get("top_flows", 20))
    reason = args.get("reason") or ""
    data = get_traffic_summary(
        ctx.executor,
        ctx.judge,
        ntopng_url=ctx.ntopng_url,
        top_flows=top_flows,
        reason=reason,
    )
    return json.dumps(data, indent=2) if data else "Denied."


def _handle_scan_lan(args: dict, ctx: ToolContext) -> str:
    subnet = args.get("subnet") or ""
    reason = args.get("reason") or ""
    if not subnet:
        return "Error: subnet is required."
    hosts = scan_lan(subnet, ctx.executor, ctx.judge, reason=reason)
    return json.dumps(hosts, indent=2)


def _handle_web_search(args: dict, ctx: ToolContext) -> str:
    query = args.get("query") or ""
    reason = args.get("reason") or ""
    if not ctx.judge.approve("web_search", query, reason=reason):
        return "Web search denied by policy."
    if not ctx.tavily_api_key:
        return "web_search is disabled — TAVILY_API_KEY is not configured."
    try:
        results = _web_search(query, api_key=ctx.tavily_api_key)
        lines = []
        for r in results:
            lines.append(f"**{r['title']}**")
            lines.append(r["url"])
            lines.append(r["content"][:500])
            lines.append("")
        return "\n".join(lines) if lines else "No results found."
    except ValueError as e:
        return f"Web search blocked: {e}"
    except Exception as e:
        return f"Web search failed: {e}"


def _handle_fetch_url(args: dict, ctx: ToolContext) -> str:
    url = args.get("url") or ""
    reason = args.get("reason") or ""
    if not ctx.judge.approve("fetch_url", url, reason=reason):
        return "URL fetch denied by policy."
    try:
        return _fetch_url(url)
    except ValueError as e:
        return f"URL blocked (SSRF protection): {e}"
    except RuntimeError as e:
        return f"Fetch failed: {e}"
    except Exception as e:
        return f"Fetch failed: {e}"


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
    "get_action_stats": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_action_stats",
                "description": (
                    "Return aggregated success/denial stats from HAL's audit log. "
                    "Use this to check how often HAL has successfully performed a specific action "
                    "before proposing to do it again. Accepts a substring or regex; matches tool name, "
                    "command detail, or normalized action class (e.g., 'docker restart')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action_pattern": {
                            "type": "string",
                            "description": "Substring or regex to match against action type, command, or action class",
                        }
                    },
                    "required": ["action_pattern"],
                },
            },
        },
        "handler": _handle_get_action_stats,
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
    "patch_file": {
        "schema": {
            "type": "function",
            "function": {
                "name": "patch_file",
                "description": (
                    "Edit a file on the lab server by replacing an exact string. "
                    "Safer than write_file — only the changed lines are touched. "
                    "Shows a diff before applying. Use for targeted config edits."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path to the file",
                        },
                        "old_str": {
                            "type": "string",
                            "description": "The exact text currently in the file to replace",
                        },
                        "new_str": {
                            "type": "string",
                            "description": "The new text to substitute in",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why this edit is needed",
                        },
                    },
                    "required": ["path", "old_str", "new_str"],
                },
            },
        },
        "handler": _handle_patch_file,
        "enabled": _always_enabled,
    },
    "git_status": {
        "schema": {
            "type": "function",
            "function": {
                "name": "git_status",
                "description": (
                    "Show uncommitted file changes in a git repository on the lab server. "
                    "Use to see what has recently changed in a project or config directory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Absolute path to the git repository root",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need git status",
                        },
                    },
                    "required": ["repo_path"],
                },
            },
        },
        "handler": _handle_git_status,
        "enabled": _always_enabled,
    },
    "git_diff": {
        "schema": {
            "type": "function",
            "function": {
                "name": "git_diff",
                "description": (
                    "Show the diff of uncommitted or committed changes in a git repository "
                    "on the lab server. Defaults to comparing working tree against HEAD. "
                    "Pass a commit ref to compare that specific point."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Absolute path to the git repository root",
                        },
                        "ref": {
                            "type": "string",
                            "description": "Git ref to diff against (default: HEAD)",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need the diff",
                        },
                    },
                    "required": ["repo_path"],
                },
            },
        },
        "handler": _handle_git_diff,
        "enabled": _always_enabled,
    },
    "get_security_events": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_security_events",
                "description": (
                    "Return recent Falco security events from the lab server. "
                    "Use for questions like 'anything suspicious?', 'any alerts?', "
                    "'what did Falco catch?'. Known-noisy rules are filtered automatically. "
                    "Returns a list of events with time, rule, priority, and process name."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "n": {
                            "type": "integer",
                            "description": "Number of recent events to return (default: 50)",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need security events",
                        },
                    },
                    "required": [],
                },
            },
        },
        "handler": _handle_get_security_events,
        "enabled": _always_enabled,
    },
    "get_host_connections": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_host_connections",
                "description": (
                    "Return listening ports, established TCP connections, and ARP cache "
                    "for the lab server via Osquery. "
                    "Use for 'what's listening on this host?', 'who is connected?', "
                    "'show me active network connections'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need host connection data",
                        },
                    },
                    "required": [],
                },
            },
        },
        "handler": _handle_get_host_connections,
        "enabled": _always_enabled,
    },
    "get_traffic_summary": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_traffic_summary",
                "description": (
                    "Return aggregate network traffic stats and top active flows from ntopng. "
                    "Use for 'how much traffic?', 'what are the busiest flows?', "
                    "'is there unusual traffic?', 'show me bandwidth usage'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "top_flows": {
                            "type": "integer",
                            "description": "Number of active flows to return (default: 20)",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need traffic data",
                        },
                    },
                    "required": [],
                },
            },
        },
        "handler": _handle_get_traffic_summary,
        "enabled": _always_enabled,
    },
    "scan_lan": {
        "schema": {
            "type": "function",
            "function": {
                "name": "scan_lan",
                "description": (
                    "Ping-sweep a subnet to discover live hosts (no port probing). "
                    "Use for 'what's on the network?', 'scan the LAN', "
                    "'show me all devices on 192.168.5.0/24'. "
                    "Requires approval — will prompt the user before running."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subnet": {
                            "type": "string",
                            "description": "CIDR subnet to scan, e.g. 192.168.5.0/24",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need a LAN scan",
                        },
                    },
                    "required": ["subnet"],
                },
            },
        },
        "handler": _handle_scan_lan,
        "enabled": _always_enabled,
    },
    "fetch_url": {
        "schema": {
            "type": "function",
            "function": {
                "name": "fetch_url",
                "description": (
                    "Fetch a public web page and extract its article text. "
                    "Use this after web_search to read full page content, or when the "
                    "user provides a specific URL to read. "
                    "SSRF-protected: internal IPs and private hostnames are blocked. "
                    "Output is capped at 15 000 characters."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Public HTTP(S) URL to fetch",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need to fetch this URL",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        "handler": _handle_fetch_url,
        "enabled": _always_enabled,
    },
    "web_search": {
        "schema": {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the public web for current information using Tavily. "
                    "Use this for questions about latest software versions, CVEs, "
                    "release notes, or topics not covered by the homelab knowledge base. "
                    "Try search_kb first — only use web_search when the answer requires "
                    "up-to-date external information. "
                    "NEVER include internal IP addresses, hostnames, or file paths in "
                    "the search query."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (public, generic — no internal IPs or hostnames)",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need a web search",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        "handler": _handle_web_search,
        "enabled": _tavily_enabled,
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
