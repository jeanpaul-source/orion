# Code Review Findings — Feb 25–26, 2026

*Full architectural review done by Copilot (two passes: Feb 25 structural, Feb 26 deep
audit). This note captures actionable findings only. See ROADMAP.md for the strategic
backlog.*

---

## Summary verdict

### Grade: B+ / A−

Architecture is clean. Security model (Judge) is production-quality. Documentation is
unusually good. Main gaps: structural coupling between `server.py` and `main.py`,
three separate implementations of the same tool-call stripping logic, duplicated
intent-dispatch blocks across three callers, and the Planner/Critic sub-agents adding
2× LLM latency with no measured quality benefit.

---

## Completed — Feb 25, 2026

### ~~C1 — Merge the duplicate Falco noise filter~~ ✅ DONE

`hal/falco_noise.py` with `NOISE_RULES` tuples and `is_falco_noise()`. Both
`security.py` and `watchdog.py` import it. Watchdog no longer loads `security.py`
(and its `SSHExecutor`/`Judge` deps). `_POISON_FENCE_RE` cross-module import replaced
by `TOOL_CALL_FENCE_RE` in `hal/patterns.py`.

### ~~C2 — Gate `_extract_tool_calls_from_content()`~~ ✅ DONE

Fallback tag extraction in `hal/llm.py` is now off by default behind
`HAL_EXTRACT_FALLBACK=1`. Tests in `tests/test_llm.py` cover default-off, opt-in,
and malformed-tag cases.

### ~~C3 — `config.py` fail-loud on missing required fields~~ ✅ DONE

`OLLAMA_HOST`, `PGVECTOR_DSN`, `PROMETHEUS_URL` now raise `RuntimeError` with an
`.env.example` message when absent. No more silent LAN-IP defaults.
Covered by `tests/test_config.py`.

### ~~H1 — Gate PlannerAgent / CriticAgent on query complexity~~ ✅ DONE

`_should_use_planner_critic()` added. Short non-action queries skip the two extra
LLM calls. `MAX_TOOL_CALLS = 5` and `PLANNER_CRITIC_ACTION_VERBS` defined as module
constants.

### ~~H2 — Extract tool registry into `hal/tools.py`~~ ✅ DONE

`TOOL_REGISTRY` dict with `schema` + `handler` per tool. `_dispatch()` is now a
3-line registry lookup. `get_tools()` iterates the registry.

### ~~H3 — `run_conversational` missing latency telemetry~~ ✅ DONE

OTel span, `t0`/latency observe, and `REQ_TOTAL` added. Matches the pattern from
the other three handlers.

### ~~H4 — `MAX_TOOL_CALLS` magic number~~ ✅ DONE

`MAX_TOOL_CALLS = 5` defined next to `MAX_ITERATIONS = 8` with an explanatory comment.

### ~~Tests — executor / server / watchdog / prometheus~~ ✅ DONE

486 offline tests passing. `test_executor.py`, `test_server.py`, `test_watchdog.py`,
`test_prometheus.py` all added.

---

## Open — Feb 26, 2026

### ~~N1 — `server.py` imports from `main.py` (architectural inversion)~~ ✅ DONE

`hal/bootstrap.py` created with `get_system_prompt()`, `setup_clients()`, `dispatch_intent()`.
Both `main.py` and `server.py` import from there. `main.py` is a pure entrypoint again.
`hal/patterns.py` deleted — existed only to break the circular import;  
`TOOL_CALL_FENCE_RE` inlined into `memory.py` and `server.py`.

---

### N2 — Three implementations of the same tool-call stripping logic

The same failure mode (LLM hallucinating a tool call in prose) is detected and stripped
in three separate places with three different implementations:

1. `agent.py:_strip_tool_artifacts()` — JSON decoder, strips bare `{"name":...,"arguments":...}` objects from final response text.
2. `server.py:_strip_tool_call_blocks()` — regex fence, strips ` ```json {...} ``` ` fences, applied after handler returns.
3. `memory.py:is_poison_response()` — hybrid, used as a save-gate before writing to SQLite.

They use different detection paths, have different failure modes, and must all be updated
if the pattern changes.

**Fix:** One canonical function in `hal/sanitize.py` (or inline into `hal/patterns.py`):
`strip_tool_call_artifacts(text) -> str` and `is_tool_call_artifact(text) -> bool`.
All three callers use it. Delete the three local implementations.

**Effort:** ~1.5 hr. Medium risk — add tests before touching `is_poison_response()`.

---

### ~~N3 — Intent dispatch block copy-pasted three times~~ ✅ DONE

`dispatch_intent()` added to `hal/bootstrap.py`. All three call sites (`main.py` REPL,
`main.py` `--print` mode, `server.py` `_run()`) now call it. The 90-line duplication
is gone. Adding a new intent route is now a single edit in `bootstrap.py`.

---

### N4 — `args.get()` returns `None` on `null` LLM argument (latent crash)

`args.get("command", "")` only uses the default when the key is *absent*. When the LLM
passes `{"command": null}`, `args.get("command", "")` returns `None`. This `None` flows
into `judge.approve("run_command", None)` → `classify_command(None)` →
`_normalize_command(None)` → `None.split()` → `AttributeError`.

Same issue in `_handle_scan_lan` (subnet), `_handle_search_kb` (query), and any other
handler with a required string argument.

**Fix:** Replace `args.get("command", "")` with `args.get("command") or ""` in every
tool handler.

**Files touched:** `hal/tools.py` — all `_handle_*` functions.
**Effort:** ~20 min. Do immediately.

---

### N5 — SSH has no connect timeout (slow failure on dead host)

`SSHExecutor._SSH_OPTS` has no `ConnectTimeout`. When the lab host is unreachable
(powered off, network partition), SSH hangs until the subprocess 30-second timeout fires.
The error raised is `subprocess.TimeoutExpired`, not "host unreachable" — unclear failure.

**Fix:** Add `"-o", "ConnectTimeout=5"` to `_SSH_OPTS` in `hal/executor.py`.

**Effort:** ~5 min.

---

### N6 — `_dispatch()` in `agent.py` labeled "legacy" but is the live call path

```python
def _dispatch(...):
    """Compatibility wrapper for legacy tests/imports."""
    return dispatch_tool(...)
```

This 8-line wrapper calls `dispatch_tool()` with no logic. It is the only dispatch call
in `run_agent()`. Labeling it "legacy" makes it look like dead code; it is not.

**Fix:** Replace the `_dispatch()` call in `run_agent()` with a direct `dispatch_tool()`
call. Delete `_dispatch()`.

**Effort:** ~10 min.

---

### N7 — Legacy pipe-format parser in `trust_metrics.py` is dead code

`_parse_legacy_line()` handles a pipe-delimited audit log format that was replaced by
JSON during safety hardening. The JSON format is all that is written today.

**Fix:** Delete `_parse_legacy_line()` and the `_STATUS_NORMALIZE` entries that exist
only for it. Verify no test generates the old format first.

**Effort:** ~30 min.

---

### N8 — `import time` duplicated twice in `VLLMClient.chat_with_tools()`

`time` is imported at function entry, then imported again as `import time as _t` at the
end of the same span block. Classic copy-paste from `chat()`.

**Fix:** Single `import time` at module level in `hal/llm.py`.

**Effort:** 2 min.

---

### N9 — Planner/Critic gate fires on nearly everything

The gate `_should_use_planner_critic()` triggers on:

- any query containing an action verb ("list", "check", "show", "explain", "search", ...)
- any query longer than 7 words

In practice this fires for most non-trivial queries, adding 2 extra 32B inference
calls (potentially 30–90 s total on the RTX 3090 Ti) with no A/B evidence of quality
improvement. The CLAUDE.md itself calls these "pure LLM wrappers" — which is accurate,
but also describes what the base model already does via its instruction tuning.

**Longer-term decision required** (see N10). In the interim, consider raising the word
threshold from 7 → 15 and narrowing the verb set to truly multi-step action verbs
(remove "list", "check", "show", "explain", "search").

---

### N10 — Measure or remove the Planner/Critic sub-agents

The Planner/Critic have been in place as "v1" since their introduction. There is no eval
showing they improve accuracy or reduce tool loop errors. Two options:

**Option A (measure):** Run `eval/run_eval.py` against the current query set with and
without sub-agents (add a `NO_PLANNER_CRITIC=1` env gate). Compare accuracy and latency.
Make a data-driven decision.

**Option B (simplify now):** Remove `hal/agents.py` and the Planner/Critic blocks from
`run_agent()`. Replace with a single system-prompt instruction: *"Before calling tools,
state your plan in 2–3 sentences — what you're checking and why."* Same reasoning
behavior, zero extra LLM calls.

If Option B, delete `hal/agents.py`, remove the 40-line Planner/Critic blocks from
`agent.py`, remove the `PlannerAgent/CriticAgent` imports. The gate heuristic
(`_should_use_planner_critic`) also goes.

**Effort (Option B):** ~1 hr. Requires full eval run before and after to confirm no regression.

---

### N11 — `KnowledgeBase` opens a new DB connection on every `search()` call

No connection pooling. In server mode, a single `/chat` request can open 3–6 psycopg2
connections (KB seed + tool calls + intent embedding path). Under concurrent requests
this creates a connection storm and will eventually hit PostgreSQL's `max_connections`.

**Fix:** Add `psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=4, dsn=...)` as a
module-level pool, reuse it in `KnowledgeBase._connect()`.

**Effort:** ~1 hr.

---

### N12 — `facts.py:remember()` duplicates `KnowledgeBase` DB connection pattern

`hal/facts.py` opens its own psycopg2 connection, calls `register_vector()`, and
manages `conn.close()` in a try/finally — the same pattern as `hal/knowledge.py`, in
a 40-line standalone function. It's `KnowledgeBase.remember()` in disguise.

**Fix:** Move `remember()` into `KnowledgeBase` as a method. Delete `hal/facts.py`.
Update `hal/main.py:cmd_remember()` to call `kb.remember()`.

**Effort:** ~30 min.

---

### N13 — Tool handler 7-argument signature is a hidden context object

Every tool handler takes `(args, executor, judge, kb, prom, ntopng_url, tavily_api_key)`.
Most handlers ignore 4–5 of those arguments (evidenced by `_` prefix on unused params).
This is a context struct disguised as positional arguments.

**Fix:** Define `class ToolContext(NamedTuple)` with these fields. `dispatch_tool()`
constructs it once and passes `ctx`. Handlers become `(args: dict, ctx: ToolContext)`.
Also fixes `run_agent()`'s 14-argument signature (same root cause).

**Effort:** ~2 hr. Medium risk — touches every handler and all tests that mock them.
Wrap existing handler tests first.

---

### N14 — Watchdog silently exits when Prometheus is unreachable

`watchdog.py:run()` does `sys.exit(0)` when `prom.health()` fails: *"not an
alert-worthy failure."* Since the watchdog is a timer, this means a Prometheus outage
silently disables all metric alerts for each 5-minute window until Prometheus recovers.
The operator learns about it only by noticing the absence of alerts.

**Fix:** Change `sys.exit(0)` to log a WARNING to the watchdog log and, if `ntfy_url`
is configured, send a low-urgency ntfy notification: *"Watchdog: Prometheus unreachable
— metric alerts suspended."* Then exit. Recovery is automatic when Prometheus comes back.

**Effort:** ~20 min.

---

### N15 — `NTFY_URL` empty gives no startup warning

`ntfy_url` defaults to `""` with no validation or startup warning. An operator who
forgets to set it receives zero push alerts — silently. Disk-full, GPU-temp, and Falco
events all go nowhere.

**Fix:** Add an `INFO` log at startup in `watchdog.py:run()` when `config.ntfy_url` is
empty: *"NTFY_URL is not set — all alerts will be logged only, no push notifications."*

**Effort:** 5 min.

---

## Test Coverage

486 offline tests passing (Feb 26). Gaps remaining:

| Module | Status |
|---|---|
| `hal/judge.py` | Strong — 716 lines in `test_judge_hardening.py` + `test_judge.py` |
| `hal/web.py` | Strong — 495 lines |
| `hal/memory.py` | Good — add boundary tests for `is_poison_response()` before N2 |
| `hal/agents.py` | Light — low priority if N10 Option B proceeds |
| `harvest/collect.py` | Light — medium risk (nightly job) |
| `hal/intent.py` | Requires live Ollama — freeze a labeled query set before changing examples or threshold |

---

## Confirmed Solid — Do Not Touch Without Tests

- **`hal/judge.py`** — tier classification, evasion detection, git write blocking, path
  canonicalization, self-edit policy, audit logging.
- **`hal/web.py`** — SSRF protection, DNS rebinding defense, URL validation, sanitisation.
- **`hal/memory.py`** — poison filter, prune logic, session management. 92% coverage.

---

## Current Backlog Checklist

### Correctness / safety (do first)

- [x] N4: Fix `args.get() or ""` in all tool handlers (~20 min)
- [x] N5: Add `ConnectTimeout=5` to `SSHExecutor._SSH_OPTS` (~5 min)
- [x] N14: Watchdog ntfy notification on Prometheus unreachable (~20 min)
- [x] N15: Warn on empty `NTFY_URL` at startup (~5 min)

### Structural cleanup (1–2 week horizon)

- [x] N1: Extract `get_system_prompt()` + `setup_clients()` → `hal/bootstrap.py` (~2 hr)
- [ ] N2: Consolidate three tool-call stripping impls → `hal/sanitize.py` (~1.5 hr)
- [x] N3: Extract `dispatch_intent()` shared function (~1 hr)
- [x] N6: Delete `_dispatch()` shim in `agent.py` (~10 min)
- [x] N7: Delete legacy pipe-format parser in `trust_metrics.py` (~30 min)
- [x] N8: Fix double `import time` in `llm.py` (~2 min)
- [ ] N12: Move `facts.py:remember()` into `KnowledgeBase`, delete `facts.py` (~30 min)

### Architecture (month scale, data-driven)

- [ ] N9: Narrow Planner/Critic gate (raise word threshold, tighten verb set)
- [ ] N10: Eval Planner/Critic with/without; decide keep or remove
- [ ] N11: Add psycopg2 `ThreadedConnectionPool` to `KnowledgeBase` (~1 hr)
- [ ] N13: Replace 7-arg tool handler signature with `ToolContext` namedtuple (~2 hr)

### Previously completed (Feb 25)

- [x] C1: Falco noise filter → `hal/falco_noise.py`
- [x] C2: Gate `_extract_tool_calls_from_content` behind `HAL_EXTRACT_FALLBACK`
- [x] C3: Config fail-loud on missing required fields
- [x] H1: Gate PlannerAgent/CriticAgent on query complexity
- [x] H2: Extract tool registry into `hal/tools.py`
- [x] H3: Add latency telemetry to `run_conversational`
- [x] H4: Name `MAX_TOOL_CALLS = 5` constant
- [x] Tests: executor, server, watchdog, prometheus
