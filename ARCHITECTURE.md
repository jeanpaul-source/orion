# Architecture

This document describes Orion's components, data flow, and the design decisions behind them.

---

## Component map

```text
You  (terminal REPL, HTTP server, Telegram bot)
 └─ hal/main.py  [session manager, Rich console, readline history]
      └─ IntentClassifier  [embedding similarity, one embed call per query]
            │
            ├── conversational                → _handle_conversational()  — single LLM call, no tools, no KB
            └── health | fact | agentic       → run_agent()               — full tool loop, up to MAX_ITERATIONS
                                        │  (KB + Prometheus pre-seeded before iteration 0)
                                        │
                     ┌──────────────────┼──────────────────────┐
                     ▼                  ▼                      ▼
               VLLMClient          KnowledgeBase           ExecutorRegistry
               (chat+tools)        (pgvector)              (resolves host → SSHExecutor)
                     │                                         │
                     └──────────────── Judge ─────────────────┘
                                  (gates every action)

Supporting components:
  OllamaClient  — embeddings only (never chat); feeds IntentClassifier + KnowledgeBase
  MemoryStore   — SQLite session turns at ~/.orion/memory.db; loaded into context on start
  PrometheusClient — PromQL queries for live metrics + Pushgateway metric push
  SSHTunnel     — port-forwards lab services when running from a laptop (USE_SSH_TUNNEL=true)
  ExecutorRegistry — maps host names ("lab", "laptop", …) to SSHExecutor instances;
                     tools accept an optional target_host parameter; default is "lab"

HTTP layer (hal/server.py):
  FastAPI server; ServerJudge auto-denies tier 1+
  Endpoints:
    GET  /              — serve web UI (hal/static/index.html)
    GET  /health        — liveness probe (no auth)
    GET  /health/detail — per-component checks + live Prometheus metrics
    GET  /kb/categories — KB category list with chunk counts
    GET  /kb/search     — semantic search over the knowledge base
    POST /kb/remember   — store a fact in the KB (category='memory')
    POST /chat          — send a message, get a response + session_id + intent
  Auth: bearer token (HAL_WEB_TOKEN) required on all endpoints except /health and static files
  Used by: Web UI, Telegram bot, external integrations

Web UI (hal/static/):
  Lightweight browser chat interface — served by FastAPI at /
  Vanilla JS + marked.js (markdown) + highlight.js (syntax highlighting), no build step
  Sessions stored in localStorage as web-{timestamp}; sidebar with session list + /health status
  Same ServerJudge tier-0-only behavior as Telegram

Telegram interface (hal/telegram.py):
  Thin async wrapper — POSTs to /chat endpoint over localhost
  Auth: single ALLOWED_USER_ID; session: tg-{chat_id}; UX: thinking→edit
  Polling only (no webhook — no public HTTPS on the homelab)
```

---

## Data flow per query

```text
User types query
  → MemoryStore loads last N turns into context (see TURN_WINDOW in hal/memory.py)
  → IntentClassifier embeds query via Ollama (nomic-embed-text)
      → cosine_similarity vs. example sentences per category (see EXAMPLES in hal/intent.py)
      → best score ≥ THRESHOLD → route to that handler
      → best score < THRESHOLD → default to agentic (safe fallback)

  conversational path:
      → VLLMClient.chat(system_prompt + history + query)
      → response rendered to terminal
      → turn saved to MemoryStore

  run_agent path (all non-conversational intents):
      → KnowledgeBase.search(query) → inject high-confidence chunks as context
      → PrometheusClient queries live metrics snapshot → inject as context
        (both pre-seeds happen before iteration 0; simple queries resolve from context
         without issuing any tool calls)
      → loop up to MAX_ITERATIONS:
            VLLMClient.chat_with_tools(history + tools_schema)
            if tool_calls:
                for each call:
                    Judge.approve(tool, args) → tier 0: auto / tier 1+: prompt
                    if approved:
                        result = _dispatch(tool_call, executor, judge, kb, prom)
                        cap result at _MAX_TOOL_OUTPUT chars
                        append tool result to history
            else:
                break (final text response found)
      → response rendered
      → turn saved to MemoryStore
      → metrics flushed to Pushgateway
```

---

## Intent routing — design rationale

**Why classify before the LLM sees the query?**

Without pre-routing, every query — including "how's the CPU?" or "thanks" — spins up a full
LLM tool loop with multiple API round-trips. The `IntentClassifier` handles ~80% of queries
with a single embed call (< 50ms) and dispatches them to a cheaper code path.

**Why embedding similarity instead of a prompted classifier?**

One embed call is faster and cheaper than an LLM inference call. The classification is
deterministic and auditable — you can always tell why a query was routed a particular way
by checking its cosine similarity against the example sentences.

**Why default to `run_agent` on low confidence?**

`run_agent` is the most capable path — it has access to all tools and can handle any query
correctly, even if slowly. Routing an ambiguous query there is safe. All non-conversational
intents (health, fact, agentic) map to the same handler, so the only routing decision that
matters is whether the query is conversational or not.

**How to tune it:** Edit `EXAMPLES` in `hal/intent.py`. Add a sentence that looks like the
misrouted query to the correct category. No retraining, no redeploy — just restart.

---

## The Judge (policy gate) — design rationale

**Why does every action go through a gate?**

The Judge is the foundation of the progressive trust model. Without it, there is no audit
trail, no basis for expanding or contracting HAL's permissions, and no protection against
hal making a bad call silently. Every decision — approved and denied — is logged with
timestamp, tier, action, and outcome.

**Tier system:**

| Tier | Name | Behavior |
|---|---|---|
| 0 | read-only | Auto-approved silently |
| 1 | modify (reversible) | Shows intent, prompts for approval |
| 2 | config change | Explains full plan, requires explicit approval |
| 3 | destructive | Requires typing a confirmation phrase |

**Tier assignment for `run_command` (shell commands):**

Before any rule matching, two pre-checks run:

- **Evasion detection** — unconditional deny (tier 3) for shell evasion patterns
  (command substitution, eval/exec, base64-decode pipes, process substitution,
  hex/octal escapes — full list in `_EVASION_PATTERNS` in `judge.py`)
- **Compound command splitting** — commands joined by `;`, `&&`, `||`, or `|`
  are split and each sub-command classified independently; the **highest** tier
  across all sub-commands wins

Then, per sub-command (first match wins):

1. Dangerous shell patterns → 3: `rm -rf`, `drop table`, `mkfs`, `dd if=`, fork bombs, `reboot`, `shutdown`, etc.
2. Git write-operation blocking → 3: `git push`, `git commit`, `git merge`, etc.
   (read-only git subcommands like `status`, `log`, `diff` are tier 0)
3. Config-level patterns → 2: `docker run`, `systemctl enable/disable`, `chmod 777`, `chown`, `ufw`, inline script interpreters
4. Restart/stop/start patterns → 1: `docker restart`, `systemctl restart`, etc.
5. Safe command whitelist → 0: `ps`, `cat`, `df`, `ls`, `grep`, `journalctl`, `ping`, etc.
6. Safe compound prefixes → 0: `systemctl status`, `docker ps/logs/inspect`, etc.
7. Sensitive paths escalate tier by 1: credentials, secrets, shadow files, `/root`,
   and other security-critical locations (full list in `_SENSITIVE_PATHS` in `judge.py`)
8. Default → 2 (unknown command requires approval)

**Non-command action types** use a fixed tier map: `search_kb` → 0, `read_file` → 0
(sensitive paths → 1), `write_file` → 2 (repo paths → 3, sensitive paths → 3),
`run_code` → 2, `scan_lan` → 1, `fetch_url` → 1, etc.

**Why is the sensitive path check a tier bump instead of a tier set?**

Because `cat ~/.ssh/known_hosts` (safe command + sensitive path) should be tier 1, not
auto-approved. But `rm -rf ~/.ssh/` (destructive + sensitive path) should stay tier 3.
Adding 1 to the current tier preserves the relative risk ordering.

---

## Agent loop — design rationale

**Loop constraints:**

- `MAX_ITERATIONS` — prevents infinite loops when the model keeps calling tools
- `MAX_TOOL_CALLS` — caps unique tool dispatches per turn; the loop stops when either limit is reached
- `_MAX_TOOL_OUTPUT` cap per tool result — prevents context explosion from verbose tools
- Dedup guard — if the model calls the same `(tool, args)` twice in one turn, the second
  call is skipped and a synthetic "already called" message is injected
- Empty tools list on final iteration — forces a text response if the loop nears its limit
  without one
- Multi-host routing — `run_command`, `read_file`, `list_dir`, `write_file` accept an
  optional `target_host` parameter; `ExecutorRegistry.get(target_host)` resolves the
  host name to an `SSHExecutor`; default is `"lab"` (the primary server)
- Sandboxed code execution — `run_code` runs Python in a disposable Docker container
  (`orion-sandbox:latest`) with `--network none --read-only --memory 256m --cpus 1
  --pids-limit 64 --tmpfs /tmp:size=64m`; code is mounted read-only; Judge tier 2
  (requires approval in REPL, auto-denied via HTTP/Telegram `ServerJudge`);
  enabled by default (`SANDBOX_ENABLED=true`)

**Why not run the LLM in streaming mode for tool calls?**

Tool calls require parsing the full structured response. Streaming the model output while
also parsing tool call JSON from it is complex and fragile. Batch responses are simpler and
correct. The UX trade-off is acceptable for a terminal REPL.

**KB seeding threshold:**

All queries entering `run_agent()` use a cosine-similarity threshold for KB pre-seeding
(see the filter in `run_agent()` in `hal/agent.py`). Only strong matches are injected as
context before iteration 0. A lower threshold pulled in marginally-relevant docs and added
noise to the first iteration; the current value keeps the pre-seed high-signal. If no chunk
clears the threshold, the loop starts without KB context and the
model can issue a `search_kb` tool call if it determines one is needed.

---

## LLM backend split

HAL uses two separate LLM backends with completely distinct roles. **This split is
non-negotiable** — Ollama with GPU access consumes ~800 MB VRAM, causing vLLM to OOM
during inference on the RTX 3090 Ti.

| Client | Backend | Role | Model |
|---|---|---|---|
| `VLLMClient` | vLLM at `VLLM_URL` (port 8000) | All LLM inference — chat, reasoning, tool calls | See `vllm_model` in `hal/config.py` |
| `OllamaClient` | Ollama at `OLLAMA_HOST` (port 11434) | Embeddings **only** — intent classification + KB search | See `embed_model` in `hal/config.py` |

`OLLAMA_NUM_GPU=0` is set in Ollama's systemd override. Do not remove it. Ollama is a
bare-metal systemd service — never manage it with Docker commands.

---

## Memory — design rationale

**SQLite for session turns, pgvector for facts and KB:**

Session turns (conversation history) are short-lived, structured, and need full-text search.
SQLite is fast, local, and has zero operational overhead. pgvector is for semantic search
over longer documents — session turns don't need cosine similarity.

**30-day pruning + 40-turn window:**

`prune_old_turns()` runs at REPL startup and deletes old turns (see default in `hal/memory.py`).
`TURN_WINDOW` caps how many turns are loaded into the context window per session.
Together, these prevent unbounded context growth and ensure old failures don't bias new
sessions.

**Poison filter:**

`save_turn()` checks if a response is a raw JSON tool-call dump before persisting it.
If it is, the turn is dropped. This prevents pre-vLLM-era failures from being re-injected
into context.

---

## Observability

All observability is optional and no-op if disabled or unreachable.

**Structured logging** (`hal/logging_utils.py`):

- JSON format when `HAL_LOG_JSON=1` (default in server/daemon mode); REPL mode uses
  Rich console output via `RichHandler` regardless of this setting
- `session_id` and `turn_id` propagated via Python `contextvars`;
  `trace_id` comes from OpenTelemetry spans (when available), not contextvars
- `HAL_LOG_LEVEL` controls verbosity (default `INFO`)

**Tracing** (`hal/tracing.py`):

- OpenTelemetry spans wrap each REPL turn, intent classify call, LLM call, and tool call
- OTLP HTTP export to `OTLP_ENDPOINT` (default `http://localhost:4318`)
- No-op if `opentelemetry` packages not installed or endpoint unreachable
- OpenTelemetry traces exported to Grafana Tempo via OTLP HTTP (port 4318). See [OPERATIONS.md](OPERATIONS.md) for deploy and verification steps.

**Metrics** (`hal/prometheus.py`):

- In-memory accumulators (`_counters`, `_gauges`) updated throughout a turn
- `flush_metrics()` batches all metrics into a single Pushgateway POST at turn end
- Background heartbeat thread (`start_metrics_heartbeat()`) pushes every 30 seconds
- `HAL_INSTANCE` label partitions laptop vs. server metrics in Grafana
- No-op if `PROM_PUSHGATEWAY` is not set

Metric names: `hal_requests_total{intent, outcome}`, `hal_request_latency_seconds{intent}`,
`hal_tool_calls_total{tool, outcome}`

---

## Knowledge base pipeline

```text
harvest/collect.py — collectors:
  collect_ground_truth()         → knowledge/*.md — highest-priority hand-written lab docs
  collect_docker_containers()    → 1 doc per running container
  collect_system_state()         → disk, memory, listening ports, services, Ollama models
  collect_hardware()             → CPU, GPU, RAM, storage (static)
  collect_config_files()         → /opt/homelab-infrastructure/ YAML + Prometheus configs
  collect_systemd_units()        → Ollama + pgvector-kb-api unit files
  collect_static_docs()          → /data/orion/orion-data/documents/raw (subdirs = categories)

harvest/ingest.py — pipeline:
  clear_lab_docs()               → DELETE lab-infrastructure + lab-state categories
  clear_ground_truth()           → DELETE ground-truth category
  For static docs: incremental — content-hash comparison per file;
    only changed files are re-embedded; orphan rows cleaned automatically
  _chunk(text, CHUNK_SIZE, CHUNK_OVERLAP)         — see constants in harvest/ingest.py
  OllamaClient.embed(chunk)      → vector via configured embed model
  upsert to pgvector             → ON CONFLICT for idempotence

Scheduled: harvest.timer fires at 3:00am daily (Persistent=true)
Manual:    python -m harvest
Dry run:   python -m harvest --dry-run
```

Table: `documents` — columns: `content`, `embedding`, `category`, `file_name`,
`file_path`, `file_type`, `metadata`, `chunk_index`, `doc_tier`.

---

## Security stack

Four workers in `hal/security.py`, all Judge-gated, all optional (fail gracefully if the
underlying tool is absent):

| Tool | Source | Tier | What it returns |
|---|---|---|---|
| `get_security_events` | Falco — `/var/log/falco/events.json` | 0 | Recent eBPF behavioral events, noise-filtered |
| `get_host_connections` | Osquery — `sudo osqueryi` | 0 | Listening ports, established connections, and ARP cache |
| `get_traffic_summary` | ntopng — Community REST API at `:3000` | 0 | Top talkers, protocol breakdown |
| `scan_lan` | Nmap — XML output (`-oX -`) | 1 | LAN host inventory (requires approval) |

**Falco noise filter:** `is_falco_noise()` from `hal/falco_noise.py` suppresses known false
positives (e.g., `unix_chkpwd`, `pg_isready` reading `/etc/shadow`). Rules live in
`NOISE_RULES` as `(proc_name, fd_name_substring)` data tuples — add new entries there.
Do not suppress rules globally in Falco config.
