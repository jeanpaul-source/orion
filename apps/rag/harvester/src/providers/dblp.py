"""DBLP API provider for computer science bibliography.

DBLP indexes 6M+ computer science publications.

Created: 2025-11-12 - Extracted from monolith
"""

from typing import List
import logging

import requests

from .base import BaseProvider, Document
from ..constants import DBLP_API

logger = logging.getLogger(__name__)


class DBLPProvider(BaseProvider):
    """DBLP computer science bibliography."""

    def __init__(self, rate_limit: float = 1.0):
        super().__init__(rate_limit)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def get_provider_name(self) -> str:
        return "dblp"

    def get_provider_type(self) -> str:
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search DBLP bibliography."""
        self._enforce_rate_limit()

        try:
            params = {
                "q": query,
                "format": "json",
                "h": min(max_results, 30),
            }
            response = self.session.get(DBLP_API, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            documents = []
            hits = data.get("result", {}).get("hits", {}).get("hit", [])

            for item in hits:
                info = item.get("info", {})
                title = info.get("title", "")
                authors = info.get("authors", {}).get("author", [])
                if isinstance(authors, dict):
                    authors = [authors]
                author_names = [
                    a.get("text", "") if isinstance(a, dict) else str(a) for a in authors
                ]
                year = info.get("year", "unknown")
                venue = info.get("venue", "")
                url = info.get("url", "")
                doi = info.get("doi", "")

                # Fix DOI URLs - prepend resolver if needed
                if doi and doi.startswith("10."):
                    pdf_url = f"https://doi.org/{doi}"
                elif doi:
                    pdf_url = doi
                else:
                    pdf_url = url

                doc = Document(
                    url=pdf_url,
                    title=title,
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year,
                        "authors": ", ".join(author_names),
                        "venue": venue,
                        "doi": doi,
                        "citation_count": 0,
                        "source": "dblp",
                    },
                )
                documents.append(doc)

            logger.info(f"DBLP: Found {len(documents)} papers for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"DBLP error for '{query}': {e}")
            return []
