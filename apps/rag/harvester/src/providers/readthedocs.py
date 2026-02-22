"""ReadTheDocs documentation harvester.

Scrapes ReadTheDocs-hosted documentation sites.

ELI5: Like a specialized web crawler that knows how ReadTheDocs
websites are organized and can download all the documentation pages.
"""

from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
from datetime import datetime
import logging

from .base import BaseProvider, Document
from ..converters.html_converter import HTMLConverter
from ..doc_config import DEFAULT_RATE_LIMIT, DEFAULT_TIMEOUT, MAX_RETRIES, USER_AGENT

logger = logging.getLogger(__name__)


class ReadTheDocsProvider(BaseProvider):
    """Harvest documentation from ReadTheDocs sites."""

    def __init__(self, base_url: str, max_depth: int = 3, rate_limit: float = DEFAULT_RATE_LIMIT):
        """
        Initialize ReadTheDocs harvester.

        Args:
            base_url: Base URL of ReadTheDocs site (e.g., https://docs.docker.com)
            max_depth: Maximum link depth to crawl
            rate_limit: Seconds between requests
        """
        super().__init__(rate_limit)
        self.base_url = base_url.rstrip("/")
        self.max_depth = max_depth
        self.converter = HTMLConverter()
        self.visited_urls = set()

        self.session = self._create_session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic for reliability"""
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()

        # Retry on connection errors, timeouts, and 5xx server errors
        retry = Retry(
            total=3,
            backoff_factor=1,  # 1s, 2s, 4s delays
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )

        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def get_provider_name(self) -> str:
        """Return provider identifier."""
        return "readthedocs"

    def get_provider_type(self) -> str:
        """Return provider type."""
        return "documentation"

    def discover(self) -> List[str]:
        """
        Discover documentation pages.

        Strategy:
        1. Try to find sitemap.xml
        2. Fallback to crawling from base URL
        """
        urls = []

        # Try sitemap first
        sitemap_urls = self._discover_from_sitemap()
        if sitemap_urls:
            return sitemap_urls

        # Fallback: crawl from base
        urls = self._crawl_from_base()

        return urls

    def _discover_from_sitemap(self) -> List[str]:
        """Try to discover URLs from sitemap.xml."""
        sitemap_urls = [
            f"{self.base_url}/sitemap.xml",
            f"{self.base_url}/sitemap_index.xml",
        ]

        all_urls = []

        for sitemap_url in sitemap_urls:
            try:
                self._enforce_rate_limit()
                response = self.session.get(sitemap_url, timeout=DEFAULT_TIMEOUT)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "xml")

                    # Extract URLs from sitemap
                    for loc in soup.find_all("loc"):
                        url = loc.text.strip()
                        if url.startswith(self.base_url):
                            all_urls.append(url)

                    if all_urls:
                        return all_urls
            except Exception:
                continue

        return []

    def _crawl_from_base(self) -> List[str]:
        """Crawl documentation pages starting from base URL."""
        to_visit = [(self.base_url, 0)]  # (url, depth)
        discovered = []

        while to_visit:
            url, depth = to_visit.pop(0)

            if url in self.visited_urls or depth > self.max_depth:
                continue

            self.visited_urls.add(url)
            discovered.append(url)

            # Find links on this page
            if depth < self.max_depth:
                links = self._extract_links(url)
                for link in links:
                    if link not in self.visited_urls:
                        to_visit.append((link, depth + 1))

            # Be nice to the server
            time.sleep(self.rate_limit)

        return discovered

    def _extract_links(self, url: str) -> List[str]:
        """Extract documentation links from a page."""
        try:
            self._enforce_rate_limit()
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)

            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, "html.parser")
            links = []

            # Find all links
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                full_url = urljoin(url, str(href))

                # Only include links within the documentation
                if self._is_doc_link(full_url):
                    links.append(full_url)

            return links

        except Exception:
            return []

    def _is_doc_link(self, url: str) -> bool:
        """Check if URL is a documentation page (not external/anchor)."""
        # Must be same domain
        if not url.startswith(self.base_url):
            return False

        # Skip anchors
        if "#" in url:
            url = url.split("#")[0]

        # Skip common non-doc paths
        skip_patterns = [
            "/search",
            "/genindex",
            "/modindex",
            ".pdf",
            ".zip",
            ".tar.gz",
            "/downloads/",
            "/download/",
        ]

        for pattern in skip_patterns:
            if pattern in url:
                return False

        return True

    def fetch(self, url: str) -> Optional[Document]:
        """
        Fetch and convert a documentation page.

        Args:
            url: Page URL to fetch

        Returns:
            Document object or None on error
        """
        for attempt in range(MAX_RETRIES):
            try:
                self._enforce_rate_limit()
                response = self.session.get(url, timeout=DEFAULT_TIMEOUT)

                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    backoff_time = self.rate_limit * (2**attempt)  # Exponential backoff
                    time.sleep(backoff_time)
                    continue

                if response.status_code != 200:
                    continue

                # Convert HTML to Markdown
                markdown = self.converter.convert(response.text, base_url=url)

                # Extract metadata
                title = self.converter.extract_title(response.text) or url
                metadata = self.converter.extract_metadata(response.text)
                metadata["url"] = url
                metadata["fetch_timestamp"] = datetime.utcnow().isoformat()

                # Check quality
                text_density = self.converter.estimate_text_density(response.text)
                if text_density < 0.3:  # Low content
                    return None

                doc = Document(
                    url=url,
                    title=title,
                    content_type="html",
                    source_provider=self.get_provider_name(),
                    raw_content=markdown.encode("utf-8"),
                    metadata=metadata,
                    discovered_at=datetime.utcnow(),
                )

                return doc

            except Exception:
                if attempt == MAX_RETRIES - 1:
                    return None
                time.sleep(self.rate_limit * (attempt + 1))

        return None


# def main():
#     """CLI entry point for testing."""
#     import argparse
#     from infrastructure.coordinator import HarvestCoordinator
#     from ..doc_config import OUTPUT_DIR, REGISTRY_DB
#
#     parser = argparse.ArgumentParser(description="Harvest ReadTheDocs documentation")
#     parser.add_argument("--url", required=True, help="Base URL of ReadTheDocs site")
#     parser.add_argument("--max-docs", type=int, help="Maximum documents to fetch")
#
#     args = parser.parse_args()
#
#     logger.info("=" * 70)
#     logger.info("ReadTheDocs Documentation Harvester")
#     logger.info("=" * 70)
#     logger.info("")
#
#     # Initialize coordinator
#     coordinator = HarvestCoordinator(output_dir=OUTPUT_DIR, registry_db=REGISTRY_DB)
#
#     # Register provider
#     provider = ReadTheDocsProvider(base_url=args.url)
#     coordinator.register_provider(provider)
#
#     logger.info("📥 Harvesting from ReadTheDocs...")
#     logger.info("")
#
#     # Harvest
#     results = coordinator.harvest_all(max_docs_per_provider=args.max_docs)
#
#     # Display results
#     provider_stats = results.get("providers", {}).get("readthedocs", {})
#     logger.info("=" * 70)
#     logger.info("RESULTS")
#     logger.info("=" * 70)
#     logger.info(f"✅ Discovered: {provider_stats.get('discovered', 0)}")
#     logger.info(f"📥 Fetched: {provider_stats.get('fetched', 0)}")
#     logger.info(f"💾 Saved: {provider_stats.get('saved', 0)}")
#     logger.info(f"⏭️  Skipped (duplicate): {provider_stats.get('skipped_duplicate', 0)}")
#     logger.info(f"⏭️  Skipped (quality): {provider_stats.get('skipped_quality', 0)}")
#     logger.error(f"❌ Errors: {provider_stats.get('errors', 0)}")
#     logger.info("")
#     logger.info(f"📂 Files saved to: {OUTPUT_DIR}/readthedocs/")
#     logger.info(f"⏱️  Duration: {results.get('duration_seconds', 0):.2f}s")
#     logger.info("=" * 70)
#
#
# if __name__ == "__main__":
#     main()
