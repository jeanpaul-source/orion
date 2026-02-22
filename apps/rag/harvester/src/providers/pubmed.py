"""PubMed Central API provider for biomedical literature.

PubMed Central provides free access to 8M+ full-text articles.

Created: 2025-11-12 - Extracted from monolith
"""

from typing import List
import logging

import requests

from .base import BaseProvider, Document
from ..constants import PUBMED_API

logger = logging.getLogger(__name__)


class PubMedProvider(BaseProvider):
    """PubMed Central via E-utilities API."""

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
        return "pubmed"

    def get_provider_type(self) -> str:
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search PubMed Central (2-step: search then fetch)."""
        self._enforce_rate_limit()

        try:
            # Step 1: Search for PMC IDs
            search_url = f"{PUBMED_API}/esearch.fcgi"
            params = {
                "db": "pmc",
                "term": query,
                "retmax": min(max_results, 30),
                "retmode": "json",
                "sort": "relevance",
            }
            response = self.session.get(search_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            pmc_ids = data.get("esearchresult", {}).get("idlist", [])
            if not pmc_ids:
                return []

            # Step 2: Fetch summaries
            summary_url = f"{PUBMED_API}/esummary.fcgi"
            params = {"db": "pmc", "id": ",".join(pmc_ids), "retmode": "json"}
            response = self.session.get(summary_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            documents = []
            result_data = data.get("result", {})

            for pmc_id in pmc_ids:
                item = result_data.get(pmc_id, {})
                if not isinstance(item, dict):
                    continue

                title = item.get("title", "")
                authors = item.get("authors", [])
                author_names = [a.get("name", "") for a in authors if isinstance(a, dict)]
                pub_date = item.get("pubdate", "")
                year = pub_date.split()[0] if pub_date else "unknown"
                journal = item.get("fulljournalname", "")

                pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"

                doc = Document(
                    url=pdf_url,
                    title=title,
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year,
                        "authors": ", ".join(author_names),
                        "venue": journal,
                        "pmc_id": pmc_id,
                        "citation_count": 0,
                        "source": "pubmed",
                    },
                )
                documents.append(doc)

            logger.info(f"PubMed: Found {len(documents)} articles for '{query}'")
            return documents

        except Exception as e:
            logger.error(f"PubMed error for '{query}': {e}")
            return []
