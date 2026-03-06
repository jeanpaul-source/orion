"""HAL bootstrap — shared initialisation used by both the REPL and the HTTP server.

Extracted from hal/main.py so that hal/server.py does not import the REPL
entrypoint.  hal/main.py and hal/server.py both import from here.

Provides:
  get_system_prompt(config)  — build the system prompt with today's date and config values injected
  setup_clients()      — connect to vLLM and Ollama; return clients + any tunnels
  dispatch_intent()    — route a classified query to the correct handler
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from urllib.parse import urlparse

from rich.console import Console

import hal.config as cfg
from hal.agent import AgentResult, run_agent
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


def get_system_prompt(config: cfg.Config) -> str:
    """Return the system prompt with today's date and config values injected."""
    today = datetime.now(tz=UTC).strftime("%A, %B %d, %Y")
    _vllm_port = urlparse(config.vllm_url).port or 8000
    _ollama_port = urlparse(config.ollama_host).port or 11434
    _prom_port = urlparse(config.prometheus_url).port or 9091
    _ntopng_port = urlparse(config.ntopng_url).port or 3000
    _host_display = (
        f"{config.lab_hostname} ({config.lab_host})"
        if config.lab_hostname
        else config.lab_host
    )
    _hardware_line = (
        f"Hardware: {config.lab_hardware_summary}\n\n"
        if config.lab_hardware_summary
        else ""
    )
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

── LAB HOST: {_host_display} ──────────────────────────────────────────────────────
{_hardware_line}\
Core services:
  vLLM :{_vllm_port}           — your own LLM backend ({config.chat_model}, user systemd)
  Ollama :{_ollama_port}        — embeddings only (nomic-embed-text, bare-metal systemd, GPU=0 forced). \
IMPORTANT: Ollama is bare-metal. Never use docker commands for Ollama.
  Prometheus :{_prom_port}     — metrics (Docker, compose at {config.infra_base}/monitoring-stack/)
  Grafana :3001        — dashboards (Docker, same compose stack)
  Pushgateway :9092    — HAL's own metrics accumulator (Docker, same compose stack)
  Tempo :4318/:3200    — OTel trace receiver (OTLP HTTP on 4318, query API on 3200, same compose stack)
  pgvector :5432       — knowledge base (Docker, PostgreSQL+pgvector, DB: knowledge_base)
  Cockpit :9090        — server management UI (systemd) — NOT Prometheus

Monitoring infrastructure:
  node-exporter        — internal to Docker monitoring network; pid:host, --path.rootfs=/rootfs, \
textfile collector reads /var/lib/node-exporter/textfiles/ for GPU metrics
  gpu-metrics timer    — runs nvidia-smi every 15s, writes .prom file for node-exporter
  ntopng :{_ntopng_port}         — live traffic flows (Docker, interface enp130s0, login disabled)

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

• server.service — your HTTP API (FastAPI, port 8087, /chat + /health endpoints). \
Also serves the Web UI at GET / (vanilla JS chat interface at http://localhost:8087).
• telegram.service — Telegram bot, polls API, POSTs to http://127.0.0.1:8087/chat
  Both are user systemd services (Restart=on-failure). Deploy order: server first, then telegram.

── SELF-HEALING ──────────────────────────────────────────────────────
You can detect and recover from component failures:
• check_system_health — structured health check across all 8 components \
(vLLM, Ollama, pgvector, Prometheus, Containers, Pushgateway, Grafana, ntopng). \
Returns status (ok/degraded/down), detail, and latency for each.
• recover_component — trigger a recovery playbook for a failed component. \
Valid targets: pgvector, Prometheus, Grafana, Pushgateway, ntopng, Ollama, vLLM. \
Each playbook is a pre-defined restart→verify sequence gated by the Judge.
Circuit breaker: max 2–3 attempts/hour per component (prevents retry storms).
Trust evolution: proven-safe recoveries auto-promote to tier 0; repeated failures \
demote back — the system self-tunes its autonomy level.
When a user asks about failures or recovery, check the audit log at \
~/.orion/audit.log for recovery events (action: "run_command", playbook names in reason field).

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
) -> AgentResult:
    """Respond to greetings and acknowledgements with a single LLM call, no tools.

    # why: conversational turns (hello, thanks, ok) need no tool calls, no KB lookup,
    # and no Prometheus queries — routing them through run_agent wastes at least one
    # extra LLM round-trip and can trigger spurious tool calls.
    """
    working = [*history, {"role": "user", "content": user_input}]
    try:
        msg = llm.chat_with_tools(working, [], system=system_prompt)
    except Exception as e:
        # LLM error — same contract as run_agent: do NOT write to history.
        # why: error strings in history corrupt every subsequent turn (H-1 contract).
        err = f"LLM unavailable: {e}"
        console.print(f"\n[bold red]hal>[/] {err}")
        return AgentResult(response=err)
    response = (msg.get("content") or "").strip()
    console.print(f"\n[bold cyan]hal>[/] {response}")
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": response})
    mem.save_turn(session_id, "user", user_input)
    mem.save_turn(session_id, "assistant", response)
    if len(history) > 40:
        history[:] = history[-40:]
    return AgentResult(response=response)


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
    config: object | None = None,
) -> AgentResult:
    """Route a query to one of two paths based on intent classification.

    Path 1 — conversational (fast): greetings and acknowledgements skip the
    tool loop entirely. No KB lookup, no Prometheus call, one LLM round-trip.

    Path 2 — capable (everything else): health, fact, and agentic queries all
    enter run_agent, which has full tool access and pre-seeds context from both
    KB and a live Prometheus snapshot before the first LLM call. Simple health
    and fact queries resolve in iteration 1 (context already injected); boundary
    queries that need tools can call them without restriction.

    # why: collapsing health/fact into run_agent removes the capability gate that
    # caused boundary queries to get shallow answers. See notes/track-a-routing-
    # refactor-plan.md Item 1 for the full root-cause analysis.
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
        config=config,
    )
