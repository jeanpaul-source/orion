"""Sandboxed code execution — run untrusted Python in an isolated Docker container.

The sandbox tool lets the LLM write and execute Python code without affecting
HAL's own container, the host, or any other service.

Isolation layers (all enforced by Docker at the kernel level):
  --network none      no network access (non-negotiable)
  --memory 256m       hard memory cap
  --cpus 1            CPU limit
  --read-only         immutable root filesystem
  --tmpfs /tmp:64m    writable scratch space (capped)
  --pids-limit 64     fork bomb protection

Code transfer:
  1. Write code to a temp file on the host via SSHExecutor.write()
  2. Mount the file into the sandbox container as read-only
  3. Run python3 against it
  4. Parse stdout/stderr/exit_code
  5. Clean up the temp file (in a finally block — always runs)
"""

from __future__ import annotations

import logging
import shlex
import uuid
from dataclasses import dataclass

from hal.executor import SSHExecutor

_log = logging.getLogger(__name__)

# Hardcoded security constraints — not configurable via .env to prevent
# accidental weakening.  Change these only with a CLAUDE.md proposal.
_MEMORY_LIMIT = "256m"
_CPU_LIMIT = "1"
_PIDS_LIMIT = "64"
_TMPFS_SIZE = "64m"

# Maximum output length returned from the sandbox.  Capped before the
# agent loop's own 8000-char limit to leave room for the header/delimiters.
_MAX_OUTPUT_CHARS = 6000


@dataclass(frozen=True)
class SandboxResult:
    """Structured result from a sandbox code execution.

    Attributes:
        stdout:    Standard output from the code (possibly truncated).
        stderr:    Standard error from the code (possibly truncated).
        exit_code: Process exit code (0 = success, non-zero = error).
        timed_out: True if the execution was killed by the timeout.
    """

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding an ellipsis note if cut."""
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return text[:max_chars] + f"\n[…{omitted} chars omitted]"


def _build_docker_command(
    image: str,
    host_code_path: str,
    timeout: int,
) -> str:
    """Build the full ``docker run`` command string.

    The ``timeout`` utility wraps the docker run — if the container exceeds
    the time limit, ``timeout`` sends SIGTERM to ``docker run``, which stops
    the container.  The 5-second grace period (``-k 5``) sends SIGKILL if
    SIGTERM doesn't finish the cleanup.

    Returns a single shell command string safe for SSHExecutor.run().
    """
    # shlex.quote the host path to handle any unusual characters
    quoted_path = shlex.quote(host_code_path)

    # The container-side code path is fixed — no user input.
    container_code_path = "/sandbox/code.py"

    parts = [
        f"timeout -k 5 {timeout}",
        "docker run --rm",
        "--network none",
        f"--memory {_MEMORY_LIMIT}",
        f"--cpus {_CPU_LIMIT}",
        f"--pids-limit {_PIDS_LIMIT}",
        "--read-only",
        f"--tmpfs /tmp:size={_TMPFS_SIZE}",
        # Mount the code file read-only — the sandbox cannot modify it
        f"-v {quoted_path}:{container_code_path}:ro",
        # Suppress .pyc since rootfs is read-only
        "-e PYTHONDONTWRITEBYTECODE=1",
        shlex.quote(image),
        f"python3 {container_code_path}",
    ]
    return " ".join(parts)


def execute_code(
    code: str,
    executor: SSHExecutor,
    *,
    image: str = "orion-sandbox:latest",
    timeout: int = 30,
) -> SandboxResult:
    """Execute Python code in a sandboxed Docker container.

    This function:
    1. Writes the code to a unique temp file on the target host
    2. Runs ``docker run`` with full isolation constraints
    3. Parses the result into a SandboxResult
    4. Cleans up the temp file (always, via finally)

    The caller (tool handler) is responsible for Judge approval BEFORE
    calling this function.  This function does not gate anything.

    Args:
        code:     Python source code to execute.
        executor: SSHExecutor targeting the host where Docker runs.
        image:    Docker image name (from Config.sandbox_image).
        timeout:  Maximum execution time in seconds (from Config.sandbox_timeout).

    Returns:
        SandboxResult with stdout, stderr, exit_code, and timed_out flag.
    """
    # Generate a unique temp file path on the host.
    # Using /tmp with a hal-sandbox- prefix for easy identification and cleanup.
    run_id = uuid.uuid4().hex
    host_code_path = f"/tmp/hal-sandbox-{run_id}.py"  # noqa: S108 — intentional temp path on remote host

    try:
        # Step 1: Write the code to the host temp file
        write_result = executor.write(host_code_path, code)
        if write_result["returncode"] != 0:
            _log.error(
                "Failed to write sandbox code to %s: %s",
                host_code_path,
                write_result["stderr"],
            )
            return SandboxResult(
                stdout="",
                stderr=f"Failed to write code to sandbox temp file: {write_result['stderr']}",
                exit_code=1,
                timed_out=False,
            )

        # Step 2: Build and execute the Docker command
        docker_cmd = _build_docker_command(image, host_code_path, timeout)
        _log.info("Sandbox execute: image=%s timeout=%d", image, timeout)

        # Give the executor slightly more time than the sandbox timeout
        # to account for container startup/teardown overhead.
        executor_timeout = timeout + 15

        result = executor.run(docker_cmd, timeout=executor_timeout)

        # Step 3: Determine if the execution timed out.
        # The ``timeout`` utility returns exit code 124 when the command
        # is killed by the time limit.
        timed_out = result["returncode"] == 124

        return SandboxResult(
            stdout=_truncate(result["stdout"], _MAX_OUTPUT_CHARS),
            stderr=_truncate(result["stderr"], _MAX_OUTPUT_CHARS),
            exit_code=result["returncode"],
            timed_out=timed_out,
        )

    finally:
        # Step 4: Always clean up the temp file.
        # This runs even if the docker command fails or times out.
        try:
            executor.run(f"rm -f {shlex.quote(host_code_path)}", timeout=10)
        except Exception:
            # Cleanup failure is non-fatal — log but don't raise.
            # /tmp is cleaned by the OS on reboot anyway.
            _log.warning("Failed to clean up sandbox temp file: %s", host_code_path)


def format_result(result: SandboxResult) -> str:
    """Format a SandboxResult for the LLM to read.

    The format is designed so the LLM can:
    - Immediately see the exit code (success vs failure)
    - Read stdout and stderr as separate sections
    - Detect timeouts and decide whether to retry with shorter code

    Example output::

        exit_code: 0
        --- stdout ---
        Hello, world!
        --- stderr ---
        (empty)
    """
    parts: list[str] = []

    if result.timed_out:
        parts.append(f"TIMED OUT (exit_code: {result.exit_code})")
    else:
        parts.append(f"exit_code: {result.exit_code}")

    parts.append("--- stdout ---")
    parts.append(result.stdout.strip() if result.stdout.strip() else "(empty)")

    parts.append("--- stderr ---")
    parts.append(result.stderr.strip() if result.stderr.strip() else "(empty)")

    return "\n".join(parts)
