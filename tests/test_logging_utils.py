"""Tests for hal/logging_utils.py — setup_logging, JsonFormatter, context vars.

These tests are fully offline (no external services).  They lock in the
handler-selection contract so that a future edit cannot silently revert
to a StreamHandler in REPL mode and re-introduce prompt pollution.
"""

from __future__ import annotations

import json
import logging
import sys

import pytest
from rich.console import Console
from rich.logging import RichHandler

from hal import logging_utils
from hal.logging_utils import setup_logging


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """Reset the root logger to its original state after every test."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers[:] = original_handlers
    root.setLevel(original_level)


def test_setup_logging_no_args_installs_stream_handler_on_stderr():
    """setup_logging() with no console arg must use StreamHandler(stderr) — server path."""
    setup_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1
    handler = root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert not isinstance(handler, RichHandler)
    assert handler.stream is sys.stderr


def test_setup_logging_with_console_installs_rich_handler():
    """setup_logging(console=...) must use RichHandler — REPL path."""
    console = Console(quiet=True)
    setup_logging(console=console)
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], RichHandler)


def test_setup_logging_exactly_one_handler_after_repeated_calls():
    """Calling setup_logging() twice must not accumulate handlers."""
    setup_logging()
    setup_logging()
    assert len(logging.getLogger().handlers) == 1


def test_setup_logging_level_is_applied():
    """The level argument must be respected."""
    setup_logging(level="WARNING")
    assert logging.getLogger().level == logging.WARNING


# =========================================================================
# JsonFormatter
# =========================================================================


class TestJsonFormatter:
    def _make_record(
        self, msg: str = "test message", **kwargs: object
    ) -> logging.LogRecord:
        record = logging.LogRecord(
            name="hal.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_produces_valid_json(self) -> None:
        fmt = logging_utils.JsonFormatter()
        output = fmt.format(self._make_record("hello world"))
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "hal.test"

    def test_includes_timestamp(self) -> None:
        fmt = logging_utils.JsonFormatter()
        output = fmt.format(self._make_record("ts test"))
        parsed = json.loads(output)
        assert "time" in parsed

    def test_includes_context_vars_when_set(self) -> None:
        """When session_id and turn_id are set they appear in the JSON output."""
        logging_utils.set_context(session_id="test-sess", turn_id="test-turn")
        try:
            fmt = logging_utils.JsonFormatter()
            output = fmt.format(self._make_record("ctx test"))
            parsed = json.loads(output)
            assert parsed["session_id"] == "test-sess"
            assert parsed["turn_id"] == "test-turn"
        finally:
            logging_utils._ctx_session_id.set(None)
            logging_utils._ctx_turn_id.set(None)

    def test_includes_extra_fields(self) -> None:
        """intent and confidence extras are included if present on the record."""
        fmt = logging_utils.JsonFormatter()
        record = self._make_record("extra test", intent="health", confidence=0.95)
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["intent"] == "health"
        assert parsed["confidence"] == 0.95

    def test_omits_context_when_not_set(self) -> None:
        logging_utils._ctx_session_id.set(None)
        logging_utils._ctx_turn_id.set(None)
        fmt = logging_utils.JsonFormatter()
        output = fmt.format(self._make_record("no context"))
        parsed = json.loads(output)
        assert "session_id" not in parsed
        assert "turn_id" not in parsed


# =========================================================================
# set_context()
# =========================================================================


class TestSetContext:
    def test_sets_session_id(self) -> None:
        logging_utils.set_context(session_id="sess-abc")
        assert logging_utils._ctx_session_id.get() == "sess-abc"
        logging_utils._ctx_session_id.set(None)

    def test_sets_turn_id(self) -> None:
        logging_utils.set_context(turn_id="turn-123")
        assert logging_utils._ctx_turn_id.get() == "turn-123"
        logging_utils._ctx_turn_id.set(None)

    def test_does_not_overwrite_when_none(self) -> None:
        """Passing None leaves the existing value unchanged."""
        logging_utils._ctx_session_id.set("existing")
        logging_utils.set_context(session_id=None)
        assert logging_utils._ctx_session_id.get() == "existing"
        logging_utils._ctx_session_id.set(None)


# =========================================================================
# get_logger()
# =========================================================================


class TestGetLogger:
    def test_returns_named_logger(self) -> None:
        logger = logging_utils.get_logger("hal.test.module")
        assert logger.name == "hal.test.module"
        assert isinstance(logger, logging.Logger)


# =========================================================================
# setup_logging with JSON toggle
# =========================================================================


class TestSetupLoggingJsonToggle:
    def test_json_formatter_when_hal_log_json_is_1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HAL_LOG_JSON", "1")
        setup_logging(level="WARNING")
        root = logging.getLogger()
        assert isinstance(root.handlers[0].formatter, logging_utils.JsonFormatter)

    def test_plain_formatter_when_hal_log_json_is_0(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HAL_LOG_JSON", "0")
        setup_logging(level="INFO")
        root = logging.getLogger()
        handler = root.handlers[0]
        assert not isinstance(handler.formatter, logging_utils.JsonFormatter)

    def test_reads_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAL_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("HAL_LOG_JSON", "1")
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.DEBUG
