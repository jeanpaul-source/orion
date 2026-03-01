# Plan: End-State Capabilities — Verified State and Remaining Work

Created: 2026-03-01
Status: Item C in progress — Items A and B complete

---

## Verified State

The ROADMAP.md "End state" section lists five capabilities that "cross the line" from
assistant to agent. This plan was produced by reading that section and then reading the actual
code for every piece of infrastructure mentioned. Status reflects code on 2026-03-01.

---

### End-state #1 and #5 — Autonomous remediation with trust accounting / Trust evolution

These two items share infrastructure and are treated together.

ROADMAP says:
  End-state #1: HAL observes a crash-loop, diagnoses it, restarts (tier-1 auto-approved for
  known-safe actions based on prior runs), verifies recovery, sends summary. "trust_metrics.py
  + audit.log already have all the raw material. Missing piece: a feedback mechanism that
  records whether an action succeeded, and a policy that adjusts tier thresholds."

  End-state #5: "directly computable from audit.log + outcome recording — trust_metrics.py
  already parses the log; it just needs outcome tracking wired in."

What the code actually has:

FULLY IMPLEMENTED in hal/judge.py:
- record_outcome(action_type, detail, outcome) appends outcome entries to audit.log with
  status="outcome", outcome="success"|"error". Called in agent.py after every tool dispatch
  (lines ~205-215), both on success and on exception.
- _load_trust_overrides(audit_log) reads outcome entries from the raw log file, aggregates
  by trust key (run_command:<first_token> or action_type), and returns {key: 0} for any
  action with >= 10 outcome samples and >= 90% success rate. Constants:
  _TRUST_MIN_SAMPLES = 10, _TRUST_MIN_SUCCESS_RATE = 0.90.
- _trust_key(action_type, detail) normalizes by first token for run_command so "ps aux" and
  "ps -ef" both contribute to the same "run_command:ps" trust bucket.
- approve() checks if tier == 1, calls _refresh_trust_overrides(), and applies the override
  if the key is in the override table — reducing tier 1 to tier 0 for proven-safe actions.
- _refresh_trust_overrides() uses file size caching to avoid re-reading the entire log on
  every approve() call.

DELIVERED in hal/trust_metrics.py (commit a3ddaee):
- OutcomeEvent dataclass added alongside AuditEvent.
- load_outcome_log() reads and parses outcome entries (status=="outcome") from the log.
- get_action_stats() now includes an "outcomes" block: per-key success count, error count,
  success rate, and an explicit flag showing whether the trust threshold is met.
  An operator can now ask "has systemctl restart earned tier-0 trust?" and get a factual answer.

Additional gap: the ROADMAP describes autonomous remediation as "HAL observes a crash-loop,
diagnoses it, restarts it." This requires:
(a) Proactive detection that a crash-loop is happening — not just reactive response to a query.
(b) A decision to act without operator prompting — the Judge approval rate for run_command
  with tier 0 (from trust evolution) would handle (b), but (a) requires a background loop
  that monitors for specific conditions.

The current watchdog (hal/watchdog.py) does threshold alerting via ntfy but does NOT
trigger remediation actions. It is a notification system, not an autonomous actor.

---

### End-state #2 — Temporal awareness ("what changed since Tuesday?")

ROADMAP says: "requires HAL to know what state looked like at time T. Harvest pipeline already
produces timestamped snapshots. Missing piece: a diff query comparing current KB snapshot
against previous one."

What the code has:
- harvest/collect.py produces docs with timestamps embedded in content (e.g., "as of 2026-02-26
  14:30"). The timestamps are in the content strings, not in pgvector metadata.
- harvest/ingest.py: clear_lab_docs() deletes and re-inserts live-state docs. There is no
  snapshot history — the previous state is destroyed on each harvest run.
- The documents table in pgvector has columns: content, embedding, category, file_name,
  file_path, metadata, chunk_index — no created_at or version column.
- ~/.orion/harvest_last_run is a timestamp file but holds only a single value (the most
  recent run time). No history of previous runs.
- hal/prometheus.py range_query() can retrieve metric time series over a window, but this is
  for Prometheus-tracked metrics, not arbitrary system state.

The ROADMAP statement "harvest pipeline already produces timestamped snapshots" is technically
true but misleading — the harvest replaces the previous state, it does not accumulate a history
of snapshots. There is no previous snapshot to diff against.

Implementing temporal awareness requires either:
(a) Storing harvest snapshots in a versioned table or structured file history so a prior state
  can be retrieved and compared, OR
(b) Using Prometheus time-series data (via get_trend / range_query) for metric temporal
  awareness, which works for numeric metrics but not for container state, file changes, or
  service configuration.

Nothing in the current codebase provides option (a). get_trend / PrometheusClient.range_query
provides option (b) for metrics only. This capability is largely unimplemented.

---

### End-state #3 — Proactive pattern detection (background trend alerting)

ROADMAP says: "get_trend tool delivered (Feb 26, 2026) — covers the reactive side. Remaining
proactive piece: a background loop that watches key trends automatically and fires ntfy before
thresholds hit."

DELIVERED (2026-03-01) — four commits:
- fd15168 refactor: move METRIC_PROMQL to hal/prometheus.py as single source of truth
- 9eb0504 feat(config): add 4 watchdog trend rate-of-change threshold fields + .env.example
- 7e636da feat(watchdog): _check_trends() proactive rate-of-change alerting wired into run()
- 82c37bb test(watchdog): 7 tests covering all _check_trends() branches + end-to-end

What was built:
- METRIC_PROMQL moved to hal/prometheus.py; tools.py and watchdog.py both import from there.
- Four new Config fields: watchdog_disk_rate_pct_per_hour (5.0), watchdog_mem_rate_pct_per_hour
  (5.0), watchdog_swap_rate_pct_per_hour (10.0), watchdog_gpu_vram_rate_pct_per_hour (5.0).
  All operator-configurable via .env.
- _check_trends() in watchdog.py calls prom.trend('1h') for 6 metrics (disk_root, disk_docker,
  disk_data, mem, swap, gpu_vram). Fires when direction=='rising' and delta_per_hour >= threshold.
  CPU and load excluded — too spiky for rate-of-change alerting.
- Reuses existing cooldown/state/ntfy machinery. Wired in as ("trend", _check_trends, "high")
  in the simple_checks list. No new systemd unit needed.
- 575 offline tests passing.

No remaining work for end-state #3.

---

### End-state #4 — Post-incident synthesis

ROADMAP says: "DELIVERED Feb 26, 2026"

Code verified: hal/postmortem.py exists. gather_postmortem_context() collects three evidence
layers: audit log (non-trivial + denied events within window), Prometheus health snapshot +
CPU/mem/disk_docker trends, Falco security events. /postmortem slash command in hal/main.py.
8 offline tests in tests/test_postmortem.py. Fully delivered.

No remaining work for end-state #4.

---

## Problem Statement

One end-state capability has remaining work. Two are complete.

**Item A — trust_metrics analytics gap (end-state #1 and #5, analytics layer only)**

DELIVERED (commit a3ddaee). OutcomeEvent, load_outcome_log(), and the outcomes block
in get_action_stats() are all present and passing tests. No remaining work.

**Item B — proactive trend alerting (end-state #3, proactive side)**

DELIVERED (2026-03-01, commits fd15168–82c37bb). See end-state #3 section above.
No remaining work.

**Item C — temporal awareness (end-state #2)**

Approach decided: git-based harvest snapshots covering all harvested state (both container/
service state and config files). Harvest writes a structured JSON summary to a tracked file
on each run; git history becomes the temporal layer.

Scope confirmed by operator: both container/service state changes and config file changes.

Implementation not yet started. See Relevant Code Locations and Constraints below.

---

## Relevant Code Locations

Item C — temporal awareness:
- harvest/collect.py: each collector — understand what state is captured and its schema.
  This determines what goes into the snapshot JSON.
- harvest/ingest.py: clear_lab_docs() and upsert logic — the "replace" semantics that must
  remain unchanged for the live KB; snapshot write is additive alongside this.
- harvest/main.py: entry point — where the snapshot write call should be added after ingest.
- hal/prometheus.py range_query() / trend() — existing temporal mechanism for metrics only.
- knowledge/ dir — candidate home for snapshot files (already tracked, nightly harvest
  touches harvest/; snapshot file should be nearby but not in harvest/).
- tests/test_harvest.py — must not break; coverage baseline before touching harvest.

---

## Constraints

**Item C (temporal awareness):**
- The harvest pipeline's "replace" semantics are intentional — live-state docs are refreshed
  nightly. The snapshot write must be additive and must not touch the KB replace logic.
- The snapshot file must be a single tracked file in the repo so git history is the diff
  layer. Do not write one file per run — that defeats the purpose.
- Schema: JSON with a top-level "harvested_at" ISO timestamp and per-section keys matching
  what collect.py produces (containers, services, disks, etc.). Keys must be stable across
  runs so git diff is readable. Values must be primitive or sorted lists — no random ordering.
- Must not break existing harvest tests (tests/test_harvest.py).
- CLAUDE.md: propose snapshot schema before writing any code; one change at a time.
- Querying the history ("what changed since Tuesday?") requires either: (a) a new HAL tool
  that shells out to git diff on the snapshot file, or (b) the operator running git diff
  manually and pasting output. The simplest first step is (b) — the snapshot exists and
  HAL can read it; git diff is a run_command the operator or HAL can issue. A dedicated
  `get_snapshot_diff` tool is a follow-on, not a requirement for the first commit.


---

## Open Questions

**Item C (temporal awareness) — RESOLVED:**
1. Scope: both container/service state and config file changes. ✓
2. Approach: git-based harvest snapshots (single tracked JSON file, git history = diff). ✓
3. Time resolution: nightly (24h granularity) — matches existing harvest cadence. ✓

Remaining design question before coding:
- What exact keys should the snapshot JSON contain? Read harvest/collect.py collectors to
  enumerate what data is available, then propose the schema for operator approval before
  writing any code.


---

## Next Steps (Item C)

1. Read harvest/collect.py and harvest/main.py to understand the full data shape.
2. Propose snapshot JSON schema (keys, value types, ordering guarantees) — stop and wait.
3. After approval: add write_snapshot() to harvest/main.py (or a new harvest/snapshot.py).
4. Add tests for the snapshot write (assert file exists, assert required keys, assert
   timestamp field is ISO format).
5. Commit. Then decide whether to add a `get_snapshot_diff` tool to HAL or defer.
