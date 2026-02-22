"""
Shared HTTP utilities for ORION ecosystem.

Provides reliable HTTP session creation with automatic retry logic,
connection pooling, and configurable failure handling.

This module consolidates 19 duplicate implementations across the codebase:
- 14 providers in harvester/src/providers/
- 4 tools in devops-agent/devia/tools/
- 1 in research-qa/src/

Author: ORION Consolidation Initiative
Date: November 17, 2025
"""

import logging
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def create_session(
    total_retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: Optional[List[int]] = None,
    allowed_methods: Optional[List[str]] = None,
    timeout: Optional[int] = None,
) -> requests.Session:
    """
    Create HTTP session with automatic retry logic.

    Implements exponential backoff with configurable retry behavior for
    resilient HTTP communication across all ORION applications.

    Args:
        total_retries: Maximum number of retries (default: 3)
        backoff_factor: Exponential backoff multiplier (default: 1.0)
                       Delays: 1s, 2s, 4s with backoff_factor=1.0
        status_forcelist: HTTP status codes to retry on
                         (default: [429, 500, 502, 503, 504])
        allowed_methods: HTTP methods to retry for
                        (default: ["GET", "POST"])
        timeout: Default timeout in seconds for requests (optional)

    Returns:
        Configured requests.Session with retry logic

    Example:
        >>> from orion_rag.common.http_utils import create_session
        >>> session = create_session()
        >>> response = session.get("https://api.example.com/data", timeout=10)
        >>>
        >>> # Custom retry configuration
        >>> session = create_session(
        ...     total_retries=5,
        ...     backoff_factor=2.0,
        ...     status_forcelist=[429, 503]
        ... )

    Note:
        This replaces all duplicate _create_session() implementations
        found throughout the codebase. Update imports to use this
        centralized version.
    """
    if status_forcelist is None:
        status_forcelist = [429, 500, 502, 503, 504]

    if allowed_methods is None:
        allowed_methods = ["GET", "POST"]

    session = requests.Session()

    # Configure retry strategy
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=allowed_methods,
    )

    # Apply retry adapter to both HTTP and HTTPS
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    logger.debug(
        f"Created HTTP session: retries={total_retries}, "
        f"backoff={backoff_factor}x, status_codes={status_forcelist}"
    )

    return session


def get_session() -> requests.Session:
    """
    Alias for create_session() with default parameters.

    Provides backward compatibility with existing code that uses
    get_session() from harvester/src/utils.py.

    Returns:
        Configured requests.Session with default retry logic

    Example:
        >>> from orion_rag.common.http_utils import get_session
        >>> session = get_session()
        >>> response = session.get("https://example.com")

    Note:
        Prefer using create_session() for new code as it provides
        more configuration options.
    """
    return create_session()


# Convenience function for one-off requests
def resilient_get(url: str, timeout: int = 10, **kwargs) -> requests.Response:
    """
    Perform resilient GET request with automatic retry.

    Convenience wrapper for one-off GET requests that don't need
    a persistent session.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds (default: 10)
        **kwargs: Additional arguments passed to requests.get()

    Returns:
        Response object

    Raises:
        requests.RequestException: On failure after all retries

    Example:
        >>> from orion_rag.common.http_utils import resilient_get
        >>> response = resilient_get("https://api.example.com/data")
        >>> data = response.json()
    """
    session = create_session()
    try:
        response = session.get(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logger.error(f"Failed to GET {url}: {e.__class__.__name__}: {e}")
        raise


def resilient_post(url: str, timeout: int = 10, **kwargs) -> requests.Response:
    """
    Perform resilient POST request with automatic retry.

    Convenience wrapper for one-off POST requests that don't need
    a persistent session.

    Args:
        url: URL to post to
        timeout: Request timeout in seconds (default: 10)
        **kwargs: Additional arguments passed to requests.post()

    Returns:
        Response object

    Raises:
        requests.RequestException: On failure after all retries

    Example:
        >>> from orion_rag.common.http_utils import resilient_post
        >>> response = resilient_post(
        ...     "https://api.example.com/data",
        ...     json={"key": "value"}
        ... )
    """
    session = create_session()
    try:
        response = session.post(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logger.error(f"Failed to POST {url}: {e.__class__.__name__}: {e}")
        raise
