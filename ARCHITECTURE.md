# Architecture

This document describes Orion's components, data flow, and the design decisions behind them.

---

## Component map

```text
You  (terminal REPL, HTTP server, Telegram bot)
 └─ hal/main.py  [session manager, Rich console, readline history]
      └─ IntentClassifier  [embedding similarity, threshold 0.65, one embed call per query]
            │
            ├── conversational                → _handle_conversational()  — single LLM call, no tools, no KB
            └── health | fact | agentic       → run_agent()               — full tool loop, up to 8 LLM iterations
                                        │  (KB + Prometheus pre-seeded before iteration 0)
                                        │
                     ┌──────────────────┼──────────────────────┐
                     ▼                  ▼                      ▼
               VLLMClient          KnowledgeBase           SSHExecutor
               (chat+tools)        (pgvector)              (runs commands)
                     │                                         │
                     └──────────────── Judge ─────────────────┘
                                  (gates every action)

Supporting components:
  OllamaClient  — embeddings only (never chat); feeds IntentClassifier + KnowledgeBase
  MemoryStore   — SQLite session turns at ~/.orion/memory.db; loaded into context on start
  PrometheusClient — PromQL queries for live metrics + Pushgateway metric push
  SSHTunnel     — port-forwards lab services when running from a laptop (USE_SSH_TUNNEL=true)

HTTP layer (hal/server.py):
  FastAPI server — /chat (POST) + /health (GET); ServerJudge auto-denies tier 1+
  Used by: Web UI, Telegram bot, external integrations
  Serves static web UI at GET / (hal/static/ — vanilla JS, marked.js, highlight.js)

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
  → MemoryStore loads last N turns into context (TURN_WINDOW=40)
  → IntentClassifier embeds query via Ollama (nomic-embed-text)
      → cosine_similarity vs. example sentences per category (13–41 per category; fact: 13, health: 23, conversational: 30, agentic: 41)
      → best score ≥ 0.65 → route to that handler
      → best score < 0.65 → default to agentic (safe fallback)

  conversational path:
      → VLLMClient.chat(system_prompt + history + query)
      → response rendered to terminal
      → turn saved to MemoryStore

  run_agent path (all non-conversational intents):
      → KnowledgeBase.search(query, threshold=0.75) → inject matching chunks as context
      → PrometheusClient queries live metrics snapshot → inject as context
        (both pre-seeds happen before iteration 0; simple queries resolve from context
         without issuing any tool calls)
      → loop up to MAX_ITERATIONS=8:
            VLLMClient.chat_with_tools(history + tools_schema)
            if tool_calls:
                for each call:
                    Judge.approve(tool, args) → tier 0: auto / tier 1+: prompt
                    if approved:
                        result = _dispatch(tool_call, executor, judge, kb, prom)
                        cap result at 8000 chars
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

**Tier assignment (first match wins):**

1. Fixed action types: `search_kb` → 0, `write_file` → 2, etc.
2. Dangerous shell patterns → 3: `rm -rf`, `drop table`, `mkfs`, `dd if=`, fork bombs
3. Config-level patterns → 2: `docker run`, `systemctl enable/disable`, `chmod 777`, `ufw`
4. Restart/stop/start patterns → 1: `docker restart`, `systemctl restart`, etc.
5. Safe command whitelist → 0: `ps`, `cat`, `df`, `ls`, `grep`, `journalctl`, `ping`, etc.
6. Safe compound prefixes → 0: `systemctl status`, `docker ps/logs/inspect`, etc.
7. Sensitive paths escalate tier by 1: `.env`, `~/.ssh`, `/run/homelab-secrets`, `/etc/shadow`
8. Default → 1 (unknown command requires approval)

**Why is the sensitive path check a tier bump instead of a tier set?**

Because `cat ~/.ssh/known_hosts` (safe command + sensitive path) should be tier 1, not
auto-approved. But `rm -rf ~/.ssh/` (destructive + sensitive path) should stay tier 3.
Adding 1 to the current tier preserves the relative risk ordering.

---

## Agent loop — design rationale

**Loop constraints:**

- `MAX_ITERATIONS=8` — prevents infinite loops when the model keeps calling tools
- `MAX_TOOL_CALLS=5` — caps unique tool dispatches per turn; the loop stops when either limit is reached
- `8000 char` output cap per tool result — prevents context explosion from verbose tools
- Dedup guard — if the model calls the same `(tool, args)` twice in one turn, the second
  call is skipped and a synthetic message is injected ("you already have this data")
- Empty tools list on final iteration — forces a text response if 7 iterations elapsed
  without one

**Why not run the LLM in streaming mode for tool calls?**

Tool calls require parsing the full structured response. Streaming the model output while
also parsing tool call JSON from it is complex and fragile. Batch responses are simpler and
correct. The UX trade-off is acceptable for a terminal REPL.

**KB seeding threshold (0.75):**

All queries entering `run_agent()` use a 0.75 cosine-similarity threshold for KB pre-seeding.
Only strong matches are injected as context before iteration 0. A lower threshold pulled in
marginally-relevant docs and added noise to the first iteration; 0.75 keeps the pre-seed
high-signal. If no chunk clears the threshold, the loop starts without KB context and the
model can issue a `search_kb` tool call if it determines one is needed.

---

## LLM backend split

HAL uses two separate LLM backends with completely distinct roles. **This split is
non-negotiable** — Ollama with GPU access consumes ~800 MB VRAM, causing vLLM to OOM
during inference on the RTX 3090 Ti.

| Client | Backend | Role | Model |
|---|---|---|---|
| `VLLMClient` | vLLM at `VLLM_URL` (port 8000) | All LLM inference — chat, reasoning, tool calls | `Qwen/Qwen2.5-32B-Instruct-AWQ` |
| `OllamaClient` | Ollama at `OLLAMA_HOST` (port 11434) | Embeddings **only** — intent classification + KB search | `nomic-embed-text:latest` |

`OLLAMA_NUM_GPU=0` is set in Ollama's systemd override. Do not remove it. Ollama is a
bare-metal systemd service — never manage it with Docker commands.

---

## Memory — design rationale

**SQLite for session turns, pgvector for facts and KB:**

Session turns (conversation history) are short-lived, structured, and need full-text search.
SQLite is fast, local, and has zero operational overhead. pgvector is for semantic search
over longer documents — session turns don't need cosine similarity.

**30-day pruning + 40-turn window:**

`prune_old_turns(days=30)` runs at every startup and deletes turns older than 30 days.
`TURN_WINDOW=40` caps how many turns are loaded into the context window per session.
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

- JSON format when `HAL_LOG_JSON=1` (default); plain text when `0`
- `session_id` and `trace_id` propagated via Python `contextvars`
- `HAL_LOG_LEVEL` controls verbosity (default `INFO`)

**Tracing** (`hal/tracing.py`):

- OpenTelemetry spans wrap each REPL turn, intent classify call, LLM call, and tool call
- OTLP HTTP export to `OTLP_ENDPOINT` (default `http://localhost:4318`)
- No-op if `opentelemetry` packages not installed or endpoint unreachable
- Grafana Tempo receiver not yet deployed (planned)

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
  collect_docker_containers()    → 1 doc per running container
  collect_system_state()         → disk, memory, listening ports, services, Ollama models
  collect_hardware()             → CPU, GPU, RAM, storage (static)
  collect_config_files()         → /opt/homelab-infrastructure/ YAML + Prometheus configs
  collect_systemd_units()        → Ollama + pgvector-kb-api unit files
  collect_static_docs()          → /data/orion/orion-data/documents/raw (subdirs = categories)

harvest/ingest.py — pipeline:
  clear_lab_docs()               → DELETE lab-infrastructure + lab-state categories
  clear_static_docs()            → DELETE all rows under /data/orion/... path
  _chunk(text, 800 chars, 100 overlap)
  OllamaClient.embed(chunk)      → 768-dim vector via nomic-embed-text
  upsert to pgvector             → ON CONFLICT for idempotence

Scheduled: harvest.timer fires at 3:00am daily (Persistent=true)
Manual:    python -m harvest
Dry run:   python -m harvest --dry-run
```

Table: `documents` — columns: `content`, `embedding`, `category`, `file_name`,
`file_path`, `metadata`, `chunk_index`.

---

## Security stack

Four workers in `hal/security.py`, all Judge-gated, all optional (fail gracefully if the
underlying tool is absent):

| Tool | Source | Tier | What it returns |
|---|---|---|---|
| `get_security_events` | Falco — `/var/log/falco/events.json` | 0 | Recent eBPF behavioral events, noise-filtered |
| `get_host_connections` | Osquery — `sudo osqueryi` | 0 | Active network connections from host perspective |
| `get_traffic_summary` | ntopng — Community REST API at `:3000` | 0 | Top talkers, protocol breakdown |
| `scan_lan` | Nmap — XML output (`-oX -`) | 1 | LAN host inventory (requires approval) |

**Falco noise filter:** `is_falco_noise()` from `hal/falco_noise.py` suppresses known false
positives (e.g., `unix_chkpwd`, `pg_isready` reading `/etc/shadow`). Rules live in
`NOISE_RULES` as `(proc_name, fd_name_substring)` data tuples — add new entries there.
Do not suppress rules globally in Falco config.
