"""Workers — file operations on the lab server, gated through Judge."""
import difflib
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


def patch_file(
    path: str,
    old_str: str,
    new_str: str,
    executor: SSHExecutor,
    judge: Judge,
    reason: str = "",
) -> str:
    """Replace old_str with new_str in a file on the server.

    Reads the current content, validates old_str is present, shows a unified
    diff for approval, then writes back the patched content.
    Returns a result message string.
    """
    content = read_file(path, executor, judge, reason=f"reading before patch: {reason}")
    if content is None:
        return f"Could not read {path}"

    if old_str not in content:
        return f"patch_file: old_str not found in {path}"

    new_content = content.replace(old_str, new_str, 1)

    # Build a unified diff to show as context for approval
    diff_lines = list(difflib.unified_diff(
        content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    ))
    diff_text = "".join(diff_lines[:60])  # cap at 60 lines for display
    detail = f"{path}\n{diff_text}"

    if not judge.approve("patch_file", detail, reason=reason):
        return "Patch denied by user."

    result = executor.write(path, new_content)
    if result["returncode"] != 0:
        return f"Write failed: {result.get('stderr', '')}"
    changed = abs(len(new_content) - len(content))
    return f"Patched {path} ({changed:+d} bytes net change)"


def git_status(
    repo_path: str,
    executor: SSHExecutor,
    judge: Judge,
    reason: str = "",
) -> str:
    """Run git status --short in repo_path on the server. Tier-0 read-only."""
    if not judge.approve("git_status", repo_path, reason=reason):
        return "Denied."
    result = executor.run(f"git -C {shlex.quote(repo_path)} status --short 2>&1")
    if result["returncode"] != 0:
        return f"git status failed: {result['stderr'].strip()}"
    return result["stdout"].strip() or "(clean — no changes)"


def git_diff(
    repo_path: str,
    executor: SSHExecutor,
    judge: Judge,
    ref: str = "HEAD",
    reason: str = "",
) -> str:
    """Run git diff <ref> in repo_path on the server. Tier-0 read-only."""
    if not judge.approve("git_diff", repo_path, reason=reason):
        return "Denied."
    result = executor.run(
        f"git -C {shlex.quote(repo_path)} diff {shlex.quote(ref)} 2>&1"
    )
    if result["returncode"] != 0:
        return f"git diff failed: {result['stderr'].strip()}"
    output = result["stdout"].strip()
    return output if output else "(no diff — working tree matches HEAD)"
