# Roadmap

What's built, what's next, and where this is going.

---

## Done

Development history from Feb 22 – Mar 7, 2026. Full details in git history.

**Foundation:** Terminal REPL with session memory (SQLite), embedding-based intent
classifier, pgvector knowledge base (~19,900 chunks), agentic tool loop with Judge
gating (tier 0–3), SSH executor with multi-host support via `ExecutorRegistry`.

**LLM & inference:** vLLM serving Qwen2.5-32B-Instruct-AWQ (chat); Ollama CPU-only
embeddings (nomic-embed-text). `OLLAMA_NUM_GPU=0` enforced to give vLLM full VRAM.

**Security stack:** Falco eBPF, Osquery, ntopng, Nmap — all Judge-gated. SSRF-protected
`fetch_url`, privacy-guarded `web_search` (Tavily). Sandboxed `run_code` in disposable
Docker container (no network, read-only, capped resources).

**Interfaces:** HTTP server (FastAPI `/chat` + `/health`), Web UI (vanilla JS, dark theme,
markdown + syntax highlighting), Telegram bot (polling, single-user auth).

**Observability:** OTel tracing → Grafana Tempo, Prometheus Pushgateway metrics, structured
JSON logging with session/trace correlation, Grafana dashboard.

**Reliability:** Autonomous remediation via health checks + recovery playbooks with circuit
breakers. Trust evolution: outcome tracking auto-promotes/demotes Judge tiers. Proactive
trend alerting (watchdog). Post-incident synthesis (`/postmortem`). Temporal snapshots
(`harvest_snapshot.json`, git-tracked).

**Tooling:** 1,176 offline tests, ruff + mypy + markdownlint pre-commit hooks, CI on PRs,
eval harness (40 queries, 4 code metrics at 100%), 87% test coverage floor.

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
