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
- Eval harness: 40 queries, 7 code evaluators — baselines: intent 100%, no_raw_json 93.8%, hal_identity 96.9%, web_tool_accuracy 96.9% (Feb 23 2026); all four raised to 100% (Feb 26 2026)

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

### Feb 25, 2026 — Dev tooling

- `Makefile` — 6 targets: `lint`, `format`, `test`, `test-full`, `coverage`, `typecheck`
- `ruff format` enforced in CI and pre-commit hooks; applied to all 35 non-conformant files
- `mypy` added (warn-only, `continue-on-error` in CI) — baseline is 10 errors in 7 files
- `pre-commit` hooks: `ruff check --fix` + `ruff format` fire on every `git commit`
- `pytest-cov` — `make coverage` target; baseline 34% (2000 statements); memory.py 92%, trust_metrics.py 87%
- Test count: 186 (35 intent + 151 offline)

### Feb 25, 2026 — Monitoring improvements

- GPU monitoring via node-exporter textfile collector: `ops/gpu-metrics.sh` + systemd user timer (15s)
- Node-exporter fixed: `--path.rootfs=/rootfs` + `pid: host` — was returning zero filesystem metrics
- `/docker` and `/data/projects` disk monitoring added to `hal/prometheus.py` and `hal/watchdog.py`
- Container health check: `_check_containers()` monitors 5 critical containers (prometheus, grafana, pgvector-kb, ntopng, pushgateway)
- Recovery RESOLVED notifications: low-priority ntfy with ✅ tag when metrics/checks recover
- Falco proactive alerting: `_check_falco()` tails Falco JSON log, filters noise, alerts on high-priority security events
- `_send_ntfy_simple()` gains optional `title` and `tags` parameters
- System prompt rewritten with full operational awareness: automated tasks, watchdog thresholds, diagnostic guidance, KB tier model, complete service inventory, troubleshooting order
- `get_metrics` tool description updated to reflect all 9 metrics (was missing GPU, multi-disk)
- Test count: 363 (35 intent + 328 offline)

### Feb 24, 2026 — Telegram bot

- Telegram bot interface (`hal/telegram.py`) — thin async wrapper that POSTs to `/chat` HTTP endpoint
- Auth: single `TELEGRAM_ALLOWED_USER_ID` check; silently ignores unauthorized senders
- Session model: `tg-{chat_id}` deterministic session IDs; `/new` command resets with timestamp suffix
- UX: sends "thinking…" placeholder, edits with final response; output sanitised (secrets redacted, 4096 char limit)
- Polling mode (no webhook — no public HTTPS on the homelab)
- Inherits `ServerJudge` tier-0-only behaviour via the HTTP server — no new Judge subclass
- `MemoryStore.create_session(sid)` — accepts caller-chosen session IDs (used by Telegram, available to any HTTP client)
- `hal/server.py` session resolution updated — honours caller-provided `session_id` on first use
- `ops/telegram.service` — user systemd unit (`Type=simple`, `Restart=on-failure`, `RestartSec=15`)
- `python-telegram-bot>=21.0` added to `requirements.txt`
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USER_ID` added to `hal/config.py` and `.env.example`
- 17 offline tests in `tests/test_telegram.py` (sanitize, sessions, auth, commands, HTTP mocking)
- Test count: 164 (35 intent + 129 offline)

### Feb 25, 2026 — Web search (internet access Step 1)

- `hal/web.py` — `web_search()` via Tavily API with `sanitize_query()` privacy guard (strips RFC1918, loopback, Tailscale, private hostnames)
- Tool registry pattern: `_BASE_TOOLS` + `get_tools(*, tavily_api_key)` — conditional tool inclusion; LLM never sees disabled tools
- `web_search` tier 0 in Judge (read-only, audit-logged)
- 5 agentic intent examples for web search queries
- `TAVILY_API_KEY` in config + `.env.example`; `tavily-python>=0.5` in requirements
- 26 new tests in `tests/test_web.py` (sanitisation, mocked Tavily, tool registry)
- Test count: 389 (35 intent + 354 offline)

### Feb 25, 2026 — URL fetching with SSRF protection (internet access Step 2)

- `hal/web.py` — `fetch_url(url)` extracts article text from public URLs via `requests` + `trafilatura`
- `_validate_url()` SSRF protection: blocks non-HTTP(S) schemes, private/reserved IPs (literal + DNS-resolved), `.local`/`.internal`/`.localhost`/`.onion` TLDs, redirect-to-private
- DNS rebinding defence: `socket.getaddrinfo()` pre-resolves hostname; all returned IPs checked via `_is_private_ip()`
- Resource limits: 10s timeout, 1 MB response cap, 15 000 char output truncation
- `fetch_url` tier 1 in Judge (outbound HTTP to arbitrary URL, needs approval)
- Always in tool list (no API key); 3 agentic intent examples
- 34 new tests: IP classification, URL validation/SSRF, fetch+extract, tool registry
- Test count: 423 (35 intent + 388 offline)

### Feb 25, 2026 — Tool-call hallucination fix

- System prompt: two new RULES blocking tool-call simulation in prose and unbounded `web_search` for off-topic queries
- `hal/server.py`: `_strip_tool_call_blocks()` — output-layer guard strips hallucinated ` ```json {"name":...} ``` ` fences before the response reaches the user
- `hal/memory.py`: extended `is_poison_response()` — catches both bare-JSON tool dumps (existing) and embedded code-fence tool-call blocks (new); prevents hallucinated turns from persisting to SQLite
- Test count: 423 (35 intent + 388 offline) — all passing

### Feb 26, 2026 — Eval fixes, swap investigation, integration tests

- `hal/agent.py`: `_strip_tool_artifacts()` — strips bare `{"name":...,"arguments":...}` JSON leaked into prose after tool-loop exhaustion; applied inside `run_agent()` so all callers benefit
- `hal/main.py`: identity rule extended — explicitly forbids naming underlying model, provider, or company in addition to first-person claims
- `hal/main.py`: `web_search` permission strengthened to mandatory MUST directive for CVEs, vulnerabilities, release notes, version queries — with explicit date-authority statement to prevent training-data cutoff reasoning
- `OPERATIONS.md`: swap trap documented — `/dev/zram0` is compressed in-RAM swap (not disk); 75 Mi used is normal; investigation found no remediation needed
- Integration tests: `tests/test_knowledge.py` (13 tests, pgvector `KnowledgeBase.search()`), `tests/test_security.py` (17 tests, Falco/Osquery workers), `tests/test_executor.py` (+3, SSH executor), `tests/test_agent_loop.py` (+10, `_strip_tool_artifacts`), `tests/test_server.py` (+3, routing + fenced-block stripping)
- Test count: 486 → 530 (all offline, ruff clean)
- Eval re-run: all four code metrics 100% (40 queries as of Mar 6 2026)

### Feb 26, 2026 — Markdown linting toolchain

- `.markdownlint.jsonc` added — explicit rule config checked into version control; key decisions: MD013 disabled (long prose lines), MD024 disabled (duplicate Feb 23 headings in ROADMAP), MD046 fenced, MD060 spaced (matches `| --- |` table style used throughout)
- `markdownlint-cli2 v0.17.2` added as pre-commit hook — violations caught at `git commit`, not only in the VS Code Problems panel
- `make lint-md` target added to `Makefile` — wraps `pre-commit run markdownlint-cli2 --all-files`
- `CONTRIBUTING.md` updated: document markdown linting + `make lint-md`; add `lint-md` to both commit-readiness checklists; fix stale test counts (151/186 → 495/530); update eval baselines to Feb 26 100% figures; fix all MD031/MD032/MD040/MD060 violations surfaced by the new config
- Fixed all pre-existing MD022/MD031/MD032/MD060 violations in `ROADMAP.md` and `OPERATIONS.md`

### Feb 26, 2026 — Code review and structural refactor

Full two-pass review (structural + deep audit). 15 findings resolved (N1–N15, C-series):

- `hal/bootstrap.py` created — extracted `get_system_prompt()`, `setup_clients()`,
  `dispatch_intent()` from `main.py`; resolves `server.py → main.py` architectural inversion;
  intent dispatch no longer copy-pasted across three call sites
- `hal/sanitize.py` created — single implementation of tool-call stripping (`is_tool_call_artifact()`,
  `strip_tool_call_artifacts()`); deleted `_strip_tool_artifacts()` in `agent.py`,
  `_strip_tool_call_blocks()` in `server.py`, and inline logic in `memory.py`
- `hal/patterns.py` deleted — existed only to break a circular import; `TOOL_CALL_FENCE_RE`
  inlined where used
- `remember()` moved into `KnowledgeBase`; `hal/facts.py` deleted
- `ToolContext` NamedTuple introduced — tool handler context no longer passed as positional args
- Legacy pipe-format parser in `trust_metrics.py` deleted (N7)
- Bug fixes: null LLM args no longer crash `args.get()` (N4); SSH executor timeout set (N5);
  `_dispatch` shim removed (N6); import-time side-effects eliminated (N8)
- `_should_use_planner_critic()` added — short non-action queries skip two extra LLM calls
- `run_conversational` gains OTel span + latency telemetry to match other three handlers
- `MAX_TOOL_CALLS = 5` defined as module constant next to `MAX_ITERATIONS = 8`
- `config.py`: `OLLAMA_HOST`, `PGVECTOR_DSN`, `PROMETHEUS_URL` now raise `RuntimeError` on
  missing values — no more silent LAN-IP fallbacks
- Test count: 530 → 534 (all offline, ruff clean)

### Feb 26, 2026 — `get_trend` tool (end-state capability #3)

- `range_query()` added to `PrometheusClient` — wraps `/api/v1/query_range`; returns
  `(timestamp, value)` tuples; same defensive pattern as `query()`
- `trend()` added — takes a PromQL expression + window (`1h`/`6h`/`24h`); returns
  `{first, last, min, max, delta, delta_per_hour, direction}` over ~60 sampled points;
  direction is `rising`/`falling`/`stable` using 0.5%-of-range threshold
- `get_trend` tool added to `TOOL_REGISTRY` — 9 named metric shortcuts + `custom` PromQL
  mode; `_METRIC_PROMQL` dict is the single source of truth for metric→PromQL mapping;
  Judge tier 0 (read-only, same as `get_metrics`)
- 5 trend intent examples added to `agentic` classifier bucket — ensures trend questions
  route to the tool loop, not the health fast-path
- Test count: 534 → 544 (all offline, ruff clean)

### Feb 26, 2026 — `/postmortem` command (end-state capability #4)

- `hal/postmortem.py`: `gather_postmortem_context(description, window_hours, prom, executor, judge)`
  collects three evidence layers — audit log (non-trivial + denied events within window),
  Prometheus health snapshot + cpu/mem/disk_docker trends, Falco security events (noise-filtered).
  All layers wrapped in try/except; each returns `"unavailable"` on error rather than raising.
- `/postmortem <desc> [--hours N]` slash command in terminal REPL — default window 2h;
  prints `"Gathering evidence..."` status, calls `gather_postmortem_context()`, then
  invokes `run_agent()` with a postmortem-scoped system prompt override.
- Added to `/help` display alongside other slash commands.
- `tests/test_postmortem.py`: 8 offline tests covering window filtering, tier-0 denial
  inclusion, Prometheus error resilience, Falco error resilience (exception + error dict),
  usage guard, and `--hours` parsing.
- Test count: 544 → 552 (all offline, ruff clean)

### Feb 26–Mar 1, 2026 — Reliability layer, routing refactor, end-state capabilities

- **Track A routing refactor** — collapsed four dispatch paths into two:
  `conversational → _handle_conversational()` (no tools, no KB); everything else →
  `run_agent()` (full tool loop). KB context (≥0.75) and a live Prometheus snapshot pre-seeded
  at iteration 0 — simple health/fact queries resolve without a tool call; boundary queries
  have tools available. Deleted dead `_handle_health()` and `_handle_fact()` handlers.
- **Enforcement design v3** — ruff + ruff-format + markdownlint-cli2 + mypy pre-commit hooks
  enforced on every `git commit`; pre-push test run; `.github/workflows/test.yml` CI;
  doc-drift check in `scripts/check_doc_drift.py`
- **Trust metrics outcome tracking** — `record_outcome()` in `judge.py` writes success/error
  entries to `audit.log`; `_load_trust_overrides()` auto-promotes tier 1 → tier 0 for actions
  with ≥10 samples and ≥90% success rate; `trust_metrics.py` extended with `OutcomeEvent`,
  `load_outcome_log()`, and outcomes block in `get_action_stats()`
- **Proactive trend alerting** (end-state #3 complete) — `_check_trends()` in `watchdog.py`
  calls `prom.trend('1h')` for 6 metrics; fires ntfy when `direction=='rising'` and
  `delta_per_hour >= threshold`; four operator-configurable thresholds in `Config`
- **Temporal snapshot** (end-state #2 complete) — `harvest/snapshot.py` builds structured JSON
  from collected docs (containers, services, disks, ports, ollama_models, config_hashes,
  systemd_units); written to `knowledge/harvest_snapshot.json` (git-tracked) after each
  successful harvest; git history is the diff layer
- Test count: 552 → 589 (all offline, ruff clean)

### Mar 5, 2026 — Grafana Tempo (OTel trace receiver)

- Grafana Tempo deployed in the monitoring stack — receives OTel traces from HAL via OTLP HTTP on port 4318
- `ops/tempo.yaml` — single-node config with local storage and 7-day retention
- `ops/grafana-tempo-datasource.yaml` — Grafana provisioning file, auto-configures Tempo as a datasource
- `ops/deploy-tempo.sh` — deploy script: copies configs to monitoring stack, prints docker-compose snippet, restarts stack
- OPERATIONS.md: new "Tracing" section with deploy, config, 4-step verification, span name table; Tempo added to services table; OTLP trap updated
- System prompt (`hal/bootstrap.py`): Tempo added to Core services so HAL knows it exists
- `OTLP_ENDPOINT=http://host.docker.internal:4318` — correct value for HAL container → host Tempo

### Mar 5, 2026 — Web UI

- Lightweight browser chat interface served by FastAPI at `GET /` — vanilla JS, no build tooling
- `hal/static/index.html` + `style.css` + `app.js` — single-page chat app
- Design: dark monospace-rooted interface with collapsible sidebar (session list + `/health` status dot)
- Markdown rendering via `marked.js` (CDN), syntax highlighting via `highlight.js` (CDN, github-dark theme)
- Sessions stored in `localStorage` as `web-{timestamp}`; "New Session" button in sidebar
- Flat message blocks (no bubbles): user messages prefixed with `>`, HAL messages with blue left border
- Intent badge displayed below each HAL response; "thinking..." animation while waiting
- Mobile responsive: sidebar collapses to hamburger menu, full-width chat, pinned input
- `StaticFiles` mount at `/static` + `CORSMiddleware` added to `hal/server.py`
- 3 new tests in `test_server.py` (root HTML, CSS served, JS served)
- Test count: 784 → 787 (all offline, ruff clean)

---

## Backlog (immediate)

<!-- empty — all items shipped -->

---

## Architectural backlog (Path C — stop hardcoding lab-specific values)

The architecture is clean and generic. The implementation has lab-specific hardcodings
that should be externalized so HAL can redeploy on a second machine without source edits.

1. **Template the system prompt** from `Config` fields — `hal/bootstrap.py:get_system_prompt()`
   contains literal hardware specs, interface names (`enp130s0`), mount points, and version
   numbers that will silently be wrong if the server changes.

   *Constraints:* System prompt is one large f-string; any refactor must not degrade prompt
   quality (it is the primary LLM behavior driver). Hardware specs can't easily come from
   `.env` — needs KB or a separate config section. Port numbers exist in `Config` (derivable
   from URLs). Template change may require test updates in `test_agent_loop.py` and
   `test_server.py`.

   *Open questions:* How much hardware spec stays inline vs. sourced from KB via `search_kb`?
   Should `get_system_prompt()` accept a `Config` param, or introduce a separate "lab profile"
   concept?

2. **Externalize Judge patterns** — `_CMD_RULES`, `_SENSITIVE_PATHS`, and `_SAFE_FIRST_TOKENS`
   in `hal/judge.py` are Python literals. Adding a site-specific safe command requires editing
   shared policy code.

   *Constraints:* A missing/malformed rules file must fail loud — silent auto-approve is worse
   than hardcoding. Tests in `test_judge.py` and `test_judge_hardening.py` test specific command
   strings; they must be rewritten to load the external file. Git write blocking
   (`_GIT_WRITE_SUBCOMMANDS`) and `_EVASION_PATTERNS` are universal security policy and should
   stay in source regardless.

   *Open questions:* YAML vs. separate Python module vs. Config section? Only site-specific
   entries go external (e.g. `_SENSITIVE_PATHS`), or all rule structures?

   *Pending follow-up (prerequisite for removing from source):* `/run/homelab-secrets` is the
   only site-specific entry in `_SENSITIVE_PATHS`. Before removing it from `judge.py`: add
   `JUDGE_EXTRA_SENSITIVE_PATHS=/run/homelab-secrets` to the server's `.env`, confirm it is
   picked up, then remove the literal. One commit.

3. ~~**Remove hardcoded defaults** from `config.py`~~ ✓ done — `LAB_HOST` and `LAB_USER`
   now use `_required_env()` and raise `RuntimeError` if unset.

4. ~~**Pluggable harvest collectors**~~ ✓ done — `collect_config_files()` uses glob patterns;
   per-collector `try/except` in `collect_all()` provides graceful degradation;
   `collect_system_state()` receives `ollama_host` as an argument.

---

## End state — what makes this genuinely impressive

The system can detect, answer, and act autonomously within a trust envelope —
diagnosing failures, executing recovery playbooks, and reporting what it did.

**Five capabilities that cross the line:**

### 1. Autonomous remediation with trust accounting ✓ delivered Mar 5, 2026

HAL observes a component failure, diagnoses it via structured health checks, restarts it
(tier 1 auto-approved when trust-promoted based on N clean prior runs), verifies recovery,
and sends a summary — all without operator prompting.

Full stack: `hal/healthcheck.py` (8-component health check registry returning
`ComponentHealth` with status/detail/latency) → `hal/playbooks.py` (7 declarative
recovery playbooks with circuit breaker, max 2–3 attempts/hour) → `hal/watchdog.py`
(`_check_component_health()` runs every 5 min, auto-executes tier ≤1 playbooks) →
`hal/tools.py` (`check_system_health` + `recover_component` tools for interactive use).
Trust accounting: `record_outcome()` writes success/error to audit log;
`_load_trust_overrides()` auto-promotes proven-safe actions (≥90% success, ≥10 samples)
to tier 0; demotion revokes overrides when success rate drops below 70%.
`trust_metrics.py` surfaces outcome stats via `get_action_stats()`.

### 2. Temporal awareness ✓ delivered Mar 1, 2026

`knowledge/harvest_snapshot.json` (git-tracked) is written on each successful harvest run.
Schema: `harvested_at`, `containers`, `services`, `disks`, `ports`, `ollama_models`,
`config_hashes`, `systemd_units` — all lists sorted for stable diffs. Git history is the
diff layer: `git diff HEAD@{2026-03-08} -- knowledge/harvest_snapshot.json` answers
"what changed since Tuesday?" for container/service/disk/config state. Metric temporal
awareness via `get_trend` (Prometheus time-series). A dedicated `get_snapshot_diff` tool
is a follow-on, not yet implemented.

### 3. Proactive pattern detection ✓ delivered Mar 1, 2026

`_check_trends()` in `watchdog.py` watches 6 metrics (disk_root, disk_docker, disk_data,
mem, swap, gpu_vram) via `prom.trend('1h')`. Fires ntfy when `direction=='rising'` and
`delta_per_hour >= threshold`. Four thresholds operator-configurable via `.env`
(`WATCHDOG_DISK_RATE_PCT_PER_HOUR` etc., defaults 5%/hr disk, 5%/hr mem, 10%/hr swap,
5%/hr VRAM). `get_trend` tool covers the reactive (on-demand query) side.

### 4. Post-incident synthesis ✓ delivered Feb 26, 2026

After something goes wrong, HAL reconstructs the timeline from its audit log, Prometheus,
Falco events, and session history, and writes a brief post-mortem.

`/postmortem <incident-description> [--hours N]` delivered — collects audit log, Prometheus
trends, and Falco events into a context block, then invokes the agent loop with a
postmortem-scoped system prompt. See `hal/postmortem.py` and the `/postmortem` REPL command.

### 5. Trust evolution ✓ fully delivered Mar 5, 2026

Outcome tracking wired in (see end-state #1). `trust_metrics.py` `get_action_stats()`
now includes per-key success/error counts, success rate, and a flag showing whether the
≥90% / ≥10-sample trust threshold is met. Tier demotion implemented:
`_load_trust_overrides()` both promotes (≥90% success, ≥10 samples → tier 0) and
demotes (<70% success, ≥10 samples → override revoked, restores original tier).
This closes the feedback loop: a recovery playbook that keeps failing loses its
auto-approval privilege.

---

## Long-horizon vision

See [ARCHITECTURE.md](ARCHITECTURE.md) for the agent hierarchy and full home scope.

The short version: HAL grows from a single-machine coordinator into the autonomous
intelligence of the entire home — infrastructure, network, security, home automation, and
software development. The routing layer, Judge, and memory systems are designed to extend
to multi-agent use, not be replaced by it. The next named agent after trust evolution is
probably **Architect** — a sub-agent that can propose and implement changes to HAL's own
codebase via the existing eval/audit infrastructure.
