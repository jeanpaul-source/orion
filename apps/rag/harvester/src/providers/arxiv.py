"""arXiv API provider for preprints.

arXiv is the leading preprint server with 2M+ papers in physics, math, CS, etc.

Created: 2025-11-12 - Converted to class-based provider
Updated: 2025-11-17 - Migrated to common utilities (Phase 1 consolidation)
"""

from typing import List
import logging
import xml.etree.ElementTree as ET

import requests

from .base import BaseProvider, Document
from ..constants import ARXIV_API, MAX_RESULTS_PER_TERM

# Import from common module (replaces local _create_session)
import sys
from pathlib import Path

# Add common module to path (one level up from harvester, then into common)
_common_path = Path(__file__).parent.parent.parent.parent / "common"
if str(_common_path) not in sys.path:
    sys.path.insert(0, str(_common_path))

from http_utils import create_session  # noqa: E402 # type: ignore[import-not-found]
from exceptions import ProviderError  # noqa: E402 # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


class ArxivProvider(BaseProvider):
    """arXiv preprint server provider."""

    def __init__(self, rate_limit: float = 1.0):
        super().__init__(rate_limit)
        # Use shared HTTP session from common module
        self.session = create_session()

    def get_provider_name(self) -> str:
        return "arxiv"

    def get_provider_type(self) -> str:
        return "academic"

    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """Search arXiv for preprints."""
        self._enforce_rate_limit()

        try:
            params = {
                "search_query": f"all:{query}",
                "max_results": min(max_results, MAX_RESULTS_PER_TERM),
                "sortBy": "relevance",
            }
            response = self.session.get(ARXIV_API, params=params, timeout=10)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            documents = []
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
                if title_elem is None or title_elem.text is None:
                    continue
                title = title_elem.text.strip()

                # Find PDF link
                pdf_link = None
                for link in entry.findall("{http://www.w3.org/2005/Atom}link"):
                    if link.get("type") == "application/pdf":
                        pdf_link = link.get("href")
                        break

                if not pdf_link:
                    continue

                published_elem = entry.find("{http://www.w3.org/2005/Atom}published")
                year = (
                    published_elem.text[:4]
                    if published_elem is not None and published_elem.text
                    else "unknown"
                )
                summary_elem = entry.find("{http://www.w3.org/2005/Atom}summary")
                abstract = ""
                if summary_elem is not None and summary_elem.text:
                    abstract = " ".join(summary_elem.text.split())

                doc = Document(
                    url=pdf_link,
                    title=title,
                    content_type="pdf",
                    source_provider=self.get_provider_name(),
                    metadata={
                        "year": year,
                        "authors": "arXiv",
                        "venue": "arXiv",
                        "abstract": abstract,
                        "citation_count": 0,
                        "source": "arxiv",
                    },
                )
                documents.append(doc)

            logger.info(f"arXiv: Found {len(documents)} preprints for '{query}'")
            return documents

        except requests.RequestException as e:
            logger.error(f"arXiv HTTP request failed for '{query}': {e}", exc_info=True)
            raise ProviderError(f"arXiv API request failed") from e
        except ET.ParseError as e:
            logger.error(f"arXiv XML parsing failed for '{query}': {e}", exc_info=True)
            return []
        except Exception:
            logger.exception(f"Unexpected arXiv error for '{query}'")
            return []
