# HAL Autonomy Implementation Plan

> **Purpose:** This document is a phased implementation plan for making HAL
> a self-aware, self-healing agent. Each phase is a self-contained prompt
> designed for a fresh chat window. A new session should be able to read
> the preamble + one phase section and implement it without needing the
> full conversation history that produced this plan.
>
> **Created:** 2026-03-04 — based on the end-state vision in ROADMAP.md
> (capability #1: autonomous remediation with trust accounting) and the
> boot-order fix that landed in commit c7095b6.
>
> **Relationship to end-state:** ROADMAP.md defines five capabilities that
> cross the line from "assistant" to "agent." Three are delivered (#2–#4).
> This plan implements #1 (autonomous remediation) and completes #5 (trust
> demotion). Together they close the last gap.

---

## How to use this file

### Starting a phase

1. Open a **new chat window** (fresh context).
2. Paste the **Preamble** section below — it gives the AI enough project
   context to work without re-auditing the codebase.
3. Paste the **Phase N** section you want to work on.
4. Work through the items. Each item follows CLAUDE.md format: root cause →
   proposal → approval → implement → test → commit.

### Tracking progress

Each item has a checkbox. Update this file as you go:

- `[ ]` — not started
- `[~]` — in progress / partially done
- `[x]` — done (include commit hash)
- `[!]` — needs revision (add a note explaining what changed)

### Updating the plan

If implementation reveals that a later phase needs to change:

1. Mark the affected item with `[!]`.
2. Add a `> **Revision (date):**` blockquote under the item explaining
   what changed and why.
3. Do NOT delete the original text — future sessions need to see what was
   planned vs. what actually happened.

---

## Preamble — paste this into every new chat

```text
You are working on Orion, a homelab AI assistant at /home/jp/orion.

Key docs (read before changing anything):
- CLAUDE.md — required format before every code change (proposal → approval → implement)
- ARCHITECTURE.md — component map, data flow
- ROADMAP.md — end-state vision, what's done
- CONTRIBUTING.md — git workflow, test commands

Architecture summary:
- Chat LLM: VLLMClient → vLLM port 8000 → Qwen2.5-32B-Instruct-AWQ
- Embeddings: OllamaClient → Ollama port 11434 → nomic-embed-text (CPU only, GPU=0)
- Intent routing: IntentClassifier → dispatch_intent() in hal/bootstrap.py
  - "conversational" → _handle_conversational() (single LLM call, no tools)
  - everything else → run_agent() (full tool loop, KB + Prometheus pre-seeded)
- Judge (hal/judge.py): tier 0-3 policy gate, audit log at ~/.orion/audit.log
  - Trust overrides: _load_trust_overrides() promotes tier 1 → 0 after ≥10 samples, ≥90% success
  - record_outcome() writes success/error to audit log
- Server (hal/server.py): FastAPI on port 8087, ServerJudge auto-denies tier 1+
  - _retry_init() background task: retries setup_clients() every 15s for 10min on degraded start
- Watchdog (hal/watchdog.py): runs every 5min via systemd timer, checks thresholds + trends,
  sends ntfy alerts. Does NOT take remediation actions — alert only.
- Telegram (hal/telegram.py): polls Telegram API, POSTs to /chat endpoint
- Server: the-lab (192.168.5.10), Fedora 43, RTX 3090 Ti, user systemd services

Commands:
  pytest tests/ --ignore=tests/test_intent.py -v    # offline tests (~4s)
  ruff check hal/ tests/                              # lint
  git commit uses pre-commit hooks (ruff, format, markdownlint, mypy, doc-drift)
  git push runs pre-push hooks (full pytest with coverage)

Current test count: 681 offline tests passing.

You are implementing one phase of the HAL autonomy plan.
Read notes/hal-autonomy-plan.md for full context, then work on the specific
phase you are given.
```

---

## Phase A — Boot and Recovery Awareness

**Goal:** HAL knows when it recovered from a degraded start and can report
it. This is the perception layer — HAL gains awareness of its own lifecycle
events without taking any new actions.

**Estimated effort:** 1 session

**Prerequisites:** Boot-order fix (commit c7095b6) — `_retry_init()` in
`hal/server.py` already retries backend connections. This phase adds
awareness on top of that plumbing.

### Items

- [x] **A1 — Persist recovery events** (`d4273db`)

  When `_retry_init()` succeeds (backends come up after degraded start),
  write a structured event to `~/.orion/audit.log` using the existing
  `Judge._log()` JSON format. Fields: `ts`, `action: "system"`,
  `detail: "recovered_from_degraded_start"`, `status: "auto"`,
  `tier: 0`, `reason: "backends connected on attempt N after Xs"`.

  Files to change: `hal/server.py` (inside `_retry_init()`, after
  `_populate_state()` succeeds).

  The write should use the same JSON-lines format as `Judge._log()` but
  does NOT need to go through the Judge — it's a system lifecycle event,
  not an action needing approval. Write directly to `AUDIT_LOG` path
  imported from `hal/judge.py`.

  Tests: verify the audit log entry is written with correct fields.

- [x] **A2 — Surface recovery in /health endpoint** (`cc9a9d3`)

  Extend the `/health` response to include a `last_recovery` field when
  the server recovered from degraded mode. Store the recovery timestamp
  and attempt count in `_state` (set by `_retry_init()` on success).
  `/health` returns `{"status": "ok", "last_recovery": "2026-03-04T20:15:00", "recovery_attempts": 3}`
  when applicable, or plain `{"status": "ok"}` on clean starts.

  Files to change: `hal/server.py` — `_retry_init()` and `health_check()`.

  Tests: mock a degraded→recovered transition, verify /health output.

- [x] **A3 — Proactive Telegram notification on recovery** (`33d4ca3`)

  After `_retry_init()` succeeds and `_populate_state()` clears the
  degraded flag, send a one-shot notification via Telegram (if configured)
  or ntfy (existing `_send_ntfy_simple` pattern from watchdog).

  Design choice: use ntfy (simpler — watchdog already does this). Import
  the `_send_ntfy_simple()` function from `hal/watchdog.py` or refactor
  it into a shared utility. Prefer refactoring to a `hal/notify.py` module
  since both watchdog and server will use it.

  Files to change: create `hal/notify.py` (extract from watchdog),
  update `hal/watchdog.py` to import from it, update `hal/server.py`
  to send notification on recovery.

  Config: uses existing `NTFY_URL` from config.

  Tests: mock ntfy POST, verify notification sent on recovery with
  correct title/tags/content.

- [x] **A4 — Include recovery context in system prompt** (`f4ceab5`)

  When the server recovered from a degraded start, inject a brief note
  into the system prompt context so HAL can answer "what happened?" or
  "did anything go wrong on startup?" accurately.

  Approach: add a `_startup_context` string to `_state` (set by
  `_retry_init()` on success — e.g. "Note: this server recovered from
  a degraded start at 20:15 UTC after 3 retry attempts (backends were
  unavailable for ~45 seconds)."). Pass it through to `get_system_prompt()`
  or append it in the `/chat` handler.

  Files to change: `hal/server.py` — set context on recovery; either
  extend `get_system_prompt()` in `hal/bootstrap.py` to accept an
  optional `startup_note` kwarg, or append it in the `_run()` closure.

  Tests: verify the context string appears when recovery occurred and
  is absent on clean starts.

---

## Phase B — Structured Health Validation

**Goal:** HAL can run a structured health check across all its components
and report the results. This is the diagnostic layer — HAL can answer "is
everything actually working?" with evidence, not just "the port is open."

**Estimated effort:** 1–2 sessions

**Prerequisites:** Phase A completed (recovery awareness).

### Items

- [x] **B1 — Define component health contracts**

  Create `hal/healthcheck.py` with a `ComponentHealth` dataclass and a
  registry of health check functions. Each check returns a structured
  result: `(component_name, status: ok|degraded|down, detail: str, latency_ms: float)`.

  Components to check:
  - **vLLM**: `GET /health` + `GET /v1/models` (model name matches config)
  - **Ollama**: `GET /api/tags` (nomic-embed-text present)
  - **pgvector**: `SELECT 1` via psycopg + chunk count query
  - **Prometheus**: `GET /-/ready`
  - **Docker containers**: `docker ps --format` — compare running set against
    `CRITICAL_CONTAINERS` from watchdog.py
  - **Pushgateway**: `GET /-/ready`
  - **Grafana**: `GET /api/health`
  - **ntopng**: `GET /lua/rest/v2/get/ntopng/interfaces.lua` or similar

  Each check must have a timeout (5s default) and catch all exceptions
  (never crash the health check itself).

  Files to create: `hal/healthcheck.py`.

  Tests: mock each endpoint, verify structured results for ok/degraded/down.

- [x] **B2 — `check_system_health` tool**

  Register a new tool in `hal/tools.py` that calls the health check
  registry from B1 and returns a formatted summary. Judge tier 0 (read-only).

  The tool should return a human-readable table-like format:
  ```
  Component     | Status   | Detail
  vLLM          | ok       | Qwen2.5-32B-Instruct-AWQ loaded (142ms)
  Ollama        | ok       | nomic-embed-text available (23ms)
  pgvector      | ok       | 19,847 chunks (31ms)
  Prometheus    | ok       | ready (12ms)
  Containers    | degraded | ntopng-redis exited (0ms)
  ```

  Add to TOOL_REGISTRY, add intent examples for "is everything working",
  "system health check", "are all services up".

  Files to change: `hal/tools.py`, `hal/intent.py` (examples).

  Tests: mock health checks, verify tool output format.

- [x] **B3 — Post-boot auto-check**

  When `_retry_init()` succeeds (Phase A recovery path), automatically run
  the health check suite from B1. Include the results in the ntfy
  notification from A3 and in the startup context from A4.

  This gives the operator a single notification: "HAL recovered after 45s.
  All 8 components healthy." or "HAL recovered but pgvector is degraded."

  Files to change: `hal/server.py` — call health checks after
  `_populate_state()` in `_retry_init()`.

  Tests: mock recovery + health checks, verify combined output.

- [x] **B4 — Extend watchdog with deep health checks**

  Add the B1 health check suite as a new `_check_component_health()`
  function in the watchdog's simple_checks list. This runs every 5 minutes
  and alerts if any component is degraded or down (beyond just container
  exit status, which `_check_containers` already covers).

  This replaces the current `_check_containers()` check with a superset.
  Keep `_check_containers()` as a fallback if Docker is unreachable.

  Files to change: `hal/watchdog.py`.

  Tests: mock health checks, verify watchdog fires alerts for degraded
  components.

---

## Phase C — Recovery Playbooks

**Goal:** HAL can diagnose a problem and execute a pre-approved recovery
sequence. This is the action layer — HAL crosses the line from "I see a
problem" to "I fixed it."

**Estimated effort:** 2–3 sessions

**Prerequisites:** Phase B completed (structured health checks provide the
detection mechanism that triggers recovery).

### Items

- [ ] **C1 — Define playbook data model**

  Create `hal/playbooks.py` with a `RecoveryPlaybook` dataclass:

  ```python
  @dataclass
  class RecoveryStep:
      description: str           # human-readable step description
      command: str               # shell command to execute
      verify_command: str        # command to verify the step succeeded
      verify_expect: str         # expected substring in verify output
      timeout: int = 30          # seconds

  @dataclass
  class RecoveryPlaybook:
      name: str                  # e.g. "restart_pgvector"
      component: str             # matches ComponentHealth.name from B1
      trigger: str               # "down" or "degraded"
      description: str           # human-readable description
      judge_tier: int            # what tier this recovery needs
      max_attempts_per_hour: int # circuit breaker
      steps: list[RecoveryStep]
  ```

  Define playbooks for:
  - `restart_pgvector`: `docker restart pgvector-kb` → verify `SELECT 1`
  - `restart_prometheus`: `docker restart prometheus` → verify `/-/ready`
  - `restart_grafana`: `docker restart grafana` → verify `/api/health`
  - `restart_pushgateway`: `docker restart pushgateway` → verify `/-/ready`
  - `restart_ntopng`: `docker compose -f ... restart ntopng` → verify API
  - `restart_ollama`: `sudo systemctl restart ollama` → verify `/api/tags`
  - `restart_vllm`: `systemctl --user restart vllm` → verify `/health`

  Each playbook declares its own `judge_tier`. Docker container restarts
  start at tier 1 (reversible). vLLM restart is tier 1 (user systemd).
  Ollama restart is tier 2 (system systemd, needs sudo).

  Files to create: `hal/playbooks.py`.

  Tests: validate playbook structure, verify all referenced components
  exist in the health check registry from B1.

- [ ] **C2 — Playbook executor with circuit breaker**

  Add `execute_playbook()` to `hal/playbooks.py`:
  1. Check circuit breaker (max N attempts per hour per playbook, tracked
     in `~/.orion/recovery_state.json`)
  2. Submit each step's command to Judge for approval
  3. Execute via SSHExecutor (or subprocess for local)
  4. Run verify_command after each step
  5. Record outcome via `judge.record_outcome()`
  6. Return structured result: `(success: bool, steps_completed: int, detail: str)`

  The circuit breaker file tracks: `{playbook_name: [iso_timestamps]}`.
  Before executing, prune timestamps older than 1 hour and check count.

  Files to change: `hal/playbooks.py`.

  Tests: mock executor, verify step sequencing, circuit breaker enforcement,
  outcome recording.

- [ ] **C3 — Wire playbooks into watchdog**

  After `_check_component_health()` (from B4) detects a degraded/down
  component, look up matching playbooks and execute them. This is the
  autonomous remediation loop:

  ```
  detect (B4) → match playbook (C1) → execute (C2) → verify → notify
  ```

  Important constraints:
  - Only execute playbooks where `judge_tier <= 1` automatically (tier 0
    and tier 1 with trust override). Higher tiers log a suggestion but
    do not auto-execute.
  - The watchdog already has a cooldown mechanism — recovery attempts
    should respect the same cooldown (don't retry a restart every 5min).
  - On success: send ntfy "RECOVERED" notification.
  - On failure: send ntfy "RECOVERY FAILED" notification with detail.
  - All actions logged to audit log.

  Files to change: `hal/watchdog.py`.

  Tests: mock health checks returning "down" for a component, verify
  playbook execution path, verify cooldown respected, verify notification.

- [ ] **C4 — `recover_component` tool for interactive use**

  Register a tool that lets the operator (or HAL via the agent loop)
  trigger a specific playbook interactively:

  ```
  User: "pgvector seems down, can you fix it?"
  HAL: [calls check_system_health → confirms pgvector down]
       [calls recover_component(component="pgvector")]
       "I restarted pgvector-kb. Health check confirms it's back up
        with 19,847 chunks. The outage lasted about 2 minutes."
  ```

  This is the same `execute_playbook()` from C2, exposed as a tool.
  Judge tier: inherits from the playbook definition.

  Files to change: `hal/tools.py`.

  Tests: mock playbook execution, verify tool output.

- [ ] **C5 — Trust demotion (ROADMAP end-state #5 completion)**

  Currently `_load_trust_overrides()` only promotes (tier 1 → 0). Add
  demotion: if a trust key's success rate drops below 70% (configurable)
  with ≥10 samples, revoke the override (restore original tier).

  This closes the feedback loop: a recovery playbook that keeps failing
  loses its auto-approval privilege.

  Files to change: `hal/judge.py` — `_load_trust_overrides()`.
  Config: `TRUST_DEMOTION_RATE` in `hal/config.py` (default 0.70).

  Tests: verify demotion at 70%, verify re-promotion after recovery.

---

## Phase D — Autonomous Remediation Loop (Integration)

**Goal:** Wire everything together into the end-state described in
ROADMAP.md: "HAL observes a container crash-loop, diagnoses it, restarts
it, verifies recovery, and sends a summary."

**Estimated effort:** 1 session

**Prerequisites:** Phases A–C completed.

### Items

- [ ] **D1 — End-to-end integration test**

  Write a full-circuit integration test that simulates:
  1. Server starts in degraded mode (backends unavailable)
  2. Backends come up → `_retry_init()` succeeds
  3. Recovery event logged, ntfy sent, health check runs
  4. Later: pgvector goes down
  5. Watchdog detects it via component health check
  6. Playbook matched, executed, verified
  7. Recovery notification sent
  8. User asks "what happened?" → HAL's context includes both events

  This is a scripted test with mocked externals — no real Docker/systemd.
  Uses the "Scripted LLM" pattern from the integration test plan.

  Files to create: `tests/test_autonomy_integration.py`.

- [ ] **D2 — Update ROADMAP.md end-state section**

  Mark capability #1 (autonomous remediation) as delivered. Update the
  description to reflect the actual implementation: health check registry,
  playbook system, circuit breaker, trust demotion.

  Update capability #5 to note demotion is now implemented.

  Files to change: `ROADMAP.md`.

- [ ] **D3 — Update system prompt**

  Add a section to the system prompt (in `hal/bootstrap.py`) that
  describes HAL's self-healing capabilities so the LLM knows what it
  can do:

  ```
  ── SELF-HEALING ──
  You can detect and recover from component failures automatically:
  • check_system_health — structured health check across all components
  • recover_component — trigger a recovery playbook for a failed component
  Recovery playbooks are pre-approved sequences (restart → verify → report).
  Circuit breaker: max N attempts/hour per component. Trust-evolved actions
  auto-execute; others require operator approval.
  ```

  Files to change: `hal/bootstrap.py`.

- [ ] **D4 — Eval queries for autonomy**

  Add eval queries to `eval/queries.jsonl` covering the new capabilities:
  - "is everything working?" → should use `check_system_health`
  - "can you restart pgvector?" → should use `recover_component`
  - "what happened on startup?" → should reference recovery context

  Files to change: `eval/queries.jsonl`, possibly `eval/evaluate.py`
  for new evaluator functions.

---

## Dependency Graph

```
Phase A (awareness)
  ├─ A1: recovery event logging
  ├─ A2: /health endpoint extension
  ├─ A3: ntfy notification ──────────────┐
  └─ A4: system prompt context           │
                                         │
Phase B (diagnostics)                    │
  ├─ B1: health check registry           │
  ├─ B2: check_system_health tool        │
  ├─ B3: post-boot auto-check ───────────┘ (uses A3 + B1)
  └─ B4: watchdog deep health checks
                                         │
Phase C (action)                         │
  ├─ C1: playbook data model             │
  ├─ C2: playbook executor ──────────────┘ (uses B1 for verification)
  ├─ C3: watchdog auto-recovery (uses B4 + C2)
  ├─ C4: recover_component tool
  └─ C5: trust demotion
                                         │
Phase D (integration)                    │
  ├─ D1: end-to-end test ───────────────── (validates A–C)
  ├─ D2: update ROADMAP.md
  ├─ D3: update system prompt
  └─ D4: eval queries
```

---

## Revision Log

> Track plan changes here. Each entry should reference the item ID that
> changed and which chat session made the change.

(No revisions yet.)
