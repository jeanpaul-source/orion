"""Semantic Scholar API provider for academic papers.

Semantic Scholar uses AI to understand research papers with 200M+ papers indexed.

Created: 2025-11-12 - Converted to class-based provider
"""

from datetime import datetime
from typing import List, Optional
import logging

import requests

from .base import BaseProvider, Document
from ..constants import SEMANTIC_SCHOLAR_API, S2_API_KEY

logger = logging.getLogger(__name__)


class SemanticScholarProvider(BaseProvider):
    """Semantic Scholar API provider with citation data."""

    def __init__(self, api_key: Optional[str] = None, rate_limit: float = 1.0):
        super().__init__(rate_limit)
        self.api_key = api_key or S2_API_KEY
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
        return "semantic_scholar"

    def get_provider_type(self) -> str:
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search Semantic Scholar with AI-powered relevance."""
        self._enforce_rate_limit()

        try:
            params = {
                "query": query,
                "fields": (
                    "title,abstract,authors,year,venue,publicationTypes,openAccessPdf,"
                    "citationCount,influentialCitationCount"
                ),
                "limit": min(max_results, 100),
            }
            headers = {}
            if self.api_key:
                headers["X-API-KEY"] = self.api_key

            response = self.session.get(
                SEMANTIC_SCHOLAR_API, params=params, headers=headers, timeout=10
            )  # noqa: E501
            response.raise_for_status()
            data = response.json()

            documents = []
            for paper in data.get("data", []):
                if not (paper.get("openAccessPdf") and paper["openAccessPdf"].get("url")):
                    continue

                citation_count = paper.get("citationCount", 0)
                influential_count = paper.get("influentialCitationCount", 0)
                year = paper.get("year", None)

                # Calculate citations per year
                citations_per_year = 0.0
                if citation_count and year:
                    try:
                        current_year = datetime.now().year
                        age = current_year - int(year)
                        if age > 0:
                            citations_per_year = citation_count / age
                    except (ValueError, TypeError) as e:
                        msg = (
                            "Could not calculate citations per year for paper "
                            f"'{paper.get('title', 'unknown')}': {e}"
                        )
                        logger.debug(msg)

                doc = Document(
                    url=paper["openAccessPdf"]["url"],
                    title=paper.get("title", ""),
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year if year else "unknown",
                        "authors": ", ".join(
                            [a.get("name", "") for a in paper.get("authors", [])[:3]]
                        ),  # noqa: E501
                        "venue": paper.get("venue", ""),
                        "abstract": paper.get("abstract", ""),
                        "citation_count": citation_count,
                        "influential_citation_count": influential_count,
                        "citations_per_year": round(citations_per_year, 2),
                        "source": "semantic_scholar",
                    },
                )
                documents.append(doc)

            logger.info(f"Semantic Scholar: Found {len(documents)} papers for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"Semantic Scholar error for '{query}': {e}")
            return []
