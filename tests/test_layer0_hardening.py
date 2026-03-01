"""Layer 0 hardening contract tests.

These tests verify the specific reliability properties implemented on the
reliability/layer-0 branch. They are NOT happy-path tests — they test that
specific failure modes that existed in the old codebase cannot recur.

Run with: pytest tests/test_layer0_hardening.py -v
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

from hal.agent import run_agent
from hal.bootstrap import dispatch_intent


def _make_console() -> Console:
    """Suppress Rich output during tests."""
    return Console(quiet=True)


# ---------------------------------------------------------------------------
# H-1: LLM error must not write to session history
# ---------------------------------------------------------------------------


def test_llm_error_does_not_write_to_history():
    """LLM failure must not poison session history.

    # why this test exists: before Item 1, if llm.chat_with_tools() raised,
    # the exception was caught at a higher level and the error string was
    # sometimes saved as an assistant turn.  On the next query, the model saw
    # its own error message as a prior response and kept referencing it —
    # every subsequent turn in the session was corrupted.
    #
    # The fix (agent.py:108-119): early-return on LLM exception BEFORE the
    # history.append() / mem.save_turn() calls at lines 229-232.
    # This test is the machine-checkable proof that the fix cannot regress.

    Verified against agent.py:
      - LLM exception caught at line 108
      - Returns f"LLM unavailable: {e}" at line 113  (before any history write)
      - history.append() is at lines 229-230  (only reached on clean exit)
      - mem.save_turn() is at lines 231-232    (only reached on clean exit)
    """
    llm = MagicMock()
    # why: every call to the LLM raises — simulates model offline / network down
    llm.chat_with_tools.side_effect = RuntimeError("model offline")

    kb = MagicMock()
    kb.search.return_value = []  # no KB context so the error is isolated to the LLM

    mem = MagicMock()
    # why: pass a real list so we can inspect it after — unlike _call_run_agent
    # in test_agent_loop.py which creates history internally and discards it
    history: list[dict] = []

    result = run_agent(
        user_input="what is the disk usage?",
        history=history,
        llm=llm,
        kb=kb,
        prom=MagicMock(),
        executor=MagicMock(),
        judge=MagicMock(),
        mem=mem,
        session_id="hardening-test",
        system="You are HAL.",
        console=_make_console(),
    )

    # The error must be surfaced to the caller (not silently swallowed)
    # why: exact prefix matches agent.py line 113: f"LLM unavailable: {e}"
    assert result.startswith("LLM unavailable:"), (
        f"Expected 'LLM unavailable: ...' but got: {result!r}"
    )

    # The history list must be untouched
    # why: history.append() at agent.py:229-230 is only reached after the
    # for-loop exits normally; the early-return at line 119 bypasses it
    assert history == [], (
        f"history was mutated on LLM error — poison bug has regressed: {history}"
    )

    # mem.save_turn must never have been called
    # why: save_turn() at agent.py:231-232 is only reached on clean exit;
    # calling it with an error string would corrupt the SQLite session
    mem.save_turn.assert_not_called()


# ---------------------------------------------------------------------------
# H-2: Layer 0 core files must not import from hal._unlocked
# ---------------------------------------------------------------------------


def test_layer0_core_files_do_not_import_unlocked():
    """The hal/ core boundary must be enforced at the import level.

    # why this test exists: Items 1-5 moved 10 modules to hal/_unlocked/ to
    # make the Layer 0 trust boundary visible.  But if a developer accidentally
    # adds 'from hal._unlocked.foo import bar' to a core file, the boundary
    # is silently breached — a bug in a locked module can then corrupt Layer 0
    # at runtime without any obvious signal.
    #
    # This test makes the boundary machine-checkable.  To graduate a module
    # back to Layer 0: git mv hal/_unlocked/foo.py hal/foo.py, update imports,
    # run this test — it will pass cleanly without any exemptions required.

    Scans every *.py file directly in hal/ (not in subdirectories) for any
    reference to hal._unlocked.  hal/_unlocked/ itself is not scanned.
    """
    hal_dir = Path(__file__).parent.parent / "hal"

    # why: glob("*.py") matches only files directly in hal/, not in _unlocked/
    # or any other subdirectory — so _unlocked files importing each other
    # correctly do not appear here
    core_files = sorted(hal_dir.glob("*.py"))
    assert core_files, "No core files found — check that hal_dir path is correct"

    violations: list[str] = []
    for f in core_files:
        source = f.read_text(encoding="utf-8")
        # why: check only import lines — docstrings and comments that mention
        # _unlocked for documentation purposes (e.g. tools.py module docstring)
        # must not trigger a false positive
        import_lines = [
            line
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from ")) and "_unlocked" in line
        ]
        if import_lines:
            violations.append(f.name)

    assert violations == [], (
        "Core Layer 0 files import from hal._unlocked — trust boundary breached:\n"
        + "\n".join(f"  hal/{v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# L1-H1: Conversational queries must call no tools
# ---------------------------------------------------------------------------


def test_conversational_query_calls_no_tools():
    """Conversational intent must bypass the tool loop entirely.

    # why this test exists: _handle_conversational() calls chat_with_tools()
    # with tools=[] — but if someone accidentally changes this, greetings would
    # trigger Prometheus queries, KB searches, and multiple LLM round-trips.
    # This test is the machine-readable guarantee that the conversational path
    # is a zero-tool path forever.
    #
    # Verified against bootstrap.py:
    #   - dispatch_intent() calls classifier.classify() → "conversational"
    #   - routes to _handle_conversational()
    #   - _handle_conversational() calls llm.chat_with_tools(working, [], ...)
    #   - prom and kb are never referenced in that path
    """
    llm = MagicMock()
    # why: return a plain dict — VLLMClient.chat_with_tools returns a dict with "content"
    llm.chat_with_tools.return_value = {"role": "assistant", "content": "Hello there!"}
    prom = MagicMock()
    kb = MagicMock()
    mem = MagicMock()
    classifier = MagicMock()
    # why: force conversational routing regardless of the actual query text
    classifier.classify.return_value = ("conversational", 0.9)

    history: list[dict] = []
    result = dispatch_intent(
        "hello",
        history,
        llm,
        prom,
        kb,
        MagicMock(),
        MagicMock(),
        mem,
        "l1-test",
        "You are HAL.",
        _make_console(),
        classifier=classifier,
    )

    assert result == "Hello there!"

    # Prometheus and KB must never be touched on a conversational turn
    # why: conversational turns need no live metrics and no knowledge lookup;
    # touching them adds latency and can corrupt the response
    prom.health.assert_not_called()
    kb.search.assert_not_called()

    # The LLM must have been called with an empty tools list
    # why: passing tools=[] is what prevents tool calls from happening;
    # if tools were non-empty the LLM could call get_metrics or search_kb
    tools_arg = llm.chat_with_tools.call_args[0][1]  # second positional arg
    assert tools_arg == [], (
        f"Conversational path must call LLM with tools=[], got: {tools_arg!r}"
    )


# ---------------------------------------------------------------------------
# L2-H1: Health queries must use Prometheus snapshot, not the tool loop
# ---------------------------------------------------------------------------


def test_health_query_routes_to_run_agent_with_metrics_seeded():
    """Health intent enters run_agent with metrics pre-seeded and full tool access.

    # why this test exists (Track A regression guard): health-classified queries must
    # enter run_agent so the LLM has tool access for boundary queries. Simple status
    # questions resolve in iteration 1 because the Prometheus snapshot is already in
    # context; boundary questions ("is the vLLM config causing memory pressure?")
    # can call read_file or search_kb without hitting a tools=[] gate.
    #
    # This replaces test_health_query_uses_prometheus_not_tool_loop which tested the
    # now-removed _handle_health() path. See ROADMAP.md (architectural backlog section).
    #
    # Verified against bootstrap.py + agent.py:
    #   - dispatch_intent() routes health intent to run_agent() (not _handle_health)
    #   - run_agent() calls prom.health() for metrics pre-seed before first LLM call
    #   - run_agent() calls llm.chat_with_tools(working, available_tools, ...) — tools != []
    """
    llm = MagicMock()
    llm.chat_with_tools.return_value = {"role": "assistant", "content": "All good."}
    prom = MagicMock()
    prom.health.return_value = {
        "cpu_pct": 12.3,
        "mem_pct": 45.6,
        "disk_root_pct": 30.0,
        "disk_docker_pct": 55.0,
        "disk_data_pct": 20.0,
        "swap_pct": 1.0,
        "load1": 0.5,
        "gpu_vram_pct": 80.0,
        "gpu_temp_c": 65.0,
    }
    kb = MagicMock()
    # why: no KB hits expected for a status query; metrics pre-seed is the context
    kb.search.return_value = []
    mem = MagicMock()
    classifier = MagicMock()
    # why: force health routing regardless of the actual query text
    classifier.classify.return_value = ("health", 0.92)

    result = dispatch_intent(
        "how is the server doing?",
        [],
        llm,
        prom,
        kb,
        MagicMock(),
        MagicMock(),
        mem,
        "l2-test",
        "You are HAL.",
        _make_console(),
        classifier=classifier,
    )

    assert result == "All good."

    # Prometheus must have been queried for the metrics pre-seed
    prom.health.assert_called_once()

    # LLM must be called with a NON-EMPTY tools list — health queries must have tool access.
    # why: this is the core Track A guarantee. If this assertion fails, a tools=[] gate
    # was re-introduced on the health path and boundary queries will get shallow answers.
    tools_arg = llm.chat_with_tools.call_args[0][1]
    assert tools_arg != [], (
        "Health path must have tool access (tools != []). "
        "A tools=[] gate was re-introduced — see ROADMAP.md (architectural backlog section)."
    )

    # The metrics snapshot must appear in the augmented user message.
    # why: pre-seeding avoids a get_metrics tool call for simple status queries;
    # the LLM sees the snapshot immediately and can answer in one iteration.
    # Note: search by role — working list is mutated post-call (assistant msg appended),
    # so [-1] would return the assistant reply, not the user message.
    all_msgs = llm.chat_with_tools.call_args_list[0][0][0]
    augmented_user = next(m["content"] for m in all_msgs if m.get("role") == "user")
    assert "cpu=12.3%" in augmented_user, (
        f"Expected metrics snapshot in augmented user message, got: {augmented_user!r}"
    )


# ---------------------------------------------------------------------------
# L2-H2: Prometheus failure on health path must fall back to run_agent
# ---------------------------------------------------------------------------


def test_health_prometheus_failure_falls_back_to_agent():
    """If Prometheus raises, health path must fall back to the full agent loop.

    # why this test exists: when Prometheus is down, _handle_health() returns None
    # and dispatch_intent() must fall through to run_agent() rather than returning
    # an empty or misleading response.  run_agent() can call get_metrics, detect
    # the failure, and explain it to the user — _handle_health() cannot.
    #
    # Verified against bootstrap.py:
    #   - _handle_health() returns None on prom.health() exception
    #   - dispatch_intent() checks `if result is not None` before returning
    #   - falls through to run_agent() when result is None
    """
    llm = MagicMock()
    # why: run_agent will also call the LLM; return a valid response so the test
    # doesn't fail on the agent loop's own LLM interaction
    llm.chat_with_tools.return_value = {
        "role": "assistant",
        "content": "Prometheus is unreachable.",
    }
    prom = MagicMock()
    # why: simulate Prometheus being completely down
    prom.health.side_effect = ConnectionError("Prometheus unreachable")
    prom.query.return_value = None  # get_metrics tool also fails gracefully
    kb = MagicMock()
    kb.search.return_value = []
    mem = MagicMock()
    classifier = MagicMock()
    classifier.classify.return_value = ("health", 0.88)

    dispatch_intent(
        "is the server healthy?",
        [],
        llm,
        prom,
        kb,
        MagicMock(),
        MagicMock(),
        mem,
        "l2-fallback-test",
        "You are HAL.",
        _make_console(),
        classifier=classifier,
    )

    # prom.health was attempted (and failed)
    prom.health.assert_called_once()

    # run_agent was entered — it will call llm.chat_with_tools at least once
    # why: if the fallback didn't happen, llm would never be called
    # (prom.health raised before the LLM call in _handle_health)
    llm.chat_with_tools.assert_called()


# ---------------------------------------------------------------------------
# L2-H3: Fact queries must use KB context, not the tool loop
# ---------------------------------------------------------------------------


def test_fact_query_routes_to_run_agent_with_kb_seeded():
    """Fact intent enters run_agent with KB context pre-seeded and full tool access.

    # why this test exists (Track A regression guard): fact-classified queries must
    # enter run_agent so the LLM has tool access. Simple documented facts resolve
    # from the KB pre-seed in iteration 1; queries that need live data can use
    # get_metrics or run_command without hitting a tools=[] gate.
    #
    # This replaces test_fact_query_uses_kb_not_tool_loop which tested the
    # now-removed _handle_fact() path. See ROADMAP.md (architectural backlog section).
    #
    # Verified against bootstrap.py + agent.py:
    #   - dispatch_intent() routes fact intent to run_agent() (not _handle_fact)
    #   - run_agent() calls kb.search() for KB pre-seed; score 0.82 >= 0.75 threshold
    #   - run_agent() calls prom.health() for metrics pre-seed
    #   - run_agent() calls llm.chat_with_tools(working, available_tools, ...) — tools != []
    """
    llm = MagicMock()
    llm.chat_with_tools.return_value = {
        "role": "assistant",
        "content": "Prometheus runs on port 9091.",
    }
    prom = MagicMock()
    # why: metrics pre-seed runs for all non-conversational queries in run_agent;
    # provide a real dict so the snapshot formats cleanly in the context message.
    prom.health.return_value = {
        "cpu_pct": 10.0,
        "mem_pct": 40.0,
        "disk_root_pct": 30.0,
        "disk_docker_pct": 50.0,
        "disk_data_pct": 20.0,
        "swap_pct": 1.0,
        "load1": 0.4,
        "gpu_vram_pct": 75.0,
        "gpu_temp_c": 60.0,
    }
    kb = MagicMock()
    # score 0.82 is above the 0.75 pre-seed threshold — chunk will be injected
    kb.search.return_value = [
        {"content": "Prometheus: port 9091", "file": "services.md", "score": 0.82},
    ]
    mem = MagicMock()
    classifier = MagicMock()
    # why: force fact routing regardless of the actual query text
    classifier.classify.return_value = ("fact", 0.91)

    result = dispatch_intent(
        "what port does prometheus run on?",
        [],
        llm,
        prom,
        kb,
        MagicMock(),
        MagicMock(),
        mem,
        "l2-fact-test",
        "You are HAL.",
        _make_console(),
        classifier=classifier,
    )

    assert result == "Prometheus runs on port 9091."
    kb.search.assert_called()

    # LLM must be called with a NON-EMPTY tools list — fact queries must have tool access.
    # why: this is the core Track A guarantee. If this assertion fails, a tools=[] gate
    # was re-introduced on the fact path and boundary queries will get shallow answers.
    tools_arg = llm.chat_with_tools.call_args[0][1]
    assert tools_arg != [], (
        "Fact path must have tool access (tools != []). "
        "A tools=[] gate was re-introduced — see ROADMAP.md (architectural backlog section)."
    )

    # KB context must have been injected into the augmented user message.
    # why: pre-seeding avoids a search_kb tool call for simple factual queries;
    # the LLM sees the relevant chunk immediately and can answer in one iteration.
    # Note: search by role — working list is mutated post-call (assistant msg appended),
    # so [-1] would return the assistant reply, not the user message.
    all_msgs = llm.chat_with_tools.call_args_list[0][0][0]
    augmented_user = next(m["content"] for m in all_msgs if m.get("role") == "user")
    assert "Prometheus: port 9091" in augmented_user, (
        f"Expected KB chunk in augmented user message, got: {augmented_user!r}"
    )


# ---------------------------------------------------------------------------
# L2-H4: Fact path with no KB hits must fall back to run_agent
# ---------------------------------------------------------------------------


def test_fact_no_kb_hits_falls_back_to_agent():
    """If KB search returns no results above threshold, fact path must fall back.

    # why this test exists: _handle_fact() returns None when all scores are below
    # 0.5.  dispatch_intent() must then fall through to run_agent() — not return
    # an empty or hallucinated answer.
    #
    # Verified against bootstrap.py:
    #   - _handle_fact() returns None when hits list is empty after threshold filter
    #   - dispatch_intent() checks `if result is not None` before returning
    #   - falls through to run_agent() when result is None
    """
    llm = MagicMock()
    llm.chat_with_tools.return_value = {
        "role": "assistant",
        "content": "I couldn't find that in the KB.",
    }
    prom = MagicMock()
    kb = MagicMock()
    # why: scores all below 0.5 threshold — no confident KB match
    kb.search.return_value = [
        {"content": "unrelated chunk", "file": "other.md", "score": 0.3},
    ]
    mem = MagicMock()
    classifier = MagicMock()
    classifier.classify.return_value = ("fact", 0.78)

    dispatch_intent(
        "what is the wifi password?",
        [],
        llm,
        prom,
        kb,
        MagicMock(),
        MagicMock(),
        mem,
        "l2-fact-fallback",
        "You are HAL.",
        _make_console(),
        classifier=classifier,
    )

    assert kb.search.called
    # run_agent was entered — LLM was called at least once
    # why: if fallback didn't happen, LLM would not be called
    # (_handle_fact returns None before reaching llm.chat_with_tools)
    # note: assert_called_once() not used — run_agent also calls kb.search
    llm.chat_with_tools.assert_called()


# ---------------------------------------------------------------------------
# L1-H2: Ollama failure must fall back to agentic gracefully
# ---------------------------------------------------------------------------


def test_ollama_failure_falls_back_to_agentic():
    """IntentClassifier must degrade to agentic routing when Ollama is unavailable.

    # why this test exists: IntentClassifier._build() embeds all example sentences
    # at startup using Ollama. If Ollama is down, _build() must catch the exception
    # and set _ready=False — NOT raise. classify() must then return ("agentic", 0.0)
    # without touching Ollama at all, so HAL continues to work for all queries.
    #
    # Without this contract, an Ollama restart would silently break every query
    # (HAL would crash on classify()) rather than just losing intent routing.
    #
    # Verified against intent.py:
    #   - _build() catches Exception at ~line 173, sets _ready=False (logs warning)
    #   - classify() returns ("agentic", 0.0) at ~line 193 when not self._ready
    """
    from hal.intent import IntentClassifier

    ollama = MagicMock()
    # why: every embed() call raises — simulates Ollama completely unreachable
    ollama.embed.side_effect = ConnectionError("Ollama is not running")

    # __init__ calls _build() which will hit the ConnectionError and set _ready=False
    # why: we construct a real IntentClassifier to test the actual fallback code path,
    # not a mock — mocking it would not prove the fallback works
    classifier = IntentClassifier(ollama)

    assert not classifier._ready, (
        "Expected classifier._ready=False after Ollama failure during _build(), "
        "but _ready is True — exception was not caught"
    )

    # classify() must return the agentic fallback, not raise
    # why: if classify() raises, every query while Ollama is down would crash HAL
    intent, confidence = classifier.classify("what is the CPU usage?")

    assert intent == "agentic", (
        f"Expected 'agentic' fallback when classifier not ready, got: {intent!r}"
    )
    assert confidence == 0.0, (
        f"Expected confidence=0.0 for fallback, got: {confidence!r}"
    )
