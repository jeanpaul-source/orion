"""SSH executor — run commands and write files on the lab server.

Approval is NOT handled here — call Judge.approve() before calling run().
"""
import shlex
import subprocess


class SSHExecutor:
    def __init__(self, host: str, user: str):
        self.host = host
        self.user = user

    def run(self, command: str, timeout: int = 30) -> dict:
        """Run a shell command on the server. No approval — caller must gate."""
        result = subprocess.run(
            ["ssh", f"{self.user}@{self.host}", command],
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
        result = subprocess.run(
            ["ssh", f"{self.user}@{self.host}", f"cat > {shlex.quote(path)}"],
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
