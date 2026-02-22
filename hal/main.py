#!/usr/bin/env python3
"""HAL — Orion's coordinator. Run with: python -m hal"""
import readline  # noqa: F401 — enables history/editing in input()
import sys
import textwrap

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

import hal.config as cfg
from hal.executor import SSHExecutor
from hal.knowledge import KnowledgeBase
from hal.llm import OllamaClient
from hal.prometheus import PrometheusClient
from hal.tunnel import SSHTunnel, port_open

console = Console()

SYSTEM_PROMPT = """\
You are HAL, the AI coordinator for the Orion homelab assistant.
You know the infrastructure and help the operator understand, monitor, and manage it.

Lab host: the-lab (192.168.5.10)
  CPU: Intel Core Ultra 7 265K (20 cores), 62 GB RAM, RTX 3090 Ti (24 GB VRAM)
  Services: Prometheus :9090, Grafana :3000, pgvector :5432, Ollama :11434

You have access to a knowledge base of 2,244 homelab documentation chunks.
When context is provided above the user's question, use it to give precise, grounded answers.
Be concise. Cite file names when relevant. If you don't know something, say so.
Do not hallucinate service names, ports, or config values — verify against context.
"""

HELP_TEXT = """\
Commands:
  /health          — live Prometheus metrics (cpu, mem, disk, load)
  /search <query>  — search the knowledge base directly
  /run <command>   — run a command on the lab server (tiered approval)
  /kb              — list knowledge base categories
  /exit            — quit

Anything else is sent to HAL as a question (with knowledge base context).
"""


def format_context(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    lines = ["--- knowledge base context ---"]
    for c in chunks:
        score = c["score"]
        if score < 0.4:
            continue  # skip low-relevance chunks
        lines.append(f"[{c['file']} | {c['category']} | score={score:.2f}]")
        lines.append(c["content"].strip())
        lines.append("")
    if len(lines) == 1:
        return ""
    lines.append("--- end context ---")
    return "\n".join(lines)


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
    with console.status("querying prometheus...", spinner="dots"):
        h = prom.health()
    lines = []
    for key, val in h.items():
        if val is not None:
            lines.append(f"  {key:<16} {val}")
        else:
            lines.append(f"  {key:<16} unavailable")
    console.print(Panel("\n".join(lines), title="lab health", border_style="cyan"))


def cmd_search(query: str, kb: KnowledgeBase) -> None:
    if not query:
        console.print("[yellow]Usage: /search <query>[/]")
        return
    with console.status("searching...", spinner="dots"):
        chunks = kb.search(query, top_k=5)
    for i, c in enumerate(chunks, 1):
        console.print(f"\n[bold]{i}. {c['file']}[/] [{c['category']}] score={c['score']:.3f}")
        console.print(textwrap.indent(c["content"][:400].strip(), "   "))


def cmd_run(command: str, executor: SSHExecutor) -> None:
    if not command:
        console.print("[yellow]Usage: /run <shell command>[/]")
        return
    result = executor.run(command)
    if not result["approved"]:
        console.print("[yellow]Cancelled.[/]")
        return
    if result["stdout"]:
        console.print(result["stdout"])
    if result["stderr"]:
        console.print(f"[red]{result['stderr']}[/]")
    if result["returncode"] != 0:
        console.print(f"[red]exit code {result['returncode']}[/]")


def cmd_kb(kb: KnowledgeBase) -> None:
    with console.status("querying...", spinner="dots"):
        cats = kb.categories()
    for name, count in cats:
        console.print(f"  {count:>5}  {name}")


def run_query(
    user_input: str,
    history: list[dict],
    ollama: OllamaClient,
    kb: KnowledgeBase,
    prom: PrometheusClient,
) -> str:
    with console.status("[dim]thinking...[/]", spinner="dots"):
        chunks = kb.search(user_input, top_k=5)

        # Attach Prometheus metrics if the question looks health-related
        health_keywords = {"cpu", "memory", "disk", "load", "uptime", "health", "metrics", "status"}
        words = set(user_input.lower().split())
        prom_context = ""
        if words & health_keywords:
            h = prom.health()
            prom_context = "--- live metrics ---\n"
            prom_context += "\n".join(f"{k}: {v}" for k, v in h.items() if v is not None)
            prom_context += "\n--- end metrics ---\n\n"

    context_str = format_context(chunks)
    augmented = f"{prom_context}{context_str}\n\n{user_input}".strip()

    history.append({"role": "user", "content": augmented})

    console.print("\n[bold cyan]hal>[/] ", end="")
    response_text = ""
    for token in ollama.stream_chat(history, system=SYSTEM_PROMPT):
        console.print(token, end="")
        response_text += token
    console.print()

    # Store clean message in history (without the injected context)
    history[-1] = {"role": "user", "content": user_input}
    history.append({"role": "assistant", "content": response_text})

    # Keep history bounded
    if len(history) > 20:
        history[:] = history[-20:]

    return response_text


def main() -> None:
    config = cfg.load()

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

    console.print(
        f"[green]connected[/] — model: [bold]{config.ollama_model}[/]  "
        f"kb: 2,244 chunks  prom: {config.prometheus_url}"
    )

    history: list[dict] = []

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
                cmd_run(user_input[5:].strip(), executor)
            elif user_input == "/kb":
                cmd_kb(kb)
            elif user_input.startswith("/"):
                console.print(f"[yellow]Unknown command. Type /help.[/]")
            else:
                run_query(user_input, history, ollama, kb, prom)

    finally:
        if tunnel:
            tunnel.stop()


if __name__ == "__main__":
    main()
