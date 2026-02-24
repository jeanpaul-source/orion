# HAL — Personal Autonomous Home AI

HAL is an intentionally built AI system designed to become the autonomous intelligence of
an entire home: infrastructure, network, security, home automation, and software development,
all coordinated by a single boss. It is not a chatbot wrapper. Every component exists for a
reason, every action goes through a policy gate, and every decision is logged.

**Current state (Feb 2026):** Single-machine coordinator with deterministic intent routing,
a tiered approval system, a pgvector knowledge base of the lab, and a functional agentic
tool loop. The foundation is in place. The full vision is below.

> This README is written for two audiences equally: the operator returning after months away,
> and an AI reading this file cold. Both should be able to understand what exists, why it's
> built this way, and where it's going — without reading the source code first.

---

## Table of Contents

- [HAL — Personal Autonomous Home AI](#hal--personal-autonomous-home-ai)
  - [Table of Contents](#table-of-contents)
  - [Vision: The Completed System](#vision-the-completed-system)
    - [What HAL Becomes](#what-hal-becomes)
    - [The Agent Hierarchy](#the-agent-hierarchy)
    - [Full Home Scope](#full-home-scope)
    - [Predictive and Self-Healing](#predictive-and-self-healing)
    - [Self-Development](#self-development)
    - [Interfaces](#interfaces)
    - [Memory: The Elephant](#memory-the-elephant)
    - [Progressive Trust](#progressive-trust)
    - [Active Security](#active-security)
  - [Current State: How It Works Today](#current-state-how-it-works-today)
  - [Architecture](#architecture)
  - [Intent Routing](#intent-routing)
  - [The Judge (Policy Gate)](#the-judge-policy-gate)
    - [Tiers](#tiers)
    - [Tier Assignment (first match wins, applied in this order)](#tier-assignment-first-match-wins-applied-in-this-order)
    - [Audit Log](#audit-log)
  - [LLM Backend Split](#llm-backend-split)
  - [Tools Available to the Agentic Loop](#tools-available-to-the-agentic-loop)
  - [Data and Memory](#data-and-memory)
    - [Knowledge Base (pgvector)](#knowledge-base-pgvector)
    - [Session Memory (SQLite)](#session-memory-sqlite)
    - [Audit Log](#audit-log-1)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
    - [Full `.env` Reference](#full-env-reference)
  - [Running HAL](#running-hal)
  - [Developer Workflow](#developer-workflow)
    - [Tests](#tests)
    - [Evaluation](#evaluation)
    - [Harvest](#harvest)
    - [Deploy (laptop → server)](#deploy-laptop--server)
  - [Watchdog](#watchdog)
  - [Key Files](#key-files)
  - [Known Issues and Open Work](#known-issues-and-open-work)
    - [Open](#open)
    - [Resolved](#resolved)
    - [Known Traps](#known-traps)

---

## Vision: The Completed System

> *This section defines the intended end state. Every architectural decision should be
> evaluated against it. If something in the current implementation conflicts with this
> vision, that is a bug in the implementation, not in the vision.*

### What HAL Becomes

HAL grows from a single-machine coordinator into the autonomous intelligence of an entire
home — infrastructure, network, security, home automation, and software development, all
unified under one boss with named sub-agents, persistent structured memory, and a trust
model that earns its autonomy rather than assuming it.

The project name "Orion" is a placeholder. The system will be renamed as its identity
solidifies.

HAL is not an assistant you manage. The goal is a system you *trust* — one whose track
record, reasoning transparency, and audit trail are thorough enough that it feels fully
autonomous, even though every critical decision remains traceable and reversible.

---

### The Agent Hierarchy

HAL is the queen. Everything else reports to HAL, gets tasked by HAL, and returns results
to HAL. There is no orchestration layer above HAL except the operator.

```
Operator (you)
    └─ HAL  [queen — coordinator, memory, trust arbiter, developer, final decision-maker]
          │
          ├─ Thinker / Judge agents   [reason, plan, evaluate risk, propose actions to HAL]
          │     Named examples: Planner, Critic, Security Analyst, Risk Assessor
          │     These agents do not execute — they advise and gate.
          │
          ├─ Generic doer agents      [execute tasks HAL delegates, domain-agnostic]
          │     Named examples: Shell Worker, File Worker, Git Worker
          │     These agents have low trust by default, earn more through track record.
          │
          └─ Specialized doer agents  [own a domain end-to-end, deep context in one area]
                Named examples:
                  NetGuard      — network topology, routing, firewall rules, DNS
                  Sentinel      — cameras, physical security, intrusion detection, blocking
                  Architect     — self-development: writes, tests, reviews, deploys code
                  HomeOS        — home automation: lights, climate, routines, presence
                  Quartermaster — hardware inventory, power, physical machine health
```

**Why names matter:** Each agent has a name, an identity, a defined capability boundary, and
a trust tier. They can be addressed individually, audited individually, and replaced or
upgraded individually without disrupting the rest of the system. As compute grows, agents
distribute across machines naturally — the naming scheme is the stable interface.

---

### Full Home Scope

The completed system owns the entire home environment:

| Domain | Agent(s) | Full ownership means |
|---|---|---|
| **Compute** | HAL + Shell/File/Git Workers | Health, performance, container lifecycle, VM management, deployment |
| **Network** | NetGuard | Switches, routing, DNS, VLANs, traffic visibility, topology awareness |
| **Security** | Sentinel + NetGuard | Firewall rules, IDS, active traffic blocking, device quarantine, camera feeds, physical intrusion |
| **Home automation** | HomeOS | Lights, climate, routines, presence detection, scene control — HAL is the brain of the house |
| **Software development** | Architect | Writes, tests, reviews, and deploys code changes to HAL itself and to lab services |
| **AI reliability** | HAL + Critic | Monitors its own models, detects output drift, manages model upgrades without operator intervention |

---

### Predictive and Self-Healing

The completed HAL does not wait to be asked. It:

- **Detects trends before they become incidents:** disk filling, memory creeping, latency
  rising, certificate expiry approaching — all caught and acted on before they page you
- **Correlates patterns across time:** "this happens every Tuesday at 3am, here's the root
  cause" — not just alerting, but explaining
- **Resolves known failure modes automatically:** restarts degraded services, clears temp
  dirs, rotates logs, rolls back bad deployments — and writes a full account of what it
  did and why to the audit log
- **Escalates novel or ambiguous situations** rather than guessing — confidence-gated
  autonomous action means it acts when it knows, and asks when it doesn't
- **Learns from every incident:** each resolved problem is added to the knowledge base so
  the next similar event is recognized and handled faster

The end state: SSHing directly into the server becomes rare — not because it's blocked,
but because HAL has already handled it.

---

### Self-Development

The highest-trust capability, and the last thing to be unlocked:

- HAL identifies bugs, regressions, and missing capabilities in its own codebase
- Proposes changes: states root cause, proposed fix, confidence level (mirrors CLAUDE.md
  format so the operator review process is consistent)
- Implements the change on a branch, runs the full eval suite, presents diff + results
- Deploys on operator approval, monitors for regressions post-deploy, rolls back
  automatically if evals degrade

**Prerequisite infrastructure already in place:** the eval harness (`eval/`), the audit log
(`~/.orion/audit.log`), and the CLAUDE.md operating contract. Architect is built on top of
these — it doesn't replace them.

---

### Interfaces

All interfaces are first-class. A Telegram message and a terminal command have the same
capability surface, go through the same Judge, and produce the same audit trail.

| Channel | Role |
|---|---|
| **Terminal REPL** | Primary dev/ops interface — exists today |
| **Web UI** | Full dashboard: system status, KB browser, agent activity feed, audit log, trust management |
| **Telegram** | Mobile-first: receive alerts, reply to escalations, issue commands, full conversation from anywhere |
| **Voice** | In-home: HAL is the spoken interface for the house — rooms, routines, status queries, device control |

---

### Memory: The Elephant

HAL remembers everything, organized into retrievable categories — not a flat log:

| Memory category | What it contains |
|---|---|
| **Infrastructure state** | Live and indexed configs, service docs, topology snapshots (current KB) |
| **Change history** | What changed, when, by whom: "firewall rule added 2026-02-18 by HAL — blocked port scan from 203.0.113.4" |
| **Incident history** | What went wrong, what fixed it, how long it took, what was learned |
| **Operator preferences** | Decisions made, approaches rejected, stated preferences, working style |
| **Agent behavior** | Which agents performed well, which made bad calls, rolling trust scores |
| **Temporal patterns** | Recurring events, seasonal trends, anomalies and their correlates |

Memory is actively used — before acting on something it has done before, HAL surfaces the
relevant history and incorporates it into its reasoning. "Last time I restarted this
container it took 40 seconds and caused a brief metrics gap — proceeding, noting this."

---

### Progressive Trust

HAL starts constrained and earns autonomy through demonstrated reliability. Trust is
never assumed — it is versioned, logged, and revocable.

**Two paths to expanded permissions:**

1. **Operator grant:** You review the audit log, observe a clean track record over a period,
   and explicitly expand HAL's permissions for a class of actions. ("HAL has restarted
   Docker containers 47 times with zero bad outcomes — granting tier-1 auto-approval for
   `docker restart`.")

2. **HAL proposal:** HAL identifies an action class it handles reliably, presents the
   evidence (N successful executions, 0 rollbacks, sample reasoning), and formally requests
   expanded autonomy. You approve or deny. The proposal and your decision are logged.

**Trust can decrease:** a bad call triggers a review and can result in a tier downgrade for
that action class. Nothing silently persists after a failure.

**The line that never moves** regardless of trust level: actions that are irreversible at
infrastructure or home scale — data destruction, network isolation of the home, external
exposure of secrets, physical security changes — always require explicit human confirmation.
No trust tier unlocks these.

---

### Active Security

The completed security domain is not passive observation:

- Monitors all network traffic for anomalous patterns in real time
- **Blocks traffic and quarantines devices autonomously** when confidence is high and the
  action is reversible
- Escalates ambiguous cases with full evidence before acting — never silently drops traffic
  it isn't sure about
- Can isolate a compromised device from the rest of the network without taking down home
  services or triggering collateral disruption
- Maintains a complete, tamper-evident audit trail of every block, rule change, quarantine,
  and escalation with timestamps and reasoning

---

## Current State: How It Works Today

*Everything below this line describes what exists as of Feb 2026. Read the Vision above
first — it is the context that makes the current architecture legible.*

HAL today is a single-machine coordinator running on or connecting to `the-lab`
(`192.168.5.10`). It has:

- A working terminal REPL with session memory
- A deterministic intent classifier that routes ~80% of queries without calling the LLM
- A pgvector knowledge base with ~19,900 indexed chunks across 18 categories of lab documentation, configs, and domain knowledge
- A full agentic tool loop gated by a tiered policy Judge
- A standalone watchdog running as a user systemd timer
- An eval harness with 24 queries and scored baselines

The agent network, home automation, expanded interfaces, and self-development capabilities
are not yet built. The architecture has been designed from the start to support them —
the routing layer, Judge, and memory systems are intended to extend to multi-agent use,
not be replaced by it.

---

## Architecture

```
You  (terminal REPL today; Telegram, Web UI, Voice — planned)
 └─ hal/main.py  [session manager, Rich console, history at ~/.orion/history]
      └─ IntentClassifier  [embedding similarity, threshold 0.65, one embed call per query]
            │
            ├── conversational  → run_conversational()  — direct LLM reply, no tools
            ├── health          → run_health()          — Prometheus query only, no tool loop
            ├── fact            → run_fact()            — pgvector KB search only, no tool loop
            └── agentic         → run_agent()           — full tool loop, up to 8 LLM iterations
                                        │
                     ┌──────────────────┼──────────────────────┐
                     ▼                  ▼                      ▼
               VLLMClient          KnowledgeBase           SSHExecutor
               (chat+tools)        (pgvector)              (runs commands)
                     │                                         │
                     └──────────────── Judge ─────────────────┘
                                  (gates every action)
```

**Supporting components:**
- `OllamaClient` — embeddings only (never chat); feeds IntentClassifier and KnowledgeBase
- `MemoryStore` — SQLite session turns at `~/.orion/memory.db`; loaded into context on start
- `PrometheusClient` — PromQL queries for live metrics
- `SSHTunnel` — port-forwards lab services when running from a laptop (`USE_SSH_TUNNEL=true`)

**Why the routing layer exists:** Without pre-routing, every query — including "how's the
CPU?" — spins up a full LLM tool loop with multiple round trips. The `IntentClassifier`
handles the majority of queries with a single embed call and a direct lookup. The agentic
path is reserved for queries that actually require multi-step reasoning or action.

---

## Intent Routing

```
Query
  │
  ▼
OllamaClient.embed(query)           ← one API call, ~50ms
  │
  ▼
cosine_similarity(query_vec, EXAMPLES[category])   ← for each of 4 categories
  │
  ├── best score ≥ 0.65  →  route to that category's handler
  └── best score < 0.65  →  default to agentic  (safest fallback)
```

| Intent | Handler | What happens |
|---|---|---|
| `conversational` | `run_conversational()` | LLM responds directly — no KB, no tools, no Prometheus |
| `health` | `run_health()` | Single Prometheus query, formatted response — no LLM tool loop |
| `fact` | `run_fact()` | pgvector similarity search, top chunks returned — no LLM tool loop |
| `agentic` | `run_agent()` | Full VLLMClient tool loop, up to `MAX_ITERATIONS=8`, all tools available |

**Tuning the classifier:** The classifier lives in `hal/intent.py`. It works by comparing
the query embedding against ~13 example sentences per category (`EXAMPLES` dict). To fix a
misrouted query, add a sentence that looks like the misrouted query to the correct
category — no code changes, no retraining, no redeploy. Just add the sentence and restart.

**If the embedding model is unreachable at startup:** the classifier degrades gracefully to
always returning `agentic`. HAL keeps working; it just loses the efficiency of pre-routing.

---

## The Judge (Policy Gate)

Every tool call and shell command goes through `hal/judge.py` before execution. There are
no exceptions, no bypass paths, and no way for HAL to execute anything without this gate.
This is the trust infrastructure that the progressive autonomy model is built on.

### Tiers

| Tier | Name | Behavior |
|---|---|---|
| 0 | read-only | Auto-approved silently, no prompt |
| 1 | modify (reversible) | Prints what it wants to do, prompts operator, executes on approval |
| 2 | config change | Explains full plan, waits for explicit approval before any action |
| 3 | destructive | Requires typing a confirmation phrase — no accidental approvals |

### Tier Assignment (first match wins, applied in this order)

1. **Fixed action types** — `search_kb` → 0, `get_metrics` → 0, `write_file` → 2, `remember_fact` → 0
2. **Destructive shell patterns** → 3: `rm -rf`, `drop table`, `mkfs`, `dd if=`, fork bombs
3. **Config-level shell patterns** → 2: `docker run`, `systemctl enable/disable`, `chmod 777`, `ufw`, redirect to `/etc`
4. **Restart/stop/start patterns** → 1: `docker restart/stop/start`, `systemctl restart/stop/start`
5. **Safe first-token whitelist** → 0: `ps`, `cat`, `df`, `ls`, `grep`, `journalctl`, `netstat`, `ping`, and others
6. **Safe compound prefixes** → 0: `systemctl status`, `docker ps/stats/logs/inspect/images`, etc.
7. **Sensitive path escalation** → tier + 1: `.env`, `~/.ssh`, `/run/homelab-secrets`, `/etc/shadow`, `/root/`
8. **Default** → 1 (anything unrecognized requires approval)

### Audit Log

Every decision — approved and denied — is appended to `~/.orion/audit.log` with timestamp,
action, tier, and outcome. This log is the foundation of the progressive trust model: it
is the evidence base for expanding or contracting HAL's permissions over time.

---

## LLM Backend Split

HAL uses two separate LLM backends with completely distinct roles. **This split is
non-negotiable** — Ollama with GPU access was consuming ~800 MB VRAM, causing vLLM to OOM
during inference on the RTX 3090 Ti. Both models running on GPU simultaneously is not viable.

| Client | Backend | Role | Model |
|---|---|---|---|
| `VLLMClient` | vLLM at `VLLM_URL` (`:8000`) | All LLM inference: chat, reasoning, tool calls | `Qwen/Qwen2.5-32B-Instruct-AWQ` |
| `OllamaClient` | Ollama at `OLLAMA_HOST` (`:11434`) | Embeddings **only** — intent classification and KB search | `nomic-embed-text:latest` |

**Ollama is CPU-bound.** `OLLAMA_NUM_GPU=0` is set in
`/etc/systemd/system/ollama.service.d/override.conf`. Do not remove this flag. Ollama is
a bare-metal systemd service — never manage it with Docker commands.

**vLLM runs as a user systemd service:**

```bash
systemctl --user status vllm.service     # check running state
systemctl --user restart vllm.service    # restart
systemctl --user stop vllm.service       # stop
journalctl --user -u vllm -f             # follow logs
```

**Required env vars in the vllm.service unit file** (both are load-bearing — do not remove):
- `VLLM_USE_FLASHINFER_SAMPLER=0` — fixes CUDA device-side assert crash on RTX 3090 Ti
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` — prevents KV cache OOM under inference load

**vLLM launch flags:**
```
--enable-auto-tool-choice
--tool-call-parser hermes
--enforce-eager
--max-model-len 8192
--gpu-memory-utilization 0.95
```

To update the unit file: edit `ops/vllm.service`, then:
```bash
cp ops/vllm.service ~/.config/systemd/user/vllm.service
systemctl --user daemon-reload
systemctl --user restart vllm.service
```

---

## Tools Available to the Agentic Loop

When `run_agent()` is active, the LLM autonomously selects and calls these tools. Every
call goes through the Judge before execution.

| Tool | Default Tier | What it does |
|---|---|---|
| `search_kb` | 0 | Cosine similarity search over the pgvector knowledge base |
| `get_metrics` | 0 | Live Prometheus metrics: CPU, memory, disk, load average, uptime |
| `run_command` | 0–3 | Shell command on the server via SSH — tier assigned by Judge per command |
| `read_file` | 0 | Read a file from the server filesystem |
| `list_dir` | 0 | List a directory on the server |
| `write_file` | 2 | Write/overwrite a file on the server (shows content preview before approval) |
| `patch_file` | 2 | Replace a string in a file — reads, validates, shows unified diff, then writes |
| `git_status` | 0 | `git status` on a repo on the server |
| `git_diff` | 0 | `git diff` on a repo on the server |

**Tool selection guidance (baked into the system prompt):**
- Prefer `search_kb` over `run_command` when the answer may already be documented
- Use `run_command` only for live state that cannot be in the KB (current process list,
  active connections, recent log lines)
- `patch_file` is preferred over `write_file` for targeted changes — safer, diffable,
  easier to review

---

## Data and Memory

### Knowledge Base (pgvector)

The lab's infrastructure documentation, service configs, and state are chunked, embedded
with `nomic-embed-text`, and stored in a pgvector database. HAL searches this via
`search_kb` to answer factual questions without running commands.

Current size: **~19,900 chunks across 18 categories** (as of Feb 23, 2026). Re-harvest to update:
```bash
python -m harvest
```

The harvest pipeline lives in `harvest/`. It collects live lab state (containers, system metrics, configs, systemd units) and ingests pre-scraped static documents from `/data/orion/orion-data/documents/raw`, chunks them, embeds them via `nomic-embed-text`, and upserts into pgvector.

Stale chunks from deleted files are cleared automatically on each harvest run. A nightly harvest timer (`harvest.timer`) runs at 3am on the server to keep lab state current and pick up new static docs.

### Session Memory (SQLite)

Conversation turns are persisted at `~/.orion/memory.db`. On startup, previous session
turns are loaded into the LLM context window, giving HAL continuity across sessions.

```bash
python -m hal          # continues from last session
python -m hal --new    # starts a fresh session (clears loaded history, keeps the db)
```

**Known issue (RC3):** There is currently no pruning of old turns. Very long session
histories will eventually degrade context quality and may hit the 8192 token limit. The
workaround is `hal --new`. A proper pruning strategy (summarization or sliding window)
is needed.

**SQLite init race (known trap):** If HAL crashes between opening `~/.orion/memory.db` and
completing `_init()`, the file is left as an empty schema-0 database. The next start fails
with `sqlite3.OperationalError: disk I/O error`. Fix:
```bash
rm ~/.orion/memory.db   # HAL recreates it cleanly on next launch
```

### Audit Log

Every Judge decision — approved and denied — is appended to `~/.orion/audit.log` with
timestamp, action type, tier, command or detail, and outcome. This file grows indefinitely
and should be reviewed periodically. It is also the evidence base for progressive trust
decisions.

---

## Prerequisites

**On the machine running HAL (server or laptop):**
- Python 3.11+
- SSH key-based access to `LAB_HOST` (no password prompt)

**On the server (`the-lab`, `192.168.5.10`):**
- `vllm.service` running (user systemd) — the chat LLM
- `ollama.service` running (system systemd) — embeddings only, CPU-bound
- pgvector Docker container running on port 5432
- Prometheus Docker container running on port 9091 (not 9090 — that is Cockpit)
- Grafana Docker container running on port 3001
- `falco-modern-bpf.service` running (system systemd) — host behavioral IDS, eBPF probe
- `osquery` installed — queried on demand via `sudo osqueryi`
- ntopng + Redis running via Docker Compose at `~/ntopng/` — traffic monitor on port 3000
- `nmap` installed — LAN inventory scanning, invoked on demand

**If running HAL from a laptop (not the server directly):**
- Set `USE_SSH_TUNNEL=true` in `.env`
- The tunnel module (`hal/tunnel.py`) will forward the required ports automatically

---

## Setup

```bash
git clone https://github.com/jeanpaul-source/orion
cd orion

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Open .env and fill in the PGVECTOR_DSN password.
# Password is in: /run/homelab-secrets/pgvector-kb.env  (on the server)
```

### Full `.env` Reference

| Variable | Default value | Notes |
|---|---|---|
| `OLLAMA_HOST` | `http://192.168.5.10:11434` | Embeddings only — do not point at vLLM |
| `CHAT_MODEL` | `Qwen/Qwen2.5-32B-Instruct-AWQ` | Must exactly match the model loaded in vLLM |
| `EMBED_MODEL` | `nomic-embed-text:latest` | Must be pulled in Ollama (`ollama pull nomic-embed-text`) |
| `PGVECTOR_DSN` | `postgresql://kb_user@192.168.5.10:5432/knowledge_base` | **Fill in the password** |
| `PROMETHEUS_URL` | `http://192.168.5.10:9091` | Port **9091** — 9090 is Cockpit, a completely different service |
| `LAB_HOST` | `192.168.5.10` | SSH target for all remote commands |
| `LAB_USER` | `jp` | SSH user on the server |
| `USE_SSH_TUNNEL` | `false` | Set `true` when running from a laptop outside the server |
| `NTFY_URL` | *(empty)* | Push alerts via ntfy.sh topic URL — leave empty to disable |
| `VLLM_URL` | `http://localhost:8000` | vLLM OpenAI-compatible API — `localhost` on the server, tunneled on laptop |
| `NTOPNG_URL` | `http://localhost:3000` | ntopng traffic monitor REST API — no auth required (login disabled, local only) |
| `OTLP_ENDPOINT` | `http://localhost:4318` | OpenTelemetry OTLP HTTP endpoint for traces (export only if reachable) |
| `HAL_LOG_LEVEL` | `INFO` | Root log level (DEBUG, INFO, WARNING, ERROR) |
| `HAL_LOG_JSON` | `1` | When `1`/true, logs are JSON; set `0` to use plain text formatter |
| `PROM_PUSHGATEWAY` | *(empty)* | When set (e.g., `http://the-lab:9091`), emit metrics via Pushgateway |

---

## Running HAL

```bash
# Continue last session
python -m hal

# Start fresh (new session, history cleared from context)
python -m hal --new

# Server shortcut (alias defined in shell config)
hal     # expands to: cd ~/orion && .venv/bin/python -m hal
```

HAL uses a Rich console with a persistent readline history at `~/.orion/history`.
The system prompt establishes HAL's identity — it is not Qwen, not Claude. It is HAL.

---

## Observability

HAL includes optional, zero-downtime observability that you can enable via environment variables. Defaults are safe no-ops unless configured.

- Structured logs (JSON by default):
  - Enable/disable JSON: HAL_LOG_JSON=1 (default) or 0
  - Log level: HAL_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR (default INFO)
  - Logs include trace_id/span_id when tracing is active and session_id context
- Tracing (OpenTelemetry):
  - OTLP_ENDPOINT=http://localhost:4318 (default) — OTLP HTTP traces are exported here
  - If opentelemetry packages are not installed or the endpoint is unreachable, tracing is a no-op
- Metrics (Prometheus Pushgateway):
  - PROM_PUSHGATEWAY=http://the-lab:9091 — when set, HAL emits lightweight counters/histograms via Pushgateway text format
  - If not set, metrics calls are no-ops

Emitted metric names (labels in braces):
- hal_requests_total{intent, outcome}
- hal_request_latency_seconds{intent}
- hal_tool_calls_total{tool, outcome}

Where instrumentation lives:
- Logging: hal/logging_utils.py (used by hal/main.py and hal/agent.py)
- Tracing: hal/tracing.py (setup_tracing + get_tracer); spans wrap each turn and tool call
- Metrics: hal/prometheus.py (Counter, Histogram helpers; push-only, optional)

Example (enable JSON logs + tracing + Pushgateway):

```bash
export HAL_LOG_JSON=1
export HAL_LOG_LEVEL=INFO
export OTLP_ENDPOINT=http://localhost:4318
export PROM_PUSHGATEWAY=http://192.168.5.10:9091
python -m hal
```

## Developer Workflow

### Tests

```bash
# Full test suite (requires Ollama to be reachable — intent tests use live embeddings)
OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v
```

141 tests total: 35 intent classifier tests (require Ollama — live embeddings), 96 unit tests for Judge and MemoryStore (no Ollama needed), and 10 agent loop integration tests (no Ollama needed).
`pytest.ini` sets `pythonpath = .` so the `hal` package resolves without install.

### Evaluation

Run on the server after any change that could affect response quality:

```bash
python -m eval.run_eval                     # runs 24 queries → eval/responses.jsonl
python -m eval.evaluate --skip-llm-eval    # scores responses → eval/results/eval_out.json
```

**Baselines (Feb 23 2026):** `hal_identity=100%`, `no_raw_json=100%`, `intent_accuracy=95.8%`

**Security stack installed (Feb 23 2026):** Falco (eBPF, modern-bpf probe), Osquery 5.21.0,
ntopng Community (Docker Compose, `~/ntopng/`), Nmap 7.92. `hal/security.py` worker and
Judge integration are the next step — see todo list.

If a change causes any baseline to regress, do not merge.

### Harvest

Re-index the lab state into pgvector after infrastructure changes:

```bash
python -m harvest              # live run
python -m harvest --dry-run   # preview what would be written, no DB changes
```

The nightly harvest timer on the server (`harvest.timer`) runs automatically at 3am. To deploy or update it:

```bash
cp ops/harvest.service ops/harvest.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now harvest.timer
```

### Deploy (laptop → server)

```bash
# On laptop
git push origin main

# On server
cd ~/orion && git pull    # alias: orion-update
```

The server never pushes. Git flow is always laptop → GitHub → server pull.

---

## Watchdog

A standalone health monitor, separate from HAL's main process. Deployed as a user systemd
timer on the server. Fires every 5 minutes. Checks service health and resource state.
Writes to log always; pushes via ntfy when `NTFY_URL` is configured.

```bash
systemctl --user status watchdog.timer      # check schedule and last run
systemctl --user restart watchdog.service   # run immediately
journalctl --user -u watchdog -f            # follow logs
```

**Deploy or update the watchdog:**
```bash
cp ops/watchdog.service ~/.config/systemd/user/watchdog.service
cp ops/watchdog.timer   ~/.config/systemd/user/watchdog.timer
systemctl --user daemon-reload
systemctl --user enable --now watchdog.timer
```

State file: `~/.orion/watchdog_state.json` — tracks cooldowns to avoid alert storms.

---

## Key Files

| File | Role |
|---|---|
| `hal/main.py` | Entry point — REPL loop, session setup, argument parsing, Rich console |
| `hal/agent.py` | All four route handlers + the agentic tool loop (`MAX_ITERATIONS=8`) |
| `hal/intent.py` | Embedding classifier — tune `THRESHOLD` and `EXAMPLES` here, nothing else |
| `hal/judge.py` | Policy gate — full tier logic, audit log writer, `approve()` called by all workers |
| `hal/llm.py` | `VLLMClient` (chat + tools) and `OllamaClient` (embeddings only) |
| `hal/config.py` | All configuration — loaded from `.env` via `load()`, dataclass `Config` |
| `hal/memory.py` | SQLite session store at `~/.orion/memory.db` |
| `hal/executor.py` | SSH command execution on the server — wraps paramiko or subprocess |
| `hal/workers.py` | File operation tools: `read_file`, `write_file`, `patch_file`, `list_dir`, `git_*` |
| `hal/security.py` | Security worker — wraps Falco, Osquery, ntopng, Nmap into four HAL tools |
| `hal/prometheus.py` | PromQL query client; optional Counter/Histogram helpers (push via PROM_PUSHGATEWAY) — used by `run_health()` and the `get_metrics` tool |
| `hal/knowledge.py` | pgvector KB search client — used by `run_fact()` and the `search_kb` tool |
| `hal/facts.py` | `remember()` — saves a fact into session memory mid-conversation |
| `hal/tunnel.py` | SSH tunnel — forwards lab ports when `USE_SSH_TUNNEL=true` |
| `hal/watchdog.py` | Standalone monitor — runs independently as a systemd service |
| `hal/logging_utils.py` | Structured logging (JSON optional), context propagation via contextvars |
| `hal/tracing.py` | OpenTelemetry tracing setup |
| `harvest/` | Full harvest pipeline: scrape sources, chunk, embed, upsert to pgvector |
| `eval/` | Evaluation harness: 24-query suite, response collector, scorer, baseline results |
| `tests/` | 141 tests: 35 intent classifier tests (require Ollama) + 96 unit tests for Judge and MemoryStore + 10 agent loop integration tests (no Ollama needed) |
| `ops/` | Systemd unit files (`vllm.service`, `watchdog.service`, `watchdog.timer`, `harvest.service`, `harvest.timer`), `KEYS_AND_TOKENS.md` |
| `~/ntopng/docker-compose.yml` | ntopng + Redis Compose stack on server (not in repo — lives on server only) |
| `CLAUDE.md` | AI operating contract — required reading before any code change. Contains the rules that prevent drift. |
| `SESSION_FINDINGS.md` | Ground-truth audit of what actually runs on the server vs. what is documented |

---

## Known Issues and Open Work

### Open

*None — all known regressions are resolved.*

### Resolved

| ID | Description | Fix |
|---|---|---|
| **RC1** | Ollama + `qwen2.5-coder:32b` emitted tool calls as JSON text inside `content` instead of structured tool call fields. The agentic loop couldn't parse them and the session broke. | Switched to vLLM + `Qwen2.5-32B-Instruct-AWQ` with `--tool-call-parser hermes`. Eval: `no_raw_json=100%` |
| **RC2** | The model would override its identity mid-session and refer to itself as Qwen or acknowledge being "just an AI assistant." | Stronger identity lock in the system prompt + instruct model (vLLM). Eval: `hal_identity=100%` |
| **RC3** | Broken or low-quality turns accumulate in SQLite with no pruning. Long sessions compound context noise and can hit the 8192 token limit. | `MemoryStore.prune_old_turns(days=30)` called at every startup (`main.py`); `TURN_WINDOW=40` caps context loading per session |
| **RC4** | Casual short inputs (greetings, acknowledgements) near the intent threshold occasionally fall through to `agentic`, which seeds irrelevant KB context into the response. | `conversational` category expanded to 30 examples covering acknowledgements, affirmations, and short social phrases; 14 parametrized classifier tests added |
| **RC5** | Same root as RC4 — any short ambiguous input near the 0.65 threshold is at risk of misroute. | Same as RC4 |

### Known Traps

**SQLite init race:** If HAL crashes between opening `~/.orion/memory.db` and completing
schema init, the file is left as an empty schema-0 database. Next start fails with
`sqlite3.OperationalError: disk I/O error`. Fix: `rm ~/.orion/memory.db` — HAL recreates
it on next launch.

**Prometheus port:** Port 9091 is Prometheus. Port 9090 is Cockpit. These are different
services. The default fallback in `config.py` previously pointed at 9090 (wrong). The
`.env` override to 9091 is required and correct — do not "fix" it to the default.

**Ollama GPU flag:** `OLLAMA_NUM_GPU=0` in the Ollama systemd override is load-bearing.
It looks like a performance regression. It is not — it prevents Ollama from consuming
~800 MB VRAM that vLLM needs for the KV cache. Do not remove it.

**Falco `pg_isready` noise:** Falco fires `Read sensitive file untrusted` every ~30s because
the pgvector container's healthcheck script (`pg_isready`) reads `/etc/shadow`. This is
not a real threat — it is a known false positive. The security worker filters it by default.
Do not suppress this rule globally; filter it at query time by excluding `proc.name=pg_isready`.

**OllamaClient model param removed (Feb 2026):** `OllamaClient.__init__` no longer takes a
`model` argument — it was unused (Ollama is embeddings-only). The signature is now
`(base_url, embed_model)`. Any code constructing `OllamaClient` with three args will break.
