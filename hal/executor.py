"""SSH executor — run commands and write files on the lab server.

Approval is NOT handled here — call Judge.approve() before calling run().

When host is localhost/127.0.0.1, commands run directly via subprocess (no SSH).
"""

from __future__ import annotations

import shlex
import subprocess
from typing import ClassVar

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class SSHExecutor:
    def __init__(self, host: str, user: str):
        self.host = host
        self.user = user
        self._local = host in _LOCAL_HOSTS

    _SSH_OPTS: ClassVar[list[str]] = [
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
    ]

    def run(self, command: str, timeout: int = 30) -> dict:
        """Run a shell command on the server. No approval — caller must gate."""
        if self._local:
            result = subprocess.run(  # noqa: S602 -- Judge-gated: all commands pass through judge.approve()
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            result = subprocess.run(  # noqa: S603 -- Judge-gated
                ["ssh", *self._SSH_OPTS, f"{self.user}@{self.host}", command],  # noqa: S607 -- known binary, PATH controlled
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def write(self, path: str, content: str, timeout: int = 30) -> dict:
        """Write content to a file on the server via stdin."""
        if self._local:
            try:
                with open(path, "w") as f:
                    f.write(content)
                return {"returncode": 0, "stdout": "", "stderr": ""}
            except OSError as e:
                return {"returncode": 1, "stdout": "", "stderr": str(e)}
        result = subprocess.run(  # noqa: S603 -- Judge-gated: write_file passes through judge.approve()
            [  # noqa: S607 -- known binary, PATH controlled
                "ssh",
                *self._SSH_OPTS,
                f"{self.user}@{self.host}",
                f"cat > {shlex.quote(path)}",
            ],
            input=content,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }


class ExecutorRegistry:
    """Manage SSHExecutor instances for multiple configured hosts.

    The "lab" host is always present and is the default when no target_host
    is specified by the LLM.
    """

    def __init__(self, host_registry: dict[str, tuple[str, str]]) -> None:
        self._executors: dict[str, SSHExecutor] = {}
        for name, (host, user) in host_registry.items():
            self._executors[name] = SSHExecutor(host, user)
        if "lab" not in self._executors:
            raise ValueError("host_registry must contain a 'lab' entry")

    @property
    def default(self) -> SSHExecutor:
        """The primary lab executor — used when target_host is None."""
        return self._executors["lab"]

    def get(self, name: str | None = None) -> SSHExecutor:
        """Return the executor for the named host, or the default.

        Raises ValueError for unknown host names.
        """
        if name is None:
            return self.default
        if name not in self._executors:
            known = ", ".join(sorted(self._executors))
            raise ValueError(f"Unknown host: '{name}'. Available hosts: {known}")
        return self._executors[name]

    @property
    def known_hosts(self) -> list[str]:
        """Return sorted list of configured host names."""
        return sorted(self._executors)
