"""Agentic loop — LLM calls tools autonomously, Judge gates everything."""
import json
import textwrap

from rich.console import Console

from hal.executor import SSHExecutor
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import VLLMClient
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient
from hal.tracing import get_tracer
from hal.workers import list_dir, read_file, write_file, patch_file, git_status, git_diff
from hal.security import (
    get_security_events,
    get_host_connections,
    get_traffic_summary,
    scan_lan,
)

MAX_ITERATIONS = 8

TOOLS = [
    {
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
    {
        "type": "function",
        "function": {
            "name": "get_metrics",
            "description": (
                "Get live Prometheus metrics: CPU usage, memory, disk, "
                "load average, uptime."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
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
    {
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
    {
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
    {
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
    {
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
    {
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
    {
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
    {
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
    {
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
    {
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
    {
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
]


def _dispatch(
    name: str,
    args: dict,
    executor: SSHExecutor,
    judge: Judge,
    kb: KnowledgeBase,
    prom: PrometheusClient,
    ntopng_url: str = "http://localhost:3000",
) -> str:
    """Route a tool call to the right worker. Returns a result string."""
    if name == "run_command":
        command = args.get("command", "")
        reason = args.get("reason", "")
        if not judge.approve("run_command", command, reason=reason):
            return "Action denied by user."
        result = executor.run(command)
        parts = []
        if result["stdout"].strip():
            parts.append(result["stdout"].strip())
        if result["stderr"].strip():
            parts.append(f"[stderr] {result['stderr'].strip()}")
        if result["returncode"] != 0:
            parts.append(f"[exit {result['returncode']}]")
        return "\n".join(parts) or "(no output)"

    elif name == "read_file":
        path = args.get("path", "")
        reason = args.get("reason", "")
        content = read_file(path, executor, judge, reason=reason)
        return content if content is not None else f"Could not read {path}"

    elif name == "list_dir":
        path = args.get("path", "")
        reason = args.get("reason", "")
        output = list_dir(path, executor, judge, reason=reason)
        return output if output is not None else f"Could not list {path}"

    elif name == "write_file":
        path = args.get("path", "")
        content = args.get("content", "")
        reason = args.get("reason", "")
        ok = write_file(path, content, executor, judge, reason=reason)
        return f"Written {len(content)} bytes to {path}" if ok else f"Write failed or denied for {path}"

    elif name == "search_kb":
        query = args.get("query", "")
        try:
            chunks = kb.search(query, top_k=5)
            lines = []
            for c in chunks:
                if c["score"] < 0.3:
                    continue
                lines.append(f"[{c['file']} | score={c['score']:.2f}]")
                lines.append(c["content"].strip())
                lines.append("")
            return "\n".join(lines) if lines else "No relevant results found."
        except Exception as e:
            return f"KB search failed: {e}"

    elif name == "patch_file":
        path = args.get("path", "")
        old_str = args.get("old_str", "")
        new_str = args.get("new_str", "")
        reason = args.get("reason", "")
        return patch_file(path, old_str, new_str, executor, judge, reason=reason)

    elif name == "git_status":
        repo_path = args.get("repo_path", "")
        reason = args.get("reason", "")
        return git_status(repo_path, executor, judge, reason=reason)

    elif name == "git_diff":
        repo_path = args.get("repo_path", "")
        ref = args.get("ref", "HEAD")
        reason = args.get("reason", "")
        return git_diff(repo_path, executor, judge, ref=ref, reason=reason)

    elif name == "get_metrics":
        try:
            h = prom.health()
            return "\n".join(f"{k}: {v}" for k, v in h.items() if v is not None)
        except Exception as e:
            return f"Metrics unavailable: {e}"

    elif name == "get_security_events":
        n = int(args.get("n", 50))
        reason = args.get("reason", "")
        events = get_security_events(executor, judge, n=n, reason=reason)
        return json.dumps(events, indent=2)

    elif name == "get_host_connections":
        reason = args.get("reason", "")
        data = get_host_connections(executor, judge, reason=reason)
        return json.dumps(data, indent=2) if data else "Denied."

    elif name == "get_traffic_summary":
        top_flows = int(args.get("top_flows", 20))
        reason = args.get("reason", "")
        data = get_traffic_summary(executor, judge, ntopng_url=ntopng_url, top_flows=top_flows, reason=reason)
        return json.dumps(data, indent=2) if data else "Denied."

    elif name == "scan_lan":
        subnet = args.get("subnet", "")
        reason = args.get("reason", "")
        if not subnet:
            return "Error: subnet is required."
        hosts = scan_lan(subnet, executor, judge, reason=reason)
        return json.dumps(hosts, indent=2)

    else:
        return f"Unknown tool: {name}"


def run_health(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    prom: PrometheusClient,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
) -> str:
    """Health handler: fetch live metrics, answer in one LLM call with no tools."""
    with get_tracer().start_as_current_span("hal.run_health") as span:
        span.set_attribute("hal.session_id", session_id)
        span.set_attribute("hal.query", user_input[:200])
        try:
            with console.status("[dim]fetching metrics...[/]", spinner="dots"):
                h = prom.health()
            metrics_str = "\n".join(
                f"{k}: {v}" for k, v in h.items() if v is not None
            )
            span.set_attribute("hal.metrics_available", True)
        except Exception as e:
            metrics_str = f"Metrics unavailable: {e}"
            span.set_attribute("hal.metrics_available", False)

        messages = list(history) + [{
            "role": "user",
            "content": f"Current lab metrics:\n{metrics_str}\n\n{user_input}",
        }]

        with console.status("[dim]thinking...[/]", spinner="dots"):
            response = llm.chat(messages, system=system)

        response = response.strip()
        span.set_attribute("hal.response_len", len(response))
        console.print(f"\n[bold cyan]hal>[/] {response}")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        mem.save_turn(session_id, "user", user_input)
        mem.save_turn(session_id, "assistant", response)

        if len(history) > 40:
            history[:] = history[-40:]

        return response


def run_fact(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    kb: KnowledgeBase,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
) -> str:
    """Fact handler: search KB once, answer in one LLM call with no tools.

    If the KB has nothing relevant, the LLM answers from the system prompt alone
    (which contains key lab facts). If it still doesn't know, it says so.
    """
    with get_tracer().start_as_current_span("hal.run_fact") as span:
        span.set_attribute("hal.session_id", session_id)
        span.set_attribute("hal.query", user_input[:200])
        try:
            with console.status("[dim]searching knowledge base...[/]", spinner="dots"):
                chunks = kb.search(user_input, top_k=3)
            relevant = [c for c in chunks if c["score"] >= 0.5]
            span.set_attribute("hal.kb.chunks_returned", len(chunks))
            span.set_attribute("hal.kb.relevant_chunks", len(relevant))
            if relevant:
                span.set_attribute("hal.kb.top_score", relevant[0]["score"])
        except Exception:
            relevant = []
            span.set_attribute("hal.kb.chunks_returned", 0)
            span.set_attribute("hal.kb.relevant_chunks", 0)

        if relevant:
            context = "\n\n".join(
                f"[{c['file']} | score={c['score']:.2f}]\n{c['content'].strip()}"
                for c in relevant
            )
            augmented = f"{context}\n\n{user_input}"
        else:
            augmented = user_input

        messages = list(history) + [{"role": "user", "content": augmented}]

        with console.status("[dim]thinking...[/]", spinner="dots"):
            response = llm.chat(messages, system=system)

        response = response.strip()
        span.set_attribute("hal.response_len", len(response))
        console.print(f"\n[bold cyan]hal>[/] {response}")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        mem.save_turn(session_id, "user", user_input)
        mem.save_turn(session_id, "assistant", response)

        if len(history) > 40:
            history[:] = history[-40:]

        return response


def run_agent(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    kb: KnowledgeBase,
    prom: PrometheusClient,
    executor: SSHExecutor,
    judge: Judge,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
    ntopng_url: str = "http://localhost:3000",
) -> str:
    """Agentic loop: LLM calls tools autonomously until it produces a final answer.

    Returns the final text response.
    """
    with get_tracer().start_as_current_span("hal.run_agent") as span:
        span.set_attribute("hal.session_id", session_id)
        span.set_attribute("hal.query", user_input[:200])
        # Seed the first message with KB context (fast, cheap, often helpful)
        # Threshold 0.75: only inject context that is a strong semantic match.
        # At 0.6 casual queries pulled in loosely-related docs (e.g. Prometheus
        # config for a greeting) which the LLM answered instead of the question.
        try:
            chunks = kb.search(user_input, top_k=3)
            context_lines = []
            for c in chunks:
                if c["score"] >= 0.75:
                    context_lines.append(f"[{c['file']} | score={c['score']:.2f}]")
                    context_lines.append(c["content"].strip())
            if context_lines:
                context_str = "\n".join(context_lines)
                augmented = f"{context_str}\n\n{user_input}"
            else:
                augmented = user_input
            span.set_attribute("hal.kb.seeded_chunks", len(context_lines) // 2)
        except Exception:
            augmented = user_input
            span.set_attribute("hal.kb.seeded_chunks", 0)

        # Working history — don't mutate the session history until we have a final answer
        working = list(history) + [{"role": "user", "content": augmented}]

        response_text = ""
        seen_calls: set[tuple] = set()  # (name, args_json) — detect repeat tool calls
        total_calls = 0  # total unique tool calls dispatched this turn

        for iteration in range(MAX_ITERATIONS):
            label = f" (step {iteration + 1})" if iteration > 0 else ""
            # If we've already dispatched 5 unique tool calls, stop collecting data
            # and force a text-only response regardless of iteration count
            effective_tools = TOOLS if (iteration < MAX_ITERATIONS - 1 and total_calls < 5) else []
            with console.status(f"[dim]thinking{label}...[/]", spinner="dots"):
                msg = llm.chat_with_tools(working, effective_tools, system=system)

            working.append(msg)
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                # Text-only response — agent is done
                response_text = (msg.get("content") or "").strip()
                span.set_attribute("hal.iterations", iteration + 1)
                span.set_attribute("hal.total_tool_calls", total_calls)
                span.set_attribute("hal.response_len", len(response_text))
                console.print(f"\n[bold cyan]hal>[/] {response_text}")
                break

            # Execute each tool call and feed results back
            new_calls = 0
            for tc in tool_calls:
                call_id = tc.get("id", "")
                fn = tc.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {})

                # Some models return arguments as a JSON string instead of a dict
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {}

                # Detect repeat calls — model stuck in a loop
                call_key = (name, json.dumps(raw_args, sort_keys=True))
                if call_key in seen_calls:
                    working.append({"role": "tool", "content": "[Already called — use the result above.]", "tool_call_id": call_id})
                    continue
                seen_calls.add(call_key)

                console.print(f"\n[bold green]⏺[/] [cyan]{name}[/]({_fmt_args(raw_args)})")
                with get_tracer().start_as_current_span("hal.tool_call") as tool_span:
                    tool_span.set_attribute("tool.name", name)
                    tool_span.set_attribute("tool.iteration", iteration)
                    tool_span.set_attribute("tool.args", json.dumps(raw_args, sort_keys=True)[:500])
                    result = _dispatch(name, raw_args, executor, judge, kb, prom, ntopng_url)
                    tool_span.set_attribute("tool.result_len", len(result))

                # Cap tool output to protect the context window
                _MAX_TOOL_OUTPUT = 8000
                if len(result) > _MAX_TOOL_OUTPUT:
                    omitted = len(result) - _MAX_TOOL_OUTPUT
                    result = result[:_MAX_TOOL_OUTPUT] + f"\n[…{omitted} chars omitted]"

                preview = textwrap.shorten(result, width=140, placeholder="…")
                console.print(f"  [dim]{preview}[/]")

                working.append({"role": "tool", "content": result, "tool_call_id": call_id})
                new_calls += 1
                total_calls += 1

            # If every call this iteration was a duplicate, the model is looping.
            # Inject a directive to stop collecting data and respond in plain text.
            if new_calls == 0:
                working.append({
                    "role": "user",
                    "content": (
                        "You already have all the data you need. "
                        "Please provide your final answer now as plain text, "
                        "without calling any more tools."
                    ),
                })

        else:
            response_text = "Reached max iterations without a final answer."
            span.set_attribute("hal.iterations", MAX_ITERATIONS)
            span.set_attribute("hal.total_tool_calls", total_calls)
            span.set_attribute("hal.max_iterations_reached", True)
            console.print(f"\n[bold cyan]hal>[/] {response_text}")

        # Persist clean user input + final response to session history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response_text})
        mem.save_turn(session_id, "user", user_input)
        mem.save_turn(session_id, "assistant", response_text)

        if len(history) > 40:
            history[:] = history[-40:]

        return response_text


def run_conversational(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
) -> str:
    """Fast path for greetings and small talk — one LLM call, no tools, no KB lookup."""
    messages = list(history) + [{"role": "user", "content": user_input}]
    response = llm.chat(messages, system=system).strip()
    console.print(f"\n[bold cyan]hal>[/] {response}")
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": response})
    mem.save_turn(session_id, "user", user_input)
    mem.save_turn(session_id, "assistant", response)
    if len(history) > 40:
        history[:] = history[-40:]
    return response


def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:60] + "…"
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)
