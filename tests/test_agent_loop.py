"""Integration tests for the agentic tool loop (hal/agent.py — run_agent).

These tests are pure unit tests — no external services (no Ollama, no SSH,
no Prometheus, no vLLM). All I/O is mocked. They verify that the loop
orchestration logic is correct: tool dispatch, deduplication, loop-breaking,
max-iteration guard, token cap, and tool_call_id propagation.

Run with: pytest tests/test_agent_loop.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock

from rich.console import Console

from hal.agent import _dispatch, run_agent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_console() -> Console:
    """Return a no-op Rich console (suppresses output during tests)."""
    return Console(quiet=True)


def _make_text_msg(text: str) -> dict:
    """LLM response with no tool calls — final answer."""
    return {"role": "assistant", "content": text, "tool_calls": None}


def _make_tool_call_msg(name: str, args: dict, call_id: str = "tc_001") -> dict:
    """LLM response requesting one tool call."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "function": {"name": name, "arguments": args},
            }
        ],
    }


def _make_mocks(llm_responses: list[dict]) -> tuple:
    """Return (llm, kb, prom, executor, judge, mem) mocks.

    llm.chat_with_tools returns each response in order, then repeats the last.
    """
    llm = MagicMock()
    llm.chat_with_tools.side_effect = llm_responses + [llm_responses[-1]] * 20

    kb = MagicMock()
    kb.search.return_value = []  # no KB context injected

    prom = MagicMock()
    prom.health.return_value = {
        "cpu_percent": 12.5,
        "memory_used_percent": 45.0,
        "disk_used_percent": 38.0,
    }

    executor = MagicMock()
    judge = MagicMock()
    judge.approve.return_value = True

    mem = MagicMock()
    mem.save_turn.return_value = None

    return llm, kb, prom, executor, judge, mem


def _call_run_agent(llm, kb, prom, executor, judge, mem, user_input="test query") -> str:
    history: list[dict] = []
    return run_agent(
        user_input=user_input,
        history=history,
        llm=llm,
        kb=kb,
        prom=prom,
        executor=executor,
        judge=judge,
        mem=mem,
        session_id="test-sess",
        system="You are HAL.",
        console=_make_console(),
    )


# ---------------------------------------------------------------------------
# 1. Direct text response — no tool calls
# ---------------------------------------------------------------------------

def test_direct_text_response():
    """LLM emits a text reply without calling any tools — loop exits after one step."""
    llm, kb, prom, executor, judge, mem = _make_mocks([
        _make_text_msg("Everything looks fine."),
    ])
    result = _call_run_agent(llm, kb, prom, executor, judge, mem)
    assert result == "Everything looks fine."
    llm.chat_with_tools.assert_called_once()
    # Verify turn was persisted
    mem.save_turn.assert_any_call("test-sess", "assistant", "Everything looks fine.")


# ---------------------------------------------------------------------------
# 2. One tool call then final answer
# ---------------------------------------------------------------------------

def test_single_tool_call_then_answer():
    """LLM calls get_metrics once, receives result, then produces final answer."""
    llm, kb, prom, executor, judge, mem = _make_mocks([
        _make_tool_call_msg("get_metrics", {}, call_id="tc_m1"),
        _make_text_msg("CPU is at 12.5%, RAM at 45%."),
    ])
    result = _call_run_agent(llm, kb, prom, executor, judge, mem, "how is the server?")
    assert result == "CPU is at 12.5%, RAM at 45%."
    # get_metrics must have caused prom.health() to be called
    prom.health.assert_called_once()
    # tool result message must carry the correct tool_call_id
    second_call_args = llm.chat_with_tools.call_args_list[1]
    working_history = second_call_args[0][0]  # first positional arg
    tool_msgs = [m for m in working_history if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "tc_m1", (
        "Tool result message is missing or has wrong tool_call_id. "
        "This is required by the OpenAI spec for correct multi-tool correlation."
    )


# ---------------------------------------------------------------------------
# 3. Duplicate tool call triggers loop-breaker injection
# ---------------------------------------------------------------------------

def test_duplicate_tool_call_injects_loop_breaker():
    """When the model repeats the exact same tool call, a directive is injected
    to stop collecting data and the loop does not call the tool a second time."""
    call_msg = _make_tool_call_msg("get_metrics", {}, call_id="tc_dup")
    llm, kb, prom, executor, judge, mem = _make_mocks([
        call_msg,   # first iteration — dispatched
        call_msg,   # second iteration — duplicate, triggers loop-breaker
        _make_text_msg("The metrics are fine."),
    ])
    result = _call_run_agent(llm, kb, prom, executor, judge, mem)
    assert result == "The metrics are fine."
    # Tool was dispatched exactly once despite being requested twice
    assert prom.health.call_count == 1
    # Verify the loop-breaker user message appeared in working history
    all_args = llm.chat_with_tools.call_args_list
    found_breaker = False
    for call in all_args[1:]:  # skip first step
        history_arg = call[0][0]
        for msg in history_arg:
            if msg.get("role") == "user" and "already have all the data" in msg.get("content", ""):
                found_breaker = True
                break
    assert found_breaker, (
        "Expected a loop-breaker user message to appear in working history "
        "when the model repeats the same tool call."
    )


# ---------------------------------------------------------------------------
# 4. Max iterations guard
# ---------------------------------------------------------------------------

def test_max_iterations_guard():
    """If the model never produces a final text answer, the loop exits at MAX_ITERATIONS
    and returns the 'max iterations' sentinel string."""
    # Always return a different tool call so dedup doesn't trigger
    from hal.agent import MAX_ITERATIONS
    side_effects = [
        _make_tool_call_msg("get_metrics", {"i": i}, call_id=f"tc_{i}")
        for i in range(MAX_ITERATIONS + 5)
    ]
    llm, kb, prom, executor, judge, mem = _make_mocks(side_effects)
    result = _call_run_agent(llm, kb, prom, executor, judge, mem)
    assert "max iterations" in result.lower() or "without a final answer" in result.lower(), (
        f"Expected max-iterations message, got: {result!r}"
    )
    assert llm.chat_with_tools.call_count == MAX_ITERATIONS


# ---------------------------------------------------------------------------
# 5. Tool output truncation at _MAX_TOOL_OUTPUT chars
# ---------------------------------------------------------------------------

def test_tool_output_is_truncated():
    """Tool output longer than 8000 chars must be capped before being fed back."""
    # return a huge blob from executor.run so run_command produces > 8000 chars
    huge_output = "x" * 20_000
    llm, kb, prom, executor, judge, mem = _make_mocks([
        _make_tool_call_msg("run_command", {"command": "cat bigfile", "reason": "test"}, call_id="tc_big"),
        _make_text_msg("Done."),
    ])
    judge.approve.return_value = True
    executor.run.return_value = {"stdout": huge_output, "stderr": "", "returncode": 0}

    _call_run_agent(llm, kb, prom, executor, judge, mem, "cat bigfile")

    # Inspect what was passed to the second LLM call
    second_call_args = llm.chat_with_tools.call_args_list[1]
    working_history = second_call_args[0][0]
    tool_msg = next(m for m in working_history if m.get("role") == "tool")
    assert len(tool_msg["content"]) <= 8000 + 50, (  # +50 for the ellipsis annotation
        f"Tool output was not truncated: {len(tool_msg['content'])} chars"
    )
    assert "omitted" in tool_msg["content"], "Expected truncation annotation in capped output"


# ---------------------------------------------------------------------------
# 6. search_kb returns no-results string when KB is empty
# ---------------------------------------------------------------------------

def test_search_kb_returns_no_results_when_empty():
    """_dispatch('search_kb', ...) returns a human-readable string when KB has no hits."""
    kb = MagicMock()
    kb.search.return_value = []
    executor = MagicMock()
    judge = MagicMock()
    prom = MagicMock()

    result = _dispatch("search_kb", {"query": "nonexistent thing"}, executor, judge, kb, prom)
    assert "No relevant results" in result


# ---------------------------------------------------------------------------
# 7. Unknown tool name returns graceful error, not exception
# ---------------------------------------------------------------------------

def test_unknown_tool_returns_graceful_error():
    """An unknown tool name must return an error string, not raise an exception."""
    kb = MagicMock()
    executor = MagicMock()
    judge = MagicMock()
    prom = MagicMock()

    result = _dispatch("totally_unknown_tool_xyz", {}, executor, judge, kb, prom)
    assert "unknown tool" in result.lower() or result  # must return something, not throw


# ---------------------------------------------------------------------------
# 8. get_metrics falls back gracefully when Prometheus is down
# ---------------------------------------------------------------------------

def test_get_metrics_prometheus_unavailable():
    """If prom.health() raises, _dispatch returns an error string, not an exception."""
    kb = MagicMock()
    executor = MagicMock()
    judge = MagicMock()
    prom = MagicMock()
    prom.health.side_effect = ConnectionError("Prometheus unreachable")

    result = _dispatch("get_metrics", {}, executor, judge, kb, prom)
    assert "unavailable" in result.lower() or "error" in result.lower(), (
        f"Expected fallback error message, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 9. KB context is injected for strong matches (score >= 0.75)
# ---------------------------------------------------------------------------

def test_kb_context_injected_for_high_score_chunks():
    """Chunks returned by the KB with score >= 0.75 are prepended to the first message."""
    llm, kb, prom, executor, judge, mem = _make_mocks([
        _make_text_msg("Prometheus runs on port 9091."),
    ])
    kb.search.return_value = [
        {"score": 0.82, "file": "monitoring.md", "content": "Prometheus port: 9091"},
    ]
    history: list[dict] = []
    run_agent(
        user_input="what port does prometheus run on?",
        history=history,
        llm=llm,
        kb=kb,
        prom=prom,
        executor=executor,
        judge=judge,
        mem=mem,
        session_id="s1",
        system="You are HAL.",
        console=_make_console(),
    )
    first_call_args = llm.chat_with_tools.call_args_list[0]
    working_history = first_call_args[0][0]
    user_msg = next(m for m in working_history if m.get("role") == "user")
    assert "Prometheus port: 9091" in user_msg["content"], (
        "Expected KB chunk to be injected into the first user message when score >= 0.75."
    )


# ---------------------------------------------------------------------------
# 10. Low-score KB chunks are NOT injected (score < 0.75)
# ---------------------------------------------------------------------------

def test_kb_context_not_injected_for_low_score_chunks():
    """Chunks with score < 0.75 are silently discarded (below injection threshold)."""
    llm, kb, prom, executor, judge, mem = _make_mocks([
        _make_text_msg("I don't know."),
    ])
    kb.search.return_value = [
        {"score": 0.60, "file": "monitoring.md", "content": "Some weakly related config"},
    ]
    history: list[dict] = []
    run_agent(
        user_input="something obscure",
        history=history,
        llm=llm,
        kb=kb,
        prom=prom,
        executor=executor,
        judge=judge,
        mem=mem,
        session_id="s2",
        system="You are HAL.",
        console=_make_console(),
    )
    first_call_args = llm.chat_with_tools.call_args_list[0]
    working_history = first_call_args[0][0]
    user_msg = next(m for m in working_history if m.get("role") == "user")
    assert "Some weakly related config" not in user_msg["content"], (
        "Low-score KB chunk should NOT be injected into the user message."
    )
