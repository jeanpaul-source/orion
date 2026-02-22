"""SSH executor — run commands and write files on the lab server.

Approval is NOT handled here — call Judge.approve() before calling run().

When host is localhost/127.0.0.1, commands run directly via subprocess (no SSH).
"""
import shlex
import subprocess

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class SSHExecutor:
    def __init__(self, host: str, user: str):
        self.host = host
        self.user = user
        self._local = host in _LOCAL_HOSTS

    _SSH_OPTS = ["-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes"]

    def run(self, command: str, timeout: int = 30) -> dict:
        """Run a shell command on the server. No approval — caller must gate."""
        if self._local:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            result = subprocess.run(
                ["ssh", *self._SSH_OPTS, f"{self.user}@{self.host}", command],
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
        result = subprocess.run(
            ["ssh", *self._SSH_OPTS, f"{self.user}@{self.host}", f"cat > {shlex.quote(path)}"],
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
