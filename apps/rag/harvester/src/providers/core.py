"""CORE API provider for academic papers.

CORE (COnnecting REpositories) aggregates 250M+ open access papers from
repositories worldwide.

ELI5: CORE is like a mega-library catalog that connects thousands of university
and research institution repositories to find free research papers.

Created: 2025-11-12 - Extracted from monolith
"""

from typing import List, Optional
import logging

import requests

from .base import BaseProvider, Document
from ..constants import CORE_API, CORE_API_KEY

logger = logging.getLogger(__name__)


class COREProvider(BaseProvider):
    """CORE API provider (250M+ open access papers)."""

    def __init__(self, api_key: Optional[str] = None, rate_limit: float = 1.0):
        """
        Initialize CORE provider.

        Args:
            api_key: CORE API key (optional, but recommended for higher rate limits)
            rate_limit: Seconds between requests
        """
        super().__init__(rate_limit)
        self.api_key = api_key or CORE_API_KEY
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create session with retry logic."""
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def get_provider_name(self) -> str:
        """Return provider identifier."""
        return "core"

    def get_provider_type(self) -> str:
        """Return provider type."""
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """
        Search CORE API for academic papers.

        Args:
            query: Search query string
            max_results: Maximum results to return (max 100)

        Returns:
            List of Document objects with PDF URLs
        """
        self._enforce_rate_limit()

        try:
            params = {
                "q": query,
                "limit": min(max_results, 100),  # CORE API max is 100
            }

            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = self.session.get(CORE_API, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            documents = []
            for work in data.get("results", []):
                # CORE requires downloadUrl for PDF
                pdf_url = work.get("downloadUrl")
                if not pdf_url:
                    continue

                # Extract authors
                authors = ", ".join([a.get("name", "") for a in work.get("authors", [])[:3]])

                # Create Document
                doc = Document(
                    url=pdf_url,
                    title=work.get("title", "Unknown"),
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": work.get("yearPublished", "unknown"),
                        "authors": authors or "Unknown",
                        "venue": work.get("publisher", ""),
                        "abstract": work.get("abstract") or work.get("description", ""),
                        "citation_count": 0,  # CORE free tier doesn't provide citations
                        "source": "core",
                    },
                )
                documents.append(doc)

            logger.info(f"CORE: Found {len(documents)} papers for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"CORE error for '{query}': {e}")
            return []
