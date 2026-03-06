# Multi-Agent Architecture Recommendation for Orion/HAL

> **Date:** 2025-07-14
> **Status:** Research complete — recommendation ready for review
> **Based on:** Codebase analysis + web research on Agent Zero API, MCP ecosystem, OpenAI Agents SDK, LangGraph/CrewAI/AutoGen

---

## Executive Summary

**Recommended architecture: Hybrid A+B — Multi-host SSH (Phase 1) + Agent Zero as headless worker (Phase 2)**

Phase 1 gives HAL the ability to run commands on any LAN host via a `target_host` parameter — this solves the immediate "organize files on my laptop" problem with ~200 lines of code. Phase 2 adds Agent Zero as an invisible backend worker for complex tasks (code generation, multi-step research, sandboxed execution) — HAL delegates via Agent Zero's REST API and presents results to the operator.

MCP (Option C) is deferred to Phase 3 as a future-proofing layer. It's the "right" 2025-2026 pattern for tool federation, but adds complexity that isn't justified until HAL needs to interact with many heterogeneous tool providers. Agent Zero already exposes an MCP server endpoint, so the migration path is built in.

---

## Table of Contents

1. [Architecture Options Analysis](#1-architecture-options-analysis)
2. [Recommended Architecture](#2-recommended-architecture)
3. [Implementation Plan](#3-implementation-plan)
4. [Agent Zero Fresh Start Guide](#4-agent-zero-fresh-start-guide)
5. [Security Analysis](#5-security-analysis)
6. [Resource Budget](#6-resource-budget)
7. [Research Findings Appendix](#7-research-findings-appendix)

---

## 1. Architecture Options Analysis

### Option A: Multi-host SSH for HAL's existing tools

**What it is:** Extend `SSHExecutor` to support multiple hosts. Add a `target_host` parameter to `run_command`, `read_file`, `list_dir`, `write_file`. Maintain a host inventory in config.

**Pros:**
- Minimal code change (~200 LoC across `executor.py`, `tools.py`, `config.py`)
- No new dependencies or services
- Judge already gates every command — trivially extends to new hosts
- SSH key management is a solved problem
- Zero additional RAM/CPU/VRAM

**Cons:**
- Only solves file/command operations, not complex multi-step tasks
- Each new host needs SSH key setup
- No sandboxing — commands run directly on the target host
- Doesn't help with tasks requiring code generation, package installation, etc.

**Verdict:** ✅ **Must-do.** This is the minimum viable fix for the stated problem. Build this first.

### Option B: Agent Zero as headless worker via REST API

**What it is:** Run Agent Zero as a Docker container. HAL detects out-of-scope tasks, POSTs them to Agent Zero's REST API (`POST /api_message`), monitors progress, collects results, and presents them to the operator.

**Pros:**
- Agent Zero has a well-documented REST API (see §7.1)
- Can share vLLM backend (via LiteLLM → `http://host.docker.internal:8000`)
- Built-in sandboxing (Docker container with configurable mounts)
- Code execution, web browsing, memory all included
- Context persistence via `context_id` — can hold multi-turn conversations
- 8GB RAM + 4 CPU is a reasonable allocation (no GPU needed)

**Cons:**
- ~8GB additional RAM overhead
- Adds operational complexity (another container to monitor/restart)
- Latency: Agent Zero tasks can take 30s–minutes
- Agent Zero's internal actions bypass HAL's Judge

**Verdict:** ✅ **High-value Phase 2.** Unlocks complex task delegation, sandboxed execution, and multi-step research.

### Option C: MCP-based tool federation

**What it is:** Run MCP servers (filesystem, Docker, SSH) on each host. HAL connects to them as an MCP client. Agent Zero also exposes MCP server endpoints.

**Pros:**
- Industry-standard protocol (Anthropic, OpenAI ecosystem convergence)
- Hundreds of existing MCP servers (filesystem, Docker, Git, SSH — see §7.2)
- Agent Zero already has MCP server endpoints (SSE and Streamable HTTP)
- Clean separation: each host owns its tools, HAL discovers and calls them
- Future-proof: as the ecosystem matures, HAL gets free integrations

**Cons:**
- HAL's custom agent loop (`VLLMClient` + tool dispatch) doesn't speak MCP natively
- Would need an MCP client library integrated into HAL's tool dispatch
- Adds network dependencies (each MCP server is another service to run)
- Overhead is unjustified for a 2-host LAN right now
- MCP transport (SSE/Streamable HTTP) adds latency vs. direct SSH

**Verdict:** ⏳ **Defer to Phase 3.** The protocol is right, but the ecosystem benefit doesn't justify the implementation cost for a 2-host homelab today. Agent Zero's built-in MCP server endpoint means the migration path exists when needed.

### Option D: Framework adoption (LangGraph, CrewAI, AutoGen)

**What it is:** Replace HAL's custom agent loop with a multi-agent framework.

**Pros:**
- Built-in multi-agent orchestration patterns (supervisor, handoff, hierarchical)
- LangGraph offers graph-based state machines, observability via LangSmith
- OpenAI Agents SDK has clean handoff primitives

**Cons:**
- HAL's custom loop is well-tuned for its specific needs (8-iteration limit, Judge gating, KB pre-seeding, intent classification)
- Frameworks add dependencies and abstraction layers that fight with custom policy logic
- LangGraph/CrewAI are designed for OpenAI/Anthropic APIs — adapting to local vLLM adds friction
- The "supervisor + worker" pattern can be implemented with ~100 lines in the existing architecture
- Rewriting the agent loop would be a massive regression risk for zero immediate benefit

**Verdict:** ❌ **Don't adopt.** HAL's custom loop is working. The multi-agent coordination problem (HAL → Agent Zero) is simple enough to solve with direct API calls. Framework adoption would be justified only if HAL needed 5+ specialized sub-agents with complex routing — that's not the current need.

---

## 2. Recommended Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Operator (REPL / Telegram / HTTP)                               │
└──────────┬───────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  HAL (agent loop)                                                │
│  ┌─────────────┐  ┌───────────┐  ┌──────────┐  ┌─────────────┐ │
│  │IntentClassif.│→│ run_agent()│→│  Judge    │→│ Tool Dispatch│ │
│  └─────────────┘  └───────────┘  └──────────┘  └──────┬──────┘ │
└──────────────────────────────────────────────────┬─────┼────────┘
                                                   │     │
                    ┌──────────────────────────────┐│     │
                    │ Phase 1: Multi-host SSH      ││     │
                    │                              ││     │
                    │  ┌─────────────────────┐     ││     │
                    │  │ ExecutorRegistry     │◄────┘│     │
                    │  │  the-lab → SSHExec() │      │     │
                    │  │  laptop  → SSHExec() │      │     │
                    │  │  (static config)     │      │     │
                    │  └─────────────────────┘      │     │
                    └───────────────────────────────┘     │
                                                          │
                    ┌─────────────────────────────────────┘
                    │ Phase 2: Agent Zero delegation
                    │
                    │  ┌─────────────────────────────────────┐
                    │  │ delegate_task tool                   │
                    │  │  POST /api_message → Agent Zero      │
                    │  │  poll /api_log_get for progress      │
                    │  │  return result to agent loop          │
                    │  └───────────┬─────────────────────────┘
                    │              │
                    │  ┌───────────▼─────────────────────────┐
                    │  │ Agent Zero (Docker container)        │
                    │  │  LiteLLM → vLLM (port 8000)         │
                    │  │  Code exec / Web / Memory / Files    │
                    │  │  8GB RAM, 4 CPU, no GPU              │
                    │  └─────────────────────────────────────┘
                    │
                    │ Phase 3 (future): MCP federation
                    │  Agent Zero already exposes /mcp/t-TOKEN/sse
                    │  HAL could consume it via MCP client library
                    └─────────────────────────────────────────────
```

### Key Design Principles

1. **HAL is the only user-facing agent.** Agent Zero is invisible. The operator never interacts with it directly.
2. **Judge gates everything.** Multi-host commands go through Judge like single-host commands. Delegations to Agent Zero are a new tool call that Judge approves.
3. **Fail-safe defaults.** New hosts are not auto-discovered. They must be explicitly listed in `.env`/config. Agent Zero workspace mounts are minimal.
4. **One change at a time.** Phase 1 is independent of Phase 2. Each ships and works on its own.

---

## 3. Implementation Plan

### Phase 1: Multi-host SSH (Priority: HIGH — solves the stated problem)

**Estimated effort:** 1–2 sessions, ~200 LoC + tests

#### Step 1.1: Host inventory in config

Add to `.env`:
```env
# Multi-host inventory — comma-separated host:user pairs
# First entry is the default ("lab") host
EXTRA_HOSTS=laptop:jp@192.168.5.20
```

Add to `Config` dataclass:
```python
extra_hosts: str  # comma-separated "name:user@host" entries; default ""
```

Parse into a dict at load time:
```python
@property
def host_registry(self) -> dict[str, tuple[str, str]]:
    """Returns {name: (host, user)} including the primary lab host."""
    hosts = {"lab": (self.lab_host, self.lab_user)}
    for entry in self.extra_hosts.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, userhost = entry.split(":", 1)
        user, host = userhost.split("@", 1)
        hosts[name] = (host, user)
    return hosts
```

#### Step 1.2: ExecutorRegistry

New class (or simple dict wrapper) in `executor.py`:
```python
class ExecutorRegistry:
    """Manages SSHExecutor instances for multiple hosts."""
    def __init__(self, config: Config):
        self._executors: dict[str, SSHExecutor] = {}
        for name, (host, user) in config.host_registry.items():
            self._executors[name] = SSHExecutor(host, user)
        self.default = self._executors.get("lab")
    
    def get(self, name: str | None = None) -> SSHExecutor:
        if name is None:
            return self.default
        if name not in self._executors:
            raise ValueError(f"Unknown host: {name}. Known: {list(self._executors)}")
        return self._executors[name]
    
    @property
    def known_hosts(self) -> list[str]:
        return list(self._executors.keys())
```

#### Step 1.3: Add `target_host` to tool schemas

For `run_command`, `read_file`, `list_dir`, `write_file`, add an optional parameter:
```json
{
  "name": "target_host",
  "type": "string",
  "description": "Which host to run on. Options: lab, laptop. Default: lab.",
  "required": false
}
```

Update each tool handler to resolve the executor:
```python
def _handle_run_command(ctx, args):
    target = args.get("target_host")
    executor = ctx.registry.get(target)  # registry replaces single executor
    # ... rest of handler unchanged
```

#### Step 1.4: Update ToolContext

Replace single `executor: SSHExecutor` with `registry: ExecutorRegistry` in ToolContext. Update all call sites in `bootstrap.py`, `agent.py`.

#### Step 1.5: Update system prompt

Add to the system prompt (in `bootstrap.py`):
```
You can target different hosts using the target_host parameter.
Available hosts: {', '.join(registry.known_hosts)}
Default host: lab (the server)
```

#### Step 1.6: SSH key setup (operational)

```bash
# From the-lab, generate key pair if needed
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""

# Copy to laptop
ssh-copy-id jp@192.168.5.20

# Test
ssh -o BatchMode=yes jp@192.168.5.20 "hostname"
```

#### Step 1.7: Tests

- Test `ExecutorRegistry` init with various config strings
- Test tool handlers with `target_host` parameter
- Test invalid host name raises clear error
- Test Judge still gates commands on non-default hosts (it should — Judge sees the command, not the host)

---

### Phase 2: Agent Zero as headless worker (Priority: MEDIUM — unlocks complex task delegation)

**Estimated effort:** 2–3 sessions, ~400 LoC + tests + ops setup

#### Step 2.1: Fresh Agent Zero setup

See §4 for the complete fresh start guide.

#### Step 2.2: New `delegate_task` tool

Create a new tool that HAL can call:
```python
TOOL_SPEC = {
    "name": "delegate_task",
    "description": (
        "Delegate a complex task to a sandboxed worker agent. Use for tasks that "
        "require code generation, multi-step research, package installation, or "
        "operations that need a full sandbox environment. The worker runs in a "
        "Docker container and can execute Python/bash, browse the web, and manage files."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Complete task description. Be specific — the worker has no context about prior conversation."
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Maximum time to wait for result. Default 120.",
                "default": 120
            }
        },
        "required": ["task"]
    }
}
```

#### Step 2.3: Agent Zero client module

New file `hal/agent_zero.py`:
```python
"""Client for Agent Zero REST API — headless worker delegation."""

import time
import httpx

AGENT_ZERO_URL = "http://localhost:50081"  # from config

async def submit_task(
    task: str,
    api_key: str,
    context_id: str | None = None,
    timeout: int = 120,
) -> dict:
    """Submit a task to Agent Zero and wait for completion."""
    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        response = await client.post(
            f"{AGENT_ZERO_URL}/api_message",
            json={
                "message": task,
                "context_id": context_id or "",
            },
            headers={"X-API-KEY": api_key},
        )
        response.raise_for_status()
        data = response.json()
        return {
            "context_id": data.get("context_id", ""),
            "response": data.get("response", ""),
            "ok": True,
        }


async def get_logs(context_id: str, api_key: str) -> list:
    """Retrieve execution logs for a task context."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{AGENT_ZERO_URL}/api_log_get",
            json={"context_id": context_id},
            headers={"X-API-KEY": api_key},
        )
        response.raise_for_status()
        return response.json().get("logs", [])
```

#### Step 2.4: Wire into tool registry

Register `delegate_task` as a new tool in `tools.py`. The handler:
1. Judge approves the delegation (tier 1 — needs operator confirmation in REPL mode)
2. Calls `submit_task()` with the task description
3. Returns the result (or timeout message) to the agent loop

#### Step 2.5: Config additions

```env
# Agent Zero integration (optional — empty values disable delegation)
AGENT_ZERO_URL=http://localhost:50081
AGENT_ZERO_API_KEY=<auto-generated-token>
```

#### Step 2.6: Intent routing

Add logic in `dispatch_intent()` or as guidance in the system prompt:
- Tasks mentioning "code generation", "install packages", "download and process", "run a script" should consider `delegate_task`
- HAL should try its own tools first; only delegate when the task is clearly beyond file/command scope

#### Step 2.7: Tests

- Mock Agent Zero API responses
- Test timeout handling
- Test Judge gating of delegation
- Test context_id persistence for follow-up tasks
- Integration test with real Agent Zero (manual, not CI)

---

### Phase 3: MCP Federation (Priority: LOW — future-proofing)

**Estimated effort:** 3–4 sessions, ~600 LoC

This is deferred until HAL needs to interact with more than 2–3 tool sources. When ready:

1. Add an MCP client library to HAL (e.g. `mcp` Python SDK)
2. Connect to Agent Zero's MCP endpoint (`/mcp/t-TOKEN/sse`)
3. Optionally run the reference MCP Filesystem server on the laptop (avoids SSH key management)
4. HAL discovers available tools from MCP servers dynamically

This is the "right" long-term architecture but premature for the current 2-host setup.

---

## 4. Agent Zero Fresh Start Guide

### 4.1: Clean up old data

```bash
# Archive old GHS profile data (optional — or just delete)
sudo tar czf /tmp/agent-zero-ghs-backup.tar.gz /docker/agent-zero-data/
sudo rm -rf /docker/agent-zero-data/*

# Remove old workspace files
rm -rf /home/jp/agentzero-workspace/*
```

### 4.2: Minimal docker-compose.yml

```yaml
# /opt/homelab-infrastructure/agent-zero/docker-compose.yml
services:
  agent-zero:
    image: agent0ai/agent-zero:latest
    container_name: agent-zero
    restart: unless-stopped
    ports:
      - "127.0.0.1:50081:50081"  # bind to localhost only — HAL accesses directly
    environment:
      # Authentication — generates API token from these credentials
      A0_SET_AUTH_LOGIN: "hal"
      A0_SET_AUTH_PASSWORD: "${AGENT_ZERO_PASSWORD}"

      # LLM — point at the shared vLLM backend (OpenAI-compatible)
      A0_SET_CHAT_MODEL_PROVIDER: "openai"
      A0_SET_CHAT_MODEL_NAME: "Qwen/Qwen2.5-32B-Instruct-AWQ"
      A0_SET_CHAT_API_KEY: "dummy"  # vLLM doesn't require a real key
      A0_SET_CHAT_API_URL: "http://host.docker.internal:8000/v1"

      # Utility model — same vLLM endpoint
      A0_SET_UTILITY_MODEL_PROVIDER: "openai"
      A0_SET_UTILITY_MODEL_NAME: "Qwen/Qwen2.5-32B-Instruct-AWQ"
      A0_SET_UTILITY_API_KEY: "dummy"
      A0_SET_UTILITY_API_URL: "http://host.docker.internal:8000/v1"

      # Embeddings — point at Ollama (CPU-only)
      A0_SET_EMBEDDING_MODEL_PROVIDER: "ollama"
      A0_SET_EMBEDDING_MODEL_NAME: "nomic-embed-text:latest"
      A0_SET_EMBEDDING_API_URL: "http://host.docker.internal:11434"

      # Disable browser for now (saves memory, can enable later)
      A0_SET_BROWSER_ENABLED: "false"

      # MCP/A2A — disable for Phase 2, enable in Phase 3
      A0_SET_MCP_ENABLED: "false"
      A0_SET_A2A_ENABLED: "false"

    volumes:
      # Workspace — where Agent Zero creates/manages files
      - /home/jp/agentzero-workspace:/workspace
      # Persistent data (memory, settings)
      - /docker/agent-zero-data:/data
    deploy:
      resources:
        limits:
          cpus: "4"
          memory: 8G
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### 4.3: Configuration notes

**Agent profile:** Use the default profile. Agent Zero v0.9.8+ has a sensible default agent that:
- Follows instructions in its system prompt
- Executes code when asked
- Uses web search when needed
- Manages files in `/workspace`

Do NOT create a custom profile unless you need to restrict/customize behavior. The old "GHS Coordinator" profile should be deleted, not adapted.

**API token generation:** Agent Zero auto-generates a token from the `A0_SET_AUTH_LOGIN` and `A0_SET_AUTH_PASSWORD` values. To retrieve it:
```bash
# The token is base64(login:password) with some processing
# Or retrieve programmatically:
curl -s http://localhost:50081/api_tokens | jq .
```
Store the token in HAL's `.env` as `AGENT_ZERO_API_KEY`.

**Headless operation:** Agent Zero's Web UI still runs (it's the same Flask server that serves the API), but no one needs to interact with it. Bind port to localhost only (`127.0.0.1:50081`) so it's not accessible from the LAN.

### 4.4: Starting the container

```bash
cd /opt/homelab-infrastructure/agent-zero
docker compose up -d

# Verify it's running
docker compose logs -f --tail 20

# Test the API
curl -s -H "X-API-KEY: YOUR_TOKEN" \
  -X POST http://localhost:50081/api_message \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 2+2?"}'
```

### 4.5: LiteLLM → vLLM integration detail

Agent Zero uses LiteLLM internally, which supports OpenAI-compatible endpoints natively. Setting `A0_SET_CHAT_MODEL_PROVIDER: "openai"` with `A0_SET_CHAT_API_URL: "http://host.docker.internal:8000/v1"` makes LiteLLM call:

```
POST http://host.docker.internal:8000/v1/chat/completions
```

This is exactly what vLLM serves. The `api_key` can be any non-empty string (vLLM doesn't validate it by default).

**Important:** Both HAL and Agent Zero will share vLLM's inference capacity. Under concurrent load, this means slower responses. vLLM handles concurrent requests via continuous batching, so it won't OOM — it just queues.

---

## 5. Security Analysis

### Phase 1: Multi-host SSH

| Risk | Severity | Mitigation |
|------|----------|------------|
| SSH key compromise | HIGH | Use ed25519 keys, password-protect with ssh-agent |
| Commands on wrong host | MEDIUM | Judge sees the target_host — can add per-host rules |
| Lateral movement | MEDIUM | Static host inventory (no auto-discovery). Judge default-deny |
| SSH to untrusted host | LOW | Hosts must be explicitly configured in .env |

**Judge integration:** No changes needed. Judge already sees the full command text. Add the host name to the audit log entry so post-hoc review shows which host was targeted.

### Phase 2: Agent Zero delegation

| Risk | Severity | Mitigation |
|------|----------|------------|
| Agent Zero bypasses Judge | HIGH | HAL's Judge gates the delegation itself. Agent Zero's internal actions are not individually approved. This is a conscious trade-off. |
| Privilege escalation via delegation | HIGH | Agent Zero runs in Docker with limited mounts. No host Docker socket. No SSH keys. |
| Container escape | MEDIUM | Keep Docker and Agent Zero updated. Don't mount `/`, Docker socket, or SSH keys. |
| Shared LLM jailbreak | LOW | Agent Zero has its own system prompt. Injection via task description is possible but Agent Zero defaults are hardened. |
| Audit gap | MEDIUM | HAL logs the delegation and Agent Zero's final response. Agent Zero's internal logs are retrievable via `/api_log_get`. |

**Key decision: Should Agent Zero have Docker socket access?**

**No.** In the original docker-compose, it mounted the Docker socket for container management. For the headless-worker use case, remove this. Agent Zero should be a sandboxed code executor, not a Docker manager. If container management is needed, HAL already has `run_command` which can call `docker` CLI through the Judge-gated SSH path.

**Audit trail design:**
1. HAL logs: `{"tool": "delegate_task", "task": "<description>", "target": "agent-zero", "tier": 1, "approved": true, "context_id": "..."}`
2. Agent Zero logs: Retrievable via `GET /api_log_get?context_id=...` — store these alongside HAL's audit log for unified review
3. Each delegation gets a unique `context_id` that ties HAL's audit entry to Agent Zero's execution logs

### Phase 3: MCP

| Risk | Severity | Mitigation |
|------|----------|------------|
| Unauthenticated MCP endpoints | HIGH | Use token-based auth (Agent Zero supports `t-TOKEN` in URL path) |
| Tool discovery exposes attack surface | MEDIUM | HAL only connects to configured MCP servers, never auto-discovers |
| MCP server compromise | MEDIUM | Each MCP server runs with minimal permissions on its host |

---

## 6. Resource Budget

### Current baseline (what's running now)

| Component | RAM | VRAM | CPU |
|-----------|-----|------|-----|
| vLLM (Qwen2.5-32B-AWQ) | ~4 GB | ~23.4 GB (97.5%) | 2 cores (inference) |
| Ollama (embeddings, CPU-only) | ~1.5 GB | 0 | 1 core |
| PostgreSQL/pgvector | ~0.5 GB | 0 | 0.5 core |
| Prometheus + Grafana + exporters | ~1 GB | 0 | 0.5 core |
| ntopng + Redis | ~0.5 GB | 0 | 0.5 core |
| HAL (server.service + telegram) | ~0.3 GB | 0 | 0.5 core |
| System/kernel | ~2 GB | 0 | — |
| **Total** | **~10 GB** | **~23.4 GB** | **~5 cores** |

### Phase 1 additions

| Component | RAM | VRAM | CPU |
|-----------|-----|------|-----|
| Multi-host SSH | 0 | 0 | 0 |
| **Total after Phase 1** | **~10 GB** | **~23.4 GB** | **~5 cores** |

Phase 1 has zero resource cost — it's just code changes in HAL.

### Phase 2 additions

| Component | RAM | VRAM | CPU |
|-----------|-----|------|-----|
| Agent Zero container | 8 GB (limit) | 0 | 4 cores (limit) |
| **Total after Phase 2** | **~18 GB** | **~23.4 GB** | **~9 cores** |

**64 GB RAM — 18 GB used = 46 GB free.** Comfortable.
**24 GB VRAM — 23.4 GB used.** No change — Agent Zero doesn't use the GPU.
**8 cores — 9 used.** The CPU limits are soft; in practice, Agent Zero bursts only during code execution. There's enough headroom.

### Verdict

The server can comfortably handle both phases. The main constraint remains VRAM (97.5% used by vLLM), but since Agent Zero shares the same vLLM endpoint via API, no additional VRAM is needed. The 8 GB RAM limit for Agent Zero is right — it includes LiteLLM, the web server, FAISS memory, and the code execution sandbox.

---

## 7. Research Findings Appendix

### 7.1: Agent Zero API Surface (from codebase analysis)

Agent Zero (v0.9.8+) exposes the following external APIs:

**REST API:**
- `POST /api_message` — Submit a task
  - Body: `{"message": str, "context_id": str (optional), "attachments": [] (optional), "project": str (optional), "lifetime_hours": int (optional)}`
  - Header: `X-API-KEY: <token>`
  - Response: `{"response": str, "context_id": str}`
  - The `context_id` enables conversation continuity — send a follow-up with the same ID
- `GET/POST /api_log_get` — Retrieve execution logs by `context_id`
- `POST /api_terminate_chat` — Stop an in-progress task
- `POST /api_reset_chat` — Clear a conversation context
- `POST /api_files_get` — Retrieve files by path as base64

**MCP Server (when enabled):**
- SSE transport: `/mcp/t-TOKEN/sse`
- Streamable HTTP: `/mcp/t-TOKEN/http/`
- With project context: `/mcp/t-TOKEN/p-PROJECT_NAME/sse`

**A2A Server (when enabled):**
- FastA2A endpoint: `/a2a/t-TOKEN`
- With project: `/a2a/t-TOKEN/p-PROJECT_NAME`

**Configuration:**
- `A0_SET_*` environment variables override settings without requiring UI
- Auth token derived from `A0_SET_AUTH_LOGIN` + `A0_SET_AUTH_PASSWORD`
- LiteLLM provider config: `A0_SET_CHAT_MODEL_PROVIDER`, `A0_SET_CHAT_API_URL`, etc.

Source: Agent Zero docs — `docs/developer/connectivity.md`, `docs/guides/api-integration.md`, `docs/guides/a2a-setup.md`

### 7.2: MCP Ecosystem Findings

**Reference MCP servers (maintained by MCP steering group):**
- **Filesystem** — Secure file operations with configurable access controls
- **Git** — Repository management, file operations
- **Fetch** — Web content fetching
- **Memory** — Knowledge graph-based persistent memory

**Community MCP servers relevant to Orion:**
- **SSH MCP servers:** `mcp-ssh` (AiondaDotCom), `ssh-mcp-server` (classfang), `mcp_ssh` (sinjab) — production-ready SSH automation with file transfers and timeout protection
- **Docker MCP servers:** `mcp-server-docker` (ckreiling) — container, image, volume, network management
- **DesktopCommander** (wonderwhy-er) — file editing, terminal commands, SSH to remote servers; one of the most popular community MCP servers
- **Console Automation** — 40 tools for SSH, session management, testing, monitoring

**MCP transport options:**
- **stdio** — for local processes (Claude Desktop config style)
- **SSE** — Server-Sent Events over HTTP (Agent Zero supports this)
- **Streamable HTTP** — newer transport, also supported by Agent Zero

**Key insight:** The MCP ecosystem is massive (500+ servers) and growing. Agent Zero already speaks MCP (as both client and server). When HAL is ready for Phase 3, the integration surface is pre-built.

### 7.3: Multi-Agent Pattern Findings

**OpenAI Agents SDK:**
- Key pattern: **Handoffs** — primary agent transfers control to a specialized agent, which can hand back
- Architecture: `triage_agent → [shopping_agent, support_agent]`
- Each agent has its own `instructions`, `tools`, and `handoffs` list
- Built on Responses API; works with any OpenAI-compatible endpoint
- Tracing built in for observability
- **Relevance to Orion:** The handoff pattern is exactly what HAL→Agent Zero needs. But the SDK itself is unnecessary — HAL's delegation is a simple POST, not a complex multi-agent graph.

**LangGraph:**
- Represents agents as nodes in a graph, connections as edges
- Three patterns: Multi-Agent Collaboration (shared scratchpad), Agent Supervisor (independent agents + router), Hierarchical Teams (nested graphs)
- **Relevance to Orion:** Conceptually aligned (HAL is a supervisor, Agent Zero is a worker). But LangGraph is deeply tied to LangChain ecosystem and designed for OpenAI/Anthropic APIs. Adopting it would mean rewriting HAL's agent loop for marginal benefit.

**CrewAI:**
- Higher-level than LangGraph — define "teams" of agents with roles
- **Relevance to Orion:** Too high-level. Orion needs low-level control (Judge gating, custom intent routing, KB pre-seeding).

**AutoGen:**
- Frames multi-agent as "conversations" between agents
- **Relevance to Orion:** Different mental model from Orion's graph-based dispatch. No advantage over direct API integration.

**Practical consensus (2025-2026):**
- Simple delegation (1 primary + 1–2 workers) → Direct API calls, no framework needed
- Complex orchestration (5+ agents, dynamic routing) → LangGraph or custom graph
- The "right" protocol layer → MCP for tool federation, A2A for agent-to-agent
- Most successful homelab AI deployments use direct integration, not frameworks

### 7.4: Answers to Specific Research Questions

**Q1: Should HAL's tools support a `target_host` parameter?**
Yes. This is the simplest, highest-value change. Production AI agent systems handle multi-host execution via:
1. Static host inventories (most common for small deployments)
2. Service meshes/discovery (for cloud-scale)
3. MCP servers per host (emerging standard)

For a 2-host LAN, static config is correct. HAL's Judge already gates every command — extending to new hosts is trivial.

**Q2: Does Agent Zero have an API for programmatic task submission?**
Yes. `POST /api_message` is the primary endpoint. It accepts a message, returns a response, supports `context_id` for conversation continuity. Fully documented. See §7.1.

**Q3: Can Agent Zero use the same vLLM endpoint?**
Yes. Set `A0_SET_CHAT_MODEL_PROVIDER=openai` and `A0_SET_CHAT_API_URL=http://host.docker.internal:8000/v1`. LiteLLM natively supports OpenAI-compatible endpoints. Both agents share vLLM's inference capacity via continuous batching — no VRAM conflict.

**Q4: Is MCP the right way to do multi-agent communication in 2026?**
For tool federation, yes. For agent-to-agent delegation, A2A (which Agent Zero also supports) is emerging as the standard. However, for Orion's current 2-host setup, direct SSH + REST API is simpler and sufficient. MCP becomes valuable at 3+ tool sources or when integrating with the broader ecosystem (e.g., Grafana MCP server for dashboards, GitHub MCP server for repo management).

---

## Decision Matrix

| Criterion | A: Multi-host SSH | B: Agent Zero Worker | C: MCP Federation | D: Framework |
|-----------|:-:|:-:|:-:|:-:|
| Solves stated problem | ✅ | ⚠️ (indirectly) | ⚠️ (overkill) | ❌ |
| Implementation effort | ~200 LoC | ~400 LoC | ~600 LoC | ~2000+ LoC |
| New dependencies | 0 | httpx | mcp SDK | langchain/etc |
| New services to run | 0 | 1 container | N servers | 0 |
| Additional RAM | 0 | 8 GB | ~1 GB | 0 |
| Unlocks complex tasks | ❌ | ✅ | ⚠️ (via Agent Zero) | ⚠️ |
| Judge compatibility | ✅ native | ✅ gates delegation | needs adapter | needs rewrite |
| Future-proof | ⚠️ | ✅ | ✅ ✅ | ⚠️ |
| **Recommendation** | **Phase 1** | **Phase 2** | **Phase 3** | **Skip** |

---

*End of recommendation document.*
