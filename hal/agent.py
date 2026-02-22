"""Agentic loop — LLM calls tools autonomously, Judge gates everything."""
import json
import re
import textwrap

# Qwen model control tokens that sometimes leak into responses
_CONTROL_TOKEN_RE = re.compile(r"<\|[^|>]+\|>")

from rich.console import Console

from hal.executor import SSHExecutor
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import OllamaClient
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient
from hal.workers import list_dir, read_file, write_file

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
]


def _dispatch(
    name: str,
    args: dict,
    executor: SSHExecutor,
    judge: Judge,
    kb: KnowledgeBase,
    prom: PrometheusClient,
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

    elif name == "get_metrics":
        try:
            h = prom.health()
            return "\n".join(f"{k}: {v}" for k, v in h.items() if v is not None)
        except Exception as e:
            return f"Metrics unavailable: {e}"

    else:
        return f"Unknown tool: {name}"


def run_health(
    user_input: str,
    history: list[dict],
    ollama: OllamaClient,
    prom: PrometheusClient,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
) -> str:
    """Health handler: fetch live metrics, answer in one LLM call with no tools."""
    try:
        with console.status("[dim]fetching metrics...[/]", spinner="dots"):
            h = prom.health()
        metrics_str = "\n".join(
            f"{k}: {v}" for k, v in h.items() if v is not None
        )
    except Exception as e:
        metrics_str = f"Metrics unavailable: {e}"

    messages = list(history) + [{
        "role": "user",
        "content": f"Current lab metrics:\n{metrics_str}\n\n{user_input}",
    }]

    with console.status("[dim]thinking...[/]", spinner="dots"):
        response = ollama.chat(messages, system=system)

    response = _CONTROL_TOKEN_RE.sub("", response).strip()
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
    ollama: OllamaClient,
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
    try:
        with console.status("[dim]searching knowledge base...[/]", spinner="dots"):
            chunks = kb.search(user_input, top_k=3)
        relevant = [c for c in chunks if c["score"] >= 0.5]
    except Exception:
        relevant = []

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
        response = ollama.chat(messages, system=system)

    response = _CONTROL_TOKEN_RE.sub("", response).strip()
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
    ollama: OllamaClient,
    kb: KnowledgeBase,
    prom: PrometheusClient,
    executor: SSHExecutor,
    judge: Judge,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
) -> str:
    """Agentic loop: LLM calls tools autonomously until it produces a final answer.

    Returns the final text response.
    """
    # Seed the first message with KB context (fast, cheap, often helpful)
    try:
        chunks = kb.search(user_input, top_k=3)
        context_lines = []
        for c in chunks:
            if c["score"] >= 0.6:
                context_lines.append(f"[{c['file']} | score={c['score']:.2f}]")
                context_lines.append(c["content"].strip())
        if context_lines:
            context_str = "\n".join(context_lines)
            augmented = f"{context_str}\n\n{user_input}"
        else:
            augmented = user_input
    except Exception:
        augmented = user_input

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
            msg = ollama.chat_with_tools(working, effective_tools, system=system)

        working.append(msg)
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            # Text-only response — agent is done; strip any leaked control tokens
            raw_content = msg.get("content", "")
            response_text = _CONTROL_TOKEN_RE.sub("", raw_content).strip()
            console.print(f"\n[bold cyan]hal>[/] {response_text}")
            break

        # Execute each tool call and feed results back
        new_calls = 0
        for tc in tool_calls:
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
                working.append({"role": "tool", "content": "[Already called — use the result above.]"})
                continue
            seen_calls.add(call_key)

            console.print(f"\n  [dim cyan]→ {name}({_fmt_args(raw_args)})[/]")
            result = _dispatch(name, raw_args, executor, judge, kb, prom)

            # Cap tool output to protect the context window
            _MAX_TOOL_OUTPUT = 8000
            if len(result) > _MAX_TOOL_OUTPUT:
                omitted = len(result) - _MAX_TOOL_OUTPUT
                result = result[:_MAX_TOOL_OUTPUT] + f"\n[…{omitted} chars omitted]"

            preview = textwrap.shorten(result, width=140, placeholder="…")
            console.print(f"  [dim]↳ {preview}[/]")

            working.append({"role": "tool", "content": result})
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
        console.print(f"\n[bold cyan]hal>[/] {response_text}")

    # Persist clean user input + final response to session history
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": response_text})
    mem.save_turn(session_id, "user", user_input)
    mem.save_turn(session_id, "assistant", response_text)

    if len(history) > 40:
        history[:] = history[-40:]

    return response_text


def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:60] + "…"
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)
