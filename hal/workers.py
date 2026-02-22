"""Workers — file operations on the lab server, gated through Judge."""
import shlex

from hal.executor import SSHExecutor
from hal.judge import Judge


def read_file(path: str, executor: SSHExecutor, judge: Judge, reason: str = "") -> str | None:
    """Read a file from the server. Returns content string or None."""
    if not judge.approve("read_file", path, reason=reason):
        return None
    result = executor.run(f"cat {shlex.quote(path)}")
    if result["returncode"] != 0:
        return None
    return result["stdout"]


def list_dir(path: str, executor: SSHExecutor, judge: Judge, reason: str = "") -> str | None:
    """List a directory on the server. Returns ls output or None."""
    if not judge.approve("list_dir", path, reason=reason):
        return None
    result = executor.run(f"ls -la {shlex.quote(path)}")
    if result["returncode"] != 0:
        return None
    return result["stdout"]


def write_file(
    path: str,
    content: str,
    executor: SSHExecutor,
    judge: Judge,
    reason: str = "",
) -> bool:
    """Write content to a file on the server (creates or overwrites)."""
    preview = content[:80].replace("\n", "↵")
    detail = f"{path}  [{len(content)} bytes]  {preview}"
    if not judge.approve("write_file", detail, reason=reason):
        return False
    result = executor.write(path, content)
    return result["returncode"] == 0
