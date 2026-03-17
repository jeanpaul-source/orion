# Roadmap

> Last audited: 2026-03-17 against code (Pass 5).

What's built, what's next, and where this is going.

---

## Done

Development history from Feb 22 – Mar 7, 2026. Full details in git history.

**Foundation:** Terminal REPL with session memory (SQLite — see [hal/memory.py](hal/memory.py)),
embedding-based intent classifier ([hal/intent.py](hal/intent.py), threshold 0.65, 4
categories), pgvector knowledge base (thousands of chunks — see
[hal/knowledge.py](hal/knowledge.py)), agentic tool loop with Judge gating (tier 0–3 —
see [hal/agent.py](hal/agent.py), [hal/judge.py](hal/judge.py)), SSH executor with
multi-host support via `ExecutorRegistry` ([hal/executor.py](hal/executor.py)).

**LLM & inference:** vLLM serving Qwen2.5-32B-Instruct-AWQ (chat — see `CHAT_MODEL` in
[hal/config.py](hal/config.py)); Ollama CPU-only embeddings (nomic-embed-text — see
`EMBED_MODEL`). `OLLAMA_NUM_GPU=0` enforced to give vLLM full VRAM.

**Security stack:** Falco eBPF, Osquery, ntopng, Nmap — all Judge-gated (see
[hal/security.py](hal/security.py)). SSRF-protected `fetch_url`, privacy-guarded
`web_search` (Tavily) — both in [hal/web.py](hal/web.py). Sandboxed `run_code` in
disposable Docker container (no network, read-only, capped resources — see
[hal/sandbox.py](hal/sandbox.py)).

**Interfaces:** HTTP server (FastAPI `/chat` + `/health` — see
[hal/server.py](hal/server.py)), Web UI (vanilla JS, dark theme, markdown + syntax
highlighting — see [hal/static/](hal/static/)), Telegram bot (polling, single-user
auth — see [hal/telegram.py](hal/telegram.py)).

**Observability:** OTel tracing → Grafana Tempo ([hal/tracing.py](hal/tracing.py)),
Prometheus Pushgateway metrics ([hal/prometheus.py](hal/prometheus.py)), structured JSON
logging with session/trace correlation ([hal/logging_utils.py](hal/logging_utils.py)),
Grafana dashboard.

**Reliability:** Autonomous remediation via health checks + recovery playbooks with circuit
breakers (see [End state §1](#1-autonomous-remediation-with-trust-accounting--delivered-mar-5-2026)).
Trust evolution: outcome tracking auto-promotes/demotes Judge tiers. Proactive trend alerting
([hal/watchdog.py](hal/watchdog.py)). Post-incident synthesis (`/postmortem` — see
[hal/postmortem.py](hal/postmortem.py)). Temporal snapshots
([knowledge/harvest_snapshot.json](knowledge/harvest_snapshot.json), git-tracked).

**Tooling:** Offline test suite (run `make test` for current count), ruff + mypy +
markdownlint pre-commit hooks, CI on PRs, eval harness
([eval/queries.jsonl](eval/queries.jsonl) for query set, 7 code evaluators + 2 LLM
evaluators — see [eval/evaluate.py](eval/evaluate.py)), coverage floor auto-ratcheted
via [.coverage-threshold](.coverage-threshold).

---

## Backlog (immediate)

<!-- empty — all items shipped -->

---

## Architectural backlog (Path C — stop hardcoding lab-specific values)

The architecture is clean and generic. The implementation has lab-specific hardcodings
that should be externalized so HAL can redeploy on a second machine without source edits.

1. **Template the system prompt** from `Config` fields — partially done.
   [hal/bootstrap.py](hal/bootstrap.py) `get_system_prompt()` now derives ports from Config
   URLs, hardware summary from `LAB_HARDWARE_SUMMARY`, and hostname from `LAB_HOSTNAME`.

   **Remaining:** `enp130s0` (interface name, L99) and `~19,900 doc chunks` (L71) are still
   hardcoded literals. See [F-89](docs/planning-pack/audit-findings.md) for the chunk count
   issue.

   *Constraints:* System prompt is one large f-string; any refactor must not degrade prompt
   quality (it is the primary LLM behavior driver). The chunk count could be queried from
   pgvector at startup but adds a DB dependency to prompt construction.

   *Open questions:* Interface name → new env var or KB lookup? Chunk count → runtime
   query or just drop the number from the prompt?

2. **Externalize Judge patterns** — `_CMD_RULES`, `_SENSITIVE_PATHS`, and `_SAFE_FIRST_TOKENS`
   in [hal/judge.py](hal/judge.py) are Python literals. Adding a site-specific safe command
   requires editing shared policy code. See also
   [F-73](docs/planning-pack/audit-findings.md) (undocumented env vars including
   `JUDGE_EXTRA_SENSITIVE_PATHS`).

   *Constraints:* A missing/malformed rules file must fail loud — silent auto-approve is worse
   than hardcoding. Tests in `test_judge.py` and `test_judge_hardening.py` test specific command
   strings; they must be rewritten to load the external file. Git write blocking
   (`_GIT_WRITE_SUBCOMMANDS`) and `_EVASION_PATTERNS` are universal security policy and should
   stay in source regardless.

   *Open questions:* YAML vs. separate Python module vs. Config section? Only site-specific
   entries go external (e.g. `_SENSITIVE_PATHS`), or all rule structures?

   *Pending follow-up (prerequisite for removing from source):* `/run/homelab-secrets` is the
   only site-specific entry in `_SENSITIVE_PATHS`. `JUDGE_EXTRA_SENSITIVE_PATHS` already exists
   in [hal/config.py](hal/config.py) but the literal hasn't been removed from source yet.
   Next step: add it to the server's `.env`, confirm it is picked up, then remove the literal.
   One commit.

3. ~~**Remove hardcoded defaults** from `config.py`~~ ✓ done — `LAB_HOST` and `LAB_USER`
   now use `_required_env()` in [hal/config.py](hal/config.py) and raise `RuntimeError`
   if unset.

4. ~~**Pluggable harvest collectors**~~ ✓ done — `collect_config_files()` uses glob patterns;
   per-collector `try/except` in `collect_all()` provides graceful degradation;
   `collect_system_state()` receives `ollama_host` as an argument. See
   [harvest/collect.py](harvest/collect.py).

---

## End state — what makes this genuinely impressive

The system can detect, answer, and act autonomously within a trust envelope —
diagnosing failures, executing recovery playbooks, and reporting what it did.

**Five capabilities that cross the line:**

### 1. Autonomous remediation with trust accounting ✓ delivered Mar 5, 2026

HAL observes a component failure, diagnoses it via structured health checks, restarts it
(tier 1 auto-approved when trust-promoted based on N clean prior runs), verifies recovery,
and sends a summary — all without operator prompting.

Full stack: [hal/healthcheck.py](hal/healthcheck.py) (health check registry — see
`HEALTH_CHECKS` for current component list — returning `ComponentHealth` with
status/detail/latency) → [hal/playbooks.py](hal/playbooks.py) (declarative recovery
playbooks — see `PLAYBOOKS` for current list — with per-playbook circuit breaker) →
[hal/watchdog.py](hal/watchdog.py) (`_check_component_health()` runs every 5 min,
auto-executes tier ≤1 playbooks) → [hal/tools.py](hal/tools.py) (`check_system_health`
\+ `recover_component` tools for interactive use).
Trust accounting: `record_outcome()` writes success/error to audit log;
`_load_trust_overrides()` auto-promotes proven-safe actions (≥90% success, ≥10 samples)
to tier 0; demotion revokes overrides when success rate drops below 70%.
[hal/trust_metrics.py](hal/trust_metrics.py) surfaces outcome stats via
`get_action_stats()` (per-key success/error counts, success rate, confidence).

### 2. Temporal awareness ✓ delivered Mar 1, 2026

[knowledge/harvest_snapshot.json](knowledge/harvest_snapshot.json) (git-tracked) is written
on each successful harvest run. Schema: `harvested_at`, `containers`, `services`, `disks`,
`ports`, `ollama_models`, `config_hashes`, `systemd_units` — all lists sorted for stable
diffs. Git history is the diff layer:
`git diff HEAD@{2026-03-08} -- knowledge/harvest_snapshot.json` answers "what changed since
Tuesday?" for container/service/disk/config state. Metric temporal awareness via `get_trend`
(Prometheus time-series). A dedicated `get_snapshot_diff` tool is a follow-on, not yet
implemented.

### 3. Proactive pattern detection ✓ delivered Mar 1, 2026

`_check_trends()` in [hal/watchdog.py](hal/watchdog.py) watches metrics defined in
`TREND_METRICS` (disk, memory, swap, GPU VRAM) via `prom.trend('1h')`. Fires ntfy when
`direction=='rising'` and `delta_per_hour >= threshold`. Thresholds operator-configurable
via `.env` (`WATCHDOG_DISK_RATE_PCT_PER_HOUR` etc. — see [hal/config.py](hal/config.py)
for defaults). `get_trend` tool covers the reactive (on-demand query) side.

### 4. Post-incident synthesis ✓ delivered Feb 26, 2026

After something goes wrong, HAL reconstructs the timeline from its audit log, Prometheus,
Falco events, and session history, and writes a brief post-mortem.

`/postmortem <incident-description> [--hours N]` delivered — collects audit log, Prometheus
trends, and Falco events into a context block, then invokes the agent loop with a
postmortem-scoped system prompt. See [hal/postmortem.py](hal/postmortem.py) and the
`/postmortem` REPL command in [hal/main.py](hal/main.py).

### 5. Trust evolution ✓ fully delivered Mar 5, 2026

Outcome tracking wired in (see end-state #1).
[hal/trust_metrics.py](hal/trust_metrics.py) `get_action_stats()` returns per-key
success/error counts, success rate, and confidence score. Promotion/demotion logic lives
in `_load_trust_overrides()` in [hal/judge.py](hal/judge.py): promotes (≥90% success,
≥10 samples → tier 0) and demotes (<70% success, ≥10 samples → override revoked, restores
original tier). This closes the feedback loop: a recovery playbook that keeps failing
loses its auto-approval privilege.

---

## Long-horizon vision

See [ARCHITECTURE.md](ARCHITECTURE.md) for the current component map and data flow.

The short version: HAL grows from a single-machine coordinator into the autonomous
intelligence of the entire home — infrastructure, network, security, home automation, and
software development. The routing layer, Judge, and memory systems are designed to extend
to multi-agent use, not be replaced by it. The next named agent after trust evolution is
probably **Architect** — a sub-agent that can propose and implement changes to HAL's own
codebase via the existing eval/audit infrastructure.
