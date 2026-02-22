"""
Centralized logging configuration for ORION ecosystem.

Provides:
- Consistent logging format across applications
- Structured logging with context
- Environment-aware configuration
- Performance metrics logging
- Rotating file handlers

Author: ORION Consolidation Initiative
Date: November 17, 2025
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Literal

# ============================================================================
# LOGGING FORMATS
# ============================================================================

# Detailed format for production and file logging
DETAILED_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s "
    "[%(filename)s:%(lineno)d] - %(message)s"
)

# Simple format for console output
SIMPLE_FORMAT = "%(levelname)s - %(name)s - %(message)s"

# Minimal format for CI/CD environments
MINIMAL_FORMAT = "%(levelname)s - %(message)s"

# JSON-style structured logging format (for log aggregation)
STRUCTURED_FORMAT = (
    '{"timestamp": "%(asctime)s", "logger": "%(name)s", '
    '"level": "%(levelname)s", "file": "%(filename)s", '
    '"line": %(lineno)d, "message": "%(message)s"}'
)

# Date format
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ============================================================================
# MAIN LOGGING SETUP
# ============================================================================


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    format_style: Literal["detailed", "simple", "minimal", "structured"] = "detailed",
    console_output: bool = True,
    propagate: bool = True,
) -> logging.Logger:
    """
    Set up centralized logging for ORION applications.

    This function configures the root logger with consistent formatting,
    optional file output, and appropriate handlers for both console
    and file logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file to write logs to (with rotation)
        format_style: Log format style ("detailed", "simple", "minimal", "structured")
        console_output: Enable console output (default: True)
        propagate: Allow log propagation to parent loggers (default: True)

    Returns:
        Configured root logger

    Example:
        >>> from orion_rag.common.logging_config import setup_logging
        >>> from pathlib import Path
        >>>
        >>> # Basic setup
        >>> logger = setup_logging(level="INFO")
        >>> logger.info("Application started")
        >>>
        >>> # With file logging
        >>> logger = setup_logging(
        ...     level="DEBUG",
        ...     log_file=Path("~/.orion/logs/harvester.log").expanduser(),
        ...     format_style="detailed"
        ... )
        >>>
        >>> # Structured logging for log aggregation
        >>> logger = setup_logging(
        ...     level="INFO",
        ...     format_style="structured",
        ...     log_file=Path("/var/log/orion.json")
        ... )
    """
    # Choose format
    format_map = {
        "detailed": DETAILED_FORMAT,
        "simple": SIMPLE_FORMAT,
        "minimal": MINIMAL_FORMAT,
        "structured": STRUCTURED_FORMAT,
    }
    fmt = format_map.get(format_style, DETAILED_FORMAT)
    formatter = logging.Formatter(fmt, datefmt=DATE_FORMAT)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.propagate = propagate

    # Remove existing handlers to avoid duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler (if enabled)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler with rotation (if specified)
    if log_file:
        log_file = Path(log_file).expanduser()
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB per file
            backupCount=5,  # Keep 5 backup files
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # Log everything to file
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        root_logger.info(f"Logging to file: {log_file}")

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get logger for a module.

    This is the recommended way to get a logger in ORION applications.
    Use __name__ as the logger name to automatically namespace logs
    by module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance

    Example:
        >>> from orion_rag.common.logging_config import get_logger
        >>>
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing started")
        >>> logger.debug("Debug details: %s", data)
        >>> logger.error("Error occurred: %s", error, exc_info=True)
    """
    return logging.getLogger(name)


def configure_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[Path] = None,
    format_style: str = "detailed",
) -> logging.Logger:
    """
    Configure a specific logger (not the root logger).

    Use this when you need fine-grained control over individual loggers,
    such as setting different log levels for different modules.

    Args:
        name: Logger name
        level: Logging level
        log_file: Optional file for this specific logger
        format_style: Log format style

    Returns:
        Configured logger instance

    Example:
        >>> # Set harvester to DEBUG, but keep others at INFO
        >>> harvester_logger = configure_logger(
        ...     "orion_rag.harvester",
        ...     level="DEBUG",
        ...     log_file=Path("~/.orion/logs/harvester.log")
        ... )
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Add file handler if specified
    if log_file:
        log_file = Path(log_file).expanduser()
        log_file.parent.mkdir(parents=True, exist_ok=True)

        format_map = {
            "detailed": DETAILED_FORMAT,
            "simple": SIMPLE_FORMAT,
            "minimal": MINIMAL_FORMAT,
            "structured": STRUCTURED_FORMAT,
        }
        fmt = format_map.get(format_style, DETAILED_FORMAT)
        formatter = logging.Formatter(fmt, datefmt=DATE_FORMAT)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# ============================================================================
# SPECIALIZED LOGGING UTILITIES
# ============================================================================


def log_function_call(logger: logging.Logger, func_name: str, **kwargs):
    """
    Log function call with parameters.

    Utility for debugging function calls with their arguments.

    Args:
        logger: Logger instance
        func_name: Function name
        **kwargs: Function arguments to log

    Example:
        >>> logger = get_logger(__name__)
        >>> def process_document(doc_path, max_tokens=1000):
        ...     log_function_call(logger, "process_document",
        ...                      doc_path=doc_path, max_tokens=max_tokens)
        ...     # ... processing ...
    """
    args_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.debug(f"Calling {func_name}({args_str})")


def log_performance(logger: logging.Logger, operation: str, duration: float):
    """
    Log performance metrics.

    Args:
        logger: Logger instance
        operation: Operation name
        duration: Duration in seconds

    Example:
        >>> import time
        >>> logger = get_logger(__name__)
        >>>
        >>> start = time.time()
        >>> # ... do work ...
        >>> log_performance(logger, "document_processing", time.time() - start)
    """
    logger.info(f"Performance: {operation} took {duration:.2f}s")


def log_exception_context(logger: logging.Logger, exc: Exception, context: str):
    """
    Log exception with additional context.

    Args:
        logger: Logger instance
        exc: Exception instance
        context: Context description

    Example:
        >>> try:
        ...     response = session.get(url)
        ... except requests.RequestException as e:
        ...     log_exception_context(logger, e, f"Failed to fetch {url}")
        ...     raise
    """
    logger.error(f"{context}: {exc.__class__.__name__}: {exc}", exc_info=True)


# ============================================================================
# LOGGING DECORATORS
# ============================================================================


def logged_function(logger: logging.Logger):
    """
    Decorator to log function entry/exit with parameters.

    Args:
        logger: Logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>>
        >>> @logged_function(logger)
        ... def process_document(doc_path: Path, max_tokens: int = 1000):
        ...     # ... processing ...
        ...     return result
    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            args_repr = ", ".join(repr(a) for a in args)
            kwargs_repr = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            signature = f"{func.__name__}({args_repr}, {kwargs_repr})"

            logger.debug(f"Calling {signature}")

            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func.__name__} returned {result!r}")
                return result
            except Exception as e:
                logger.exception(f"{func.__name__} raised {e.__class__.__name__}")
                raise

        return wrapper

    return decorator


# ============================================================================
# SILENCE NOISY LOGGERS
# ============================================================================


def silence_library_loggers(libraries: Optional[list] = None):
    """
    Reduce verbosity of third-party library loggers.

    Some libraries (urllib3, requests, etc.) can be very noisy at DEBUG level.
    This function sets them to WARNING to reduce log clutter.

    Args:
        libraries: List of library names to silence (default: common noisy libraries)

    Example:
        >>> silence_library_loggers()
        >>> # Now urllib3, requests, etc. will only show WARNING and above
    """
    if libraries is None:
        libraries = [
            "urllib3",
            "requests",
            "httpx",
            "httpcore",
            "charset_normalizer",
            "filelock",
        ]

    for lib in libraries:
        logging.getLogger(lib).setLevel(logging.WARNING)
