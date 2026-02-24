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
from hal.agent import run_agent, run_conversational, run_fact, run_health
from hal.executor import SSHExecutor
from hal.facts import remember
from hal.intent import IntentClassifier
from hal.judge import AUDIT_LOG, Judge
from hal.knowledge import KnowledgeBase
from hal.llm import OllamaClient, VLLMClient
from hal.logging_utils import set_context, setup_logging
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient, start_metrics_heartbeat
from hal.tracing import get_tracer, setup_tracing
from hal.tunnel import SSHTunnel, port_open
from hal.workers import list_dir, read_file, write_file

console = Console()

HISTORY_FILE = Path.home() / ".orion" / "history"

SYSTEM_PROMPT = """\
You are HAL — a personal homelab AI assistant built intentionally. \
You are not Qwen, Claude, or any other model. You are HAL. Never break this identity.

Your purpose has five roles:
1. KNOW the infrastructure — you have a knowledge base of lab configs, service docs, and live state.
2. ANSWER questions about it — precisely, grounded in that knowledge, never invented.
3. ACT on it — run commands, restart services, edit configs — always through the approval tiers.
4. MONITOR health — spot problems in metrics, logs, and service state before the operator asks.
5. GUARD the network — four dedicated security tools exist; prefer them over run_command for security questions:
   - get_security_events   → recent Falco runtime alerts, noise-filtered; use for "anything suspicious?"
   - get_host_connections  → listening ports, established connections, ARP table (Osquery)
   - get_traffic_summary   → live flows and bandwidth stats (ntopng)
   - scan_lan <subnet>     → discover live hosts on the LAN (Nmap, prompts user first)

Lab host: the-lab (192.168.5.10)
  CPU: Intel Core Ultra 7 265K (20 cores), 62 GB RAM, RTX 3090 Ti (24 GB VRAM)
  Services: Prometheus :9091, Grafana :3001, pgvector :5432, Ollama :11434 (bare metal — NOT Docker)
  IMPORTANT: Ollama is a bare-metal systemd service. Never use docker commands for Ollama.
  Security stack (all on the-lab):
    Falco (eBPF modern-bpf) — runtime security alerts → /var/log/falco/events.json
    Osquery 5.21.0          — SQL-queryable OS state (ports, processes, sockets, ARP)
    ntopng :3000 (Docker)   — live traffic flows, bandwidth, per-host stats (interface enp130s0)
    Nmap 7.92               — LAN host discovery (ping sweep only, tier-1 approval required)

Memory: your conversation history from previous sessions is in the context above. \
When asked what you remember, refer to those messages. Never claim you can't recall past conversations.

Rules:
- Do not hallucinate ports, service names, file paths, or config values — only state what the context confirms.
- Use tools to check live state when the question requires it; use the KB when the answer is already documented.
- If context from the knowledge base is not relevant to the question, ignore it entirely.
- Keep answers SHORT: 2–5 sentences for status queries, one short paragraph for complex ones.
- If you don't know something, say so plainly.
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



def _connect(
    name: str, url: str, lab_user: str, lab_host: str, default_port: int
) -> tuple[str, SSHTunnel | None]:
    """Return (reachable_url, tunnel_or_None). Tries direct first, then SSH tunnel.

    SSH tunnel is only attempted when the target host is a remote address.
    If the URL already points to localhost/127.0.0.1 and the port is closed,
    the service simply isn't running — tunneling can't help.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or default_port

    if port_open(host, port):
        return url, None

    # Don't try to SSH-tunnel to ourselves — it can't help.
    if host in ("localhost", "127.0.0.1"):
        console.print(f"[red]{name} is not reachable on {host}:{port} — is it running?[/]")
        sys.exit(1)

    console.print(f"[yellow]{name} not directly reachable — trying SSH tunnel...[/]")
    tunnel = SSHTunnel(lab_user, lab_host, port, default_port)
    try:
        tunnel.start()
        console.print(f"[green]{name} SSH tunnel established.[/]")
        return f"http://127.0.0.1:{tunnel.local_port}", tunnel
    except RuntimeError as e:
        console.print(f"[red]{name} tunnel failed: {e}[/]")
        sys.exit(1)


def setup_clients(
    config: cfg.Config,
) -> tuple[VLLMClient, OllamaClient, list[SSHTunnel]]:
    """Connect to vLLM (chat) and Ollama (embeddings). Returns both clients and any tunnels opened."""
    tunnels: list[SSHTunnel] = []

    vllm_url, t = _connect("vLLM", config.vllm_url, config.lab_user, config.lab_host, 8000)
    if t:
        tunnels.append(t)
    llm = VLLMClient(vllm_url, config.chat_model)
    if not llm.ping():
        console.print(
            "[red]vLLM is not ready.[/] The service may still be loading the model. "
            "Check with: [dim]journalctl --user -u vllm -n 30[/]"
        )
        sys.exit(1)

    ollama_url, t = _connect("Ollama", config.ollama_host, config.lab_user, config.lab_host, 11434)
    if t:
        tunnels.append(t)
    embed = OllamaClient(ollama_url, config.embed_model)
    if not embed.ping():
        console.print("[red]Ollama is not responding. Is it running?[/]")
        sys.exit(1)

    return llm, embed, tunnels


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
        console.print("[red]write failed or cancelled[/]")


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


def cmd_remember(fact: str, dsn: str, embed: OllamaClient) -> None:
    if not fact:
        console.print("[yellow]Usage: /remember <fact>[/]")
        return
    with console.status("storing fact...", spinner="dots"):
        remember(fact, dsn, embed)
    console.print(f"[green]remembered:[/] {fact}")




def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hal",
        description="HAL — Orion homelab AI coordinator",
    )
    parser.add_argument(
        "--new", action="store_true", help="start a fresh session (don't resume last)"
    )
    parser.add_argument(
        "--print", dest="query", metavar="QUERY",
        help="run a single query non-interactively, print the answer, and exit",
    )
    args = parser.parse_args()

    config = cfg.load()

    # Observability init: logs then tracing
    setup_logging()
    setup_tracing()
    start_metrics_heartbeat()

    # Load readline history (skip in non-interactive --print mode)
    if not args.query:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            readline.read_history_file(str(HISTORY_FILE))
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)

    if not args.query:
        console.print(
            Panel(
                Text("HAL \u2014 Orion homelab coordinator", style="bold cyan"),
                subtitle="type /help for commands",
                border_style="cyan",
            )
        )

    llm, embed, tunnels = setup_clients(config)
    kb = KnowledgeBase(config.pgvector_dsn, embed)
    prom = PrometheusClient(config.prometheus_url)
    executor = SSHExecutor(config.lab_host, config.lab_user)
    judge = Judge(llm=llm)
    mem = MemoryStore()
    mem.prune_old_turns()  # silently drop turns older than 30 days on every startup

    with console.status("[dim]building intent classifier...[/]", spinner="dots"):
        classifier = IntentClassifier(embed)

    # Resume last session or start fresh
    session_id = mem.last_session_id()
    if session_id and not args.new:
        history = mem.load_turns(session_id)
        exchanges = len(history) // 2
        if not args.query:
            console.print(
                f"[green]connected[/] \u2014 model: [bold]{config.chat_model}[/]  "
                f"prom: {config.prometheus_url}"
            )
            console.print(f"[dim]resumed session {session_id} ({exchanges} exchanges)[/]")
    else:
        session_id = mem.new_session()
        history = []
        if not args.query:
            console.print(
                f"[green]connected[/] \u2014 model: [bold]{config.chat_model}[/]  "
                f"prom: {config.prometheus_url}"
            )
            console.print(f"[dim]new session {session_id}[/]")

    # --print mode: single-shot query, no REPL
    if args.query:
        try:
            user_input = args.query.strip()
            intent, confidence = classifier.classify(user_input)
            if intent == "conversational":
                run_conversational(user_input, history, llm, mem, session_id, SYSTEM_PROMPT, console)
            elif intent == "health":
                run_health(user_input, history, llm, prom, mem, session_id, SYSTEM_PROMPT, console)
            elif intent == "fact":
                run_fact(user_input, history, llm, kb, mem, session_id, SYSTEM_PROMPT, console)
            else:
                run_agent(user_input, history, llm, kb, prom, executor, judge, mem, session_id, SYSTEM_PROMPT, console, ntopng_url=config.ntopng_url)
        finally:
            for tunnel in tunnels:
                tunnel.stop()
            mem.close()
        return

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
                cmd_remember(user_input[10:].strip(), config.pgvector_dsn, embed)
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
                intent, confidence = classifier.classify(user_input)
                console.print(f"[dim]  intent: {intent} ({confidence:.2f})[/]")

                # Set logging context for this turn
                set_context(session_id=session_id)
                with get_tracer().start_as_current_span("hal.turn") as turn_span:
                    turn_span.set_attribute("hal.session_id", session_id)
                    turn_span.set_attribute("hal.query", user_input[:200])
                    turn_span.set_attribute("hal.intent", intent)
                    turn_span.set_attribute("hal.confidence", confidence)

                    if intent == "conversational":
                        run_conversational(
                            user_input, history, llm,
                            mem, session_id, SYSTEM_PROMPT, console,
                        )
                    elif intent == "health":
                        run_health(
                            user_input, history, llm, prom,
                            mem, session_id, SYSTEM_PROMPT, console,
                        )
                    elif intent == "fact":
                        run_fact(
                            user_input, history, llm, kb,
                            mem, session_id, SYSTEM_PROMPT, console,
                        )
                    else:
                        run_agent(
                            user_input, history, llm, kb, prom,
                            executor, judge, mem, session_id, SYSTEM_PROMPT, console,
                            ntopng_url=config.ntopng_url,
                        )

    finally:
        for tunnel in tunnels:
            tunnel.stop()
        mem.close()
        readline.write_history_file(str(HISTORY_FILE))


if __name__ == "__main__":
    main()
