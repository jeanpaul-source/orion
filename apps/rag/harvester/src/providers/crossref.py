"""Crossref API provider for academic papers.

Crossref is the official DOI registration agency with 140M+ metadata records.
Uses Unpaywall for OA PDF resolution.

Created: 2025-11-12 - Extracted from monolith
"""

from typing import List, Optional
import logging

import requests

from .base import BaseProvider, Document
from ..constants import CROSSREF_API, CONTACT_EMAIL, UNPAYWALL_API

logger = logging.getLogger(__name__)


class CrossrefProvider(BaseProvider):
    """Crossref API provider with Unpaywall PDF resolution."""

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
        return "crossref"

    def get_provider_type(self) -> str:
        return "academic"

    def _resolve_via_unpaywall(self, doi: str) -> Optional[str]:
        """Get OA PDF URL from Unpaywall."""
        if not doi:
            return None
        try:
            from urllib.parse import quote

            email = CONTACT_EMAIL or "contact@example.com"
            url = f"{UNPAYWALL_API}/{quote(doi)}"
            resp = self.session.get(url, params={"email": email}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            best = data.get("best_oa_location") or {}
            return best.get("url_for_pdf") or best.get("url")
        except Exception as e:
            logger.debug(f"Unpaywall resolve failed for DOI {doi}: {e}")
            return None

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search Crossref and resolve PDFs via Unpaywall."""
        self._enforce_rate_limit()

        try:
            params = {
                "query": query,
                "rows": min(max_results, 1000),
            }
            headers = {"User-Agent": f"OrionHarvester/1.0 ({CONTACT_EMAIL or 'no-email'})"}
            resp = self.session.get(CROSSREF_API, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            documents = []
            for item in data.get("message", {}).get("items", []):
                title_list = item.get("title") or []
                title = title_list[0] if title_list else ""
                doi = item.get("DOI") or ""

                # Extract year
                year = None
                issued = item.get("issued", {})
                if isinstance(issued, dict):
                    parts = (issued.get("date-parts") or [[None]])[0]
                    year = parts[0] if parts and parts[0] else None

                # Extract authors
                authors = []
                for a in (item.get("author") or [])[:3]:
                    name = " ".join(filter(None, [a.get("given"), a.get("family")]))
                    if name:
                        authors.append(name)

                # Try direct PDF link from Crossref
                pdf_url = None
                for link in item.get("link", []) or []:
                    if link.get("content-type") == "application/pdf" and link.get("URL"):
                        pdf_url = link["URL"]
                        break

                # Fallback to Unpaywall
                if not pdf_url and doi:
                    pdf_url = self._resolve_via_unpaywall(doi)

                if not pdf_url:
                    continue

                doc = Document(
                    url=pdf_url,
                    title=title,
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year or "unknown",
                        "authors": ", ".join(authors) if authors else "Unknown",
                        "venue": (
                            ("; ".join(item.get("container-title", [])[:1]))
                            if item.get("container-title")
                            else ""
                        ),
                        "doi": doi,
                        "citation_count": 0,
                        "source": "crossref",
                    },
                )
                documents.append(doc)

            logger.info(f"Crossref: Found {len(documents)} papers for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"Crossref error for '{query}': {e}")
            return []
