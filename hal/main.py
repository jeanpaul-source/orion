#!/usr/bin/env python3
"""HAL — Orion's coordinator. Run with: python -m hal"""
import argparse
import os
import readline
import sys
import textwrap
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

import hal.config as cfg
from hal.agent import run_agent
from hal.executor import SSHExecutor
from hal.facts import remember
from hal.judge import AUDIT_LOG, Judge
from hal.knowledge import KnowledgeBase
from hal.llm import OllamaClient
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient
from hal.tunnel import SSHTunnel, port_open
from hal.workers import list_dir, read_file, write_file

console = Console()

HISTORY_FILE = Path.home() / ".orion" / "history"

SYSTEM_PROMPT = """\
You are HAL, the AI coordinator for the Orion homelab assistant. This is your identity — \
do not refer to yourself as Qwen, Claude, or any other model name. You are HAL.

Lab host: the-lab (192.168.5.10)
  CPU: Intel Core Ultra 7 265K (20 cores), 62 GB RAM, RTX 3090 Ti (24 GB VRAM)
  Services: Prometheus :9091, Grafana :3001, pgvector :5432, Ollama :11434 (bare metal — NOT Docker)
  IMPORTANT: Ollama runs as a systemd service on bare metal. Do NOT use docker commands for Ollama.

Your conversation history from previous sessions is loaded in the context above. \
When the operator asks what you remember or what was discussed, refer to those messages — \
that is your memory. Never say you cannot recall past conversations.

You have access to a knowledge base of homelab documentation, lab infrastructure configs, \
and live lab state. When context is provided above the user's question, use it to give \
precise, grounded answers. Cite file names when relevant. \
If you don't know something, say so. \
Do not hallucinate service names, ports, or config values — verify against context. \
Do not invent analysis, suggestions, or content that was not asked for. \
Keep answers SHORT — 2 to 5 sentences for status queries, a short paragraph for complex ones. \
If context from the knowledge base is not directly relevant to the question, ignore it.

For questions about ports, services, file paths, configuration, or any documented fact — \
call search_kb first. Only use run_command if you need live state that the KB cannot provide. \
For greetings or questions you can answer from context, respond directly without tools. \
Once you have the information you need, respond in plain text — do not keep calling tools \
to verify what you already know.
"""

HELP_TEXT = """\
Commands:
  /health          — live Prometheus metrics (cpu, mem, disk, load)
  /search <query>  — search the knowledge base directly
  /run <command>   — run a command on the lab server (tiered approval)
  /read <path>     — read a file from the server
  /ls <path>       — list a directory on the server
  /write <path>    — write a file on the server (prompts for content)
  /audit           — show recent audit log
  /kb              — list knowledge base categories
  /remember <fact> — store a fact permanently in the knowledge base
  /search_memory <q> — search past sessions for a keyword
  /sessions        — list recent sessions
  /resume <id>     — resume a past session
  /new             — start a fresh session
  /clear           — clear the screen
  /exit            — quit

Anything else is sent to HAL as a question (with knowledge base context).
"""



def setup_ollama(config: cfg.Config) -> tuple[OllamaClient, SSHTunnel | None]:
    from urllib.parse import urlparse

    parsed = urlparse(config.ollama_host)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434

    tunnel = None

    if not port_open(host, port):
        if config.use_ssh_tunnel:
            console.print(
                f"[yellow]Ollama not directly reachable — starting SSH tunnel "
                f"({config.lab_user}@{config.lab_host}:{port})[/]"
            )
            tunnel = SSHTunnel(config.lab_user, config.lab_host, port, 11434)
            tunnel.start()
            ollama_url = f"http://127.0.0.1:{tunnel.local_port}"
        else:
            # Auto-try SSH tunnel even if not explicitly configured
            console.print(
                "[yellow]Ollama not reachable directly — trying SSH tunnel...[/]"
            )
            tunnel = SSHTunnel(config.lab_user, config.lab_host, port, 11434)
            try:
                tunnel.start()
                ollama_url = f"http://127.0.0.1:{tunnel.local_port}"
                console.print("[green]SSH tunnel established.[/]")
            except RuntimeError as e:
                tunnel = None
                console.print(f"[red]Tunnel failed: {e}[/]")
                console.print(
                    "[red]Cannot reach Ollama. Check SSH access or set OLLAMA_HOST.[/]"
                )
                sys.exit(1)
    else:
        ollama_url = config.ollama_host

    client = OllamaClient(ollama_url, config.ollama_model, config.embed_model)

    if not client.ping():
        console.print("[red]Ollama is not responding. Is the service running?[/]")
        sys.exit(1)

    return client, tunnel


def cmd_health(prom: PrometheusClient) -> None:
    try:
        with console.status("querying prometheus...", spinner="dots"):
            h = prom.health()
        lines = []
        for key, val in h.items():
            if val is not None:
                lines.append(f"  {key:<16} {val}")
            else:
                lines.append(f"  {key:<16} unavailable")
        console.print(Panel("\n".join(lines), title="lab health", border_style="cyan"))
    except Exception as e:
        console.print(f"[red]Prometheus unreachable: {e}[/]")


def cmd_search(query: str, kb: KnowledgeBase) -> None:
    if not query:
        console.print("[yellow]Usage: /search <query>[/]")
        return
    try:
        with console.status("searching...", spinner="dots"):
            chunks = kb.search(query, top_k=5)
        for i, c in enumerate(chunks, 1):
            console.print(f"\n[bold]{i}. {c['file']}[/] [{c['category']}] score={c['score']:.3f}")
            console.print(textwrap.indent(c["content"][:400].strip(), "   "))
    except Exception as e:
        console.print(f"[red]KB unavailable: {e}[/]")


def cmd_run(command: str, executor: SSHExecutor, judge: Judge) -> None:
    if not command:
        console.print("[yellow]Usage: /run <shell command>[/]")
        return
    if not judge.approve("run_command", command):
        console.print("[yellow]Cancelled.[/]")
        return
    result = executor.run(command)
    if result["stdout"]:
        console.print(result["stdout"])
    if result["stderr"]:
        console.print(f"[red]{result['stderr']}[/]")
    if result["returncode"] != 0:
        console.print(f"[red]exit code {result['returncode']}[/]")


def cmd_read(path: str, executor: SSHExecutor, judge: Judge) -> None:
    if not path:
        console.print("[yellow]Usage: /read <path>[/]")
        return
    content = read_file(path, executor, judge)
    if content is None:
        console.print(f"[red]Could not read {path}[/]")
    else:
        console.print(content)


def cmd_ls(path: str, executor: SSHExecutor, judge: Judge) -> None:
    if not path:
        console.print("[yellow]Usage: /ls <path>[/]")
        return
    output = list_dir(path, executor, judge)
    if output is None:
        console.print(f"[red]Could not list {path}[/]")
    else:
        console.print(output)


def cmd_write(path: str, executor: SSHExecutor, judge: Judge) -> None:
    if not path:
        console.print("[yellow]Usage: /write <path>[/]")
        return
    console.print(f"[dim]Enter content for {path} (Ctrl+D on empty line to finish):[/]")
    lines = []
    try:
        while True:
            lines.append(input())
    except EOFError:
        pass
    content = "\n".join(lines)
    if not content.strip():
        console.print("[yellow]Empty content — aborted.[/]")
        return
    ok = write_file(path, content, executor, judge)
    if ok:
        console.print(f"[green]wrote {len(content)} bytes to {path}[/]")
    else:
        console.print(f"[red]write failed or cancelled[/]")


def cmd_audit(n: int = 20) -> None:
    try:
        lines = AUDIT_LOG.read_text().splitlines()
        if not lines:
            console.print("[dim]audit log is empty[/]")
            return
        for line in lines[-n:]:
            if "denied" in line:
                console.print(f"  [red]{line}[/]")
            elif "tier=0" in line:
                console.print(f"  [dim]{line}[/]")
            else:
                console.print(f"  [yellow]{line}[/]")
    except FileNotFoundError:
        console.print("[dim]no audit log yet[/]")


def cmd_kb(kb: KnowledgeBase) -> None:
    try:
        with console.status("querying...", spinner="dots"):
            cats = kb.categories()
        for name, count in cats:
            console.print(f"  {count:>5}  {name}")
    except Exception as e:
        console.print(f"[red]KB unavailable: {e}[/]")


def cmd_search_memory(query: str, mem: MemoryStore) -> None:
    if not query:
        console.print("[yellow]Usage: /search_memory <query>[/]")
        return
    results = mem.search_sessions(query)
    if not results:
        console.print("[dim]no matches found[/]")
        return
    prev_sid = None
    for r in results:
        if r["session_id"] != prev_sid:
            console.print(f"\n  [bold dim]session {r['session_id']}[/]")
            prev_sid = r["session_id"]
        role_color = "cyan" if r["role"] == "assistant" else "white"
        ts = r["timestamp"][:16].replace("T", " ")
        preview = r["content"][:180].replace("\n", " ")
        console.print(f"    [{role_color}]{r['role']:<10}[/] [dim]{ts}[/]  {preview}")


def cmd_sessions(mem: MemoryStore) -> None:
    sessions = mem.list_sessions(10)
    if not sessions:
        console.print("[dim]no sessions yet[/]")
        return
    for s in sessions:
        ts = s["started_at"][:16].replace("T", " ")
        label = s["label"] or "(no label)"
        exchanges = s["turn_count"] // 2
        console.print(
            f"  [bold]{s['id']}[/]  {ts}  {exchanges} exchanges  [dim]{label}[/]"
        )


def cmd_remember(fact: str, dsn: str, llm: OllamaClient) -> None:
    if not fact:
        console.print("[yellow]Usage: /remember <fact>[/]")
        return
    with console.status("storing fact...", spinner="dots"):
        remember(fact, dsn, llm)
    console.print(f"[green]remembered:[/] {fact}")




def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hal",
        description="HAL — Orion homelab AI coordinator",
    )
    parser.add_argument(
        "--new", action="store_true", help="start a fresh session (don't resume last)"
    )
    args = parser.parse_args()

    config = cfg.load()

    # Load readline history
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(str(HISTORY_FILE))
    except FileNotFoundError:
        pass
    readline.set_history_length(1000)

    console.print(
        Panel(
            Text("HAL — Orion homelab coordinator", style="bold cyan"),
            subtitle="type /help for commands",
            border_style="cyan",
        )
    )

    ollama, tunnel = setup_ollama(config)
    kb = KnowledgeBase(config.pgvector_dsn, ollama)
    prom = PrometheusClient(config.prometheus_url)
    executor = SSHExecutor(config.lab_host, config.lab_user)
    judge = Judge(ollama=ollama)
    mem = MemoryStore()

    # Resume last session or start fresh
    session_id = mem.last_session_id()
    if session_id and not args.new:
        history = mem.load_turns(session_id)
        exchanges = len(history) // 2
        console.print(
            f"[green]connected[/] — model: [bold]{config.ollama_model}[/]  "
            f"prom: {config.prometheus_url}"
        )
        console.print(f"[dim]resumed session {session_id} ({exchanges} exchanges)[/]")
    else:
        session_id = mem.new_session()
        history = []
        console.print(
            f"[green]connected[/] — model: [bold]{config.ollama_model}[/]  "
            f"prom: {config.prometheus_url}"
        )
        console.print(f"[dim]new session {session_id}[/]")

    try:
        while True:
            try:
                user_input = input("\nyou> ").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]shutting down.[/]")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                console.print("[dim]shutting down.[/]")
                break

            if user_input == "/help":
                console.print(HELP_TEXT)
            elif user_input == "/health":
                cmd_health(prom)
            elif user_input.startswith("/search "):
                cmd_search(user_input[8:].strip(), kb)
            elif user_input.startswith("/run "):
                cmd_run(user_input[5:].strip(), executor, judge)
            elif user_input.startswith("/read "):
                cmd_read(user_input[6:].strip(), executor, judge)
            elif user_input.startswith("/ls "):
                cmd_ls(user_input[4:].strip(), executor, judge)
            elif user_input.startswith("/write "):
                cmd_write(user_input[7:].strip(), executor, judge)
            elif user_input == "/audit":
                cmd_audit()
            elif user_input == "/kb":
                cmd_kb(kb)
            elif user_input.startswith("/remember "):
                cmd_remember(user_input[10:].strip(), config.pgvector_dsn, ollama)
            elif user_input.startswith("/search_memory "):
                cmd_search_memory(user_input[15:].strip(), mem)
            elif user_input == "/sessions":
                cmd_sessions(mem)
            elif user_input.startswith("/resume "):
                sid = user_input[8:].strip()
                if mem.session_exists(sid):
                    session_id = sid
                    turns = mem.load_turns(sid)
                    history[:] = turns
                    console.print(
                        f"[dim]resumed session {session_id} ({len(turns) // 2} exchanges)[/]"
                    )
                else:
                    console.print(f"[red]session {sid} not found[/]")
            elif user_input == "/new":
                session_id = mem.new_session()
                history.clear()
                console.print(f"[dim]new session {session_id}[/]")
            elif user_input == "/clear":
                os.system("clear")
            elif user_input.startswith("/"):
                console.print("[yellow]Unknown command. Type /help.[/]")
            else:
                run_agent(
                    user_input, history, ollama, kb, prom,
                    executor, judge, mem, session_id, SYSTEM_PROMPT, console,
                )

    finally:
        if tunnel:
            tunnel.stop()
        mem.close()
        readline.write_history_file(str(HISTORY_FILE))


if __name__ == "__main__":
    main()
