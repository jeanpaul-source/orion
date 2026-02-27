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
