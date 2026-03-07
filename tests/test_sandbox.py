"""Offline tests for hal/sandbox.py and the run_code tool handler.

All tests use mocked executors — no Docker needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hal.sandbox import (
    SandboxResult,
    _build_docker_command,
    _truncate,
    execute_code,
    format_result,
)
from hal.tools import (
    ToolContext,
    _handle_run_code,
    _sandbox_enabled,
    _web_search_enabled,
    dispatch_tool,
    get_tools,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_executor(
    run_return: dict | None = None,
    write_return: dict | None = None,
) -> MagicMock:
    """Build a mock SSHExecutor with configurable run() and write() returns."""
    executor = MagicMock()
    executor.run.return_value = run_return or {
        "stdout": "Hello, world!\n",
        "stderr": "",
        "returncode": 0,
    }
    executor.write.return_value = write_return or {
        "returncode": 0,
        "stdout": "",
        "stderr": "",
    }
    return executor


def _mock_registry(executor: MagicMock | None = None) -> MagicMock:
    """Build an ExecutorRegistry mock whose .default and .get() return executor."""
    if executor is None:
        executor = _mock_executor()
    reg = MagicMock()
    reg.default = executor
    reg.get.return_value = executor
    reg.known_hosts = ["lab"]
    return reg


def _make_ctx(
    *,
    judge: MagicMock | None = None,
    executor: MagicMock | None = None,
    config: object | None = None,
) -> ToolContext:
    """Build a ToolContext with reasonable defaults for sandbox tests."""
    if judge is None:
        judge = MagicMock()
        judge.approve.return_value = True
    if executor is None:
        executor = _mock_executor()
    reg = _mock_registry(executor)
    return ToolContext(
        registry=reg,
        judge=judge,
        kb=MagicMock(),
        prom=MagicMock(),
        config=config,
    )


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_within_limit(self):
        assert _truncate("short", 100) == "short"

    def test_at_exact_limit(self):
        text = "x" * 50
        assert _truncate(text, 50) == text

    def test_exceeds_limit(self):
        text = "x" * 100
        result = _truncate(text, 50)
        assert result.startswith("x" * 50)
        assert "[…50 chars omitted]" in result

    def test_empty_string(self):
        assert _truncate("", 10) == ""


# ---------------------------------------------------------------------------
# _build_docker_command
# ---------------------------------------------------------------------------


class TestBuildDockerCommand:
    def test_contains_network_none(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        assert "--network none" in cmd

    def test_contains_memory_limit(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        assert "--memory 256m" in cmd

    def test_contains_cpu_limit(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        assert "--cpus 1" in cmd

    def test_contains_pids_limit(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        assert "--pids-limit 64" in cmd

    def test_contains_read_only(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        assert "--read-only" in cmd

    def test_contains_tmpfs(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        assert "--tmpfs /tmp:size=64m" in cmd

    def test_timeout_wraps_command(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 45)
        assert cmd.startswith("timeout -k 5 45 docker run")

    def test_mounts_code_read_only(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        # The volume mount should bind the host path to /sandbox/code.py:ro
        assert "/sandbox/code.py:ro" in cmd

    def test_image_name_in_command(self):
        cmd = _build_docker_command("my-image:v2", "/tmp/code.py", 30)
        assert "my-image:v2" in cmd

    def test_runs_python3(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        assert "python3 /sandbox/code.py" in cmd

    def test_path_with_spaces_is_quoted(self):
        cmd = _build_docker_command("img:latest", "/tmp/my code.py", 30)
        # shlex.quote wraps paths with spaces in single quotes
        assert "'/tmp/my code.py'" in cmd

    def test_suppresses_pyc(self):
        cmd = _build_docker_command("orion-sandbox:latest", "/tmp/code.py", 30)
        assert "-e PYTHONDONTWRITEBYTECODE=1" in cmd


# ---------------------------------------------------------------------------
# execute_code
# ---------------------------------------------------------------------------


class TestExecuteCode:
    def test_success_returns_stdout(self):
        executor = _mock_executor(
            run_return={"stdout": "42\n", "stderr": "", "returncode": 0},
        )
        result = execute_code("print(42)", executor, image="img:latest", timeout=10)
        assert result.exit_code == 0
        assert result.stdout == "42\n"
        assert result.timed_out is False

    def test_error_returns_stderr_and_exit_code(self):
        executor = _mock_executor(
            run_return={"stdout": "", "stderr": "NameError: ...", "returncode": 1},
        )
        result = execute_code("bad_code", executor, image="img:latest", timeout=10)
        assert result.exit_code == 1
        assert "NameError" in result.stderr
        assert result.timed_out is False

    def test_timeout_detected_by_exit_124(self):
        executor = _mock_executor(
            run_return={"stdout": "", "stderr": "", "returncode": 124},
        )
        result = execute_code(
            "while True: pass", executor, image="img:latest", timeout=5
        )
        assert result.exit_code == 124
        assert result.timed_out is True

    def test_write_failure_returns_error(self):
        executor = _mock_executor(
            write_return={"returncode": 1, "stdout": "", "stderr": "Permission denied"},
        )
        result = execute_code("print(1)", executor, image="img:latest", timeout=10)
        assert result.exit_code == 1
        assert "Permission denied" in result.stderr

    def test_cleanup_always_runs(self):
        """The finally block should always run rm -f on the temp file."""
        executor = _mock_executor(
            run_return={"stdout": "", "stderr": "", "returncode": 0},
        )
        execute_code("print(1)", executor, image="img:latest", timeout=10)

        # executor.run is called twice: docker run + rm -f cleanup
        assert len(executor.run.call_args_list) == 2
        # Last call should be the cleanup rm -f
        cleanup_call = str(executor.run.call_args_list[-1])
        assert "rm -f" in cleanup_call

    def test_cleanup_runs_even_on_docker_failure(self):
        """rm -f should still run if the docker command itself raises."""
        executor = _mock_executor()
        # Make the docker run call raise (first call), cleanup should still work
        executor.run.side_effect = [
            RuntimeError("docker broke"),
            {"stdout": "", "stderr": "", "returncode": 0},
        ]

        # execute_code does NOT catch RuntimeError from executor.run —
        # it propagates.  But the finally block should still clean up.
        with pytest.raises(RuntimeError, match="docker broke"):
            execute_code("print(1)", executor, image="img:latest", timeout=10)

        # Verify cleanup was attempted (second run call = rm -f)
        assert executor.run.call_count == 2
        cleanup_call = str(executor.run.call_args_list[-1])
        assert "rm -f" in cleanup_call

    def test_output_truncated_when_large(self):
        """Stdout/stderr exceeding _MAX_OUTPUT_CHARS are truncated."""
        long_output = "x" * 10000
        executor = _mock_executor(
            run_return={"stdout": long_output, "stderr": long_output, "returncode": 0},
        )
        result = execute_code(
            "print('x'*10000)", executor, image="img:latest", timeout=10
        )
        assert len(result.stdout) < 10000
        assert "[…" in result.stdout
        assert len(result.stderr) < 10000
        assert "[…" in result.stderr

    def test_executor_timeout_adds_overhead(self):
        """The executor timeout should be sandbox_timeout + 15."""
        executor = _mock_executor()
        execute_code("print(1)", executor, image="img:latest", timeout=20)

        # The docker run call (first run call) should use timeout=35
        docker_call = executor.run.call_args_list[0]
        assert docker_call.kwargs.get("timeout") == 35 or (
            len(docker_call.args) > 1 and docker_call.args[1] == 35
        )

    def test_temp_file_path_has_hal_sandbox_prefix(self):
        """The code file should be written to /tmp/hal-sandbox-*.py."""
        executor = _mock_executor()
        execute_code("print(1)", executor, image="img:latest", timeout=10)

        write_call = executor.write.call_args
        path_arg = write_call.args[0] if write_call.args else write_call[0][0]
        assert path_arg.startswith("/tmp/hal-sandbox-")
        assert path_arg.endswith(".py")


# ---------------------------------------------------------------------------
# format_result
# ---------------------------------------------------------------------------


class TestFormatResult:
    def test_success_format(self):
        result = SandboxResult(stdout="42", stderr="", exit_code=0, timed_out=False)
        text = format_result(result)
        assert "exit_code: 0" in text
        assert "--- stdout ---" in text
        assert "42" in text
        assert "--- stderr ---" in text

    def test_error_format(self):
        result = SandboxResult(
            stdout="",
            stderr="NameError: name 'x' is not defined",
            exit_code=1,
            timed_out=False,
        )
        text = format_result(result)
        assert "exit_code: 1" in text
        assert "NameError" in text

    def test_timeout_format(self):
        result = SandboxResult(stdout="", stderr="", exit_code=124, timed_out=True)
        text = format_result(result)
        assert "TIMED OUT" in text
        assert "124" in text

    def test_empty_stdout_shows_empty(self):
        result = SandboxResult(stdout="", stderr="", exit_code=0, timed_out=False)
        text = format_result(result)
        assert "(empty)" in text

    def test_whitespace_only_stdout_shows_empty(self):
        result = SandboxResult(
            stdout="   \n  ", stderr="", exit_code=0, timed_out=False
        )
        text = format_result(result)
        # After strip(), whitespace-only becomes empty
        assert "(empty)" in text


# ---------------------------------------------------------------------------
# _handle_run_code tool handler
# ---------------------------------------------------------------------------


class TestHandleRunCode:
    def test_empty_code_returns_error(self):
        ctx = _make_ctx()
        result = _handle_run_code({"code": "", "reason": "test"}, ctx)
        assert "code is required" in result

    def test_whitespace_only_code_returns_error(self):
        ctx = _make_ctx()
        result = _handle_run_code({"code": "   \n  ", "reason": "test"}, ctx)
        assert "code is required" in result

    def test_judge_denial_returns_message(self):
        judge = MagicMock()
        judge.approve.return_value = False
        ctx = _make_ctx(judge=judge)

        result = _handle_run_code({"code": "print(1)", "reason": "test"}, ctx)
        assert "denied" in result.lower()
        judge.approve.assert_called_once()

    def test_judge_approval_calls_sandbox(self):
        executor = _mock_executor()
        judge = MagicMock()
        judge.approve.return_value = True
        ctx = _make_ctx(judge=judge, executor=executor)

        result = _handle_run_code({"code": "print(42)", "reason": "test"}, ctx)
        # Should have called executor.write (code file) and executor.run (docker)
        assert executor.write.called
        assert executor.run.called
        assert "exit_code:" in result or "TIMED OUT" in result

    def test_success_records_outcome_success(self):
        executor = _mock_executor(
            run_return={"stdout": "ok", "stderr": "", "returncode": 0},
        )
        judge = MagicMock()
        judge.approve.return_value = True
        ctx = _make_ctx(judge=judge, executor=executor)

        _handle_run_code({"code": "print('ok')", "reason": "test"}, ctx)
        judge.record_outcome.assert_called_once_with(
            "run_code", "print('ok')", "success"
        )

    def test_nonzero_exit_records_outcome_error(self):
        executor = _mock_executor(
            run_return={"stdout": "", "stderr": "err", "returncode": 1},
        )
        judge = MagicMock()
        judge.approve.return_value = True
        ctx = _make_ctx(judge=judge, executor=executor)

        _handle_run_code({"code": "bad", "reason": "test"}, ctx)
        judge.record_outcome.assert_called_once_with("run_code", "bad", "error")

    def test_exception_records_outcome_error(self):
        executor = _mock_executor()
        executor.write.side_effect = RuntimeError("SSH down")
        judge = MagicMock()
        judge.approve.return_value = True
        ctx = _make_ctx(judge=judge, executor=executor)

        result = _handle_run_code({"code": "print(1)", "reason": "test"}, ctx)
        assert "Sandbox execution failed" in result
        judge.record_outcome.assert_called_once_with("run_code", "print(1)", "error")

    def test_uses_config_image_and_timeout(self):
        """Handler should read image and timeout from ctx.config."""

        class FakeConfig:
            sandbox_enabled = True
            sandbox_image = "custom-sandbox:v2"
            sandbox_timeout = 60

        executor = _mock_executor()
        judge = MagicMock()
        judge.approve.return_value = True
        ctx = _make_ctx(judge=judge, executor=executor, config=FakeConfig())

        _handle_run_code({"code": "print(1)", "reason": "test"}, ctx)

        # The docker run command should contain the custom image and timeout
        docker_call_args = executor.run.call_args_list[0]
        docker_cmd = (
            docker_call_args.args[0]
            if docker_call_args.args
            else docker_call_args[0][0]
        )
        assert "custom-sandbox:v2" in docker_cmd
        assert "timeout -k 5 60" in docker_cmd

    def test_default_image_when_no_config(self):
        """Without config, handler uses defaults."""
        executor = _mock_executor()
        judge = MagicMock()
        judge.approve.return_value = True
        ctx = _make_ctx(judge=judge, executor=executor, config=None)

        _handle_run_code({"code": "print(1)", "reason": "test"}, ctx)

        docker_call_args = executor.run.call_args_list[0]
        docker_cmd = (
            docker_call_args.args[0]
            if docker_call_args.args
            else docker_call_args[0][0]
        )
        assert "orion-sandbox:latest" in docker_cmd
        assert "timeout -k 5 30" in docker_cmd


# ---------------------------------------------------------------------------
# dispatch_tool integration
# ---------------------------------------------------------------------------


class TestDispatchRunCode:
    def test_dispatch_routes_to_handler(self):
        """dispatch_tool('run_code', ...) calls _handle_run_code."""
        executor = _mock_executor()
        judge = MagicMock()
        judge.approve.return_value = True
        ctx = _make_ctx(judge=judge, executor=executor)

        result = dispatch_tool("run_code", {"code": "print(1)", "reason": "test"}, ctx)
        assert "exit_code:" in result or "TIMED OUT" in result


# ---------------------------------------------------------------------------
# Enabled function tests
# ---------------------------------------------------------------------------


class TestEnabledFunctions:
    def test_sandbox_enabled_true(self):
        assert _sandbox_enabled(sandbox_enabled=True) is True

    def test_sandbox_enabled_false(self):
        assert _sandbox_enabled(sandbox_enabled=False) is False

    def test_sandbox_enabled_default_false(self):
        assert _sandbox_enabled() is False

    def test_sandbox_enabled_ignores_extra_kwargs(self):
        assert _sandbox_enabled(sandbox_enabled=True, tavily_api_key="k") is True

    def test_web_search_enabled_with_key(self):
        assert _web_search_enabled(tavily_api_key="key123") is True

    def test_web_search_enabled_without_key(self):
        assert _web_search_enabled(tavily_api_key="") is False

    def test_web_search_enabled_ignores_extra_kwargs(self):
        assert _web_search_enabled(tavily_api_key="k", sandbox_enabled=True) is True


# ---------------------------------------------------------------------------
# get_tools gating
# ---------------------------------------------------------------------------


class TestGetToolsGating:
    def test_run_code_absent_when_sandbox_disabled(self):
        names = [t["function"]["name"] for t in get_tools(sandbox_enabled=False)]
        assert "run_code" not in names

    def test_run_code_present_when_sandbox_enabled(self):
        names = [t["function"]["name"] for t in get_tools(sandbox_enabled=True)]
        assert "run_code" in names

    def test_both_flags_enable_both_tools(self):
        names = [
            t["function"]["name"]
            for t in get_tools(tavily_api_key="k", sandbox_enabled=True)
        ]
        assert "web_search" in names
        assert "run_code" in names


# ---------------------------------------------------------------------------
# Judge tier for run_code
# ---------------------------------------------------------------------------


class TestJudgeTier:
    def test_run_code_is_tier_2(self):
        from hal.judge import tier_for

        assert tier_for("run_code", "print(1)") == 2
