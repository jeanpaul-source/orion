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
