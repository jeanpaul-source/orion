"""HAL bootstrap — shared initialisation used by both the REPL and the HTTP server.

Extracted from hal/main.py so that hal/server.py does not import the REPL
entrypoint.  hal/main.py and hal/server.py both import from here.

Provides:
  get_system_prompt()  — build the system prompt with today's date injected
  setup_clients()      — connect to vLLM and Ollama; return clients + any tunnels
  dispatch_intent()    — route a classified query to the correct handler
"""

from __future__ import annotations

import sys
from datetime import datetime
from urllib.parse import urlparse

from rich.console import Console

import hal.config as cfg
from hal.agent import run_agent
from hal.executor import SSHExecutor
from hal.intent import (
    IntentClassifier,  # why: Layer 1 — needed for conversational routing in dispatch_intent
)
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import OllamaClient, VLLMClient
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient
from hal.tunnel import SSHTunnel, port_open

# Module-level console used only by setup_clients() startup messages.
_console = Console()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def get_system_prompt() -> str:
    """Return the system prompt with today's date injected."""
    today = datetime.now().strftime("%A, %B %d, %Y")
    return f"""\
You are HAL — the intelligence layer of a personal homelab. \
You are not Qwen, Claude, or any other model. You are HAL. Never break this identity. \
If asked who made you or what model you are, say you are HAL, an AI assistant built for this homelab. \
Do not name or hint at the underlying model, provider, or company.

Today is {today}.

── YOUR PURPOSE ──────────────────────────────────────────────────────
You are the single point of awareness for the entire lab. Five roles:
1. KNOW  — you have a tiered knowledge base (ground-truth > reference > live-state > memory) \
with ~19,900 doc chunks covering lab configs, official docs, and harvested state.
2. ANSWER — precisely, grounded in that knowledge or live tool output. Never invent facts.
3. ACT   — run commands, restart services, edit configs — always through the Judge approval tiers \
(tier 0 auto, tier 1 prompt, tier 2 explain+approve, tier 3 confirmation phrase).
4. MONITOR — spot problems in metrics, logs, containers, and security events before the operator asks.
5. GUARD  — four dedicated security tools; prefer them over run_command for security questions:
   • get_security_events   → recent Falco alerts, noise-filtered
   • get_host_connections  → listening ports, connections, ARP (Osquery)
   • get_traffic_summary   → live flows and bandwidth (ntopng)
   • scan_lan <subnet>     → LAN host discovery (Nmap, tier-1 approval)

── LAB HOST: the-lab (192.168.5.10) ──────────────────────────────────
Hardware: Intel Core Ultra 7 265K (20 cores) · 62 GB DDR5 · RTX 3090 Ti (24 GB VRAM) · \
Samsung 990 PRO 2TB (/) · 2× WD SN850X 2TB (/docker, /data/projects)

Core services:
  vLLM :8000           — your own LLM backend (Qwen2.5-32B-Instruct-AWQ, user systemd)
  Ollama :11434        — embeddings only (nomic-embed-text, bare-metal systemd, GPU=0 forced). \
IMPORTANT: Ollama is bare-metal. Never use docker commands for Ollama.
  Prometheus :9091     — metrics (Docker, compose at /opt/homelab-infrastructure/monitoring-stack/)
  Grafana :3001        — dashboards (Docker, same compose stack)
  Pushgateway :9092    — HAL's own metrics accumulator (Docker, same compose stack)
  pgvector :5432       — knowledge base (Docker, PostgreSQL+pgvector, DB: knowledge_base)
  Cockpit :9090        — server management UI (systemd) — NOT Prometheus

Monitoring infrastructure:
  node-exporter        — internal to Docker monitoring network; pid:host, --path.rootfs=/rootfs, \
textfile collector reads /var/lib/node-exporter/textfiles/ for GPU metrics
  gpu-metrics timer    — runs nvidia-smi every 15s, writes .prom file for node-exporter
  ntopng :3000         — live traffic flows (Docker, interface enp130s0, login disabled)

Security stack:
  Falco (eBPF)         — runtime alerts → /var/log/falco/events.json (system systemd)
  Osquery 5.21.0       — SQL-queryable OS state (bare metal, sudoers scoped)
  Nmap 7.92            — LAN discovery (bare metal)

── AUTOMATED & SCHEDULED TASKS ───────────────────────────────────────
These run without human intervention. Know them so you can explain alerts and diagnose issues:

• watchdog.timer (every 5 min) — queries Prometheus, checks thresholds, sends ntfy alerts:
  Metric thresholds: CPU ≥85%, Memory ≥90%, Disk / ≥85%, Disk /docker ≥85%, \
Disk /data ≥85%, Swap ≥80%, Load ≥16, GPU VRAM ≥95%, GPU temp ≥83°C
  Boolean checks: NTP sync, harvest freshness (<2h), critical containers \
(prometheus, grafana, pgvector-kb, ntopng, pushgateway), Falco security events
  Alerts go to ntfy. Recovery sends "RESOLVED" with ✅. Cooldown: 30 min per metric.
  State file: ~/.orion/watchdog_state.json · Log: ~/.orion/watchdog.log

• harvest.timer (daily 3:00am) — re-indexes lab state into pgvector:
  Clears live-state rows, re-harvests containers/services/disk/configs/hardware.
  Reference docs use incremental ingestion (content-hash skip). Orphan cleanup automatic.
  Timestamp: ~/.orion/harvest_last_run

• gpu-metrics.timer (every 15s) — nvidia-smi → .prom file for node-exporter textfile collector

• server.service — your HTTP API (FastAPI, port 8087, /chat + /health endpoints)
• telegram.service — Telegram bot, polls API, POSTs to http://127.0.0.1:8087/chat
  Both are user systemd services (Restart=on-failure). Deploy order: server first, then telegram.

── HOW TO HANDLE COMMON QUESTIONS ────────────────────────────────────
"Is everything okay?" / "How's the lab?" →
  1. Call get_metrics for live CPU/mem/disk/GPU/swap/load
  2. Summarise any metric near thresholds (compare against watchdog thresholds above)
  3. Mention container health if relevant
  4. Check security events if anything looks off

"I got an alert" / "Why did I get a notification?" →
  The watchdog sent it via ntfy. Check get_metrics for which metric breached its threshold, \
or read ~/.orion/watchdog.log for the specific ALERT entry. Explain what threshold was hit \
and whether it has since recovered (look for CLEAR entries).

"What changed?" / "What happened while I was away?" →
  Check watchdog log, recent Falco events, and Prometheus metrics for anomalies. \
Use git_status on /opt/homelab-infrastructure if config changes are suspected.

Troubleshooting order: metrics → docker ps → journalctl → Falco → KB search

── MEMORY ────────────────────────────────────────────────────────────
Your conversation history from previous sessions is in the context above. \
When asked what you remember, refer to those messages. Never claim you can't recall past conversations.
The /remember command stores facts permanently in the KB as memory tier (never cleared by harvest).

── RULES ─────────────────────────────────────────────────────────────
• Do not hallucinate ports, service names, file paths, or config values — only state what context confirms.
• Use tools to check live state; use the KB when the answer is already documented.
• If KB context is not relevant to the question, ignore it entirely.
• Keep answers SHORT: 2–5 sentences for status, one short paragraph for complex questions.
• If you don't know, say so plainly — never guess.
• Never simulate a tool call or fabricate shell/command output in a prose response. \
If you need live data but cannot call a tool, say "I'd need to check [X] for that — ask me directly" and stop.
• web_search MUST be called for any question about CVEs, security vulnerabilities, software release \
notes, or version information — call it first, do not reason from training data for these topics. \
The current date injected above is authoritative; never assume you cannot find current data. \
For topics with no homelab context (e.g. unrelated consumer technology), ask the user to clarify \
instead of searching the web.
"""


# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------


def _connect(
    name: str, url: str, lab_user: str, lab_host: str, default_port: int
) -> tuple[str, SSHTunnel | None]:
    """Return (reachable_url, tunnel_or_None). Tries direct first, then SSH tunnel.

    SSH tunnel is only attempted when the target host is a remote address.
    If the URL already points to localhost/127.0.0.1 and the port is closed,
    the service simply isn't running — tunneling can't help.
    """
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or default_port

    if port_open(host, port):
        return url, None

    # Don't try to SSH-tunnel to ourselves — it can't help.
    if host in ("localhost", "127.0.0.1"):
        _console.print(
            f"[red]{name} is not reachable on {host}:{port} — is it running?[/]"
        )
        sys.exit(1)

    # Also skip if lab_host is local — even if the service URL contains the server's
    # IP (e.g. VLLM_URL=http://192.168.5.10:8000), tunnelling to localhost still
    # can't help: we're already on the machine and the port is simply closed.
    # why: lab_host=localhost means HAL is running on the server itself;
    # the URL check above only catches http://localhost:... not http://192.168.x.x:...
    if lab_host in ("localhost", "127.0.0.1", "::1"):
        _console.print(
            f"[red]{name} is not reachable on {host}:{port} — is it running?[/]"
        )
        sys.exit(1)

    _console.print(f"[yellow]{name} not directly reachable — trying SSH tunnel...[/]")
    tunnel = SSHTunnel(lab_user, lab_host, port, default_port)
    try:
        tunnel.start()
        _console.print(f"[green]{name} SSH tunnel established.[/]")
        return f"http://127.0.0.1:{tunnel.local_port}", tunnel
    except RuntimeError as e:
        _console.print(f"[red]{name} tunnel failed: {e}[/]")
        sys.exit(1)


def setup_clients(
    config: cfg.Config,
) -> tuple[VLLMClient, OllamaClient, list[SSHTunnel]]:
    """Connect to vLLM (chat) and Ollama (embeddings). Returns both clients and any tunnels opened."""
    tunnels: list[SSHTunnel] = []

    vllm_url, t = _connect(
        "vLLM", config.vllm_url, config.lab_user, config.lab_host, 8000
    )
    if t:
        tunnels.append(t)
    llm = VLLMClient(vllm_url, config.chat_model)
    if not llm.ping():
        _console.print(
            "[red]vLLM is not ready.[/] The service may still be loading the model. "
            "Check with: [dim]journalctl --user -u vllm -n 30[/]"
        )
        sys.exit(1)

    ollama_url, t = _connect(
        "Ollama", config.ollama_host, config.lab_user, config.lab_host, 11434
    )
    if t:
        tunnels.append(t)
    embed = OllamaClient(ollama_url, config.embed_model)
    if not embed.ping():
        _console.print("[red]Ollama is not responding. Is it running?[/]")
        sys.exit(1)

    return llm, embed, tunnels


# ---------------------------------------------------------------------------
# Intent dispatch
# ---------------------------------------------------------------------------


def _handle_conversational(
    user_input: str,
    history: list,
    llm: VLLMClient,
    mem: MemoryStore,
    session_id: str,
    system_prompt: str,
    console: Console,
) -> str:
    """Respond to greetings and acknowledgements with a single LLM call, no tools.

    # why: conversational turns (hello, thanks, ok) need no tool calls, no KB lookup,
    # and no Prometheus queries — routing them through run_agent wastes at least one
    # extra LLM round-trip and can trigger spurious tool calls.
    """
    working = list(history) + [{"role": "user", "content": user_input}]
    try:
        msg = llm.chat_with_tools(working, [], system=system_prompt)
    except Exception as e:
        # LLM error — same contract as run_agent: do NOT write to history.
        # why: error strings in history corrupt every subsequent turn (H-1 contract).
        err = f"LLM unavailable: {e}"
        console.print(f"\n[bold red]hal>[/] {err}")
        return err
    response = (msg.get("content") or "").strip()
    console.print(f"\n[bold cyan]hal>[/] {response}")
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": response})
    mem.save_turn(session_id, "user", user_input)
    mem.save_turn(session_id, "assistant", response)
    if len(history) > 40:
        history[:] = history[-40:]
    return response


def dispatch_intent(
    user_input: str,
    history: list,
    llm: VLLMClient,
    prom: PrometheusClient,
    kb: KnowledgeBase,
    executor: SSHExecutor,
    judge: Judge,
    mem: MemoryStore,
    session_id: str,
    system_prompt: str,
    console: Console,
    *,
    classifier: IntentClassifier | None = None,
    ntopng_url: str = "",
    tavily_api_key: str = "",
) -> str:
    """Route a query to the correct handler based on intent classification.

    # why: Layer 1 — conversational queries (greetings, acknowledgements) skip the
    # full agentic tool loop for lower latency and fewer spurious tool calls.
    # classifier is optional during Layer 1 rollout; once main.py passes it,
    # all conversational queries are routed here instead of run_agent.
    # All non-conversational intents (health, fact, agentic) still use run_agent.
    """
    if classifier is not None:
        intent, _confidence = classifier.classify(user_input)
        if intent == "conversational":
            return _handle_conversational(
                user_input, history, llm, mem, session_id, system_prompt, console
            )
    return run_agent(
        user_input,
        history,
        llm,
        kb,
        prom,
        executor,
        judge,
        mem,
        session_id,
        system_prompt,
        console,
        ntopng_url=ntopng_url,
        tavily_api_key=tavily_api_key,
    )
