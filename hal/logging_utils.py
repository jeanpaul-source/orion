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
from contextvars import ContextVar
from typing import Any, Dict

# Context vars for correlation
_ctx_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_ctx_turn_id: ContextVar[str | None] = ContextVar("turn_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
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


def setup_logging(level: str | int | None = None) -> None:
    lvl = level or os.getenv("HAL_LOG_LEVEL", "INFO")
    if isinstance(lvl, str):
        lvl = getattr(logging, lvl.upper(), logging.INFO)
    handler = logging.StreamHandler()
    use_json = os.getenv("HAL_LOG_JSON", "1").lower() not in ("0", "false", "no")
    if use_json:
        formatter = JsonFormatter()
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
