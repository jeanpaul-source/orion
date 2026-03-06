"""Structured logging utilities with optional JSON formatting and context propagation.

If python-json-logger is not installed, falls back to standard logging.Formatter.
Exposes get_logger(name) and setup_logging(level) to configure root logging.

Adds request/session correlation using contextvars. Other modules can set
context via set_context(session_id=..., turn_id=...).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.console import Console

# Context vars for correlation
_ctx_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_ctx_turn_id: ContextVar[str | None] = ContextVar("turn_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
        }
        # Attach tracing/context info if present
        try:
            from opentelemetry import trace  # type: ignore

            span = trace.get_current_span()
            ctx = span.get_span_context() if span else None
            if ctx and ctx.is_valid:
                payload["trace_id"] = f"{ctx.trace_id:032x}"
                payload["span_id"] = f"{ctx.span_id:016x}"
        except Exception:
            pass
        sid = _ctx_session_id.get()
        tid = _ctx_turn_id.get()
        if sid:
            payload["session_id"] = sid
        if tid:
            payload["turn_id"] = tid

        # Include extras if present
        for key in ("intent", "confidence"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    level: str | int | None = None,
    console: Console | None = None,
) -> None:
    """Configure the root logger.

    When *console* is provided (REPL mode) a ``RichHandler`` is installed so
    that all log output flows through the same Rich ``Console`` instance used
    for the UI.  Rich then manages cursor state for both logs and the status
    spinner, preventing log lines from appearing at the readline input prompt.

    When *console* is absent (server, watchdog, harvest) a plain
    ``StreamHandler(sys.stderr)`` is used — identical to the previous
    behaviour, now with an explicit stream argument.
    """
    lvl = level or os.getenv("HAL_LOG_LEVEL", "INFO")
    if isinstance(lvl, str):
        lvl = getattr(logging, lvl.upper(), logging.INFO)

    if console is not None:
        from rich.logging import RichHandler  # imported lazily — not a hard dep

        handler: logging.Handler = RichHandler(
            console=console,
            show_path=False,
            show_time=False,
            rich_tracebacks=False,
        )
    else:
        handler = logging.StreamHandler(sys.stderr)
        use_json = os.getenv("HAL_LOG_JSON", "1").lower() not in ("0", "false", "no")
        if use_json:
            formatter: logging.Formatter = JsonFormatter()
        else:
            formatter = logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(lvl)  # type: ignore[arg-type]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def set_context(session_id: str | None = None, turn_id: str | None = None) -> None:
    if session_id is not None:
        _ctx_session_id.set(session_id)
    if turn_id is not None:
        _ctx_turn_id.set(turn_id)
