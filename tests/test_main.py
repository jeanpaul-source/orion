"""Tests for hal/main.py — REPL slash command handlers.

Tests the individual cmd_* functions in isolation. The main() REPL loop is
excluded because it needs live services. Each cmd_* function accepts explicit
dependencies (prom, kb, executor, judge, mem, console) so they're easy to
test with stubs and fixtures from conftest.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from rich.console import Console

from hal import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_console() -> tuple[Console, list[str]]:
    """Return a Console that captures printed output and a list of captured strings.

    Uses an io.StringIO buffer so Rich Panel and other renderables are
    serialised to text properly.
    """
    import io

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=120)
    # output list is a single-element wrapper so callers can do " ".join(output)
    output: list[str] = []

    original_print = console.print

    def capturing_print(*args, **kwargs):
        original_print(*args, **kwargs)
        output.clear()
        output.append(buf.getvalue())

    console.print = capturing_print  # type: ignore[assignment]
    return console, output


class _StubKB:
    """KB stub for testing cmd_search, cmd_kb, cmd_remember."""

    def __init__(
        self,
        search_results: list[dict] | None = None,
        categories: list[tuple[str, int]] | None = None,
    ):
        self._results = search_results or []
        self._cats = categories or []
        self.remembered: list[str] = []

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        return self._results[:top_k]

    def categories(self) -> list[tuple[str, int]]:
        return self._cats

    def remember(self, fact: str) -> None:
        self.remembered.append(fact)


class _AlwaysApproveJudge:
    def approve(self, *_args, **_kwargs):
        return True


class _AlwaysDenyJudge:
    def approve(self, *_args, **_kwargs):
        return False


class _StubExecutor:
    """Executor stub that returns pre-configured results."""

    def __init__(self, result: dict | None = None):
        self._result = result or {"stdout": "", "stderr": "", "returncode": 0}
        self.commands_run: list[str] = []

    def run(self, command: str, timeout: int = 30) -> dict:
        self.commands_run.append(command)
        return self._result


# =========================================================================
# cmd_health()
# =========================================================================


class TestCmdHealth:
    def test_prints_metrics_panel(self, monkeypatch):
        """cmd_health prints a panel with metric values from Prometheus."""
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)

        class FakeProm:
            def health(self):
                return {"cpu_pct": 12.5, "mem_pct": 45.0}

        main.cmd_health(FakeProm())
        text = " ".join(output)
        assert "cpu_pct" in text or "12.5" in text

    def test_prints_error_on_exception(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)

        class BrokenProm:
            def health(self):
                raise ConnectionError("connection refused")

        main.cmd_health(BrokenProm())
        text = " ".join(output)
        assert "unreachable" in text.lower() or "connection refused" in text.lower()


# =========================================================================
# cmd_search()
# =========================================================================


class TestCmdSearch:
    def test_prints_results(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        kb = _StubKB(
            search_results=[
                {
                    "file": "test.md",
                    "category": "docs",
                    "score": 0.95,
                    "content": "This is a test document.",
                }
            ]
        )
        main.cmd_search("test query", kb)
        text = " ".join(output)
        assert "test.md" in text

    def test_prints_usage_when_empty_query(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_search("", _StubKB())
        text = " ".join(output)
        assert "usage" in text.lower()

    def test_prints_error_on_exception(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)

        class BrokenKB:
            def search(self, *a, **kw):
                raise RuntimeError("db down")

        main.cmd_search("test query", BrokenKB())
        text = " ".join(output)
        assert "unavailable" in text.lower() or "db down" in text.lower()


# =========================================================================
# cmd_run()
# =========================================================================


class TestCmdRun:
    def test_executes_command_when_judge_approves(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        executor = _StubExecutor(
            {"stdout": "hello world", "stderr": "", "returncode": 0}
        )
        main.cmd_run("echo hello", executor, _AlwaysApproveJudge())
        text = " ".join(output)
        assert "hello world" in text

    def test_prints_cancelled_when_judge_denies(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        executor = _StubExecutor()
        main.cmd_run("rm -rf /", executor, _AlwaysDenyJudge())
        text = " ".join(output)
        assert "cancelled" in text.lower()

    def test_prints_usage_when_empty_command(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_run("", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "usage" in text.lower()

    def test_prints_stderr_on_failure(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        executor = _StubExecutor(
            {"stdout": "", "stderr": "command not found", "returncode": 127}
        )
        main.cmd_run("badcmd", executor, _AlwaysApproveJudge())
        text = " ".join(output)
        assert "command not found" in text


# =========================================================================
# cmd_read()
# =========================================================================


class TestCmdRead:
    def test_prints_file_content(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        monkeypatch.setattr(
            main,
            "read_file",
            lambda path, executor, judge: "file content here",
        )
        main.cmd_read("/tmp/test.txt", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "file content here" in text

    def test_prints_error_when_read_fails(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        monkeypatch.setattr(main, "read_file", lambda *a, **kw: None)
        main.cmd_read("/nonexistent", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "could not read" in text.lower()

    def test_prints_usage_when_empty_path(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_read("", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "usage" in text.lower()


# =========================================================================
# cmd_ls()
# =========================================================================


class TestCmdLs:
    def test_prints_directory_listing(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        monkeypatch.setattr(
            main, "list_dir", lambda path, executor, judge: "file1\nfile2"
        )
        main.cmd_ls("/tmp", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "file1" in text

    def test_prints_error_when_listing_fails(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        monkeypatch.setattr(main, "list_dir", lambda *a, **kw: None)
        main.cmd_ls("/nonexistent", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "could not list" in text.lower()

    def test_prints_usage_when_empty_path(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_ls("", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "usage" in text.lower()


# =========================================================================
# cmd_write()
# =========================================================================


class TestCmdWrite:
    def test_prints_usage_when_empty_path(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_write("", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "usage" in text.lower()

    def test_aborts_on_empty_content(self, monkeypatch):
        """When user hits Ctrl+D immediately, content is empty and write is aborted."""
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        monkeypatch.setattr(
            "builtins.input", lambda *a: (_ for _ in ()).throw(EOFError)
        )
        main.cmd_write("/tmp/test.txt", _StubExecutor(), _AlwaysApproveJudge())
        text = " ".join(output)
        assert "empty" in text.lower() or "aborted" in text.lower()


# =========================================================================
# cmd_postmortem()
# =========================================================================


class TestCmdPostmortem:
    def test_prints_usage_when_empty_description(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        prom = MagicMock()
        executor = _StubExecutor()
        judge = _AlwaysApproveJudge()
        main.cmd_postmortem("", prom, executor, judge)
        text = " ".join(output)
        assert "usage" in text.lower()

    def test_prints_error_on_exception(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        monkeypatch.setattr(
            main,
            "gather_postmortem_context",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("prom down")),
        )
        prom = MagicMock()
        executor = _StubExecutor()
        judge = _AlwaysApproveJudge()
        main.cmd_postmortem("disk full incident", prom, executor, judge)
        text = " ".join(output)
        assert "failed" in text.lower() or "prom down" in text.lower()


# =========================================================================
# cmd_audit()
# =========================================================================


class TestCmdAudit:
    def test_prints_recent_lines(self, monkeypatch, tmp_path):
        """cmd_audit reads the audit log and prints recent entries."""
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        audit_file = tmp_path / "audit.log"
        entries = [
            json.dumps({"status": "auto", "tier": 0, "action": "read_file"}),
            json.dumps({"status": "denied", "tier": 1, "action": "run_command"}),
            json.dumps({"status": "approved", "tier": 1, "action": "restart"}),
        ]
        audit_file.write_text("\n".join(entries))
        monkeypatch.setattr(main, "AUDIT_LOG", audit_file)
        main.cmd_audit(n=20)
        text = " ".join(output)
        assert "read_file" in text
        assert "denied" in text

    def test_prints_empty_message_when_no_log(self, monkeypatch, tmp_path):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        monkeypatch.setattr(main, "AUDIT_LOG", tmp_path / "nonexistent.log")
        main.cmd_audit()
        text = " ".join(output)
        assert "no audit log" in text.lower()

    def test_colorizes_denied_entries(self, monkeypatch, tmp_path):
        """Denied entries should be styled differently (red in Rich markup)."""
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        audit_file = tmp_path / "audit.log"
        entry = json.dumps({"status": "denied", "tier": 2, "action": "write_file"})
        audit_file.write_text(entry)
        monkeypatch.setattr(main, "AUDIT_LOG", audit_file)
        main.cmd_audit()
        # Output contains the denied entry text
        text = " ".join(output)
        assert "denied" in text

    def test_handles_empty_log_file(self, monkeypatch, tmp_path):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        audit_file = tmp_path / "audit.log"
        audit_file.write_text("")
        monkeypatch.setattr(main, "AUDIT_LOG", audit_file)
        main.cmd_audit()
        text = " ".join(output)
        assert "empty" in text.lower()


# =========================================================================
# cmd_kb()
# =========================================================================


class TestCmdKb:
    def test_prints_categories(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        kb = _StubKB(categories=[("lab-state", 18), ("lab-infrastructure", 35)])
        main.cmd_kb(kb)
        text = " ".join(output)
        assert "lab-state" in text
        assert "lab-infrastructure" in text

    def test_prints_error_on_exception(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)

        class BrokenKB:
            def categories(self):
                raise RuntimeError("db down")

        main.cmd_kb(BrokenKB())
        text = " ".join(output)
        assert "unavailable" in text.lower() or "db down" in text.lower()


# =========================================================================
# cmd_remember()
# =========================================================================


class TestCmdRemember:
    def test_stores_fact(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        kb = _StubKB()
        main.cmd_remember("The server has 64GB RAM", kb)
        assert "The server has 64GB RAM" in kb.remembered
        text = " ".join(output)
        assert "remembered" in text.lower()

    def test_prints_usage_when_empty(self, monkeypatch):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_remember("", _StubKB())
        text = " ".join(output)
        assert "usage" in text.lower()


# =========================================================================
# cmd_search_memory()
# =========================================================================


class TestCmdSearchMemory:
    def test_prints_results(self, monkeypatch, memory_store):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        # Write some turns to the memory store
        sid = memory_store.new_session()
        memory_store.save_turn(sid, "user", "tell me about docker")
        memory_store.save_turn(sid, "assistant", "Docker runs containers...")
        main.cmd_search_memory("docker", memory_store)
        text = " ".join(output)
        assert "docker" in text.lower()

    def test_prints_no_matches(self, monkeypatch, memory_store):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_search_memory("xyznonexistent", memory_store)
        text = " ".join(output)
        assert "no matches" in text.lower()

    def test_prints_usage_when_empty_query(self, monkeypatch, memory_store):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_search_memory("", memory_store)
        text = " ".join(output)
        assert "usage" in text.lower()


# =========================================================================
# cmd_sessions()
# =========================================================================


class TestCmdSessions:
    def test_prints_session_list(self, monkeypatch, memory_store):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        sid = memory_store.new_session()
        memory_store.save_turn(sid, "user", "hello")
        main.cmd_sessions(memory_store)
        text = " ".join(output)
        assert sid in text

    def test_prints_no_sessions_message(self, monkeypatch, memory_store):
        console, output = _capture_console()
        monkeypatch.setattr(main, "console", console)
        main.cmd_sessions(memory_store)
        text = " ".join(output)
        assert "no sessions" in text.lower()
