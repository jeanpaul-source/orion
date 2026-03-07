"""Tests for hal/tunnel.py — port_open() and SSHTunnel.

All tests mock socket/subprocess to stay offline. No SSH connections are made.
"""

from __future__ import annotations

import socket
import subprocess
from unittest.mock import MagicMock

import pytest

from hal import tunnel

# =========================================================================
# port_open()
# =========================================================================


class TestPortOpen:
    def test_returns_true_when_connection_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_socket = MagicMock()
        monkeypatch.setattr(
            socket, "create_connection", lambda addr, timeout: fake_socket
        )
        assert tunnel.port_open("localhost", 8000) is True
        fake_socket.close.assert_called_once()

    def test_returns_false_when_connection_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_os_error(*_args, **_kwargs):
            raise OSError("Connection refused")

        monkeypatch.setattr(socket, "create_connection", raise_os_error)
        assert tunnel.port_open("localhost", 8000) is False

    def test_returns_false_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def raise_timeout(*_args, **_kwargs):
            raise TimeoutError("timed out")

        monkeypatch.setattr(socket, "create_connection", raise_timeout)
        assert tunnel.port_open("localhost", 8000) is False


# =========================================================================
# SSHTunnel
# =========================================================================


class TestSSHTunnel:
    def test_start_succeeds_when_port_opens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tunnel starts subprocess and returns when local port becomes reachable."""
        fake_proc = MagicMock()
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: fake_proc)
        # port_open returns True immediately
        monkeypatch.setattr(tunnel, "port_open", lambda host, port: True)

        t = tunnel.SSHTunnel("jp", "192.168.5.10", 8000, 8000)
        t.start(wait=1.0)
        assert t._proc is fake_proc

    def test_start_raises_when_port_never_opens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the local port never becomes reachable, start() raises RuntimeError."""
        fake_proc = MagicMock()
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: fake_proc)
        monkeypatch.setattr(tunnel, "port_open", lambda host, port: False)
        # Use a very short wait to avoid slow tests
        monkeypatch.setattr(tunnel.time, "sleep", lambda _: None)

        t = tunnel.SSHTunnel("jp", "192.168.5.10", 11434, 11434)
        with pytest.raises(RuntimeError, match="did not open"):
            t.start(wait=0.01)
        # Process should be terminated on failure
        fake_proc.terminate.assert_called_once()

    def test_stop_terminates_process(self) -> None:
        t = tunnel.SSHTunnel("jp", "192.168.5.10", 8000, 8000)
        fake_proc = MagicMock()
        t._proc = fake_proc
        t.stop()
        fake_proc.terminate.assert_called_once()
        assert t._proc is None

    def test_stop_is_safe_when_no_process(self) -> None:
        """stop() does not raise if no process was started."""
        t = tunnel.SSHTunnel("jp", "192.168.5.10", 8000, 8000)
        t.stop()  # Should not raise

    def test_context_manager_starts_and_stops(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_proc = MagicMock()
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: fake_proc)
        monkeypatch.setattr(tunnel, "port_open", lambda host, port: True)

        with tunnel.SSHTunnel("jp", "192.168.5.10", 8000, 8000) as t:
            assert t._proc is fake_proc
        # After context exit, process should be terminated
        fake_proc.terminate.assert_called_once()

    def test_init_stores_parameters(self) -> None:
        t = tunnel.SSHTunnel("user", "host.example.com", 5432, 15432)
        assert t.remote_user == "user"
        assert t.remote_host == "host.example.com"
        assert t.remote_port == 5432
        assert t.local_port == 15432
