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

from hal.agent import _strip_tool_artifacts, run_agent
from hal.tools import dispatch_tool

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


def _call_run_agent(
    llm, kb, prom, executor, judge, mem, user_input="test query"
) -> str:
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
    llm, kb, prom, executor, judge, mem = _make_mocks(
        [
            _make_text_msg("Everything looks fine."),
        ]
    )
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
    llm, kb, prom, executor, judge, mem = _make_mocks(
        [
            _make_tool_call_msg("get_metrics", {}, call_id="tc_m1"),
            _make_text_msg("CPU is at 12.5%, RAM at 45%."),
        ]
    )
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
    llm, kb, prom, executor, judge, mem = _make_mocks(
        [
            call_msg,  # first iteration — dispatched
            call_msg,  # second iteration — duplicate, triggers loop-breaker
            _make_text_msg("The metrics are fine."),
        ]
    )
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
            if msg.get("role") == "user" and "already have all the data" in msg.get(
                "content", ""
            ):
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
    assert (
        "max iterations" in result.lower() or "without a final answer" in result.lower()
    ), f"Expected max-iterations message, got: {result!r}"
    assert llm.chat_with_tools.call_count == MAX_ITERATIONS


# ---------------------------------------------------------------------------
# 5. Tool output truncation at _MAX_TOOL_OUTPUT chars
# ---------------------------------------------------------------------------


def test_tool_output_is_truncated():
    """Tool output longer than 8000 chars must be capped before being fed back."""
    # return a huge blob from executor.run so run_command produces > 8000 chars
    huge_output = "x" * 20_000
    llm, kb, prom, executor, judge, mem = _make_mocks(
        [
            _make_tool_call_msg(
                "run_command",
                {"command": "cat bigfile", "reason": "test"},
                call_id="tc_big",
            ),
            _make_text_msg("Done."),
        ]
    )
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
    assert "omitted" in tool_msg["content"], (
        "Expected truncation annotation in capped output"
    )


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

    result = dispatch_tool(
        "search_kb", {"query": "nonexistent thing"}, executor, judge, kb, prom
    )
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

    result = dispatch_tool("totally_unknown_tool_xyz", {}, executor, judge, kb, prom)
    assert (
        "unknown tool" in result.lower() or result
    )  # must return something, not throw


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

    result = dispatch_tool("get_metrics", {}, executor, judge, kb, prom)
    assert "unavailable" in result.lower() or "error" in result.lower(), (
        f"Expected fallback error message, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 9. KB context is injected for strong matches (score >= 0.75)
# ---------------------------------------------------------------------------


def test_kb_context_injected_for_high_score_chunks():
    """Chunks returned by the KB with score >= 0.75 are prepended to the first message."""
    llm, kb, prom, executor, judge, mem = _make_mocks(
        [
            _make_text_msg("Prometheus runs on port 9091."),
        ]
    )
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
    llm, kb, prom, executor, judge, mem = _make_mocks(
        [
            _make_text_msg("I don't know."),
        ]
    )
    kb.search.return_value = [
        {
            "score": 0.60,
            "file": "monitoring.md",
            "content": "Some weakly related config",
        },
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


# ---------------------------------------------------------------------------
# 11. Planner/Critic gating — simple query skips sub-agents
# ---------------------------------------------------------------------------


def test_planner_critic_skipped_for_simple_query():
    """Short non-action query should skip PlannerAgent/CriticAgent entirely."""
    llm, kb, prom, executor, judge, mem = _make_mocks(
        [
            _make_text_msg("All good."),
        ]
    )
    planner = MagicMock()
    planner.run.return_value = "Step 1"
    critic = MagicMock()
    critic.run.return_value = "Looks good"

    history: list[dict] = []
    run_agent(
        user_input="status?",
        history=history,
        llm=llm,
        kb=kb,
        prom=prom,
        executor=executor,
        judge=judge,
        mem=mem,
        session_id="s-simple",
        system="You are HAL.",
        console=_make_console(),
        planner=planner,
        critic=critic,
    )

    planner.run.assert_not_called()
    critic.run.assert_not_called()
    first_call_args = llm.chat_with_tools.call_args_list[0]
    working_history = first_call_args[0][0]
    user_msg = next(m for m in working_history if m.get("role") == "user")
    assert "Planner's plan:" not in user_msg["content"]
    assert "Critic's review:" not in user_msg["content"]


# ---------------------------------------------------------------------------
# 12. Planner/Critic gating — action-ish query uses sub-agents
# ---------------------------------------------------------------------------


def test_planner_critic_used_for_action_query():
    """Action-ish query should run PlannerAgent and CriticAgent once."""
    llm, kb, prom, executor, judge, mem = _make_mocks(
        [
            _make_text_msg("Restart plan complete."),
        ]
    )
    planner = MagicMock()
    planner.run.return_value = "1) restart prometheus"
    critic = MagicMock()
    critic.run.return_value = "Plan is safe and ordered"

    history: list[dict] = []
    run_agent(
        user_input="restart prometheus and verify metrics",
        history=history,
        llm=llm,
        kb=kb,
        prom=prom,
        executor=executor,
        judge=judge,
        mem=mem,
        session_id="s-action",
        system="You are HAL.",
        console=_make_console(),
        planner=planner,
        critic=critic,
    )

    planner.run.assert_called_once()
    critic.run.assert_called_once()
    first_call_args = llm.chat_with_tools.call_args_list[0]
    working_history = first_call_args[0][0]
    user_msg = next(m for m in working_history if m.get("role") == "user")
    assert "Planner's plan:" in user_msg["content"]
    assert "Critic's review:" in user_msg["content"]


# ---------------------------------------------------------------------------
# _strip_tool_artifacts — B1 sanitiser
# ---------------------------------------------------------------------------


def test_strip_bare_tool_call_removed():
    """A bare {\"name\":...,\"arguments\":...} appended to prose must be stripped."""
    text = (
        "Prose before.\n\n"
        '{"name": "run_command", "arguments": {"command": "ls", "reason": "check"}}'
    )
    out = _strip_tool_artifacts(text)
    assert '{"name"' not in out
    assert out == "Prose before."


def test_strip_clean_text_unchanged():
    """Clean prose with no JSON must pass through unmodified."""
    text = "Everything is fine, no tool calls here."
    assert _strip_tool_artifacts(text) == text


def test_strip_preserves_non_tool_json():
    """A JSON dict that is NOT a tool call (no 'name'+'arguments') must be preserved."""
    text = 'Config: {"port": 9090, "host": "localhost"}'
    out = _strip_tool_artifacts(text)
    assert '"port"' in out
    assert '"host"' in out


def test_strip_multiple_tool_calls():
    """Multiple consecutive tool-call objects must all be removed."""
    text = (
        'First step.\n{"name": "cmd_a", "arguments": {}}\n'
        'Second step.\n{"name": "cmd_b", "arguments": {"x": 1}}\nDone.'
    )
    out = _strip_tool_artifacts(text)
    assert '{"name"' not in out
    assert "First step." in out
    assert "Done." in out


def test_strip_nested_json_in_arguments():
    """A tool call whose argument value contains a nested JSON string must still be stripped."""
    text = '{"name": "run_command", "arguments": {"command": "echo \'{}\'", "reason": "test"}}'
    out = _strip_tool_artifacts(text)
    assert "run_command" not in out


def test_strip_invalid_json_fragment_preserved():
    """An unmatched opening brace (not valid JSON) must survive unchanged."""
    text = "Use { as an escape char in the template."
    out = _strip_tool_artifacts(text)
    assert "{" in out


def test_strip_empty_string():
    """Empty string input must return empty string."""
    assert _strip_tool_artifacts("") == ""


def test_strip_only_whitespace():
    """Whitespace-only input must return empty string (strip behaviour)."""
    assert _strip_tool_artifacts("   \n  ") == ""


def test_strip_tool_artifact_leaves_plain_list_json():
    """A JSON array (not a dict) must not be stripped."""
    text = "Valid output: [1, 2, 3]"
    out = _strip_tool_artifacts(text)
    assert "[1, 2, 3]" in out


def test_run_agent_strips_tool_artifact_from_final_response():
    """run_agent must return clean text even when the LLM appends a tool-call JSON object."""
    artifact = '{"name": "run_command", "arguments": {"command": "ls"}}'
    response_with_artifact = f"Here is the answer.\n\n{artifact}"

    llm, kb, prom, executor, judge, mem = _make_mocks(
        [_make_text_msg(response_with_artifact)]
    )
    result = _call_run_agent(llm, kb, prom, executor, judge, mem)

    assert "run_command" not in result
    assert "Here is the answer." in result
