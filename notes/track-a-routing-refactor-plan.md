<!-- markdownlint-disable MD032 MD040 -->
# Track A — 2-Path Routing Refactor: Full Plan

**Created:** 2026-02-28  
**Branch target:** `feat/routing-refactor` (cut from `main`)  
**Approval gate:** Operator must approve each Item individually before implementation.

---

## ⚠️ CURRENT POSITION (read this first after any context reset)

**Branch:** `feat/routing-refactor`  
**Last commit:** `359b55e` — `feat(routing): binary dispatch + metrics pre-seed in run_agent`  
**Test status:** 558 passed, 0 failed, lint clean  
**Working tree:** clean (one unrelated unstaged file: `notes/new_02-26-26`)  

**Item 1 is done. Item 2 is next and requires operator approval before any code change.**

Item 2 proposal is in section 3 below. The exact files and lines to delete are
called out there. Do not proceed past reading until the operator says "Item 2 approved".

---

## 1. What the problem actually is

### The claim in the task description

> "Boundary queries like 'is the vLLM config causing the memory pressure?' land
> on health, get a shallow answer with no tools available."

### Why that description is exactly right

`dispatch_intent()` in `hal/bootstrap.py` (lines 395–457) routes to one of four
paths based on what `IntentClassifier.classify()` returns. The health and fact
paths call their own LLM invocation with an explicit empty tool list:

```python
# _handle_health (line 332)
msg = llm.chat_with_tools(working, [], system=system_prompt)

# _handle_fact (line 285)
msg = llm.chat_with_tools(working, [], system=system_prompt)
```

The `[]` is not an oversight — it was a deliberate optimisation: "this query
only needs a metric snapshot / KB chunk, no tools needed." That reasoning is
correct for the happy path. It is **wrong for boundary queries** where the
initial context raises a follow-up question that requires a tool to answer.

"Is the vLLM config causing memory pressure?" looks like `health` to the
classifier because it mentions memory pressure. The health handler fetches a
Prometheus snapshot (CPU, mem, VRAM etc.) and calls the LLM with no tools. The
LLM sees that VRAM is 91% and wants to read `/etc/systemd/user/vllm.service` to
check the `--gpu-memory-utilization` flag — but it cannot. It has no `read_file`
tool. So it either hallucinates a config value or says "I'd need to check the
config for that." Both are wrong answers.

The fallback to `run_agent` only fires when Prometheus is **unreachable**, not
when the answer turns out to be insufficient. That means boundary queries are
silently degraded — the operator never knows a tool was needed.

### Why the existing fallback structure does not solve it

```python
if intent == "health":
    result = _handle_health(...)
    if result is not None:        # ← only None when Prometheus is down
        return result
# falls through to run_agent only on Prometheus outage
```

The fallback is a resilience mechanism (graceful degradation when Prometheus is
down), not a quality mechanism. It has no way to know whether the LLM's answer
was good.

---

## 2. The correct fix and why

### Core insight

`_handle_health` and `_handle_fact` do **two unrelated things**:

1. **Pre-seed context**: fetch a metrics snapshot or KB chunks and inject them
   into the first user message.
2. **Invoke the LLM with no tools and return the result**.

Step 1 is valuable and should be preserved — it saves one tool-call iteration
for simple queries. Step 2 is the constraint that causes the bug. The fix is to
keep step 1 and discard step 2 by letting `run_agent` own the LLM invocation
(which it already does, with full tool access).

`run_agent` already does KB pre-seeding at lines 68–84 of `hal/agent.py`:

```python
chunks = kb.search(user_input, top_k=3)
for c in chunks:
    if c["score"] >= 0.75:
        context_lines.append(...)
if context_lines:
    sections.append("KB context:\n" + context_str)
```

Adding metrics pre-seeding alongside that is symmetric: one `prom.health()` call
at iteration 0, inject the snapshot into `sections[]`. Total added cost: one
cheap HTTP call. The LLM sees the snapshot for free and still has all tools
available if it needs them.

For simple health queries ("how's CPU?") the LLM will see the metric snapshot
and answer directly in iteration 1 without calling a tool — identical quality to
today's health handler, zero regression. For boundary queries it can call
`read_file` or `get_metrics` or `search_kb` — which it could not before.

### What does NOT change

- `_handle_conversational()` is untouched. Conversational routing remains a
  separate fast path — it correctly needs no tools and no context. This is the
  one route that is unambiguously right as-is.
- The `IntentClassifier` itself is untouched. The health/fact example sentences
  remain useful as training signal for future classification work (Track B uses
  them for outcome correlation). Removing them would be premature.
- `MAX_ITERATIONS`, `MAX_TOOL_CALLS`, and all other agent loop constants are
  untouched.
- The KB pre-seed threshold (`0.75`) in `run_agent` is untouched.
- All 10 tool handlers in `hal/tools.py` are untouched.

---

## 3. Backlog — full item list

Each item is one logical change = one commit = one approval.

### Item 1 — Binary routing + metrics pre-seed in run_agent ✅ DONE

**Commit:** `359b55e` — `feat(routing): binary dispatch + metrics pre-seed in run_agent`  
**Branch:** `feat/routing-refactor`  
**Result:** 558 passed, lint clean, all pre-commit hooks passed.

**Files:** `hal/bootstrap.py` + `hal/agent.py` + `tests/test_agent_loop.py` + `tests/test_layer0_hardening.py`  
**What changed:**

In `dispatch_intent()`:
- Remove the `if intent == "health":` block (lines 429–436).
- Remove the `if intent == "fact":` block (lines 437–448).
- Keep the `if intent == "conversational":` block exactly as-is.
- The final `return run_agent(...)` call becomes the path for health, fact, AND
  agentic — i.e., everything that is not conversational.

In `run_agent()`:
- After the existing KB pre-seed block (lines 68–84), add a metrics pre-seed
  block:
  - Call `prom.health()` inside a try/except (Prometheus may be down).
  - If it succeeds, format the snapshot string (same format as `_handle_health`
    does today) and append it to `sections[]` before `sections.append("User
    query:\n" + user_input)`.
  - If it fails, silently skip (run_agent can still call `get_metrics` as a
    tool on iteration 1 if needed).
- The `prom: PrometheusClient` argument already exists in `run_agent`'s
  signature — no signature change needed.

**Acceptance criteria:**
- `558 passed, 0 failed` (test count does not drop).
- `make lint` clean.
- Smoke: `"how's the cpu?"` → correct answer in ≤1 iteration.
- Smoke: `"what port does prometheus run on?"` → correct answer from KB context.
- Smoke: `"is the vllm config causing the memory pressure?"` → LLM can call
  `read_file` or `search_kb` in the response; it is not blocked.

**Risk:** Low. The change removes decision code and adds one pre-seed call. The
LLM path is structurally identical to what health/fact queries already fall back
to when Prometheus/KB is unavailable.

---

### Item 2 — Remove dead _handle_health and _handle_fact functions ← NEXT (awaiting approval)

**Root cause:** `_handle_health()` (lines 298–358) and `_handle_fact()` (lines 240–296)
in `hal/bootstrap.py` are now unreachable — `dispatch_intent()` no longer routes to them
after Item 1. Dead code misleads future readers and will silently diverge from any
future changes to `run_agent`.

**Files:** `hal/bootstrap.py` only  
**Why this is a separate item:** After Item 1 merges, `_handle_health()` and
`_handle_fact()` are unreachable. They are not deleted in Item 1 because:
1. One change at a time — confirming Item 1 works first reduces blast radius.
2. If Item 1 reveals an unexpected regression, restoring the old routing is
   trivial if the handlers still exist.

**What changes:**
- Delete `_handle_health()` (lines 298–358, approx 60 lines).
- Delete `_handle_fact()` (lines 240–296, approx 56 lines).
- The imports they relied on exclusively (none — all imports are shared with
  `_handle_conversational` and `run_agent`) remain.

**Acceptance criteria:**
- `558 passed, 0 failed`.
- `make lint` clean (no unused import warnings — ruff will catch these).
- `grep -n "_handle_health\|_handle_fact" hal/bootstrap.py` returns 0 matches.

---

### Item 3 — Update CLAUDE.md "Current State" routing table

**Files:** `CLAUDE.md`  
**Why:** CLAUDE.md "Current State" section still lists the 4-route table. After
Items 1+2 it drifts from reality. Updating it is part of the one-change-per-
commit discipline — documentation must match code at every merge point.

**What changes:**
- In the "Agent loop" bullet, change the 4-route list to 2 routes:
  - `conversational` → `_handle_conversational()` — unchanged, fast path
  - everything else → `run_agent()` — full tool loop, KB + metrics pre-seeded
- Add a note: "health/fact seeding happens inside `run_agent` as context
  injection, not as hard routing gates."
- Remove the description of `_handle_health()` and `_handle_fact()` as they
  will no longer exist.

**Acceptance criteria:**
- `make lint-md` passes on CLAUDE.md specifically (or the pre-existing errors
  in other files are the only remaining violations).
- No factual drift introduced.

---

### Item 4 — Add regression tests for boundary routing

**Files:** `tests/test_agent_loop.py` (new test cases)  
**Why:** The current test suite has no test that verifies a health-classified or
fact-classified boundary query has tool access. Without this test, Item 1's
guarantee is an assertion in comments, not in CI. This is the test that prevents
a future refactor from accidentally re-introducing `tools=[]` on a fast path.

**What to add:**

Test A — health boundary:
- Patch `IntentClassifier.classify` to return `("health", 0.9)`.
- Patch `prom.health()` to return a metrics dict.
- Patch `llm.chat_with_tools` to return a tool call on iteration 1 (e.g.
  `read_file`) and a text answer on iteration 2.
- Assert that `dispatch_intent` calls the tool (i.e., `chat_with_tools` was
  called with a non-empty tools list).
- **This test would have FAILED before Item 1** — that is its value as a
  regression guard.

Test B — fact boundary:
- Same structure but `classify` returns `("fact", 0.9)`.
- Patch KB to return no chunks above threshold (simulating a miss).
- Assert tool call is possible in the response.

**Acceptance criteria:**
- Both new tests pass.
- Full suite still `558 + N passed, 0 failed`.

---

## 4. Execution sequence with reasoning

```text
main (clean, 558 tests passing)
  └─ feat/routing-refactor
        ├─ Item 1: binary routing + metrics pre-seed  ✔️ 359b55e
        ├─ Item 2: delete dead handlers              ← HERE (awaiting approval)
        ├─ Item 3: update CLAUDE.md
        └─ Item 4: add regression tests
```

The order is deliberate:

- **Item 1 before Item 2**: If Item 1 reveals a problem, the old handlers are
  still present and can be re-wired in one line. Deleting them first would make
  rollback a recovery operation rather than a revert.
- **Item 3 after Items 1+2**: Documentation is updated to match the final code
  state, not an in-progress state. Otherwise CLAUDE.md would describe a
  partially-complete architecture.
- **Item 4 last**: Tests are added against the final state so they validate the
  full change, not an intermediate form. Adding tests first would require
  patching them twice (once to make them pass with the old code, once for the
  new code).

---

## 5. What Track A does NOT do (important)

To prevent scope creep, these are explicitly out of scope for this Track:

- **No change to the intent classifier or its examples.** Classification quality
  is a separate concern. The routing refactor makes classification less
  consequential (a misclassified health query no longer loses tool access) but
  does not fix classifier accuracy.
- **No change to the conversational fast path.** It is correct as-is.
- **No change to MAX_ITERATIONS (8) or MAX_TOOL_CALLS (5).** These are separate
  tuning concerns.
- **No eval harness changes.** The existing `eval/queries.jsonl` covers both
  health and fact categories. Running `python -m eval.run_eval` before and after
  Item 1 is the validation, not a change to the harness itself.
- **No change to `_handle_conversational`.** Converting that to also use
  `run_agent` would regress latency on greetings — out of scope.

---

## 6. Next steps after Track A (pointer only)

Once `feat/routing-refactor` is merged into `main`:

- **Track C (system prompt templating)** becomes the next priority. The work is
  in `hal/bootstrap.py` `get_system_prompt()` (lines 39–229). The ~190-line
  hardcoded string has ~15 values that can drift from `hal/config.py` and the
  live lab state. Track C replaces those with f-string interpolation from
  `cfg.Config` fields, keeping the static policy/rules sections as curated
  literal text.
- **Track B (trust evolution)** follows Track C. It reads `audit.log` outcome
  history from `hal/judge.py`'s JSON log and lowers tier for proven-safe
  tool+arg patterns. It needs a stable routing layer (Track A) and a stable
  system prompt (Track C) before its own behavior baselines are meaningful.

---

## 7. Approval checkpoint

**Item 1 is done.** Awaiting approval for **Item 2**.

To approve Item 2: reply "Item 2 approved" or equivalent. I will then:

1. Delete `_handle_fact()` (lines 240–296 of `hal/bootstrap.py`).
2. Delete `_handle_health()` (lines 298–358 of `hal/bootstrap.py`).
3. Run `pytest tests/ --ignore=tests/test_intent.py -q` and `make lint`.
4. Verify `grep -n "_handle_health\|_handle_fact" hal/bootstrap.py` returns 0 matches.
5. Commit: `refactor(routing): remove dead _handle_health and _handle_fact`.
6. Present result and Item 3 proposal (CLAUDE.md update).

After Items 2 and 3 are done, Item 4 adds the explicit boundary-query regression
tests (health/fact-classified queries must have `tools != []`). Then
`feat/routing-refactor` is ready to merge into `main`.
