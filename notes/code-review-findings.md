# Code Review Findings — Feb 25–26, 2026

*Full architectural review done by Copilot (two passes: Feb 25 structural, Feb 26 deep
audit). This note captures actionable findings only. See ROADMAP.md for the strategic
backlog.*

---

## Summary verdict

### Grade: B+ / A−

Architecture is clean. Security model (Judge) is production-quality. Documentation is
unusually good. All structural coupling issues resolved Feb 26. Remaining open items
are architecture-scale decisions (Planner/Critic eval, connection pooling) that
require live server measurements before acting.

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

### ~~N2 — Three implementations of the same tool-call stripping logic~~ ✅ DONE

`hal/sanitize.py` created with `is_tool_call_artifact(text) -> bool` and
`strip_tool_call_artifacts(text) -> str`. `TOOL_CALL_FENCE_RE` defined once there.
`agent.py:_strip_tool_artifacts()`, `server.py:_strip_tool_call_blocks()`, and the
inline logic in `memory.py:is_poison_response()` all deleted; callers delegate to
`sanitize.py`. Coverage improved: `agent.py` now strips fenced hallucinations
(previously only bare objects); `server.py` now strips bare-object hallucinations
(previously only fences). `is_poison_response()` kept as a one-liner wrapper.

---

### ~~N3 — Intent dispatch block copy-pasted three times~~ ✅ DONE

`dispatch_intent()` added to `hal/bootstrap.py`. All three call sites (`main.py` REPL,
`main.py` `--print` mode, `server.py` `_run()`) now call it. The 90-line duplication
is gone. Adding a new intent route is now a single edit in `bootstrap.py`.

---

### ~~N4 — `args.get()` returns `None` on `null` LLM argument (latent crash)~~ ✅ DONE

All `args.get("key", "")` patterns replaced with `args.get("key") or ""` in every
`_handle_*` function in `hal/tools.py`.

---

### ~~N5 — SSH has no connect timeout (slow failure on dead host)~~ ✅ DONE

`"-o", "ConnectTimeout=5"` added to `SSHExecutor._SSH_OPTS` in `hal/executor.py`.

---

### ~~N6 — `_dispatch()` in `agent.py` labeled "legacy" but is the live call path~~ ✅ DONE

`_dispatch()` deleted. `run_agent()` calls `dispatch_tool()` directly.

---

### ~~N7 — Legacy pipe-format parser in `trust_metrics.py` is dead code~~ ✅ DONE

`_parse_legacy_line()` deleted. `_STATUS_NORMALIZE` whitespace-padded entries removed.
`_parse_line()` now only processes `{`-prefixed lines. Test fixture updated to JSON format.

---

### ~~N8 — `import time` duplicated twice in `VLLMClient.chat_with_tools()`~~ ✅ DONE

Single `import time` at module level in `hal/llm.py`. Four inline imports removed.

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

### ~~N12 — `facts.py:remember()` duplicates `KnowledgeBase` DB connection pattern~~ ✅ DONE

`KnowledgeBase.remember(fact)` added to `hal/knowledge.py`. `hal/facts.py` deleted.
`cmd_remember()` in `main.py` calls `kb.remember()` — no more separate DSN/embed args.
4 new tests in `test_knowledge.py`.

---

### ~~N13 — Tool handler 7-argument signature is a hidden context object~~ ✅ DONE

`class ToolContext(NamedTuple)` added to `hal/tools.py` with fields `executor`, `judge`,
`kb`, `prom`, `ntopng_url`, `tavily_api_key`. All 16 `_handle_*` functions now take
`(args: dict, ctx: ToolContext)`. `dispatch_tool()` accepts `ctx: ToolContext`.
`run_agent()` constructs one `ToolContext` per turn. Adding a new shared dependency is
now one line in `ToolContext` + one line at the construction site.

---

### ~~N14 — Watchdog silently exits when Prometheus is unreachable~~ ✅ DONE

`sys.exit(0)` on Prometheus failure replaced with a WARNING log + low-urgency ntfy
notification: *"Watchdog: Prometheus unreachable — metric alerts suspended."*

---

### ~~N15 — `NTFY_URL` empty gives no startup warning~~ ✅ DONE

INFO log added at startup when `config.ntfy_url` is empty.

---

## Test Coverage

534 offline tests passing (Feb 26). Gaps remaining:

| Module | Status |
|---|---------|
| `hal/judge.py` | Strong — 716 lines in `test_judge_hardening.py` + `test_judge.py` |
| `hal/web.py` | Strong — 495 lines |
| `hal/memory.py` | Good — poison filter, prune, session. `is_poison_response` delegates to `sanitize.py` |
| `hal/sanitize.py` | Good — covered via `test_agent_loop.py`, `test_server.py`, `test_memory.py` |
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
- [x] N2: Consolidate three tool-call stripping impls → `hal/sanitize.py` (~1.5 hr)
- [x] N3: Extract `dispatch_intent()` shared function (~1 hr)
- [x] N6: Delete `_dispatch()` shim in `agent.py` (~10 min)
- [x] N7: Delete legacy pipe-format parser in `trust_metrics.py` (~30 min)
- [x] N8: Fix double `import time` in `llm.py` (~2 min)
- [x] N12: Move `facts.py:remember()` into `KnowledgeBase`, delete `facts.py` (~30 min)

### Architecture (month scale, data-driven)

- [ ] N9: Narrow Planner/Critic gate (raise word threshold, tighten verb set)
- [ ] N10: Eval Planner/Critic with/without; decide keep or remove
- [ ] N11: Add psycopg2 `ThreadedConnectionPool` to `KnowledgeBase` (~1 hr)
- [x] N13: Replace 7-arg tool handler signature with `ToolContext` namedtuple (~2 hr)

### Previously completed (Feb 25)

- [x] C1: Falco noise filter → `hal/falco_noise.py`
- [x] C2: Gate `_extract_tool_calls_from_content` behind `HAL_EXTRACT_FALLBACK`
- [x] C3: Config fail-loud on missing required fields
- [x] H1: Gate PlannerAgent/CriticAgent on query complexity
- [x] H2: Extract tool registry into `hal/tools.py`
- [x] H3: Add latency telemetry to `run_conversational`
- [x] H4: Name `MAX_TOOL_CALLS = 5` constant
- [x] Tests: executor, server, watchdog, prometheus
