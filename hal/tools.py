"""Tool registry for the agent loop.

Layer 0 tools (always available, no external API keys required):
  search_kb       — pgvector semantic search
  get_metrics     — live Prometheus metrics
  get_trend       — Prometheus range-query trend analysis
  run_command     — shell command execution (Judge-gated)
  read_file       — file read (Judge-gated)
  list_dir        — directory listing (Judge-gated)
  write_file      — file write (Judge-gated)

Layer 3 tools (graduated — active):
  web_search           — Tavily web search (enabled only when TAVILY_API_KEY is set)
  fetch_url            — SSRF-safe URL fetch + text extraction (Judge tier 1)
  get_action_stats     — audit log analytics
  get_security_events  — Falco security event reader (noise-filtered)
  get_host_connections — Osquery listening ports + established connections + ARP
  get_traffic_summary  — ntopng interface stats + top flows
  scan_lan             — Nmap ping-sweep LAN discovery (Judge tier 1)
  run_code             — sandboxed Python execution (Docker, Judge tier 2)

Locked tools (still in hal/_unlocked/ — return with their layer):
  Layer 3: patch_file, git_status, git_diff
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple, TypedDict

import hal.sandbox as _sandbox
import hal.security as _security
import hal.trust_metrics as _trust_metrics
import hal.web as _web
from hal.executor import ExecutorRegistry
from hal.judge import Judge, tier_for
from hal.knowledge import KnowledgeBase
from hal.prometheus import METRIC_PROMQL as _METRIC_PROMQL
from hal.prometheus import PrometheusClient
from hal.workers import list_dir, read_file, write_file


class ToolContext(NamedTuple):
    """Shared runtime dependencies threaded through every tool handler.

    Construct once per agent turn at the ``dispatch_tool`` / ``run_agent``
    boundary.  Adding a new shared dependency only requires changing this class
    and its single construction site — not every handler signature.
    """

    registry: ExecutorRegistry
    judge: Judge
    kb: KnowledgeBase
    prom: PrometheusClient
    ntopng_url: str = "http://localhost:3000"
    tavily_api_key: str = ""
    config: object | None = None  # hal.config.Config — optional, enables health checks


class ToolSpec(TypedDict):
    schema: dict
    handler: Callable[[dict, ToolContext], str]
    enabled: Callable[..., bool]


def _always_enabled(**_: Any) -> bool:
    return True


def _handle_run_command(args: dict, ctx: ToolContext) -> str:
    command = args.get("command") or ""
    reason = args.get("reason") or ""
    target_host = args.get("target_host") or None
    if not ctx.judge.approve("run_command", command, reason=reason):
        tier = tier_for("run_command", command)
        return (
            f"Command denied (tier {tier} — requires interactive approval). "
            "Try a read-only alternative instead: ps, cat, head, tail, grep, "
            "systemctl status, systemctl is-active, systemctl list-units, "
            "docker ps, docker logs, journalctl, ls, df, free, nvidia-smi."
        )
    try:
        executor = ctx.registry.get(target_host)
    except ValueError as e:
        return str(e)
    result = executor.run(command)
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
    target_host = args.get("target_host") or None
    try:
        executor = ctx.registry.get(target_host)
    except ValueError as e:
        return str(e)
    content = read_file(path, executor, ctx.judge, reason=reason)
    return content if content is not None else f"Could not read {path}"


def _handle_list_dir(args: dict, ctx: ToolContext) -> str:
    path = args.get("path") or ""
    reason = args.get("reason") or ""
    target_host = args.get("target_host") or None
    try:
        executor = ctx.registry.get(target_host)
    except ValueError as e:
        return str(e)
    output = list_dir(path, executor, ctx.judge, reason=reason)
    return output if output is not None else f"Could not list {path}"


def _handle_write_file(args: dict, ctx: ToolContext) -> str:
    path = args.get("path") or ""
    content = args.get("content") or ""
    reason = args.get("reason") or ""
    target_host = args.get("target_host") or None
    try:
        executor = ctx.registry.get(target_host)
    except ValueError as e:
        return str(e)
    ok = write_file(path, content, executor, ctx.judge, reason=reason)
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


def _handle_web_search(args: dict, ctx: ToolContext) -> str:
    query = args.get("query") or ""
    try:
        results = _web.web_search(query, api_key=ctx.tavily_api_key)
    except (ValueError, RuntimeError) as exc:
        return f"web_search failed: {exc}"
    if not results:
        return "No results found."
    lines = []
    for r in results:
        lines.append(f"[{r['score']:.2f}] {r['title']}")
        lines.append(f"  {r['url']}")
        lines.append(f"  {r['content']}")
        lines.append("")
    return "\n".join(lines)


def _handle_fetch_url(args: dict, ctx: ToolContext) -> str:
    url = args.get("url") or ""
    reason = args.get("reason") or ""
    if not ctx.judge.approve("fetch_url", url, reason=reason):
        return (
            "URL fetch denied (tier 1 — requires interactive approval). "
            "Use web_search instead if you need information from the web."
        )
    try:
        return _web.fetch_url(url)
    except (ValueError, RuntimeError) as exc:
        return f"fetch_url failed: {exc}"


def _handle_get_action_stats(args: dict, ctx: ToolContext) -> str:
    pattern = args.get("pattern") or ""
    try:
        stats = _trust_metrics.get_action_stats(pattern)
    except Exception as exc:
        return f"get_action_stats failed: {exc}"
    by_tool: dict = stats.get("by_tool") or {}
    lines = []
    for action, s in by_tool.items():
        lines.append(
            f"{action}: total={s['total']}, approved={s['approved']}, "
            f"denied={s['denied']}, last={s['last_timestamp']}"
        )
    return "\n".join(lines) if lines else f"No audit entries matching '{pattern}'."


def _handle_get_security_events(args: dict, ctx: ToolContext) -> str:
    n = int(args.get("n") or 50)
    reason = args.get("reason") or ""
    events = _security.get_security_events(
        ctx.registry.default, ctx.judge, n=n, reason=reason
    )
    if not events:
        return "No security events found (or action denied)."
    import json as _json

    return _json.dumps(events, indent=2)


def _handle_get_host_connections(args: dict, ctx: ToolContext) -> str:
    reason = args.get("reason") or ""
    result = _security.get_host_connections(
        ctx.registry.default, ctx.judge, reason=reason
    )
    if not result:
        return "No host connection data returned (or action denied)."
    import json as _json

    return _json.dumps(result, indent=2)


def _handle_get_traffic_summary(args: dict, ctx: ToolContext) -> str:
    reason = args.get("reason") or ""
    result = _security.get_traffic_summary(
        ctx.registry.default, ctx.judge, ntopng_url=ctx.ntopng_url, reason=reason
    )
    if not result:
        return "No traffic data returned (or action denied)."
    import json as _json

    return _json.dumps(result, indent=2)


def _handle_scan_lan(args: dict, ctx: ToolContext) -> str:
    subnet = args.get("subnet") or ""
    reason = args.get("reason") or ""
    if not subnet:
        return "Error: subnet is required."
    hosts = _security.scan_lan(subnet, ctx.registry.default, ctx.judge, reason=reason)
    if not hosts:
        return "No hosts found (or action denied)."
    import json as _json

    return _json.dumps(hosts, indent=2)


def _handle_check_system_health(args: dict, ctx: ToolContext) -> str:
    if ctx.config is None:
        return "Health checks unavailable (no config in this context)."
    from hal.healthcheck import format_health_table, run_all_checks, summary_line

    results = run_all_checks(ctx.config)  # type: ignore[arg-type]
    table = format_health_table(results)
    return f"{summary_line(results)}\n\n{table}"


def _handle_recover_component(args: dict, ctx: ToolContext) -> str:
    component = args.get("component") or ""

    from hal.playbooks import COMPONENT_NAMES, execute_playbook, get_playbook

    if not component:
        return f"Error: component is required. Valid components: {', '.join(sorted(COMPONENT_NAMES))}"

    playbook = get_playbook(component, "down")
    if playbook is None:
        return (
            f"No recovery playbook found for component '{component}'. "
            f"Valid components: {', '.join(sorted(COMPONENT_NAMES))}"
        )

    # Execute the playbook — each step goes through the Judge individually
    result = execute_playbook(playbook, ctx.registry.default, ctx.judge)

    if result.success:
        # Run a follow-up health check to confirm
        if ctx.config is not None:
            from hal.healthcheck import run_all_checks

            checks = run_all_checks(ctx.config)  # type: ignore[arg-type]
            comp_check = next((c for c in checks if c.name == component), None)
            if comp_check:
                return (
                    f"Recovery successful for {component}.\n"
                    f"Playbook: {playbook.name}\n"
                    f"Steps completed: {result.steps_completed}\n"
                    f"Post-recovery status: {comp_check.status} — {comp_check.detail}"
                )
        return (
            f"Recovery successful for {component}.\n"
            f"Playbook: {playbook.name}\n"
            f"Steps completed: {result.steps_completed}\n"
            f"Detail: {result.detail}"
        )
    return (
        f"Recovery FAILED for {component}.\n"
        f"Playbook: {playbook.name}\n"
        f"Steps completed: {result.steps_completed}/{len(playbook.steps)}\n"
        f"Detail: {result.detail}"
    )


def _web_search_enabled(*, tavily_api_key: str = "", **_: Any) -> bool:
    return bool(tavily_api_key)


def _sandbox_enabled(*, sandbox_enabled: bool = False, **_: Any) -> bool:
    return sandbox_enabled


def _handle_run_code(args: dict, ctx: ToolContext) -> str:
    code = args.get("code") or ""
    reason = args.get("reason") or ""

    if not code.strip():
        return "Error: code is required (non-empty Python source)."

    # Judge approval at tier 2 (config change) — the code string is the
    # detail logged in the audit trail so we can reconstruct what ran.
    if not ctx.judge.approve("run_code", code, reason=reason):
        tier = tier_for("run_code", code)
        return (
            f"Code execution denied (tier {tier} — requires interactive approval). "
            "Sandbox execution is not available in HTTP/Telegram mode."
        )

    # Resolve config — sandbox_image and sandbox_timeout come from Config.
    # Fallback to safe defaults if config is not available (shouldn't happen
    # in normal operation, but defensive coding is correct here).
    image = "orion-sandbox:latest"
    timeout = 30
    if ctx.config is not None:
        image = getattr(ctx.config, "sandbox_image", image)
        timeout = getattr(ctx.config, "sandbox_timeout", timeout)

    try:
        executor = ctx.registry.get(None)  # default host (lab)
        result = _sandbox.execute_code(
            code,
            executor,
            image=image,
            timeout=timeout,
        )
    except Exception as exc:
        ctx.judge.record_outcome("run_code", code, "error")
        return f"Sandbox execution failed: {exc}"

    # Record outcome for trust evolution — exit_code 0 is success.
    ctx.judge.record_outcome(
        "run_code", code, "success" if result.exit_code == 0 else "error"
    )

    return _sandbox.format_result(result)


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
                    "Run a shell command on the target host (default: lab server). "
                    "Use ONLY for live state: checking processes, service status, logs, "
                    "disk usage, network. Do NOT use for questions answerable from the KB. "
                    "Auto-approved (tier 0) commands: ps, cat, head, tail, grep, ls, df, du, "
                    "free, uptime, nvidia-smi, sensors, journalctl, dmesg, w, who, last, "
                    "systemctl status/show/is-active/is-enabled/list-units/list-timers/cat, "
                    "docker ps/logs/inspect/stats/images/top/info/compose ps/compose logs, "
                    "ip addr/route/link/neigh, dnf list/info/search, ss, netstat, dig, "
                    "find, stat, lsblk, lscpu, lsof. "
                    "Commands not on this list require interactive approval and WILL BE "
                    "DENIED in HTTP/Telegram mode. Always prefer these safe commands."
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
                        "target_host": {
                            "type": "string",
                            "description": (
                                "Which host to target. Default: lab (the primary server). "
                                "Use only when explicitly asked to operate on a different host."
                            ),
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
                "description": "Read the contents of a file on the target host (default: lab server).",
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
                        "target_host": {
                            "type": "string",
                            "description": (
                                "Which host to target. Default: lab (the primary server). "
                                "Use only when explicitly asked to operate on a different host."
                            ),
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
                "description": "List the contents of a directory on the target host (default: lab server).",
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
                        "target_host": {
                            "type": "string",
                            "description": (
                                "Which host to target. Default: lab (the primary server). "
                                "Use only when explicitly asked to operate on a different host."
                            ),
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
                    "Write content to a file on the target host (default: lab server; "
                    "creates or overwrites). "
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
                        "target_host": {
                            "type": "string",
                            "description": (
                                "Which host to target. Default: lab (the primary server). "
                                "Use only when explicitly asked to operate on a different host."
                            ),
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        },
        "handler": _handle_write_file,
        "enabled": _always_enabled,
    },
    "web_search": {
        "schema": {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the public web via Tavily. Use this when the answer is "
                    "not in the KB and requires current information from the internet — "
                    "for example: CVE or security vulnerability queries, latest release "
                    "or version numbers, changelogs, recent news, anything dated in the "
                    "current or future year, or questions about software not in the homelab. "
                    "Always prefer this over guessing when the KB has no relevant results. "
                    "Private IPs and hostnames are stripped from the query before sending."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language search query",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        "handler": _handle_web_search,
        "enabled": _web_search_enabled,
    },
    "fetch_url": {
        "schema": {
            "type": "function",
            "function": {
                "name": "fetch_url",
                "description": (
                    "Fetch a public URL and extract its article text. "
                    "Only http:// and https:// are allowed. Private IPs, RFC1918 "
                    "addresses, and .local/.internal hostnames are blocked (SSRF guard). "
                    "Requires approval."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to fetch (must be http:// or https://)",
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
    "get_action_stats": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_action_stats",
                "description": (
                    "Query Judge audit log statistics — counts of approved and denied "
                    "actions matching a given pattern. Useful for trust/safety reporting."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": (
                                "Substring or regex to filter actions by name. "
                                "Use empty string to get all actions."
                            ),
                        }
                    },
                    "required": ["pattern"],
                },
            },
        },
        "handler": _handle_get_action_stats,
        "enabled": _always_enabled,
    },
    "get_security_events": {
        "schema": {
            "type": "function",
            "function": {
                "name": "get_security_events",
                "description": (
                    "Read the most recent Falco security events from the lab server, "
                    "with noisy/benign rules filtered out. Use this to check for "
                    "suspicious activity, intrusion attempts, or policy violations."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "n": {
                            "type": "integer",
                            "description": "Number of recent log lines to inspect (default 50).",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need this data.",
                        },
                    },
                    "required": ["reason"],
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
                    "Query Osquery for listening ports, established TCP connections, "
                    "and ARP cache on the lab server. Use this to investigate network "
                    "exposure, see which processes are listening, or map active sessions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need this data.",
                        }
                    },
                    "required": ["reason"],
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
                    "Get aggregate network interface statistics and the top active "
                    "flows from ntopng. Use this to answer questions about bandwidth "
                    "usage, top talkers, or anomalous traffic patterns."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need this data.",
                        }
                    },
                    "required": ["reason"],
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
                    "Run an Nmap ping-sweep (host discovery only, no port probing) "
                    "over a subnet. Use this to enumerate live hosts on the LAN. "
                    "Requires approval (tier 1) because it actively probes the network."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subnet": {
                            "type": "string",
                            "description": "CIDR subnet to scan, e.g. '192.168.5.0/24'.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you need this scan.",
                        },
                    },
                    "required": ["subnet", "reason"],
                },
            },
        },
        "handler": _handle_scan_lan,
        "enabled": _always_enabled,
    },
    "check_system_health": {
        "schema": {
            "type": "function",
            "function": {
                "name": "check_system_health",
                "description": (
                    "Run a structured health check across all HAL backend components: "
                    "vLLM, Ollama, pgvector, Prometheus, Docker containers, Pushgateway, "
                    "Grafana, and ntopng. Returns a table with status (ok/degraded/down), "
                    "detail, and latency for each component. Use this when asked if "
                    "everything is working, for a system health check, or to diagnose "
                    "which services are up or down."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        "handler": _handle_check_system_health,
        "enabled": _always_enabled,
    },
    "recover_component": {
        "schema": {
            "type": "function",
            "function": {
                "name": "recover_component",
                "description": (
                    "Trigger a recovery playbook for a failed component. Each component "
                    "has a pre-defined recovery sequence (e.g. restart the Docker container "
                    "or systemd service, then verify it came back). Use this after "
                    "check_system_health shows a component is down or degraded. "
                    "Valid components: pgvector, Prometheus, Grafana, Pushgateway, "
                    "ntopng, Ollama, vLLM. Each step is individually approved by the Judge."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "component": {
                            "type": "string",
                            "description": "The component to recover (must match a health check name).",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this recovery is needed.",
                        },
                    },
                    "required": ["component"],
                },
            },
        },
        "handler": _handle_recover_component,
        "enabled": _always_enabled,
    },
    "run_code": {
        "schema": {
            "type": "function",
            "function": {
                "name": "run_code",
                "description": (
                    "Execute Python code in an isolated sandbox container. "
                    "Use this for data analysis, calculations, text processing, "
                    "parsing structured data, or any task that benefits from "
                    "running real Python code. "
                    "The sandbox has NO network access, NO filesystem persistence, "
                    "and a 30-second timeout. Only the Python standard library is "
                    "available (no pip, no third-party packages). "
                    "Do NOT use this for system administration — use run_command "
                    "for checking services, reading logs, or managing infrastructure. "
                    "Requires interactive approval (tier 2)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": (
                                "Complete Python source code to execute. "
                                "Use print() for output — stdout is captured and returned."
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining what this code does and why.",
                        },
                    },
                    "required": ["code", "reason"],
                },
            },
        },
        "handler": _handle_run_code,
        "enabled": _sandbox_enabled,
    },
}


def get_tools(*, tavily_api_key: str = "", sandbox_enabled: bool = False) -> list[dict]:
    """Return active tools exposed to the LLM for this request."""
    return [
        spec["schema"]
        for spec in TOOL_REGISTRY.values()
        if spec["enabled"](
            tavily_api_key=tavily_api_key, sandbox_enabled=sandbox_enabled
        )
    ]


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
