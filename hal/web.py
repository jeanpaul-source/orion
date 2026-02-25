"""Web access for HAL — search (Level 0) and page fetch (Level 1).

Privacy guard: RFC1918 addresses and private hostnames are stripped from
outbound queries before they reach the Tavily API.

SSRF protection: fetch_url validates URLs against a blocklist (RFC1918,
loopback, link-local, non-HTTP(S) schemes) and resolves DNS to verify
the target IP before connecting — catches DNS rebinding attacks.

web_search is imported conditionally by hal/agent.py — only when
TAVILY_API_KEY is set.  fetch_url is always available.
"""

import ipaddress
import re
import socket
from urllib.parse import urlparse

import requests
import trafilatura

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


# ---------------------------------------------------------------------------
# Level 1 — fetch_url (read-only page content extraction)
# ---------------------------------------------------------------------------

# Hard limits to protect against resource exhaustion
_FETCH_TIMEOUT_SECS = 10
_MAX_RESPONSE_BYTES = 1_048_576  # 1 MB
_MAX_OUTPUT_CHARS = 15_000

# Blocked TLDs / domain suffixes (SSRF)
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".onion")


def _is_private_ip(ip_str: str) -> bool:
    """Return True if *ip_str* is a private, loopback, link-local, or
    reserved address that should never be fetched."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


def _validate_url(url: str) -> str:
    """Validate and normalise a URL for safe fetching.

    Returns the normalised URL string.

    Raises ``ValueError`` on any policy violation:
    - Non-HTTP(S) scheme
    - Hostname resolves to a private/loopback/link-local IP (SSRF)
    - Blocked TLD (.local, .internal, .localhost, .onion)
    - Missing or empty hostname

    DNS resolution happens *before* the HTTP request so that DNS rebinding
    attacks cannot redirect an allowed hostname to 127.0.0.1 mid-flight.
    """
    parsed = urlparse(url)

    # --- Scheme ---
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Blocked scheme '{parsed.scheme}://' — only http:// and https:// are allowed."
        )

    # --- Hostname ---
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("URL has no hostname.")

    # Block known-private TLDs
    lower = hostname.lower()
    if lower == "localhost" or any(lower.endswith(s) for s in _BLOCKED_SUFFIXES):
        raise ValueError(f"Blocked private hostname: {hostname}")

    # --- DNS resolution + IP check ---
    # Check if the hostname is already a literal IP
    if _is_private_ip(hostname):
        raise ValueError(f"Blocked private/reserved IP: {hostname}")

    # Resolve hostname → IP and verify *every* returned address
    try:
        addrinfos = socket.getaddrinfo(
            hostname, parsed.port or 443, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror:
        raise ValueError(f"DNS resolution failed for {hostname}")

    for family, _type, _proto, _canon, sockaddr in addrinfos:
        ip = sockaddr[0]
        if _is_private_ip(ip):
            raise ValueError(
                f"DNS for {hostname} resolved to private IP {ip} — blocked (possible SSRF/rebinding)."
            )

    return url


def fetch_url(url: str, max_chars: int = _MAX_OUTPUT_CHARS) -> str:
    """Fetch a public URL and extract article text.

    Uses ``requests`` for HTTP and ``trafilatura`` for content extraction
    (same library used by ``harvest/parsers.py``).

    Args:
        url: The URL to fetch (must be http:// or https://).
        max_chars: Maximum characters in the returned text (default 15 000).

    Returns:
        Extracted article text, truncated to *max_chars* with a marker if
        the full text was longer.

    Raises:
        ValueError: If the URL fails SSRF validation.
        RuntimeError: If the fetch or extraction fails.
    """
    url = _validate_url(url)
    log.info("fetch_url url=%r", url)

    try:
        resp = requests.get(
            url,
            timeout=_FETCH_TIMEOUT_SECS,
            headers={"User-Agent": "Orion-HAL/1.0 (homelab assistant)"},
            stream=True,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"HTTP request failed: {exc}") from exc

    # Re-validate after redirects — the final URL may point somewhere private
    if resp.url != url:
        _validate_url(resp.url)

    resp.raise_for_status()

    # Enforce size cap (read in chunks)
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65_536):
        chunks.append(chunk)
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            log.warning("fetch_url response exceeded 1 MB — truncating")
            break
    raw_bytes = b"".join(chunks)

    # Content extraction via trafilatura
    text = trafilatura.extract(raw_bytes.decode("utf-8", errors="replace"))
    if not text:
        # Fallback: strip HTML tags (same approach as harvest/parsers.py)
        fallback = re.sub(r"<[^>]+>", " ", raw_bytes.decode("utf-8", errors="replace"))
        text = re.sub(r"\s+", " ", fallback).strip()

    if not text:
        raise RuntimeError("Page fetched but no readable text could be extracted.")

    # Truncate with clear marker
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n--- [content truncated at 15 000 chars] ---"

    log.info("fetch_url extracted %d chars from %s", len(text), url)
    return text
