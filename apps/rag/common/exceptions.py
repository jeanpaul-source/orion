"""
Custom exception hierarchy for ORION ecosystem.

Provides consistent error handling across all applications with
domain-specific exceptions that replace generic Exception catching.

Author: ORION Consolidation Initiative
Date: November 17, 2025
"""


class ORIONError(Exception):
    """
    Base exception for all ORION-related errors.

    All custom exceptions in the ORION ecosystem should inherit from this.
    This allows for catch-all error handling when needed while still
    providing specific exception types for granular error handling.

    Example:
        >>> try:
        ...     # ORION operation
        ... except ORIONError as e:
        ...     logger.error(f"ORION operation failed: {e}")
    """

    pass


# ============================================================================
# HARVESTER EXCEPTIONS
# ============================================================================


class HarvesterError(ORIONError):
    """Base exception for document harvesting failures."""

    pass


class ProviderError(HarvesterError):
    """
    Academic provider API error.

    Raised when an academic API (arXiv, Semantic Scholar, etc.) returns
    an error or unexpected response.
    """

    pass


class RateLimitError(HarvesterError):
    """
    API rate limit exceeded.

    Raised when too many requests are made to an API and rate limiting
    is triggered. Should trigger exponential backoff.
    """

    pass


class DocumentNotFoundError(HarvesterError):
    """
    Requested document not found.

    Raised when a specific paper or document cannot be located via
    the provider API.
    """

    pass


class DownloadError(HarvesterError):
    """
    Document download failed.

    Raised when PDF/document download fails due to network issues,
    invalid URL, or server errors.
    """

    pass


class ParseError(HarvesterError):
    """
    Document parsing failed.

    Raised when PDF extraction, HTML parsing, or metadata extraction
    fails due to malformed content or unsupported format.
    """

    pass


# ============================================================================
# INGESTION EXCEPTIONS
# ============================================================================


class IngestionError(ORIONError):
    """Base exception for document ingestion failures."""

    pass


class QualityGateError(IngestionError):
    """
    Document failed quality validation.

    Raised when a document doesn't meet minimum quality thresholds
    (text density, token count, etc.) and is rejected from ingestion.
    """

    pass


class EmbeddingError(IngestionError):
    """
    Document embedding generation failed.

    Raised when vector embedding creation fails due to model errors,
    out-of-memory conditions, or invalid input text.
    """

    pass


class VectorDBError(IngestionError):
    """
    Vector database operation failed.

    Raised when Qdrant operations (insert, update, delete, search) fail
    due to connection issues, invalid data, or internal errors.
    """

    pass


class ChunkingError(IngestionError):
    """
    Document chunking failed.

    Raised when text splitting/chunking operations fail due to
    invalid input, token counting errors, or configuration issues.
    """

    pass


# ============================================================================
# CONFIGURATION EXCEPTIONS
# ============================================================================


class ConfigurationError(ORIONError):
    """
    Configuration validation failed.

    Raised when configuration values are invalid, missing required fields,
    or fail Pydantic validation.
    """

    pass


class ProfileError(ConfigurationError):
    """
    Invalid profile specified.

    Raised when an unknown profile name is provided (valid: laptop, host, dev, test).
    """

    pass


class APIKeyError(ConfigurationError):
    """
    API key missing or invalid.

    Raised when required API credentials are not found in environment
    variables or configuration files.
    """

    pass


# ============================================================================
# RAG QUERY EXCEPTIONS
# ============================================================================


class QueryError(ORIONError):
    """Base exception for RAG query failures."""

    pass


class AnythingLLMError(QueryError):
    """
    AnythingLLM API error.

    Raised when AnythingLLM API requests fail due to authentication,
    connection issues, or internal server errors.
    """

    pass


class RetrievalError(QueryError):
    """
    Document retrieval from vector DB failed.

    Raised when semantic search or vector retrieval operations fail.
    """

    pass


class LLMError(QueryError):
    """
    LLM inference error.

    Raised when vLLM, Ollama, or other LLM backend fails during
    text generation or completion.
    """

    pass


# ============================================================================
# DEVOPS AGENT EXCEPTIONS
# ============================================================================


class DevOpsAgentError(ORIONError):
    """Base exception for DevOps Agent (devia) errors."""

    pass


class ToolExecutionError(DevOpsAgentError):
    """
    Tool execution failed.

    Raised when one of devia's 46 autonomous tools encounters an error
    during execution.
    """

    pass


class ORIONIntegrationError(DevOpsAgentError):
    """
    ORION integration error.

    Raised when devia fails to query ORION's knowledge base via
    AnythingLLM API.
    """

    pass


# ============================================================================
# FILE OPERATION EXCEPTIONS
# ============================================================================


class FileOperationError(ORIONError):
    """Base exception for file operation failures."""

    pass


class DuplicateFileError(FileOperationError):
    """
    File already exists in registry.

    Raised during deduplication checks when a file with the same
    content hash already exists in the system.
    """

    pass


class InvalidFileError(FileOperationError):
    """
    File is invalid or corrupted.

    Raised when file validation fails (wrong format, corrupted, too small, etc.).
    """

    pass


# ============================================================================
# NETWORK EXCEPTIONS
# ============================================================================


class NetworkError(ORIONError):
    """
    Network communication failed.

    Raised when HTTP requests fail after all retry attempts, or when
    network connectivity issues prevent communication with services.
    """

    pass


class ServiceUnavailableError(NetworkError):
    """
    Required service is unavailable.

    Raised when Qdrant, vLLM, AnythingLLM, or other required services
    cannot be reached or are not responding.
    """

    pass


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_exception_chain(exc: Exception) -> str:
    """
    Get full exception chain as formatted string.

    Useful for logging the complete error context including all
    chained exceptions (caused by __cause__ or __context__).

    Args:
        exc: Exception instance

    Returns:
        Formatted string with exception chain

    Example:
        >>> try:
        ...     raise ValueError("Invalid input")
        ... except ValueError as e:
        ...     new_exc = HarvesterError("Harvest failed") from e
        ...     print(get_exception_chain(new_exc))
    """
    chain = []
    current = exc

    while current is not None:
        chain.append(f"{current.__class__.__name__}: {current}")
        current = current.__cause__ if current.__cause__ else current.__context__

    return " → ".join(chain)
