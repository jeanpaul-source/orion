"""Tests for hal/workers.py — file operations gated through the Judge.

Each function follows the pattern: Judge approval → executor call → result.
We test three paths for each: success, judge denial, and executor error.
"""

from __future__ import annotations

from hal import workers

# ---------------------------------------------------------------------------
# Test double: ScriptedExecutor with write() support
# ---------------------------------------------------------------------------


class WritableExecutor:
    """ScriptedExecutor-like double that also supports write()."""

    def __init__(
        self,
        run_responses: dict[str, dict] | None = None,
        write_response: dict | None = None,
    ):
        self._run_responses = run_responses or {}
        self._write_response = write_response or {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }
        self.commands_run: list[str] = []
        self.files_written: list[tuple[str, str]] = []

    def run(self, command: str, timeout: int = 30) -> dict:
        self.commands_run.append(command)
        for pattern, result in self._run_responses.items():
            if pattern in command:
                return result
        return {"stdout": "", "stderr": "", "returncode": 0}

    def write(self, path: str, content: str, timeout: int = 30) -> dict:
        self.files_written.append((path, content))
        return self._write_response


# =========================================================================
# read_file()
# =========================================================================


class TestReadFile:
    def test_returns_content_on_success(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "cat": {"stdout": "hello world", "stderr": "", "returncode": 0}
            }
        )
        result = workers.read_file("/etc/hostname", executor, auto_approve_judge)
        assert result == "hello world"

    def test_returns_none_when_judge_denies(self, real_judge):
        """real_judge auto-denies tier > 0; read_file is tier 0 so it auto-approves.
        We need a judge that denies everything."""

        class AlwaysDenyJudge:
            def approve(self, *_args, **_kwargs):
                return False

        executor = WritableExecutor()
        result = workers.read_file("/etc/shadow", executor, AlwaysDenyJudge())
        assert result is None

    def test_returns_none_on_executor_error(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "cat": {"stdout": "", "stderr": "No such file", "returncode": 1}
            }
        )
        result = workers.read_file("/nonexistent", executor, auto_approve_judge)
        assert result is None

    def test_passes_reason_to_judge(self, auto_approve_judge, monkeypatch):
        """Verify the reason= kwarg is forwarded to judge.approve()."""
        captured_reasons: list[str] = []
        original_approve = auto_approve_judge.approve

        def tracking_approve(action_type, detail, *, reason=""):
            captured_reasons.append(reason)
            return original_approve(action_type, detail, reason=reason)

        monkeypatch.setattr(auto_approve_judge, "approve", tracking_approve)
        executor = WritableExecutor(
            run_responses={"cat": {"stdout": "data", "stderr": "", "returncode": 0}}
        )
        workers.read_file(
            "/tmp/test", executor, auto_approve_judge, reason="test reason"
        )
        assert "test reason" in captured_reasons


# =========================================================================
# list_dir()
# =========================================================================


class TestListDir:
    def test_returns_output_on_success(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "ls": {"stdout": "file1\nfile2\n", "stderr": "", "returncode": 0}
            }
        )
        result = workers.list_dir("/tmp", executor, auto_approve_judge)
        assert result == "file1\nfile2\n"

    def test_returns_none_when_judge_denies(self):
        class AlwaysDenyJudge:
            def approve(self, *_args, **_kwargs):
                return False

        executor = WritableExecutor()
        result = workers.list_dir("/root", executor, AlwaysDenyJudge())
        assert result is None

    def test_returns_none_on_executor_error(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "ls": {"stdout": "", "stderr": "Permission denied", "returncode": 2}
            }
        )
        result = workers.list_dir("/root", executor, auto_approve_judge)
        assert result is None


# =========================================================================
# write_file()
# =========================================================================


class TestWriteFile:
    def test_returns_true_on_success(self, auto_approve_judge):
        executor = WritableExecutor()
        result = workers.write_file(
            "/tmp/out.txt", "hello", executor, auto_approve_judge
        )
        assert result is True
        assert executor.files_written == [("/tmp/out.txt", "hello")]

    def test_returns_false_when_judge_denies(self):
        class AlwaysDenyJudge:
            def approve(self, *_args, **_kwargs):
                return False

        executor = WritableExecutor()
        result = workers.write_file("/etc/passwd", "hack", executor, AlwaysDenyJudge())
        assert result is False
        assert executor.files_written == []  # executor never called

    def test_returns_false_on_executor_error(self, auto_approve_judge):
        executor = WritableExecutor(
            write_response={"returncode": 1, "stdout": "", "stderr": "disk full"}
        )
        result = workers.write_file(
            "/tmp/out.txt", "data", executor, auto_approve_judge
        )
        assert result is False

    def test_sends_preview_to_judge(self, auto_approve_judge, monkeypatch):
        """The detail passed to judge.approve() should contain the first 80 chars and byte count."""
        captured_details: list[str] = []
        original_approve = auto_approve_judge.approve

        def tracking_approve(action_type, detail, *, reason=""):
            captured_details.append(detail)
            return original_approve(action_type, detail, reason=reason)

        monkeypatch.setattr(auto_approve_judge, "approve", tracking_approve)
        executor = WritableExecutor()
        content = "A" * 100
        workers.write_file("/tmp/test.txt", content, executor, auto_approve_judge)
        assert len(captured_details) == 1
        assert "[100 bytes]" in captured_details[0]
        assert "/tmp/test.txt" in captured_details[0]


# =========================================================================
# patch_file()
# =========================================================================


class TestPatchFile:
    def test_replaces_old_str_and_writes_back(self, auto_approve_judge):
        """patch_file reads the file, replaces old_str with new_str, and writes it back."""
        executor = WritableExecutor(
            run_responses={
                "cat": {
                    "stdout": "line1\nold_value\nline3\n",
                    "stderr": "",
                    "returncode": 0,
                }
            }
        )
        result = workers.patch_file(
            "/tmp/config.txt", "old_value", "new_value", executor, auto_approve_judge
        )
        assert "Patched" in result
        # Verify the written content has the replacement
        assert len(executor.files_written) == 1
        path, content = executor.files_written[0]
        assert path == "/tmp/config.txt"
        assert "new_value" in content
        assert "old_value" not in content

    def test_returns_error_when_old_str_not_found(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "cat": {"stdout": "no match here", "stderr": "", "returncode": 0}
            }
        )
        result = workers.patch_file(
            "/tmp/config.txt",
            "missing_string",
            "replacement",
            executor,
            auto_approve_judge,
        )
        assert "old_str not found" in result

    def test_returns_denied_when_judge_rejects_diff(self, monkeypatch):
        """Even if reading succeeds, the patch itself can be denied at the diff-approval step."""
        approve_count = 0

        class ApproveReadDenyPatch:
            """Approves the first call (read_file), denies the second (patch_file diff)."""

            def approve(self, action_type, detail, *, reason=""):
                nonlocal approve_count
                approve_count += 1
                # First call is the read_file inside patch_file
                return approve_count <= 1

        executor = WritableExecutor(
            run_responses={
                "cat": {"stdout": "original content", "stderr": "", "returncode": 0}
            }
        )
        result = workers.patch_file(
            "/tmp/config.txt",
            "original",
            "modified",
            executor,
            ApproveReadDenyPatch(),
        )
        assert "denied" in result.lower() or "Denied" in result

    def test_returns_error_when_read_fails(self):
        """If the initial read_file fails (e.g., file not found), patch_file reports it."""

        class AlwaysApproveJudge:
            def approve(self, *_args, **_kwargs):
                return True

        executor = WritableExecutor(
            run_responses={
                "cat": {"stdout": "", "stderr": "not found", "returncode": 1}
            }
        )
        result = workers.patch_file(
            "/nonexistent", "old", "new", executor, AlwaysApproveJudge()
        )
        assert "Could not read" in result


# =========================================================================
# git_status()
# =========================================================================


class TestGitStatus:
    def test_returns_output_on_success(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "git": {
                    "stdout": " M hal/agent.py\n?? new_file.py\n",
                    "stderr": "",
                    "returncode": 0,
                }
            }
        )
        result = workers.git_status("/home/jp/orion", executor, auto_approve_judge)
        assert "hal/agent.py" in result

    def test_returns_clean_message_on_empty_output(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={"git": {"stdout": "", "stderr": "", "returncode": 0}}
        )
        result = workers.git_status("/home/jp/orion", executor, auto_approve_judge)
        assert "clean" in result.lower()

    def test_returns_denied_when_judge_rejects(self):
        class AlwaysDenyJudge:
            def approve(self, *_args, **_kwargs):
                return False

        executor = WritableExecutor()
        result = workers.git_status("/home/jp/orion", executor, AlwaysDenyJudge())
        assert result == "Denied."

    def test_returns_error_on_failure(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "git": {
                    "stdout": "",
                    "stderr": "fatal: not a git repository",
                    "returncode": 128,
                }
            }
        )
        result = workers.git_status("/tmp/not-a-repo", executor, auto_approve_judge)
        assert "failed" in result.lower()


# =========================================================================
# git_diff()
# =========================================================================


class TestGitDiff:
    def test_returns_output_on_success(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "git": {
                    "stdout": "diff --git a/file.py b/file.py\n+new line\n",
                    "stderr": "",
                    "returncode": 0,
                }
            }
        )
        result = workers.git_diff("/home/jp/orion", executor, auto_approve_judge)
        assert "diff --git" in result

    def test_returns_no_diff_message_on_empty_output(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={"git": {"stdout": "", "stderr": "", "returncode": 0}}
        )
        result = workers.git_diff("/home/jp/orion", executor, auto_approve_judge)
        assert "no diff" in result.lower()

    def test_returns_denied_when_judge_rejects(self):
        class AlwaysDenyJudge:
            def approve(self, *_args, **_kwargs):
                return False

        executor = WritableExecutor()
        result = workers.git_diff("/home/jp/orion", executor, AlwaysDenyJudge())
        assert result == "Denied."

    def test_returns_error_on_failure(self, auto_approve_judge):
        executor = WritableExecutor(
            run_responses={
                "git": {
                    "stdout": "",
                    "stderr": "fatal: bad revision",
                    "returncode": 128,
                }
            }
        )
        result = workers.git_diff(
            "/home/jp/orion", executor, auto_approve_judge, ref="nonexistent"
        )
        assert "failed" in result.lower()

    def test_uses_custom_ref(self, auto_approve_judge):
        """Verify the ref parameter is passed to the git diff command."""
        executor = WritableExecutor(
            run_responses={
                "git": {"stdout": "some diff", "stderr": "", "returncode": 0}
            }
        )
        workers.git_diff("/home/jp/orion", executor, auto_approve_judge, ref="HEAD~3")
        # The command should contain the ref
        assert any("HEAD~3" in cmd for cmd in executor.commands_run)
