# Roadmap

What's built, what's next, and where this is going.

---

## Done

### Feb 22, 2026 — Foundation
- Terminal REPL with session memory (SQLite)
- Embedding-based intent classifier — routes conversational / health / fact / agentic
- pgvector knowledge base — ~2,300 chunks at the time, lab configs and state
- Agentic tool loop with Judge gating (tier 0–3), audit log, reason tokens
- SSH executor (localhost detection — no self-SSH on the server)
- Prometheus health queries + ntfy watchdog alerts
- `conversational` category added to intent classifier — prevents greetings from hitting the agentic path

### Feb 23, 2026 — vLLM, security stack, KB expansion
- Switched from Ollama chat → vLLM (Qwen2.5-32B-Instruct-AWQ via OpenAI-compatible API)
- `OLLAMA_NUM_GPU=0` enforced — gives vLLM full 24 GB VRAM
- Security stack: Falco eBPF, Osquery, ntopng Community, Nmap — all wired into agentic loop
- `hal/security.py` — four security workers, Judge-gated, noise-filtered
- Harvest pipeline: `collect_static_docs()` — 727 docs, 17,657 chunks ingested
- Nightly harvest timer deployed (`harvest.timer`, 3:00am, `Persistent=true`)
- KB search threshold raised to 0.45, top_k raised to 8
- Session history poison filter + `prune_old_turns(days=30)` — resolves RC3
- 96 new unit tests for Judge and MemoryStore
- Eval harness: 24 queries, 5 evaluators, baselines established

### Feb 23, 2026 — Trust hardening
- NTFY_URL configured — watchdog alerts now delivered
- Intent classifier `conversational` category expanded to 30 examples
- Intent test suite expanded to 35 tests
- Agent loop integration tests (10 tests, all mocked)
- `PlannerAgent` + `CriticAgent` sub-agents — tool-less LLM wrappers

### Feb 23, 2026 — KB quality and session 4
- Static docs ingested: 727 documents, 17,657 chunks from `/data/orion/orion-data/documents/raw`
- `collect_static_docs()` + `clear_static_docs()` added to harvest pipeline
- Fixed `harvest/main.py` `OllamaClient` args bug (harvest was crashing on every run)
- Agentic KB seeding threshold raised to 0.75 — only strong matches seed context

### Feb 24, 2026 — Observability and cleanup
- Removed Agent Inspector dead code — `HalAgent`, `agentdev`, `debugpy`, `agent-framework-core`
- `hal/server.py` FastAPI HTTP server — `/chat` + `/health` endpoints
- `hal/trust_metrics.py` — audit log parser + `get_action_stats` tool
- `hal/logging_utils.py` — structured JSON logging with contextvars for session correlation
- OTel tracing (`hal/tracing.py`) — spans for each turn, intent classify, LLM call, tool call
- Prometheus Pushgateway deployed (port 9092) — `hal_requests_total`, latency, tool calls
- Metrics accumulator fix — `flush_metrics()` batches all metrics per turn in one POST
- Background heartbeat thread — pushes metrics every 30 seconds
- `HAL_INSTANCE` grouping key for per-host Grafana filtering
- Grafana HAL dashboard — 6 panels, 30s refresh, auto-provisioned
- Ruff linter enforced via pre-commit hook
- Test count: 147 (35 intent + 112 offline)

---

## Backlog (immediate)

- **Falco noise filter:** Add `systemd-userwork` + `/etc/shadow` to `_FALCO_NOISE` in `hal/security.py`
- **Eval re-run:** Baseline predates security tools, prompt rewrite, and KB expansion — run `python -m eval.run_eval && python -m eval.evaluate --skip-llm-eval` on server
- **Swap investigation:** 7.3G/8G swap used despite 49G RAM free (Feb 21 2026) — root cause unknown
- **Grafana Tempo:** `hal/tracing.py` emits OTel spans but no receiver is deployed — deploy Tempo container in monitoring stack
- **Integration tests:** Zero coverage on SSH executor, pgvector search, HTTP server, security tools — these all require live services but should have smoke tests

---

## Architectural backlog (Path C — stop hardcoding lab-specific values)

The architecture is clean and generic. The implementation has five lab-specific hardcodings
that should be externalized so HAL can redeploy on a second machine without source edits:

1. **Template the system prompt** from `Config` fields — lab host, services, ports are
   currently baked into `hal/main.py:SYSTEM_PROMPT` as string literals. They should be
   dynamically constructed from `config.py` so the system prompt is always accurate.

2. **Externalize Judge patterns** — `_CMD_RULES`, `SENSITIVE_PATHS`, and the safe command
   whitelist in `hal/judge.py` are Python dicts in source. Move them to `hal/judge_rules.py`
   or a config section so they can be tuned per deployment without touching shared code.

3. **Remove hardcoded defaults** from `config.py` — `192.168.5.10`, `jp`, and absolute paths
   should not be in code defaults. If `.env` is missing, fail loudly rather than silently
   connecting to a different machine's IP.

4. **Pluggable harvest collectors** — `harvest/collect.py` collectors use hardcoded command
   formats, absolute paths, and parse Fedora/systemd-specific output. Abstract the interface
   so collectors can register by name and fail gracefully if the underlying tool is absent.

---

## End state — what makes this genuinely impressive

The current system can detect and answer. It cannot yet act autonomously within a trust
envelope and report what it did. That's the line between "assistant" and "agent."

**Five capabilities that cross the line:**

### 1. Autonomous remediation with trust accounting

HAL observes a container crash-loop, diagnoses it (reads logs), restarts it (tier 1
auto-approved because it's a known-safe action for this service based on N clean prior runs),
verifies it recovered, and sends a summary. The key: it tracks action outcomes and adjusts
which actions are auto-approved over time.

`trust_metrics.py` + `audit.log` already have all the raw material for the trust side.
The missing piece: a feedback mechanism that records whether an action *succeeded* (not just
whether it was *approved*), and a policy that adjusts tier thresholds based on the success
rate.

### 2. Temporal awareness

"What changed since Tuesday?" across all layers — Docker, systemd, files, KB, Prometheus.

This requires HAL to know what state looked like at time T. The harvest pipeline already
produces timestamped snapshots. The missing piece: a diff query that compares the current
KB snapshot against the previous one and surfaces meaningful changes.

### 3. Proactive pattern detection

The watchdog fires on thresholds. A better version: HAL notices that disk on /docker is
growing at the same rate it was before the last runout, and tells you before the alert fires.

This is trend detection over Prometheus data — not ML, just range queries and rate
calculations. A `get_trend` tool wrapping PromQL range queries would cover most cases.

### 4. Post-incident synthesis

After something goes wrong, HAL reconstructs the timeline from its audit log, Prometheus,
Falco events, and session history, and writes a brief post-mortem.

All the raw material exists. The missing piece: a `/postmortem <incident-description>`
command that invokes the agent loop with a specific system prompt framing the task as
"reconstruct and synthesize the timeline."

### 5. Trust evolution

Trust tiers are currently static (assigned by pattern). The adult version: tiers are earned
and revoked based on outcomes.

A service that HAL has safely restarted 20 times should get automatic tier-0 restart
approval. A command that failed twice should drop to tier 2 and require re-approval. This
is directly computable from `audit.log` + outcome recording — `trust_metrics.py` already
parses the log; it just needs outcome tracking wired in.

---

## Long-horizon vision

See [ARCHITECTURE.md](ARCHITECTURE.md) for the agent hierarchy and full home scope.

The short version: HAL grows from a single-machine coordinator into the autonomous
intelligence of the entire home — infrastructure, network, security, home automation, and
software development. The routing layer, Judge, and memory systems are designed to extend
to multi-agent use, not be replaced by it. The next named agent after trust evolution is
probably **Architect** — a sub-agent that can propose and implement changes to HAL's own
codebase via the existing eval/audit infrastructure.
