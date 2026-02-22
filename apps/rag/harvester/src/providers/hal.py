"""HAL API provider for French open archive.

HAL (Hyper Articles en Ligne) is France's national open archive with 1M+ documents.

Created: 2025-11-12 - Extracted from monolith
"""

from typing import List
import logging

import requests

from .base import BaseProvider, Document
from ..constants import HAL_API

logger = logging.getLogger(__name__)


class HALProvider(BaseProvider):
    """HAL French open archive."""

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
        return "hal"

    def get_provider_type(self) -> str:
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search HAL open archive."""
        self._enforce_rate_limit()

        try:
            params = {
                "q": query,
                "rows": min(max_results, 30),
                "fl": (
                    "title_s,authFullName_s,producedDateY_i,journalTitle_s,"  # noqa: E501
                    "fileMain_s,uri_s,abstract_s"
                ),
                "wt": "json",
            }
            response = self.session.get(HAL_API, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            documents = []
            docs = data.get("response", {}).get("docs", [])

            for item in docs:
                title = item.get("title_s", [""])[0] if item.get("title_s") else ""
                authors = item.get("authFullName_s", [])
                year = str(item.get("producedDateY_i", "unknown"))
                venue = item.get("journalTitle_s", [""])[0] if item.get("journalTitle_s") else ""
                pdf_url = item.get("fileMain_s", "")
                uri = item.get("uri_s", "")
                abstract = item.get("abstract_s", [""])[0] if item.get("abstract_s") else ""

                url = pdf_url if pdf_url else uri

                doc = Document(
                    url=url,
                    title=title,
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year,
                        "authors": ", ".join(authors),
                        "venue": venue,
                        "abstract": abstract,
                        "citation_count": 0,
                        "source": "hal",
                    },
                )
                documents.append(doc)

            logger.info(f"HAL: Found {len(documents)} documents for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"HAL error for '{query}': {e}")
            return []
