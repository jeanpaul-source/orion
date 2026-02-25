"""Web search via Tavily — Level 0 internet access for HAL.

Privacy guard: RFC1918 addresses and private hostnames are stripped from
outbound queries before they reach the Tavily API.

This module is imported conditionally by hal/agent.py — the web_search tool
only appears in TOOLS when TAVILY_API_KEY is set.
"""

import re

from hal.logging_utils import get_logger

log = get_logger(__name__)

# Patterns that leak lab topology — stripped from search queries
_PRIVATE_IP_RE = re.compile(
    r"\b("
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"  # 10.0.0.0/8
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"  # 172.16.0.0/12
    r"|192\.168\.\d{1,3}\.\d{1,3}"  # 192.168.0.0/16
    r"|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"  # loopback
    r"|100\.\d{1,3}\.\d{1,3}\.\d{1,3}"  # Tailscale CGNAT
    r")\b"
)

_PRIVATE_HOSTNAME_RE = re.compile(
    r"(?:\blocalhost\b|\bthe-lab\b|\.local\b|\.internal\b)", re.IGNORECASE
)


def sanitize_query(query: str) -> str:
    """Remove private IPs and hostnames from a search query.

    Returns the cleaned query string.  Raises ValueError if the query
    becomes empty after sanitisation (i.e., it was *only* private data).
    """
    cleaned = _PRIVATE_IP_RE.sub("", query)
    cleaned = _PRIVATE_HOSTNAME_RE.sub("", cleaned)
    # Collapse leftover whitespace
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if not cleaned:
        raise ValueError(
            "Search query contained only private addresses/hostnames — "
            "refusing to send an empty query to the search API."
        )
    return cleaned


def web_search(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """Search the web via Tavily and return a list of results.

    Each result dict contains: title, url, content, score.

    Args:
        query: Natural-language search query.
        api_key: Tavily API key.  Must not be empty.
        max_results: Number of results to request (default 5).

    Returns:
        List of dicts, each with keys: title, url, content, score.

    Raises:
        ValueError: If api_key is empty or query is only private data.
    """
    if not api_key:
        raise ValueError("TAVILY_API_KEY is not set — web search is disabled.")

    cleaned = sanitize_query(query)
    log.info("web_search query=%r (sanitised from %r)", cleaned, query)

    try:
        from tavily import TavilyClient
    except ImportError:
        raise RuntimeError(
            "tavily-python is not installed. Run: pip install tavily-python"
        )

    client = TavilyClient(api_key=api_key)
    response = client.search(query=cleaned, max_results=max_results)

    results = []
    for item in response.get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0.0),
            }
        )

    log.info("web_search returned %d results", len(results))
    return results
