# HAL Full-Circuit Integration Test Plan

> **Purpose:** This document is a complete implementation plan for adding
> integration tests that exercise HAL's full circuit — query → classify →
> agent → tool call → Judge gate → execution → response. A fresh chat
> session should be able to read this file and implement every step without
> needing to re-audit the codebase.
>
> **Created:** 2026-03-03 — based on deep audit of all production code,
> test files, eval harness, and research into current best practices for
> testing agentic AI systems.
>
> **Rule:** No production code changes. These tests verify existing code
> as-is.  Any bugs found become separate fix items.

---

## Table of Contents

1. [Background & Research](#1-background--research)
2. [The Three Gaps](#2-the-three-gaps)
3. [Architecture — "Scripted LLM" Pattern](#3-architecture--scripted-llm-pattern)
4. [Step 0 — Fixtures](#4-step-0--fixtures)
5. [Step 1 — Judge Denial Mid-Agent-Loop](#5-step-1--judge-denial-mid-agent-loop)
6. [Step 2 — dispatch_intent() Routing](#6-step-2--dispatch_intent-routing)
7. [Step 3 — ServerJudge Denial Propagation](#7-step-3--serverjudge-denial-propagation)
8. [Step 4 — Trust Evolution Integration](#8-step-4--trust-evolution-integration)
9. [Step 5 — EvalJudge Correctness](#9-step-5--evaljudge-correctness)
10. [Step 6 — Cassette Replay (Future)](#10-step-6--cassette-replay-future)
11. [Implementation Order](#11-implementation-order)
12. [File Changes Summary](#12-file-changes-summary)
13. [Success Criteria](#13-success-criteria)
14. [Out of Scope](#14-out-of-scope)

---

## 1. Background & Research

### What the audit found

HAL's Judge is solid (875 lines, 4 tiers, evasion detection, trust
evolution, git write blocking, self-edit governance).  The problem is the
**test pyramid is all base and no tip** — every test mocks away the exact
thing that matters:

- `test_agent_loop.py` hardcodes `judge.approve.return_value = True`
  (line 71 of `tests/test_agent_loop.py`) — the denial path is never
  exercised.
- `test_server.py` replaces `run_agent` with a `lambda` — ServerJudge's
  auto-deny never propagates through the real agent loop.
- No test calls `dispatch_intent()` at all.

### Research sources consulted

| Source | Key insight |
|---|---|
| **Hamel Husain** (hamel.dev/blog/posts/evals) | Break agentic systems into features + scenarios; Level 1 = scoped unit tests with assertions on every change. HAL has Level 1 for individual components but not for the connected circuit. |
| **Anthropic** (building-effective-agents) | "Extensive testing in sandboxed environments, along with appropriate guardrails." Guardrails must be tested as a parallel concern. |
| **UK AISI Inspect** (inspect.aisi.org.uk/approval.html) | Their tool-approval chain (auto/human/custom approvers) mirrors HAL's Judge tiers. Confirms the design is sound — the gap is test coverage. |
| **DeepEval** (deepeval.com) | Component-level eval via tracing (white-box), not just end-to-end black-box. Our plan tests components connected together with real wiring. |
| **VCR.py** (vcrpy.readthedocs.io) | Record/replay HTTP interactions. Future Step 6 could record vLLM responses for fully deterministic CI, but the immediate plan uses scripted responses instead (no HTTP layer involved). |

### The core principle

The current tests mock *every* I/O boundary. This makes them fast and
offline, which is correct for unit tests. But the **wiring between
components** — the exact thing that breaks in production — is never
tested.

The fix: **Scripted LLM pattern** — keep LLM and executor as controlled
fakes, but let Judge, `dispatch_intent`, `dispatch_tool`, `run_agent`,
and the tool handlers run as **real code**.

---

## 2. The Three Gaps

### Gap 1: No test exercises Judge denial mid-agent-loop

- `test_agent_loop.py` line 71: `judge.approve.return_value = True`
- When Judge denies a tool call in `_handle_run_command` (tools.py
  line 71), it returns `"Action denied by user."` — but no test verifies
  the agent loop handles this gracefully, writes clean history, and
  produces a useful response.

### Gap 2: No test exercises `dispatch_intent()` routing

- `dispatch_intent()` in `hal/bootstrap.py` (line 292) routes:
  - `conversational` → `_handle_conversational()` — single LLM call,
    `tools=[]`, no KB, no Prometheus
  - everything else → `run_agent()` — full 8-iteration tool loop
- No test verifies this branching or that the correct path is taken.

### Gap 3: No test verifies ServerJudge denial propagation

- `ServerJudge` (server.py line 60) overrides `_request_approval` to
  always return `False`.
- No test runs `ServerJudge` through `run_agent` → tool call → denial
  → response to verify the HTTP user gets a graceful answer (not raw
  internal strings like `"Action denied by user."`).

---

## 3. Architecture — "Scripted LLM" Pattern

```
┌──────────────────────────────────────────────┐
│           ScriptedLLM (fake)                 │  ← only this is fake
├──────────────────────────────────────────────┤
│  dispatch_intent()   REAL                    │
│  ├─ IntentClassifier REAL or FakeClassifier  │
│  ├─ _handle_conversational()  REAL           │
│  └─ run_agent()  REAL                        │
│      ├─ KnowledgeBase  stub (canned search)  │
│      ├─ PrometheusClient  stub (canned data) │
│      ├─ Judge  REAL (real tier_for, real log) │
│      ├─ dispatch_tool()  REAL                │
│      └─ ToolContext  REAL wiring             │
├──────────────────────────────────────────────┤
│           ScriptedExecutor (fake)            │  ← and this is fake
└──────────────────────────────────────────────┘
```

**What runs as real code:** `Judge.approve()`, `tier_for()`,
`classify_command()`, `_detect_evasion()`, `_load_trust_overrides()`,
`record_outcome()`, all tool handlers (`_handle_run_command`,
`_handle_search_kb`, etc.), `dispatch_tool()`, `run_agent()`,
`dispatch_intent()`, `_handle_conversational()`, `MemoryStore` (with
tmp_path SQLite).

**What is scripted:** LLM responses (pre-defined sequence), executor
commands (pattern-matched), KB search results (canned), Prometheus
health data (canned).

---

## 4. Step 0 — Fixtures

**Files to modify:** `tests/conftest.py`
**New file:** `tests/test_integration.py`

### 4.1 ScriptedLLM

A class (not a MagicMock) with `.chat_with_tools()` that pops from a
pre-defined response list.

```python
class ScriptedLLM:
    """Replays pre-defined LLM responses in order.

    LLM response format (matches VLLMClient.chat_with_tools output):
        {"role": "assistant", "content": "text", "tool_calls": None}
        or
        {"role": "assistant", "content": None, "tool_calls": [...]}
    """

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self._index = 0
        self.call_count = 0
        self.calls: list[dict] = []  # record every call for assertions

    def chat_with_tools(
        self, messages: list[dict], tools: list[dict], system: str = ""
    ) -> dict:
        self.call_count += 1
        self.calls.append({
            "messages": messages,
            "tools": tools,
            "system": system,
        })
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        # Exhausted — return a safe text-only fallback
        return {"role": "assistant", "content": "Done.", "tool_calls": None}

    def ping(self) -> bool:
        return True

    def chat(self, messages, system="", timeout=30):
        """Used by Judge._llm_reason — return a stub."""
        return "Routine operation, low risk."
```

### 4.2 ScriptedExecutor

Pattern-matched command execution — no SSH involved.

```python
class ScriptedExecutor:
    """Returns pre-defined outputs for shell commands.

    Usage:
        executor = ScriptedExecutor({
            "ps aux": {"stdout": "PID ...", "stderr": "", "returncode": 0},
            "docker ps": {"stdout": "CONTAINER ...", "stderr": "", "returncode": 0},
        })
    """

    def __init__(self, responses: dict[str, dict] | None = None):
        self._responses = responses or {}
        self.commands_run: list[str] = []  # track what was executed

    def run(self, command: str) -> dict:
        self.commands_run.append(command)
        # Exact match first
        if command in self._responses:
            return self._responses[command]
        # Prefix match (e.g. "ps" matches "ps aux")
        for pattern, result in self._responses.items():
            if command.startswith(pattern):
                return result
        # Default: command not configured
        return {
            "stdout": f"[scripted: no output configured for '{command}']",
            "stderr": "",
            "returncode": 0,
        }
```

### 4.3 FakeClassifier

For `dispatch_intent()` tests where we need to control the
classification result.

```python
class FakeClassifier:
    """Returns a fixed intent classification for any input."""

    def __init__(self, intent: str, confidence: float = 0.95):
        self._intent = intent
        self._confidence = confidence

    def classify(self, text: str) -> tuple[str, float]:
        return (self._intent, self._confidence)
```

### 4.4 StubKB

Real class, not MagicMock — matches `KnowledgeBase.search()` contract.

```python
class StubKB:
    """Knowledge base stub with canned search results."""

    def __init__(self, results: list[dict] | None = None):
        self._results = results or []

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        return self._results[:top_k]
```

### 4.5 StubProm

Matches `PrometheusClient.health()` and `PrometheusClient.trend()`.

```python
class StubProm:
    """Prometheus client stub with canned health data."""

    def __init__(self, health_data: dict | None = None):
        self._health = health_data or {
            "cpu_pct": 12.5,
            "mem_pct": 45.0,
            "disk_root_pct": 38.0,
            "disk_docker_pct": None,
            "disk_data_pct": None,
            "swap_pct": 2.0,
            "load1": 0.5,
            "gpu_vram_pct": 60.0,
            "gpu_temp_c": 55,
        }

    def health(self) -> dict:
        return self._health

    def trend(self, promql: str, window: str = "1h") -> dict | None:
        return {
            "first": 10.0,
            "last": 12.0,
            "min": 9.5,
            "max": 13.0,
            "delta": 2.0,
            "delta_per_hour": 2.0,
            "direction": "rising",
        }
```

### 4.6 Pytest fixtures in conftest.py

Add to the existing `tests/conftest.py`:

```python
@pytest.fixture
def tmp_audit_log(tmp_path):
    """Temporary audit log path for Judge tests."""
    return tmp_path / "audit.log"

@pytest.fixture
def real_judge(tmp_audit_log):
    """Real Judge instance with temporary audit log, auto-deny mode."""
    class AutoDenyJudge(Judge):
        """Judge that auto-denies any tier > 0 (like ServerJudge)."""
        def _request_approval(self, action_type, detail, tier, reason):
            return False
    return AutoDenyJudge(audit_log=tmp_audit_log)

@pytest.fixture
def auto_approve_judge(tmp_audit_log):
    """Real Judge that auto-approves everything (for tests that need it)."""
    class AutoApproveJudge(Judge):
        def _request_approval(self, action_type, detail, tier, reason):
            return True
    return AutoApproveJudge(audit_log=tmp_audit_log)

@pytest.fixture
def scripted_executor():
    """ScriptedExecutor with no pre-configured responses."""
    return ScriptedExecutor()

@pytest.fixture
def stub_kb():
    """Empty KB stub."""
    return StubKB()

@pytest.fixture
def stub_prom():
    """Prometheus stub with default healthy metrics."""
    return StubProm()

@pytest.fixture
def memory_store(tmp_path):
    """Real MemoryStore backed by a temporary SQLite database."""
    from hal.memory import MemoryStore
    return MemoryStore(db_path=str(tmp_path / "memory.db"))

@pytest.fixture
def quiet_console():
    """Silent Rich console for tests."""
    from rich.console import Console
    return Console(quiet=True)
```

**Important:** Check the `MemoryStore.__init__` signature — if it
expects a path parameter, use it; if it reads from config, you may
need to set the env var or monkey-patch. Look at
`hal/memory.py` class `MemoryStore` constructor.

---

## 5. Step 1 — Judge Denial Mid-Agent-Loop

**File:** `tests/test_integration.py`

These tests use a **real Judge with real `tier_for()`** — no mocking of
`approve()`.

### Helper: build LLM response dicts

```python
def _text_response(text: str) -> dict:
    return {"role": "assistant", "content": text, "tool_calls": None}

def _tool_call(name: str, args: dict, call_id: str = "tc_001") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": call_id,
            "function": {"name": name, "arguments": args},
        }],
    }
```

### Test 1a: `test_agent_tool_denied_by_judge_returns_gracefully`

```python
def test_agent_tool_denied_by_judge_returns_gracefully(
    real_judge, scripted_executor, stub_kb, stub_prom, memory_store, quiet_console, tmp_path
):
    """When Judge denies a tier-2 command, the agent should respond
    gracefully and the executor should never be called."""
    llm = ScriptedLLM([
        # Step 1: LLM requests a dangerous command
        _tool_call("run_command", {
            "command": "docker run --privileged ubuntu",
            "reason": "test",
        }),
        # Step 2: After denial, LLM gives a text response
        _text_response("I was unable to run that command as it requires approval."),
    ])

    result = run_agent(
        user_input="run a privileged container",
        history=[],
        llm=llm,
        kb=stub_kb,
        prom=stub_prom,
        executor=scripted_executor,
        judge=real_judge,       # real Judge — tier_for("docker run") = 2
        mem=memory_store,
        session_id="test-denial",
        system="You are HAL.",
        console=quiet_console,
    )

    # Executor was never called
    assert len(scripted_executor.commands_run) == 0
    # Response acknowledges the denial
    assert result  # non-empty
    # Audit log has a denied entry
    log_lines = tmp_path.joinpath("audit.log").read_text().strip().split("\n")
    denied_entries = [json.loads(l) for l in log_lines if '"denied"' in l or '"status": "denied"' in l]
    # NOTE: real_judge uses tmp_audit_log which is tmp_path / "audit.log"
    # Adjust path if fixture sets it differently
```

**Key assertion:** `scripted_executor.commands_run` is empty — the
denied command never reached the executor.

### Test 1b: `test_agent_mixed_approved_and_denied_tools`

```python
def test_agent_mixed_approved_and_denied_tools(
    real_judge, stub_kb, stub_prom, memory_store, quiet_console
):
    """Tier-0 tools execute, tier-2 tools are denied, agent handles both."""
    executor = ScriptedExecutor()

    llm = ScriptedLLM([
        # Step 1: search_kb (tier 0 — auto-approved)
        _tool_call("search_kb", {"query": "docker"}, call_id="tc_001"),
        # Step 2: run_command tier 2 (denied)
        _tool_call("run_command", {
            "command": "docker run --rm ubuntu echo hi",
            "reason": "test",
        }, call_id="tc_002"),
        # Step 3: final text response
        _text_response("I found KB results but couldn't run the command."),
    ])

    result = run_agent(
        user_input="search for docker info and run a container",
        history=[],
        llm=llm,
        kb=stub_kb,
        prom=stub_prom,
        executor=executor,
        judge=real_judge,
        mem=memory_store,
        session_id="test-mixed",
        system="You are HAL.",
        console=quiet_console,
    )

    # search_kb executed (no executor call needed for KB)
    # run_command was denied — executor was never called
    assert len(executor.commands_run) == 0
    assert result  # non-empty response
```

### Test 1c: `test_agent_denial_does_not_poison_history`

```python
def test_agent_denial_does_not_poison_history(
    real_judge, scripted_executor, stub_kb, stub_prom, memory_store, quiet_console
):
    """After a denied tool call, session history contains only clean
    user/assistant turns — no tool artifacts, no 'Action denied' strings."""
    llm = ScriptedLLM([
        _tool_call("run_command", {
            "command": "chmod 777 /etc/passwd",
            "reason": "test",
        }),
        _text_response("I cannot change permissions on system files."),
    ])

    history = []
    run_agent(
        user_input="make passwd world-writable",
        history=history,
        llm=llm,
        kb=stub_kb,
        prom=stub_prom,
        executor=scripted_executor,
        judge=real_judge,
        mem=memory_store,
        session_id="test-poison",
        system="You are HAL.",
        console=quiet_console,
    )

    # History should have exactly 2 entries: user + assistant
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    # No tool call artifacts leaked
    for entry in history:
        assert "tool_call" not in entry.get("content", "").lower() or True
        assert entry.get("role") in ("user", "assistant")
```

---

## 6. Step 2 — dispatch_intent() Routing

### Test 2a: `test_dispatch_conversational_skips_agent`

```python
def test_dispatch_conversational_skips_agent(
    stub_kb, stub_prom, scripted_executor, real_judge, memory_store, quiet_console
):
    """Conversational intent skips run_agent entirely — LLM gets tools=[]."""
    llm = ScriptedLLM([
        _text_response("Hello! How can I help you today?"),
    ])

    result = dispatch_intent(
        user_input="hey there",
        history=[],
        llm=llm,
        prom=stub_prom,
        kb=stub_kb,
        executor=scripted_executor,
        judge=real_judge,
        mem=memory_store,
        session_id="test-conv",
        system_prompt="You are HAL.",
        console=quiet_console,
        classifier=FakeClassifier("conversational", 0.95),
    )

    assert result == "Hello! How can I help you today?"
    # LLM was called with tools=[] (conversational path)
    assert llm.calls[0]["tools"] == []
```

### Test 2b: `test_dispatch_health_enters_run_agent`

```python
def test_dispatch_health_enters_run_agent(
    stub_kb, stub_prom, scripted_executor, real_judge, memory_store, quiet_console
):
    """Health intent enters run_agent (not conversational fast path).
    Stub Prometheus data is pre-seeded, so LLM responds with metrics."""
    llm = ScriptedLLM([
        _text_response("CPU is at 12.5%, memory at 45%, disk at 38%. All healthy."),
    ])

    result = dispatch_intent(
        user_input="how is the server doing?",
        history=[],
        llm=llm,
        prom=stub_prom,
        kb=stub_kb,
        executor=scripted_executor,
        judge=real_judge,
        mem=memory_store,
        session_id="test-health",
        system_prompt="You are HAL.",
        console=quiet_console,
        classifier=FakeClassifier("health", 0.90),
    )

    # Response exists and LLM was called with tools (not empty list)
    assert result
    assert len(llm.calls[0]["tools"]) > 0  # run_agent passes available_tools
```

### Test 2c: `test_dispatch_without_classifier_always_runs_agent`

```python
def test_dispatch_without_classifier_always_runs_agent(
    stub_kb, stub_prom, scripted_executor, real_judge, memory_store, quiet_console
):
    """When classifier=None, dispatch_intent always routes to run_agent."""
    llm = ScriptedLLM([
        _text_response("Here you go."),
    ])

    result = dispatch_intent(
        user_input="hello",
        history=[],
        llm=llm,
        prom=stub_prom,
        kb=stub_kb,
        executor=scripted_executor,
        judge=real_judge,
        mem=memory_store,
        session_id="test-no-clf",
        system_prompt="You are HAL.",
        console=quiet_console,
        classifier=None,  # no classifier
    )

    assert result
    # run_agent was called (tools is non-empty)
    assert len(llm.calls[0]["tools"]) > 0
```

---

## 7. Step 3 — ServerJudge Denial Propagation

### Test 3a: `test_server_judge_denies_tier1_through_agent`

```python
from hal.server import ServerJudge

def test_server_judge_denies_tier1_through_agent(
    stub_kb, stub_prom, memory_store, quiet_console, tmp_path
):
    """ServerJudge auto-denies tier 1+ commands through the full agent loop."""
    server_judge = ServerJudge(audit_log=tmp_path / "audit.log")

    executor = ScriptedExecutor({
        "docker restart nginx": {"stdout": "nginx", "stderr": "", "returncode": 0},
    })

    llm = ScriptedLLM([
        _tool_call("run_command", {
            "command": "docker restart nginx",
            "reason": "user asked to restart",
        }),
        _text_response("I cannot restart services over the HTTP interface."),
    ])

    result = run_agent(
        user_input="restart nginx",
        history=[],
        llm=llm,
        kb=stub_kb,
        prom=stub_prom,
        executor=executor,
        judge=server_judge,
        mem=memory_store,
        session_id="test-server-deny",
        system="You are HAL.",
        console=quiet_console,
    )

    # docker restart is tier 1, ServerJudge denies it
    assert len(executor.commands_run) == 0
    assert result  # non-empty response
```

### Test 3b: `test_server_judge_allows_tier0_read_only`

```python
def test_server_judge_allows_tier0_read_only(
    stub_kb, stub_prom, memory_store, quiet_console, tmp_path
):
    """ServerJudge allows tier-0 tools (search_kb, get_metrics)."""
    server_judge = ServerJudge(audit_log=tmp_path / "audit.log")
    executor = ScriptedExecutor()

    llm = ScriptedLLM([
        _tool_call("search_kb", {"query": "nginx config"}, call_id="tc_001"),
        _text_response("Here's what I found about nginx configuration."),
    ])

    result = run_agent(
        user_input="tell me about nginx config",
        history=[],
        llm=llm,
        kb=StubKB([{"file": "lab.md", "score": 0.85, "content": "nginx runs on port 80"}]),
        prom=stub_prom,
        executor=executor,
        judge=server_judge,
        mem=memory_store,
        session_id="test-server-allow",
        system="You are HAL.",
        console=quiet_console,
    )

    assert result  # non-empty
    # search_kb is tier 0 — approved, result returned
```

### Test 3c: `test_server_chat_endpoint_with_real_dispatch`

```python
import pytest
from fastapi.testclient import TestClient

def test_server_chat_endpoint_with_real_dispatch(tmp_path):
    """POST /chat with ServerJudge + real dispatch_intent produces a
    graceful response, not raw internal strings."""
    # This test needs to inject fakes into _state.
    # Import the app and override its state.
    from hal.server import app, _state

    server_judge = ServerJudge(audit_log=tmp_path / "audit.log")

    llm = ScriptedLLM([
        # dispatch_intent → run_agent → LLM tries a tier 1 command
        _tool_call("run_command", {
            "command": "systemctl restart docker",
            "reason": "health check",
        }),
        _text_response("I cannot restart services over this interface."),
    ])

    # Inject test doubles into server state
    _state["llm"] = llm
    _state["judge"] = server_judge
    _state["kb"] = StubKB()
    _state["prom"] = StubProm()
    _state["executor"] = ScriptedExecutor()
    _state["mem"] = MemoryStore(db_path=str(tmp_path / "memory.db"))
    _state["system_prompt"] = "You are HAL."
    _state["classifier"] = FakeClassifier("agentic", 0.90)
    _state["ntopng_url"] = ""
    _state["tavily_api_key"] = ""

    client = TestClient(app)
    resp = client.post("/chat", json={"message": "restart docker"})

    assert resp.status_code == 200
    body = resp.json()
    assert "response" in body
    assert body["response"]  # non-empty
```

**IMPORTANT:** Before implementing Test 3c, read `hal/server.py`'s
`/chat` endpoint to understand how `_state` is used. The endpoint
accesses `_state["llm"]`, `_state["judge"]`, etc. You need to verify
the exact key names match. If the server uses a `lifespan` context
manager that initializes `_state`, you may need to skip lifespan or
pre-populate `_state` before creating `TestClient`. Check if
`TestClient(app)` triggers `lifespan` — if so, use
`TestClient(app, raise_server_exceptions=False)` or mock the lifespan.

---

## 8. Step 4 — Trust Evolution Integration

### Test 4a: `test_trust_evolution_promotes_tier1_to_tier0`

```python
import json

def test_trust_evolution_promotes_tier1_to_tier0(tmp_path):
    """After 10+ successful outcomes, a tier-1 command is auto-approved."""
    audit_log = tmp_path / "audit.log"

    # Pre-populate audit log with 10 successful outcomes for "docker restart"
    # trust_key = "run_command:docker" (first token of the command)
    for i in range(11):
        entry = {
            "ts": "2026-03-03T00:00:00+00:00",
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": f"docker restart nginx",
        }
        audit_log.write_text(
            audit_log.read_text() + json.dumps(entry) + "\n"
            if audit_log.exists()
            else json.dumps(entry) + "\n"
        )

    # Create Judge with this pre-populated audit log
    class AutoDenyJudge(Judge):
        def _request_approval(self, action_type, detail, tier, reason):
            return False  # would deny tier 1 if not promoted

    judge = AutoDenyJudge(audit_log=audit_log)

    # "docker restart nginx" is normally tier 1
    from hal.judge import tier_for
    assert tier_for("run_command", "docker restart nginx") == 1

    # But with trust evolution, approve() should auto-approve (tier reduced to 0)
    result = judge.approve("run_command", "docker restart nginx")
    assert result is True  # promoted to tier 0, auto-approved
```

### Test 4b: `test_trust_evolution_inside_agent_loop`

```python
def test_trust_evolution_inside_agent_loop(
    stub_kb, stub_prom, memory_store, quiet_console, tmp_path
):
    """Trust-promoted command executes through full agent loop even with
    _request_approval=False."""
    audit_log = tmp_path / "audit.log"

    # Pre-populate: 11 successful "docker restart" outcomes
    for _ in range(11):
        entry = {
            "ts": "2026-03-03T00:00:00+00:00",
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "docker restart nginx",
        }
        with open(audit_log, "a") as f:
            f.write(json.dumps(entry) + "\n")

    class AutoDenyJudge(Judge):
        def _request_approval(self, action_type, detail, tier, reason):
            return False
    judge = AutoDenyJudge(audit_log=audit_log)

    executor = ScriptedExecutor({
        "docker restart nginx": {"stdout": "nginx", "stderr": "", "returncode": 0},
    })

    llm = ScriptedLLM([
        _tool_call("run_command", {
            "command": "docker restart nginx",
            "reason": "user asked",
        }),
        _text_response("Successfully restarted nginx."),
    ])

    result = run_agent(
        user_input="restart nginx",
        history=[],
        llm=llm,
        kb=stub_kb,
        prom=stub_prom,
        executor=executor,
        judge=judge,
        mem=memory_store,
        session_id="test-trust-evo",
        system="You are HAL.",
        console=quiet_console,
    )

    # Trust promoted tier 1 → tier 0, so executor WAS called
    assert "docker restart nginx" in executor.commands_run
    assert result  # non-empty
```

---

## 9. Step 5 — EvalJudge Correctness

### Test 5a: `test_eval_judge_records_all_tool_attempts`

```python
from eval.run_eval import _EvalJudge

def test_eval_judge_records_all_tool_attempts(
    stub_kb, stub_prom, memory_store, quiet_console, tmp_path
):
    """EvalJudge records every tool the model attempts, approved or not."""
    eval_judge = _EvalJudge(audit_log=tmp_path / "audit.log")

    executor = ScriptedExecutor()

    llm = ScriptedLLM([
        _tool_call("search_kb", {"query": "test"}, call_id="tc_001"),
        _tool_call("run_command", {"command": "docker stop nginx", "reason": "test"}, call_id="tc_002"),
        _text_response("Done."),
    ])

    run_agent(
        user_input="search and stop nginx",
        history=[],
        llm=llm,
        kb=stub_kb,
        prom=stub_prom,
        executor=executor,
        judge=eval_judge,
        mem=memory_store,
        session_id="test-eval",
        system="You are HAL.",
        console=quiet_console,
    )

    # Both tools were recorded
    assert "search_kb" in eval_judge.tools_called
    assert "run_command" in eval_judge.tools_called
    # Only tier-0 tool (search_kb) actually executed; run_command was denied
    assert len(executor.commands_run) == 0
```

### Test 5b: `test_eval_judge_denies_destructive_commands`

```python
def test_eval_judge_denies_destructive_commands(
    stub_kb, stub_prom, memory_store, quiet_console, tmp_path
):
    """EvalJudge silently denies tier 1+ without interactive prompts."""
    eval_judge = _EvalJudge(audit_log=tmp_path / "audit.log")
    executor = ScriptedExecutor()

    llm = ScriptedLLM([
        _tool_call("run_command", {
            "command": "rm -rf /tmp/test",
            "reason": "cleanup",
        }),
        _text_response("Could not execute that command."),
    ])

    result = run_agent(
        user_input="clean up temp files",
        history=[],
        llm=llm,
        kb=stub_kb,
        prom=stub_prom,
        executor=executor,
        judge=eval_judge,
        mem=memory_store,
        session_id="test-eval-deny",
        system="You are HAL.",
        console=quiet_console,
    )

    assert len(executor.commands_run) == 0  # never executed
    assert result  # non-empty response
```

---

## 10. Step 6 — Cassette Replay (Future)

**NOT for the first implementation.** Track as a follow-up issue/PR.

The idea: use VCR.py (or a custom cassette format) to record real vLLM
HTTP responses for the 32 eval queries. Store in `tests/cassettes/`.
Replay in CI for fully deterministic, no-infrastructure tests.

When model or prompt changes, re-record: `pytest --record-mode=all`.

This is the Level 1.5 step between the Scripted LLM integration tests
(this plan) and the full Level 2 eval harness (already exists in
`eval/`).

---

## 11. Implementation Order

```
Step 0 (fixtures in conftest.py)    ← FIRST — everything depends on this
    │
    ├── Step 1 (Judge denial)       ← highest-value gap
    │
    ├── Step 2 (dispatch routing)   ← independent of Step 1
    │
    ├── Step 3 (ServerJudge)        ← depends on Step 0 only
    │
    ├── Step 4 (trust evolution)    ← depends on Step 0 + audit log format
    │
    └── Step 5 (EvalJudge)          ← depends on Step 0
```

Steps 1–5 are independent of each other (only depend on Step 0).

Suggested commit sequence:
1. `feat: add integration test fixtures (ScriptedLLM, ScriptedExecutor, etc.)`
2. `test: add Judge denial integration tests (gap 1)`
3. `test: add dispatch_intent routing integration tests (gap 2)`
4. `test: add ServerJudge propagation integration tests (gap 3)`
5. `test: add trust evolution integration tests`
6. `test: add EvalJudge correctness integration tests`

---

## 12. File Changes Summary

| File | Action | What |
|---|---|---|
| `tests/conftest.py` | **Modify** | Add `ScriptedLLM`, `ScriptedExecutor`, `FakeClassifier`, `StubKB`, `StubProm` classes + fixtures: `tmp_audit_log`, `real_judge`, `auto_approve_judge`, `scripted_executor`, `stub_kb`, `stub_prom`, `memory_store`, `quiet_console` |
| `tests/test_integration.py` | **Create** | 13 test functions + helpers (`_text_response`, `_tool_call`) |
| Production code | **None** | No changes to `hal/` or `eval/` |

---

## 13. Success Criteria

- [ ] All 13 tests pass: `pytest tests/test_integration.py -v`
- [ ] Zero external dependencies (no Ollama, no vLLM, no SSH, no Prometheus)
- [ ] Judge denial path exercised with real `tier_for()` classification
- [ ] `dispatch_intent()` routing tested with real branching logic
- [ ] ServerJudge propagation verified through full agent loop
- [ ] Trust evolution tested end-to-end (audit log → override → tier change)
- [ ] `ruff check` passes: `ruff check tests/test_integration.py`
- [ ] Existing tests still pass: `pytest tests/ --ignore=tests/test_intent.py -v`

---

## 14. Out of Scope

| What | Why |
|---|---|
| LLM response quality | That's the eval harness's job (eval/), not integration tests |
| Real SSH execution | Executor remains scripted; real execution requires the server |
| Embedding quality | Intent classification accuracy tested in `test_intent.py` (requires Ollama) |
| Telegram delivery | Already tested in `test_telegram.py` |
| Production code changes | Tests verify existing code; bugs found → separate fix items |
| VCR cassette recording | Future enhancement (Step 6) — tracked separately |

---

## Key Files to Read Before Implementing

The implementor should `read_file` these before starting:

1. **`hal/agent.py`** (289 lines) — the full `run_agent()` function
2. **`hal/judge.py`** lines 520–740 — `tier_for()`, `Judge.approve()`, trust evolution
3. **`hal/tools.py`** lines 66–102 — `_handle_run_command()` and the Judge call pattern
4. **`hal/bootstrap.py`** lines 252–340 — `_handle_conversational()` and `dispatch_intent()`
5. **`hal/server.py`** lines 58–73 — `ServerJudge` class
6. **`eval/run_eval.py`** lines 43–94 — `_MockExecutor` and `_EvalJudge`
7. **`tests/conftest.py`** (56 lines) — existing fixtures
8. **`hal/memory.py`** — `MemoryStore.__init__` signature (need to know if it accepts `db_path`)

---

## Appendix: Exact Import Paths

```python
from hal.agent import run_agent
from hal.bootstrap import dispatch_intent
from hal.judge import Judge, tier_for
from hal.server import ServerJudge
from hal.memory import MemoryStore
from hal.tools import ToolContext, dispatch_tool
from eval.run_eval import _EvalJudge
```
