"""medRxiv API provider for medical preprints.

medRxiv hosts medical/health sciences preprints (sibling of bioRxiv).

Created: 2025-11-12 - Extracted from monolith
"""

from typing import List
import logging
from datetime import datetime, timedelta

import requests

from .base import BaseProvider, Document
from ..constants import MEDRXIV_API

logger = logging.getLogger(__name__)


class MedrxivProvider(BaseProvider):
    """medRxiv medical preprint server."""

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
        return "medrxiv"

    def get_provider_type(self) -> str:
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search medRxiv preprints (last 5 years)."""
        self._enforce_rate_limit()

        try:
            # medRxiv uses same API as bioRxiv
            end_date = datetime.now()
            start_date = end_date - timedelta(days=1825)  # ~5 years

            url = (
                f"{MEDRXIV_API}/{start_date.strftime('%Y-%m-%d')}/"
                f"{end_date.strftime('%Y-%m-%d')}/0"
            )
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            documents = []
            collection = data.get("collection", [])
            query_terms = query.lower().split()

            for item in collection:
                title = item.get("title", "")
                abstract = item.get("abstract", "")
                content = (title + " " + abstract).lower()

                # Filter by query terms
                if not any(term in content for term in query_terms):
                    continue

                authors = item.get("authors", "")
                date = item.get("date", "")
                year = date.split("-")[0] if date else "unknown"
                doi = item.get("doi", "")
                pdf_url = f"https://www.medrxiv.org/content/{doi}v1.full.pdf" if doi else ""

                if not pdf_url:
                    continue

                doc = Document(
                    url=pdf_url,
                    title=title,
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year,
                        "authors": authors,
                        "venue": "medRxiv",
                        "abstract": abstract,
                        "doi": doi,
                        "citation_count": 0,
                        "source": "medrxiv",
                    },
                )
                documents.append(doc)

                if len(documents) >= max_results:
                    break

            logger.info(f"medRxiv: Found {len(documents)} preprints for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"medRxiv error for '{query}': {e}")
            return []
