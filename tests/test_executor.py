"""Tests for hal/executor.py — SSHExecutor command execution paths.

Proves to the user that:
- Localhost detection works for all local aliases (no self-SSH).
- Remote commands build correct SSH invocations.
- Return dicts always have exactly {returncode, stdout, stderr}.
- Timeout errors propagate (never silently swallowed).
- Local file writes succeed and fail with a stable error shape.
- Remote file writes pipe content through SSH correctly.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pytest

from hal.executor import _LOCAL_HOSTS, SSHExecutor

# --------------------------------------------------------------------------- #
# Proof 1 — Localhost detection
# --------------------------------------------------------------------------- #

_REMOTE_HOSTS = ["192.168.5.10", "the-lab", "example.com", "10.0.0.1"]


@pytest.mark.parametrize("host", sorted(_LOCAL_HOSTS))
def test_local_hosts_detected(host: str):
    """Each local alias must set _local=True so commands run via subprocess, not SSH."""
    exe = SSHExecutor(host, "testuser")
    assert exe._local is True, f"'{host}' should be detected as local"


@pytest.mark.parametrize("host", _REMOTE_HOSTS)
def test_remote_hosts_not_local(host: str):
    """Non-local hosts must set _local=False so commands go through SSH."""
    exe = SSHExecutor(host, "testuser")
    assert exe._local is False, f"'{host}' should NOT be detected as local"


# --------------------------------------------------------------------------- #
# Proof 2 — Local run() executes via subprocess (no SSH)
# --------------------------------------------------------------------------- #

EXPECTED_KEYS = {"returncode", "stdout", "stderr"}


@patch("hal.executor.subprocess.run")
def test_local_run_uses_shell(mock_run: MagicMock):
    """Local run must use shell=True and never construct an SSH command."""
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
    exe = SSHExecutor("localhost", "testuser")

    result = exe.run("echo hello", timeout=5)

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    # First positional arg is the command string (not a list with "ssh")
    assert args[0] == "echo hello", "local run should pass command as string"
    assert kwargs["shell"] is True, "local run must use shell=True"
    assert kwargs["timeout"] == 5
    assert set(result.keys()) == EXPECTED_KEYS


@patch("hal.executor.subprocess.run")
def test_local_run_return_contract(mock_run: MagicMock):
    """Local run must return exactly {returncode, stdout, stderr} with correct values."""
    mock_run.return_value = MagicMock(returncode=42, stdout="out", stderr="err")
    exe = SSHExecutor("127.0.0.1", "u")

    result = exe.run("failing_cmd")

    assert result == {"returncode": 42, "stdout": "out", "stderr": "err"}


# --------------------------------------------------------------------------- #
# Proof 3 — Remote run() builds correct SSH command
# --------------------------------------------------------------------------- #


@patch("hal.executor.subprocess.run")
def test_remote_run_builds_ssh_command(mock_run: MagicMock):
    """Remote run must produce ['ssh', <opts>, 'user@host', command]."""
    mock_run.return_value = MagicMock(returncode=0, stdout="data", stderr="")
    exe = SSHExecutor("192.168.5.10", "jp")

    result = exe.run("uptime", timeout=10)

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    cmd_list = args[0]

    assert cmd_list[0] == "ssh", "remote run must invoke ssh"
    assert "-o" in cmd_list, "SSH options must be present"
    assert "StrictHostKeyChecking=accept-new" in cmd_list
    assert "BatchMode=yes" in cmd_list
    assert "jp@192.168.5.10" in cmd_list
    assert cmd_list[-1] == "uptime", "command must be last element"
    assert kwargs.get("shell") is not True, "remote run must NOT use shell=True"
    assert kwargs["timeout"] == 10
    assert set(result.keys()) == EXPECTED_KEYS


@patch("hal.executor.subprocess.run")
def test_remote_run_return_contract(mock_run: MagicMock):
    """Remote run must return exactly {returncode, stdout, stderr} with correct values."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
    exe = SSHExecutor("the-lab", "admin")

    result = exe.run("nonexistent")

    assert result == {"returncode": 1, "stdout": "", "stderr": "not found"}


# --------------------------------------------------------------------------- #
# Proof 4 — Timeout propagation (never silently swallowed)
# --------------------------------------------------------------------------- #


@patch("hal.executor.subprocess.run")
def test_local_run_timeout_propagates(mock_run: MagicMock):
    """TimeoutExpired on local run must propagate — caller must see it."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 999", timeout=1)
    exe = SSHExecutor("localhost", "u")

    with pytest.raises(subprocess.TimeoutExpired):
        exe.run("sleep 999", timeout=1)


@patch("hal.executor.subprocess.run")
def test_remote_run_timeout_propagates(mock_run: MagicMock):
    """TimeoutExpired on remote run must propagate — caller must see it."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh ...", timeout=5)
    exe = SSHExecutor("192.168.5.10", "jp")

    with pytest.raises(subprocess.TimeoutExpired):
        exe.run("long_task", timeout=5)


# --------------------------------------------------------------------------- #
# Proof 5 — Local write() success and failure
# --------------------------------------------------------------------------- #


def test_local_write_success():
    """Local write must open the file, write content, and return rc=0."""
    exe = SSHExecutor("localhost", "u")
    m = mock_open()

    with patch("builtins.open", m):
        result = exe.write("/tmp/test.txt", "hello world")

    m.assert_called_once_with("/tmp/test.txt", "w")
    m().write.assert_called_once_with("hello world")
    assert result == {"returncode": 0, "stdout": "", "stderr": ""}
    assert set(result.keys()) == EXPECTED_KEYS


def test_local_write_oserror_returns_error_dict():
    """Local write OSError must return rc=1 with error message, not raise."""
    exe = SSHExecutor("127.0.0.1", "u")
    m = mock_open()
    m.side_effect = OSError("Permission denied")

    with patch("builtins.open", m):
        result = exe.write("/etc/protected", "data")

    assert result["returncode"] == 1
    assert "Permission denied" in result["stderr"]
    assert set(result.keys()) == EXPECTED_KEYS


# --------------------------------------------------------------------------- #
# Proof 6 — Remote write() pipes content through SSH
# --------------------------------------------------------------------------- #


@patch("hal.executor.subprocess.run")
def test_remote_write_builds_ssh_cat_command(mock_run: MagicMock):
    """Remote write must use 'ssh ... cat > <quoted_path>' with stdin content."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    exe = SSHExecutor("192.168.5.10", "jp")

    result = exe.write("/opt/hal/config.yaml", "key: value", timeout=15)

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    cmd_list = args[0]

    assert cmd_list[0] == "ssh"
    assert "jp@192.168.5.10" in cmd_list
    # The last element should be the cat > path command (path is shlex-quoted)
    cat_cmd = cmd_list[-1]
    assert cat_cmd.startswith("cat > "), "remote write must use 'cat > path'"
    assert "/opt/hal/config.yaml" in cat_cmd
    assert kwargs["input"] == "key: value", "content must be piped via stdin"
    assert kwargs["timeout"] == 15
    assert set(result.keys()) == EXPECTED_KEYS


@patch("hal.executor.subprocess.run")
def test_remote_write_quotes_path_with_spaces(mock_run: MagicMock):
    """Remote write must shlex-quote the path to prevent injection."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    exe = SSHExecutor("the-lab", "jp")

    exe.write("/tmp/my file.txt", "data")

    args, _ = mock_run.call_args
    cat_cmd = args[0][-1]
    # shlex.quote wraps in single quotes: cat > '/tmp/my file.txt'
    assert "'" in cat_cmd, "path with spaces must be shlex-quoted"
    assert "my file.txt" in cat_cmd


@patch("hal.executor.subprocess.run")
def test_remote_write_return_contract(mock_run: MagicMock):
    """Remote write must return exactly {returncode, stdout, stderr}."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="disk full")
    exe = SSHExecutor("the-lab", "admin")

    result = exe.write("/var/data", "big content")

    assert result == {"returncode": 1, "stdout": "", "stderr": "disk full"}


@patch("hal.executor.subprocess.run")
def test_remote_write_timeout_propagates(mock_run: MagicMock):
    """TimeoutExpired on remote write must propagate — caller must see it."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh ...", timeout=30)
    exe = SSHExecutor("192.168.5.10", "jp")

    with pytest.raises(subprocess.TimeoutExpired):
        exe.write("/tmp/file", "content", timeout=30)


# --------------------------------------------------------------------------- #
# Proof 7 — Default timeout values
# --------------------------------------------------------------------------- #


@patch("hal.executor.subprocess.run")
def test_run_default_timeout(mock_run: MagicMock):
    """run() default timeout must be 30 seconds."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    exe = SSHExecutor("localhost", "u")

    exe.run("ls")

    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 30, "default run timeout should be 30s"


@patch("hal.executor.subprocess.run")
def test_write_default_timeout_remote(mock_run: MagicMock):
    """write() default timeout must be 30 seconds for remote path."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    exe = SSHExecutor("the-lab", "jp")

    exe.write("/tmp/f", "data")

    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 30, "default write timeout should be 30s"


# --------------------------------------------------------------------------- #
# Proof 8 — SSH connection-refused returns a stable failure dict
# --------------------------------------------------------------------------- #


@patch("hal.executor.subprocess.run")
def test_remote_run_returns_failure_dict_on_unreachable_host(mock_run: MagicMock):
    """SSH exit code 255 (unreachable host) must appear in the returned dict, not raise."""
    mock_run.return_value = MagicMock(
        returncode=255,
        stdout="",
        stderr="ssh: connect to host 10.0.0.99 port 22: Connection refused",
    )
    exe = SSHExecutor("10.0.0.99", "jp")

    result = exe.run("uptime", timeout=5)

    assert result["returncode"] == 255
    assert "Connection refused" in result["stderr"]
    assert result["stdout"] == ""
    assert set(result.keys()) == EXPECTED_KEYS


# --------------------------------------------------------------------------- #
# Proof 9 — _MockExecutor interface contract
# --------------------------------------------------------------------------- #


def test_mock_executor_satisfies_sshexecutor_interface_contract():
    """_MockExecutor.run() from eval/run_eval.py must return the same dict shape as SSHExecutor."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from eval.run_eval import _MockExecutor

    exe = _MockExecutor("192.168.5.10", "jp")
    result = exe.run("echo hello")

    assert set(result.keys()) == EXPECTED_KEYS
    assert result["returncode"] == 0
    assert isinstance(result["stdout"], str)
    assert isinstance(result["stderr"], str)


def test_mock_executor_never_calls_subprocess(monkeypatch):
    """_MockExecutor must not invoke subprocess.run — it is a pure stub."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from unittest.mock import patch as _patch

    from eval.run_eval import _MockExecutor

    exe = _MockExecutor("192.168.5.10", "jp")
    with _patch("hal.executor.subprocess.run") as mock_run:
        exe.run("rm -rf /")
        mock_run.assert_not_called()
