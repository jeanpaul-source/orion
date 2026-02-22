"""
ORION Common Utilities

Shared utilities and patterns for the ORION ecosystem.

This module consolidates code that was previously duplicated across:
- harvester (14 providers)
- research-qa (ingestion pipeline)
- devops-agent (46 tools)

Provides:
- HTTP session management with automatic retry
- File utilities (sanitization, hashing, validation)
- Logging configuration (structured, rotating)
- Exception hierarchy (domain-specific errors)
- Default constants (IPs, ports, paths)

Author: ORION Consolidation Initiative
Date: November 17, 2025
Version: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "ORION Consolidation Initiative"

# ============================================================================
# PUBLIC API - Import commonly used utilities
# ============================================================================

# HTTP utilities
from .http_utils import (
    create_session,
    get_session,
    resilient_get,
    resilient_post,
)

# File utilities
from .file_utils import (
    sanitize_filename,
    compute_file_hash,
    file_changed,
    validate_file,
    ensure_directory,
    get_file_extension,
    safe_filename_from_url,
)

# Logging
from .logging_config import (
    setup_logging,
    get_logger,
    configure_logger,
    log_function_call,
    log_performance,
    log_exception_context,
    silence_library_loggers,
)

# Exceptions
from .exceptions import (
    # Base
    ORIONError,
    # Harvester
    HarvesterError,
    ProviderError,
    RateLimitError,
    DocumentNotFoundError,
    DownloadError,
    ParseError,
    # Ingestion
    IngestionError,
    QualityGateError,
    EmbeddingError,
    VectorDBError,
    ChunkingError,
    # Configuration
    ConfigurationError,
    ProfileError,
    APIKeyError,
    # Query
    QueryError,
    AnythingLLMError,
    RetrievalError,
    LLMError,
    # DevOps Agent
    DevOpsAgentError,
    ToolExecutionError,
    ORIONIntegrationError,
    # File operations
    FileOperationError,
    DuplicateFileError,
    InvalidFileError,
    # Network
    NetworkError,
    ServiceUnavailableError,
)

# Defaults (imported as module to avoid namespace pollution)
from . import defaults

# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

__all__ = [
    # HTTP
    "create_session",
    "get_session",
    "resilient_get",
    "resilient_post",
    # Files
    "sanitize_filename",
    "compute_file_hash",
    "file_changed",
    "validate_file",
    "ensure_directory",
    "get_file_extension",
    "safe_filename_from_url",
    # Logging
    "setup_logging",
    "get_logger",
    "configure_logger",
    "log_function_call",
    "log_performance",
    "log_exception_context",
    "silence_library_loggers",
    # Exceptions
    "ORIONError",
    "HarvesterError",
    "ProviderError",
    "RateLimitError",
    "DocumentNotFoundError",
    "DownloadError",
    "ParseError",
    "IngestionError",
    "QualityGateError",
    "EmbeddingError",
    "VectorDBError",
    "ChunkingError",
    "ConfigurationError",
    "ProfileError",
    "APIKeyError",
    "QueryError",
    "AnythingLLMError",
    "RetrievalError",
    "LLMError",
    "DevOpsAgentError",
    "ToolExecutionError",
    "ORIONIntegrationError",
    "FileOperationError",
    "DuplicateFileError",
    "InvalidFileError",
    "NetworkError",
    "ServiceUnavailableError",
    # Modules
    "defaults",
]
