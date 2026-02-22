"""OpenAlex API provider for academic papers.

OpenAlex is a free, open catalog of 250M+ scholarly works with comprehensive metadata.

Created: 2025-11-12 - Converted to class-based provider
"""

from datetime import datetime
from typing import Dict, List, Optional
import logging

import requests

from .base import BaseProvider, Document
from ..constants import OPENALEX_API, CONTACT_EMAIL

logger = logging.getLogger(__name__)


def _reconstruct_openalex_abstract(inv_index: Optional[Dict[str, List[int]]]) -> str:
    """Rebuild OpenAlex's inverted index format into plain text."""
    if not inv_index:
        return ""
    try:
        max_pos = max(max(pos_list) for pos_list in inv_index.values())
        words: List[Optional[str]] = [None] * (max_pos + 1)
        for word, positions in inv_index.items():
            for pos in positions:
                if 0 <= pos < len(words):
                    words[pos] = word
        return " ".join([w for w in words if w])
    except Exception:
        return ""


class OpenAlexProvider(BaseProvider):
    """OpenAlex comprehensive scholarly database."""

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
        return "openalex"

    def get_provider_type(self) -> str:
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search OpenAlex for OA scholarly works."""
        self._enforce_rate_limit()

        try:
            params = {
                "search": query,
                "filter": "is_oa:true,type:article",
                "per-page": min(max_results, 100),
                "sort": "cited_by_count:desc",
            }
            if CONTACT_EMAIL:
                params["mailto"] = CONTACT_EMAIL
            user_agent_email = f"mailto:{CONTACT_EMAIL}" if CONTACT_EMAIL else "no-email"
            headers = {"User-Agent": f"OrionHarvester/1.0 ({user_agent_email})"}

            response = self.session.get(OPENALEX_API, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            documents = []
            for work in data.get("results", []):
                pdf_url = None
                best_location = work.get("best_oa_location") or work.get("primary_location")
                if best_location and best_location.get("pdf_url"):
                    pdf_url = best_location["pdf_url"]

                if not pdf_url:
                    continue

                authors = ", ".join(
                    [
                        a.get("author", {}).get("display_name", "")
                        for a in work.get("authorships", [])[:3]
                    ]
                )
                venue_name = ""
                host_venue = work.get("host_venue") or {}
                if isinstance(host_venue, dict):
                    venue_name = host_venue.get("display_name", "")

                citation_count = work.get("cited_by_count", 0)
                year = work.get("publication_year", None)

                citations_per_year = 0.0
                if citation_count and year:
                    try:
                        current_year = datetime.now().year
                        age = current_year - int(year)
                        if age > 0:
                            citations_per_year = citation_count / age
                    except (ValueError, TypeError) as e:
                        msg = (
                            "Could not calculate citations per year for work "
                            f"'{work.get('title', 'unknown')}': {e}"
                        )
                        logger.debug(msg)

                doc = Document(
                    url=pdf_url,
                    title=work.get("title", ""),
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year if year else "unknown",
                        "authors": authors or "Unknown",
                        "venue": venue_name,
                        "abstract": _reconstruct_openalex_abstract(
                            work.get("abstract_inverted_index")
                        ),
                        "citation_count": citation_count,
                        "influential_citation_count": 0,
                        "citations_per_year": round(citations_per_year, 2),
                        "source": "openalex",
                    },
                )
                documents.append(doc)

            logger.info(f"OpenAlex: Found {len(documents)} papers for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"OpenAlex error for '{query}': {e}")
            return []
