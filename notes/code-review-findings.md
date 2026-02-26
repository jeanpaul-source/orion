# Code Review Findings — Feb 25, 2026

*Full architectural review done by Copilot. This note captures the actionable findings
only. See ROADMAP.md for the strategic backlog.*

---

## Summary verdict

**Grade: B+ / A−**

Architecture is clean. Security model (Judge) is production-quality. Documentation is
unusually good. Main gaps: test coverage on runtime components (executor, watchdog, harvest),
some accumulated hardcoding, and a few pieces of dead/duplicated code that haven't been
cleaned up yet.

---

## Critical / Do Immediately

### ~~C1 — Merge the duplicate Falco noise filter~~ ✅ DONE (Feb 25, 2026)

`hal/falco_noise.py` created with `NOISE_RULES` data tuples and `is_falco_noise()`.
Both `security.py` and `watchdog.py` import from it. Watchdog no longer loads `security.py`
(and its SSHExecutor/Judge deps) at all. Also fixed: `_POISON_FENCE_RE` private cross-module
import replaced by `TOOL_CALL_FENCE_RE` in `hal/patterns.py`.

---

### C2 — `_extract_tool_calls_from_content()` is live dead code

`hal/llm.py` contains a fallback parser that extracts `<tool_call>` / `<tools>` tags from
model content. It was written for the Coder model and should never fire on the Instruct
model. It has no tests. If the Instruct model ever emits those tags in free text (e.g. in
a code example), it would silently inject phantom tool calls into the agent loop.

**Fix:** Either remove it and monitor, or add a `HAL_EXTRACT_FALLBACK=0` env flag that
disables it by default. Add a test for the none-shall-pass case.
**Effort:** ~1 hr.

---

### C3 — `config.py` hardcoded IP defaults

All three service defaults (`OLLAMA_HOST`, `PGVECTOR_DSN`, `PROMETHEUS_URL`) point to
`192.168.5.10`. A fresh checkout without a `.env` will silently try to connect to a
specific LAN address and fail in confusing ways.

**Fix:** Remove the hardcoded defaults or replace with `None` and add a startup assertion:

```python
if not os.getenv("OLLAMA_HOST"):
    raise RuntimeError("OLLAMA_HOST must be set in .env — copy .env.example")
```

**Effort:** ~30 min. **Tracked in ROADMAP.md Path C item 3.**

---

## High Priority / Do Soon

### ~~H1 — Gate PlannerAgent / CriticAgent~~ ✅ DONE (Feb 25, 2026)

Every agentic query — including `ls /opt` — runs PlannerAgent + CriticAgent first. That is
2 LLM inference calls (32B model) before the main loop starts. The planner output is
prepended to the user message but there is no evidence the model follows it for simple queries.

**Fix options:**
- Add a complexity heuristic: skip if query < N words and contains no action verbs
- Add a `--no-plan` REPL flag
- Move planner/critic to opt-in only (caller passes `use_planner=True`)

**Where to change:** `hal/agent.py` `run_agent()` — the planner block around lines 795–820.
**Effort:** ~2 hr.

---

### ~~H2 — `agent.py` is 1045 lines with a 17-branch dispatch~~ ✅ DONE (Feb 25, 2026)

`_dispatch()` is a long if-elif chain. `_BASE_TOOLS` is a flat list of dicts in the same
file. Every new tool requires touching both in multiple places.

**Fix:** Extract tools into `hal/tools.py` — one dict per tool combining schema + handler:

```python
TOOL_REGISTRY = {
    "search_kb": {"schema": {...}, "handler": _handle_search_kb},
    ...
}
```

`_dispatch()` becomes a 3-line lookup. `get_tools()` iterates the registry.
**Effort:** ~3 hr. Not urgent but will become urgent as tool count grows.

---

### ~~H3 — `run_conversational` is missing latency telemetry~~ ✅ DONE (Feb 25, 2026)

The other three handlers (`run_health`, `run_fact`, `run_agent`) all call
`REQ_LATENCY.observe(dur, intent=...)` and wrap everything in an OTel span.
`run_conversational` calls `REQ_TOTAL.inc()` but has no latency metric and no span.

**Fix:** Add `import time`, `t0 = time.perf_counter()`, latency observe, and an OTel span
to `run_conversational` in `hal/agent.py`. Exact pattern: copy from `run_health`.
**Effort:** ~20 min.

---

### ~~H4 — `total_calls < 5` magic number in agent loop~~ ✅ DONE (Feb 25, 2026)

In `hal/agent.py` the agent loop stopping condition is:
"terminate after 8 iterations OR after 5 unique tool calls, whichever comes first."
The `5` is an undocumented inline literal. The dual constraint is not mentioned in ARCHITECTURE.md.

**Fix:** Define `MAX_TOOL_CALLS = 5` next to `MAX_ITERATIONS = 8` and add a comment
explaining the dual constraint. Update ARCHITECTURE.md agent loop section.
**Effort:** ~10 min.

---

## Test Coverage Gaps

Current coverage: 34%. Distribution is very uneven.

| Module | Coverage | Risk |
|---|---|---|
| `hal/judge.py` | ~78% | Low — well tested |
| `hal/memory.py` | 92% | Low |
| `hal/trust_metrics.py` | 87% | Low |
| `hal/web.py` | High (60+ tests) | Low |
| `hal/executor.py` | ~95% (21 tests) | Low — fully mocked offline |
| `hal/watchdog.py` | ~70% (7 tests) | Low — threshold + cooldown tested |
| `hal/server.py` endpoints | ~60% (7 tests) | Low — TestClient coverage |
| `harvest/collect.py` | Low | Medium — nightly job |
| `hal/prometheus.py` accumulator | 0% | Medium |

**Priority order for adding tests:**

1. `hal/watchdog.py` — test threshold evaluation and cooldown state (fully mockable)
2. `hal/server.py` — test `/chat` + `/health` with FastAPI `TestClient` (no live services)
3. `hal/executor.py` — test localhost detection, command formatting, return dict shape (mock `subprocess`)

---

## Style / Smell Notes (low priority)

- **`watchdog.py` `_WATCHDOG_FALCO_NOISE` uses lambdas in a list.** Replace with
  `(proc_name, path_substring)` tuples and a `_matches_noise(event, filters)` helper.
  Makes it testable and readable.

- **`reason` field on tool calls is optional everywhere.** The Judge logs empty reason
  strings when the model skips it, degrading audit-trail quality. Consider making it
  required in the schema or at least warning when absent.

- **`SYSTEM_PROMPT` in `main.py` is 110 lines with hardcoded ports, IPs, thresholds.**
  Adding a service means editing two files (`config.py` + `SYSTEM_PROMPT`). Template it
  from `Config` fields. Tracked in ROADMAP.md Path C item 1.

---

## Confirmed Solid — Do Not Touch Without Tests

These components are working correctly and have meaningful test coverage. Any change here
requires running the full test suite first.

- **`hal/judge.py`** — tier classification, evasion detection, git write blocking, path
  canonicalization, self-edit governance, audit logging. 941 lines of tests between
  `test_judge.py` and `test_judge_hardening.py`.
- **`hal/web.py`** — SSRF protection, DNS rebinding defense, URL validation, sanitisation.
  60+ tests in `test_web.py`.
- **`hal/memory.py`** — poison filter, prune logic, session management. 92% coverage.

---

## Quick Wins Checklist

- [x] C1: Merge Falco noise filter into shared module — done, `hal/falco_noise.py`
- [x] H3: Add latency telemetry to `run_conversational` (~20 min)
- [x] H4: Name the `5` as `MAX_TOOL_CALLS` next to `MAX_ITERATIONS` (~10 min)
- [ ] Run eval re-run on server (no code changes needed)
- [ ] C2: Gate or remove `_extract_tool_calls_from_content`
- [ ] C3: Config fail-loud on missing `.env` required fields
- [x] H1: Gate PlannerAgent on query complexity
- [x] H2: Refactor tool schema + dispatch registry
- [x] Tests: `hal/watchdog.py` threshold + cooldown logic
- [x] Tests: `hal/server.py` endpoints via `TestClient`
- [x] Tests: `hal/executor.py` subprocess mock
