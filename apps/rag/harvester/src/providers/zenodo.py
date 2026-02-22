"""Zenodo API provider for open access research.

Zenodo is CERN's open repository with 5M+ research outputs.

Created: 2025-11-12 - Extracted from monolith
"""

from typing import List
import logging

import requests

from .base import BaseProvider, Document
from ..constants import ZENODO_API

logger = logging.getLogger(__name__)


class ZenodoProvider(BaseProvider):
    """Zenodo API provider (CERN open repository)."""

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
        return "zenodo"

    def get_provider_type(self) -> str:
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search Zenodo for OA publications."""
        self._enforce_rate_limit()

        try:
            params = {
                "q": query,
                "type": "publication",
                "access_right": "open",
                "size": min(max_results, 500),
            }
            resp = self.session.get(ZENODO_API, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            documents = []
            for rec in data.get("hits", {}).get("hits", []):
                metadata = rec.get("metadata", {})
                title = metadata.get("title", "")
                year = metadata.get("publication_date", "")[:4]
                creators = ", ".join(
                    [c.get("name", "") for c in (metadata.get("creators") or [])[:3]]
                )

                # Find PDF file
                pdf_url = None
                files = rec.get("files") or []
                for f in files:
                    if (f.get("type") == "pdf") or (f.get("mimetype") == "application/pdf"):
                        pdf_url = f.get("links", {}).get("self") or f.get("links", {}).get(
                            "download"
                        )
                        break

                if not pdf_url:
                    links = rec.get("links", {})
                    pdf_url = links.get("pdf") or links.get("download")

                if not pdf_url:
                    continue

                doc = Document(
                    url=pdf_url,
                    title=title,
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year or "unknown",
                        "authors": creators or "Unknown",
                        "venue": metadata.get("journal", {}).get("title", ""),
                        "doi": metadata.get("doi", ""),
                        "citation_count": 0,
                        "source": "zenodo",
                    },
                )
                documents.append(doc)

            logger.info(f"Zenodo: Found {len(documents)} papers for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"Zenodo error for '{query}': {e}")
            return []
