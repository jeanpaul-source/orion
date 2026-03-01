# Plan: End-State Capabilities — Verified State and Remaining Work

Created: 2026-03-01
Status: ready for implementation

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

What the code has:

DELIVERED (reactive side):
- hal/prometheus.py range_query(expr, window) and trend(expr, window): fetches ~60 points
  over a time window, returns {first, last, min, max, delta, delta_per_hour, direction}.
  Direction is "rising"/"falling"/"stable" using 0.5%-of-range threshold.
- hal/tools.py get_trend tool: 9 named metric shortcuts + custom PromQL mode.
  _METRIC_PROMQL dict maps metric names to PromQL expressions.
- An operator can ask "is /docker disk growing?" and get a trend summary. This works.

MISSING (proactive side):
- hal/watchdog.py checks current metric values against thresholds (CPU >= 85%, mem >= 90%,
  etc.) but does NOT call trend() or range_query(). It fires when a threshold is breached
  (current value), not when a trend predicts a breach before it happens.
- There is no background loop that periodically runs trend() and fires ntfy when, for example,
  disk_docker direction == "rising" and delta_per_hour > some_rate.
- The watchdog and the get_trend tool are two separate subsystems with no connection.

Implementing proactive detection means either:
(a) Extending watchdog.py to call trend() in addition to current value checks, or
(b) Adding a separate "trend monitor" background loop in workers.py or a new module.

The question of which trends to monitor proactively (and what rate-of-change thresholds to
use) is an operator decision that the current code doesn't have config for.

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

Three end-state capabilities have actionable remaining work:

**Item A — trust_metrics analytics gap (end-state #1 and #5, analytics layer only)**

DELIVERED (commit a3ddaee). OutcomeEvent, load_outcome_log(), and the outcomes block
in get_action_stats() are all present and passing tests. No remaining work.

**Item B — proactive trend alerting (end-state #3, proactive side)**

The reactive half (get_trend tool) is delivered. The proactive half requires extending the
watchdog to call trend() and alert when a metric is on a trajectory to breach a threshold
before it actually does. This is the difference between "already on fire" alerting and
"trending toward fire" alerting.

**Item C — temporal awareness (end-state #2)**

Currently unimplemented except for Prometheus metric time series (via get_trend). Answering
"what changed since Tuesday?" for container state, service configs, file contents, or system
layout requires either snapshot versioning in the harvest pipeline or a structural addition to
how lab state is stored. This is the largest and least-defined remaining capability.

---

## Relevant Code Locations

Item A — trust_metrics analytics gap:
- hal/trust_metrics.py line ~138: _parse_json_line() — the outcome filter
- hal/trust_metrics.py line ~40–55: AuditEvent dataclass — no outcome field
- hal/trust_metrics.py CounterStats — errors field is reserved/unused, success/failure absent
- hal/trust_metrics.py get_action_stats() line ~240–303 — return dict structure
- hal/judge.py _load_trust_overrides() line ~497–535 — REFERENCE: correct outcome parsing
- hal/judge.py record_outcome() line ~555–615 — what gets written to the log
- hal/judge.py _TRUST_MIN_SAMPLES = 10, _TRUST_MIN_SUCCESS_RATE = 0.90 — the thresholds
- hal/tools.py _handle_get_action_stats and get_action_stats schema — tool interface
- tests/test_trust_metrics.py — tests to understand before changing
- tests/test_judge.py — covers record_outcome and _load_trust_overrides

Item B — proactive trend alerting:
- hal/watchdog.py: _check_metrics(), _check_containers() — current threshold checking
- hal/prometheus.py: trend(), range_query() — the trend infrastructure to leverage
- hal/tools.py _METRIC_PROMQL dict — canonical metric-to-PromQL mapping; duplicating this in
  watchdog.py would be drift; consider sharing or importing
- ops/watchdog.timer, ops/watchdog.service — scheduling and lifecycle context
- tests/test_watchdog.py — tests to understand before changing watchdog

Item C — temporal awareness:
- harvest/collect.py: each collector to understand what state is captured and with what schema
- harvest/ingest.py: clear_lab_docs() and the upsert logic — where the "replace" behavior is
- The pgvector documents table schema (visible via harvest/ingest.py or knowledge.py)
- hal/prometheus.py range_query() — the one existing temporal query mechanism
- hal/prometheus.py trend() — pre-computed trend over configurable windows
- There is no "snapshot history" module to read — this capability starts from near-zero

---

## Constraints

**Item A (trust_metrics analytics):**
- See plan-rc-findings.md "Item B" section for detailed constraints — this is the same code
  change described from both the RC-findings and end-state perspectives.
- Key: outcome entries have a different schema from approval entries. Adding outcome parsing
  must not break existing tests that parse approval/denial entries.
- AuditEvent is frozen dataclass. Must use Optional[str] = None for the outcome field to
  remain backward-compatible.
- get_action_stats() return dict is the tool interface. New fields are backward-compatible;
  changed field names are not.
- CLAUDE.md: one change at a time, propose before acting.

**Item B (proactive trend alerting):**
- watchdog.py runs in a background thread (or as a systemd-triggered process). Any blocking
  call to trend() (which makes an HTTP range query to Prometheus) adds latency to each
  watchdog cycle. The current watchdog fires every 5 minutes via watchdog.timer.
- Prometheus range_query() with a 1h window at 60 points is ~one HTTP request per metric.
  If watching 5 metrics for trends that's 5 extra Prometheus calls per watchdog cycle —
  manageable.
- Rate-of-change thresholds (at what delta_per_hour should an alert fire?) are not in Config
  or watchdog.py today. These need to be defined before implementation.
- Watchdog alerts go via ntfy (NTFY_URL in Config). The alerting mechanism already exists.
- Must not generate alert noise for stable metrics: the trend() "stable" determination
  (< 0.5% of range change) needs validation that it doesn't fire on normal fluctuation.
- Tests in tests/test_watchdog.py must cover the new trend-check code path.

**Item C (temporal awareness):**
- The harvest pipeline's "replace" semantics are intentional — live-state docs are refreshed
  nightly. Adding versioned history changes this semantics for those rows and has
  storage implications.
- pgvector is not a time-series database. Using it to store multiple versions of the same
  doc creates search confusion unless the schema clearly separates "current" from "archive."
- Prometheus already provides temporal data for metrics. The question for temporal awareness
  is what is NOT in Prometheus: container restarts (binary, Prometheus has a metric for this),
  file content changes, service configuration edits.
- The simplest approach that avoids schema changes: git-based snapshots of harvest output.
  The harvest pipeline could write a structured summary to a file in the repo on each run,
  and git history becomes the temporal layer.
- CLAUDE.md constraint: "no bandaids" — if a simple file-based approach would work well
  long-term, it may be the right answer; evaluate before proposing pgvector versioning.
- Must not break existing harvest tests.

---

## Open Questions

**Item A (trust_metrics analytics):**
- Already listed in plan-rc-findings.md Item B. Key question: single unified AuditEvent vs.
  separate OutcomeEvent type?

**Item B (proactive trend alerting):**
1. What rate-of-change thresholds should trigger a proactive alert? Options: fixed config
   values (e.g., disk growing > 5%/hour), dynamically computed from historical variance, or
   operator-configurable via .env. Get operator input before implementation.
2. Should proactive alerts be a new NTFY priority level or share the existing format?
3. Should the trend check run inside the existing watchdog.py loop or as a separate module?
   Separate module is cleaner but requires another systemd timer.
4. The _METRIC_PROMQL dict in tools.py is the single source of truth for metric-to-PromQL
   mapping. Should watchdog.py import from tools.py, or should the mapping be moved to a
   shared location (hal/prometheus.py or hal/config.py)?

**Item C (temporal awareness):**
1. What is the primary use case the operator wants to cover? "What containers changed?"
   (binary, Prometheus tracks) vs. "What config files changed?" (requires file diffing) vs.
   "What services started/stopped?" (journal + Prometheus) — these have very different
   implementation paths.
2. Git-based harvest snapshot history vs. pgvector versioning vs. sqlite snapshot store?
   Each has tradeoffs. Operator input needed before design.
3. What time resolution is needed? Nightly harvest (24h granularity) is what exists.
   Sub-daily changes would require more frequent harvests.

---

## Suggested Sequence

**Item A** — smallest scope, well-defined, builds on existing infrastructure. Implement first.
  One or two commits. See plan-rc-findings.md Item B for the detailed step breakdown.

**Item B** — medium scope, clear design space, high operational value. Implement second.
  Requires operator input on rate-of-change thresholds before coding starts.

**Item C** — largest scope, least-defined, requires a design decision before any implementation.
  Do not start until the approach question is resolved with the operator.
  If the operator resolves the approach question as "git-based snapshots," the implementation
  is localized to harvest/ and is relatively small. If it requires pgvector versioning,
  the implementation is larger and has broader test impact.

Item C is appropriate for a separate planning session after the approach is decided.
