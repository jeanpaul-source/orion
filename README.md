# Orion / HAL

**Orion** is a private infrastructure agent for serious homelabs. It runs entirely on your
hardware using a self-hosted LLM, monitors your services through Prometheus, reasons about
your lab's state using a vector knowledge base built from your actual configs and docs, and
executes operations through a tiered approval system — read-only queries run automatically,
service restarts ask first, destructive actions require explicit confirmation. Every decision
is audited. Every session is remembered.

**HAL** is the agent at Orion's core. It is not a general assistant — it knows this lab,
its history, and its failure patterns. It is designed to progress from answering questions
to diagnosing problems to autonomous remediation within a trust envelope you define.

> This is a personal tool, not a framework. It is tightly coupled to a specific homelab and
> intentionally so. See [ARCHITECTURE.md](ARCHITECTURE.md) for the design rationale and
> [ROADMAP.md](ROADMAP.md) for where it is going.

---

## What it is

- A terminal REPL (and HTTP server) that talks to a locally-hosted 32B LLM — no cloud, no data exfiltration
- An intent router that classifies every query before the LLM sees it — casual chat, health checks, KB lookups, and agentic tool loops are separate code paths
- A policy gate (the Judge) that gates every shell command, file write, and service action by tier — with a full audit trail
- A vector knowledge base of ~19,900 chunks across your lab configs, service docs, and domain reference material — harvested nightly
- A security observer that surfaces Falco events, Osquery host state, ntopng traffic, and Nmap scan results through the same agentic loop

## What it isn't

- Not a chatbot wrapper around an API call
- Not autonomous (yet) — HAL asks before acting on anything above read-only
- Not multi-user
- Not a cloud agent or a Kubernetes operator
- Not a replacement for your terminal — it runs commands *through* SSH with your approval

---

## Current state (Feb 2026)

558 offline tests (35 intent classifier tests additionally require Ollama). Eval baselines:
`hal_identity=100%`, `no_raw_json=100%`, `intent_accuracy=100%`, `web_tool_accuracy=100%`.

| Component | Status |
|---|---|
| Terminal REPL | Working |
| Intent routing (4 categories) | Working |
| Agentic tool loop + Judge | Working |
| pgvector KB (~19,900 chunks, 18 categories) | Working, harvested nightly |
| Session memory (SQLite, 30-day pruning) | Working |
| Security tools (Falco, Osquery, ntopng, Nmap) | Working |
| Observability (structured logs, OTel, Pushgateway, Grafana) | Working |
| HTTP server (`/chat`, `/health`) | Working |
| Telegram bot (polling, single-user auth) | Working |
| Autonomous remediation | Not yet built |
| Telegram / Web UI / Voice interfaces | Telegram working; Web UI, Voice not yet built |
| Trust evolution (earned/revoked tiers) | Not yet built |

---

## Quick start

```bash
git clone https://github.com/jeanpaul-source/orion
cd orion
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in PGVECTOR_DSN password (from /run/homelab-secrets/pgvector-kb.env on server)
python -m hal
```

For full setup, prerequisites, and `.env` reference: see [OPERATIONS.md](OPERATIONS.md).

---

## Slash commands

```text
/health          — live Prometheus metrics (CPU, memory, disk, load)
/search <q>      — search the knowledge base
/run <cmd>       — execute a command on the server (goes through Judge)
/read <path>     — read a file from the server
/ls <path>       — list a directory on the server
/write <path>    — write a file on the server
/remember <fact> — store a fact in the knowledge base
/search_memory   — full-text search over past sessions
/sessions        — list recent sessions
/audit           — show recent audit log entries
/help            — all commands
```

---

## Documentation

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components, data flow, design decisions |
| [OPERATIONS.md](OPERATIONS.md) | Deploy, `.env` reference, systemd units, known traps |
| [ROADMAP.md](ROADMAP.md) | What's done, what's next, end-state vision |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev workflow, tests, eval harness, CLAUDE.md |
| [CLAUDE.md](CLAUDE.md) | AI operating contract — required reading before any code change |
| [SESSION_FINDINGS.md](SESSION_FINDINGS.md) | Ground-truth audit of what runs vs. what is documented |

---

## Key files

| File | Role |
|---|---|
| `hal/main.py` | REPL entry point, session setup, slash commands |
| `hal/agent.py` | Four route handlers + agentic tool loop |
| `hal/intent.py` | Embedding classifier — tune `EXAMPLES` here |
| `hal/judge.py` | Policy gate — every action goes through this |
| `hal/llm.py` | `VLLMClient` (chat) + `OllamaClient` (embeddings only) |
| `hal/_unlocked/security.py` | Falco, Osquery, ntopng, Nmap workers |
| `hal/falco_noise.py` | Falco noise filter rules (`NOISE_RULES` + `is_falco_noise()`); no `hal.*` deps |
| `hal/web.py` | `web_search()` via Tavily; `fetch_url()` with SSRF + DNS-rebinding defence; `sanitize_query()` |
| `hal/memory.py` | SQLite session store at `~/.orion/memory.db` |
| `hal/workers.py` | File operation tools (read, write, patch, git_*) |
| `hal/executor.py` | SSH command runner |
| `hal/prometheus.py` | PromQL client + Pushgateway metrics |
| `hal/knowledge.py` | pgvector KB search client |
| `hal/_unlocked/server.py` | FastAPI HTTP server — `/chat` + `/health` |
| `hal/_unlocked/telegram.py` | Telegram bot — polls API, POSTs to `/chat`, single-user auth |
| `hal/trust_metrics.py` | Audit log parser + `get_action_stats` tool |
| `hal/_unlocked/watchdog.py` | Standalone health monitor (runs as systemd timer) |
| `harvest/` | KB harvest pipeline — scrape, chunk, embed, upsert |
| `eval/` | Evaluation harness — 24 queries, scorer, baselines |
| `tests/` | 558 offline tests + 35 intent classifier tests (require Ollama) |
| `ops/` | Systemd unit files for vllm, watchdog, harvest, telegram |
