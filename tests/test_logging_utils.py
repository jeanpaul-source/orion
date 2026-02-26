"""Tests for hal/logging_utils.py — setup_logging() handler selection.

These tests are fully offline (no external services).  They lock in the
handler-selection contract so that a future edit cannot silently revert
to a StreamHandler in REPL mode and re-introduce prompt pollution.
"""

from __future__ import annotations

import logging
import sys

import pytest
from rich.console import Console
from rich.logging import RichHandler

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
