"""SSH tunnel — used when Ollama port isn't directly reachable from the laptop."""

import socket
import subprocess
import time


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


class SSHTunnel:
    def __init__(
        self, remote_user: str, remote_host: str, remote_port: int, local_port: int
    ):
        self.remote_user = remote_user
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.local_port = local_port
        self._proc: subprocess.Popen | None = None

    def start(self, wait: float = 5.0) -> None:
        self._proc = subprocess.Popen(  # noqa: S603 -- hardcoded SSH tunnel command, no user input
            [  # noqa: S607 -- known binary, PATH controlled
                "ssh",
                "-N",
                "-o",
                "ExitOnForwardFailure=yes",
                "-L",
                f"{self.local_port}:localhost:{self.remote_port}",
                f"{self.remote_user}@{self.remote_host}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + wait
        while time.time() < deadline:
            if port_open("127.0.0.1", self.local_port):
                return
            time.sleep(0.2)
        self.stop()
        raise RuntimeError(
            f"SSH tunnel to {self.remote_host}:{self.remote_port} "
            f"did not open within {wait}s"
        )

    def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
            self._proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
