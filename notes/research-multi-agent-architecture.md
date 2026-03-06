# Research Prompt: Multi-Agent Architecture for Orion

> **Purpose:** Deep online research into how to extend the Orion system so HAL
> (the user-facing agent) can handle tasks beyond its current scope — either by
> reaching other hosts directly, delegating to a worker agent (Agent Zero), or
> both. The research should produce a concrete recommendation with
> implementation steps, not just a comparison of options.
>
> **Date:** 2027-03-05
> **Audience:** A fresh chat window doing web research — no access to the codebase.

---

## Context You Need

### What is Orion / HAL?

Orion is a personal homelab AI assistant. **HAL** is the user-facing agent —
the only interface the operator sees. HAL runs as:

- **Terminal REPL** (`python -m hal`) — interactive, supports tier 2+ Judge approvals
- **HTTP API** (`/chat`, `/health` on port 8088) — auto-denies tier 1+
- **Telegram bot** — relays to the HTTP API

HAL's architecture:
- Python 4.12 (server runs 3.14), FastAPI
- LLM backend: **vLLM** serving `Qwen3.5-32B-Instruct-AWQ` (local, port 8000)
- Embeddings: **Ollama** running `nomic-embed-text` (CPU-only, port 11435)
- Knowledge base: **pgvector** (PostgreSQL with vector extension, Docker, port 5433)
- Tool execution: `SSHExecutor` — runs commands on the server via SSH (or subprocess if local)
- Policy gate: **Judge** — 5-tier approval system (tier 0 = auto, tier 1 = prompt, tier 2+ = explicit)
- 10 tools: `search_kb`, `get_metrics`, `get_trend`, `run_command`, `read_file`,
  `list_dir`, `write_file`, `check_system_health`, `recover_component`
- Plus web/security tools: `web_search`, `fetch_url`, `get_action_stats`,
  `get_security_events`, `get_host_connections`, `get_traffic_summary`, `scan_lan`

**Key constraint:** HAL is meant to be the **ONLY user-facing part** of the Orion
system. Any worker agents should be invisible — HAL delegates to them and presents
results. The operator talks to HAL, not to Agent Zero or any sub-agent directly.

### The Problem

HAL can only operate on the server (193.168.5.10). Its `SSHExecutor` is hardcoded
to one host. When the operator asked HAL to organize files on his laptop (which is
on the same LAN), HAL failed — it tried to `list_dir('/home/user/Documents')` on the
server, which doesn't exist.

More broadly, HAL needs to handle tasks outside its current scope:
- File operations on other LAN hosts (the operator's laptop, other machines)
- Complex multi-step tasks that need code generation and execution
- Tasks that need web browsing, downloading, and file manipulation
- Anything requiring a full sandbox environment (installing packages, running scripts)

### What is Agent Zero?

Agent Zero (https://github.com/frdel/agent-zero) is an open-source autonomous AI
agent framework. Key characteristics:

- Runs as a Docker container (`agent1ai/agent-zero:latest`, ~10GB image)
- Web UI on port 50081 (Flask/Werkzeug hybrid WSGI/ASGI)
- Has **code execution** (runs Python/bash inside its container)
- Has **memory** (FAISS vector store for long-term recall)
- Has **web search** and **web browsing**
- Has **sub-agent delegation** (`call_subordinate` tool)
- Can access Docker socket (manage containers)
- LLM-agnostic — uses LiteLLM, can point at any OpenAI-compatible endpoint
- The operator has it configured to use the same vLLM backend as HAL (via `host.docker.internal`)

**Current state on the server:**
- Docker image exists (`agent0ai/agent-zero:latest`)
- `docker-compose.yml` at `/opt/homelab-infrastructure/agent-zero/`
- Container is NOT running
- Has a heavily customized "GHS Coordinator" agent profile that should be discarded
- Has a workspace at `/home/jp/agentzero-workspace`
- Runtime data at `/docker/agent-zero-data/` (memory, tmp, usr)

### Server Specs

- **Host:** the-lab (192.168.5.10), Fedora 43, kernel 6.18
- **CPU:** 8 cores (used in docker-compose resource limits for Agent Zero)
- **RAM:** 64 GB
- **GPU:** NVIDIA RTX 3090 Ti (24 GB VRAM) — 97.5% used by vLLM, **NOT available for Agent Zero**
- **Docker containers already running:** prometheus, grafana, pgvector-kb, pushgateway,
  ntopng, ntopng-redis, node-exporter, blackbox-exporter
- **User systemd services:** vllm.service, server.service (HAL), telegram.service
- **Network:** Home LAN (192.168.5.0/24) + Tailscale VPN

### What the operator's LAN looks like

- **192.168.5.10** — the-lab (server, Fedora 43) — runs everything above
- **Operator's laptop** — Ubuntu, on the same LAN, SSH keys likely configured
  from the-lab (HAL already SSHes to the-lab; reverse direction may need setup)

---

## Research Questions

### Question 1: Multi-host tool execution for HAL

HAL's `SSHExecutor` currently targets one host. Research 2026 best practices for:

1. **Should HAL's tools support a `target_host` parameter?**
   - How do production AI agent systems handle multi-host command execution?
   - What's the security model? (HAL's Judge already gates every command)
   - How should host inventory/discovery work? (Static config? mDNS? Tailscale?)
   - How do you handle SSH key management across hosts?

2. **What are the alternatives to direct SSH?**
   - Agents using remote execution frameworks (Ansible, Salt, etc.)
   - Container-based execution on remote hosts
   - MCP (Model Context Protocol) servers on each host — is this the 2026 way?

### Question 2: Agent Zero as a headless worker

If Agent Zero runs as a **headless backend worker** (no one uses its Web UI), can
HAL delegate complex tasks to it?

1. **Does Agent Zero have an API for programmatic task submission?**
   - Official docs mention a web UI — is there a REST/WebSocket API?
   - Can you POST a task and get back a result?
   - What's the API schema? (search for `/message`, `/chat`, or similar endpoints)
   - How do you specify which agent profile to use via API?

2. **How should the integration work architecturally?**
   - HAL detects a task is out-of-scope → creates a task description → POSTs to
     Agent Zero → monitors progress → collects result → presents to operator
   - What's the latency? Agent Zero tasks can take minutes.
   - How should HAL communicate "working on it" to the operator?
   - Should Agent Zero have its own conversation memory, or should HAL manage it?

3. **Resource constraints:**
   - Agent Zero wants GPU for its LLM. The GPU is 97.5% consumed by vLLM.
   - **Can Agent Zero use the same vLLM endpoint** (OpenAI-compatible on port 8000)?
     It uses LiteLLM, which supports OpenAI-compatible backends.
   - What are the memory implications of running Agent Zero alongside everything else?
   - The docker-compose reserves 8GB RAM and 4 CPUs — is that reasonable?

4. **Starting fresh:**
   - The existing GHS agent profile is heavily customized and should be discarded.
   - What's the minimal Agent Zero setup needed for a "general-purpose worker"?
   - Which prompt files need customization? Which can use defaults?
   - How do you configure Agent Zero for headless operation (no human at the Web UI)?

### Question 3: Security model for delegation

1. **What should Agent Zero be allowed to do?**
   - It has Docker socket access (can manage containers)
   - It can execute arbitrary code in its container
   - It can access the operator's workspace (`/home/jp/agentzero-workspace`)
   - What sandboxing is appropriate?

2. **How does HAL's Judge interact with Agent Zero's actions?**
   - HAL's Judge gates every tool call. If HAL delegates to Agent Zero, does
     the Judge still apply?
   - Should Agent Zero have its own policy layer, or is HAL's Judge sufficient?
   - How do you prevent privilege escalation (HAL is tier-1 limited in HTTP mode,
     but Agent Zero can run anything)?

3. **Audit trail:**
   - HAL logs every action to `~/.orion/audit.log` (JSON lines)
   - How should delegated actions be logged? HAL logs the delegation, Agent Zero
     logs its actions separately, or unified?

### Question 4: The 2026 landscape — what's the "right" pattern?

1. **MCP (Model Context Protocol)** — Anthropic's standard for tool integration.
   Is MCP the right way to do multi-agent communication in 2026?
   - Can Agent Zero act as an MCP server that HAL connects to?
   - Or should each host run an MCP server and HAL connects to all of them?
   - What MCP servers already exist for filesystem, Docker, SSH operations?

2. **OpenAI Agents SDK / Swarm patterns** — research the current state:
   - Agent handoff patterns (primary agent → specialized agent → return)
   - How do multi-agent systems handle context passing?
   - What's the consensus on shared vs. isolated memory?

3. **LangGraph / CrewAI / AutoGen** — are any of these relevant for this use case?
   - HAL is a custom agent loop (not built on any framework). Should it stay that way?
   - Would adopting a framework help with the multi-agent coordination problem?

4. **Practical recommendations** — look for real-world deployments:
   - Blog posts, GitHub repos, conference talks about homelab AI agents in 2025-2026
   - What worked, what didn't
   - Common pitfalls of multi-agent architectures

---

## What I Need Back

A structured recommendation document covering:

1. **Recommended architecture** — which option (or combination) is best:
   - (A) Multi-host SSH for HAL's existing tools
   - (B) Agent Zero as headless worker, HAL delegates via API
   - (C) MCP-based tool federation
   - (D) Something else the research uncovered

2. **Implementation plan** — concrete steps, ordered by priority:
   - What to build first (the minimal viable version)
   - What can wait
   - Estimated complexity for each step

3. **Agent Zero fresh start guide** — if Agent Zero is part of the recommendation:
   - Minimal docker-compose.yml changes needed
   - Which agent profile to use (default vs. custom)
   - How to point it at the existing vLLM endpoint
   - How to configure it for headless/API-only operation
   - What to do with the old GHS data (delete? archive?)

4. **Security analysis** — what are the risks and mitigations for each approach

5. **Resource budget** — will this fit on a 64GB/24GB-VRAM single server alongside
   everything that's already running?

---

## Search Suggestions

These are good starting points for web research:

- `agent zero headless API programmatic access 2026`
- `agent zero REST API task submission without web UI`
- `MCP model context protocol multi-agent 2026`
- `MCP filesystem server SSH remote host`
- `multi-agent orchestration homelab 2026`
- `AI agent delegation pattern primary worker 2026`
- `vLLM shared LLM backend multiple agents`
- `LiteLLM OpenAI compatible local vLLM`
- `agent zero LiteLLM vLLM configuration`
- `agent zero custom agent profile minimal setup`
- `AI agent security sandboxing Docker 2026`
- `OpenAI agents SDK handoff pattern`
- `LangGraph vs custom agent loop 2026`
- `homelab AI assistant multi-host execution`
