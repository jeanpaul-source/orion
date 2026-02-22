"""Agentic loop — LLM calls tools autonomously, Judge gates everything."""
import json
import textwrap

from rich.console import Console

from hal.executor import SSHExecutor
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import OllamaClient
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient
from hal.workers import list_dir, read_file

MAX_ITERATIONS = 8

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command on the lab server (192.168.5.10). "
                "Use for checking processes, service status, logs, disk usage, network, etc."
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
            "name": "search_kb",
            "description": (
                "Search the homelab knowledge base for documentation, configs, "
                "and infrastructure facts. Use this before running commands when "
                "you need to know how something is configured."
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
            if c["score"] >= 0.4:
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

    for iteration in range(MAX_ITERATIONS):
        label = f" (step {iteration + 1})" if iteration > 0 else ""
        with console.status(f"[dim]thinking{label}...[/]", spinner="dots"):
            msg = ollama.chat_with_tools(working, TOOLS, system=system)

        working.append(msg)
        tool_calls = msg.get("tool_calls") or []

        # Fallback: qwen sometimes outputs tool calls as JSON text in content
        # instead of using the proper tool_calls field.
        if not tool_calls and msg.get("content"):
            content = msg["content"].strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                lines = content.splitlines()
                content = "\n".join(
                    l for l in lines if not l.startswith("```")
                ).strip()
            if content.startswith("{") and '"name"' in content:
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "name" in parsed:
                        tool_calls = [{
                            "function": {
                                "name": parsed["name"],
                                "arguments": parsed.get("arguments", {}),
                            }
                        }]
                        msg["content"] = ""
                except json.JSONDecodeError:
                    pass

        if not tool_calls:
            # Text-only response — agent is done
            response_text = msg.get("content", "").strip()
            console.print(f"\n[bold cyan]hal>[/] {response_text}")
            break

        # Execute each tool call and feed results back
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

            console.print(f"\n  [dim cyan]→ {name}({_fmt_args(raw_args)})[/]")
            result = _dispatch(name, raw_args, executor, judge, kb, prom)
            preview = textwrap.shorten(result, width=140, placeholder="…")
            console.print(f"  [dim]↳ {preview}[/]")

            working.append({"role": "tool", "content": result})

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
