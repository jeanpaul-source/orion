"""Blog and technical article harvester.

Fetches content from RSS feeds and manual URL lists.

ELI5: Like subscribing to your favorite tech blogs and automatically
downloading new articles when they're published.
"""

from typing import List, Optional
from datetime import datetime
import requests
import feedparser  # type: ignore[import-untyped]
import logging

from .base import BaseProvider, Document
from ..converters.html_converter import HTMLConverter
from ..doc_config import DEFAULT_RATE_LIMIT, DEFAULT_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)


class BlogProvider(BaseProvider):
    """Harvest blog posts and technical articles."""

    def __init__(
        self,
        rss_feeds: Optional[List[str]] = None,
        manual_urls: Optional[List[str]] = None,
        rate_limit: float = DEFAULT_RATE_LIMIT,
    ):
        """
        Initialize blog harvester.

        Args:
            rss_feeds: List of RSS feed URLs
            manual_urls: List of specific article URLs
            rate_limit: Seconds between requests
        """
        super().__init__(rate_limit)
        self.rss_feeds = rss_feeds or []
        self.manual_urls = manual_urls or []
        self.converter = HTMLConverter()

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
        return "blog"

    def get_provider_type(self) -> str:
        """Return provider type."""
        return "documentation"

    def discover(self) -> List[str]:
        """
        Discover blog post URLs from RSS feeds and manual lists.

        Returns:
            List of article URLs
        """
        urls = []

        # Parse RSS feeds
        for feed_url in self.rss_feeds:
            try:
                self._enforce_rate_limit()
                feed = feedparser.parse(feed_url)

                for entry in feed.entries:
                    if hasattr(entry, "link"):
                        urls.append(entry.link)
            except Exception as e:
                logger.info(f"Error parsing feed {feed_url}: {e}")

        # Add manual URLs
        urls.extend(self.manual_urls)

        # Remove duplicates
        return list(set(urls))

    def fetch(self, url: str) -> Optional[Document]:
        """
        Fetch blog post/article.

        Args:
            url: Article URL to fetch

        Returns:
            Document object or None on error
        """
        try:
            self._enforce_rate_limit()
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)

            if response.status_code != 200:
                return None

            # Convert HTML to Markdown
            markdown = self.converter.convert(response.text, base_url=url)

            # Extract metadata
            title = self.converter.extract_title(response.text) or url
            metadata = self.converter.extract_metadata(response.text)
            metadata["url"] = url
            metadata["fetch_timestamp"] = datetime.utcnow().isoformat()

            # Check quality - blogs should have decent text density
            text_density = self.converter.estimate_text_density(response.text)
            if text_density < 0.4:  # Low content
                return None

            # Check minimum length (avoid stub articles)
            if len(markdown) < 1000:  # Less than ~1000 chars
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

        except Exception as e:
            logger.info(f"Error fetching {url}: {e}")
            return None


# def main():
#     """CLI entry point for testing."""
#     import argparse
#     import yaml
#     from infrastructure.coordinator import HarvestCoordinator
#     from ..doc_config import OUTPUT_DIR, REGISTRY_DB
#
#     parser = argparse.ArgumentParser(description="Harvest blog posts")
#     parser.add_argument("--config", help="YAML config file with feeds/URLs")
#     parser.add_argument("--feeds", nargs="+", help="RSS feed URLs")
#     parser.add_argument("--urls", nargs="+", help="Direct article URLs")
#     parser.add_argument("--max-docs", type=int, help="Maximum documents to fetch")
#
#     args = parser.parse_args()
#
#     rss_feeds = []
#     manual_urls = []
#
#     if args.config:
#         with open(args.config) as f:
#             config = yaml.safe_load(f)
#             rss_feeds = config.get("rss_feeds", [])
#             manual_urls = config.get("manual_urls", [])
#     else:
#         rss_feeds = args.feeds or []
#         manual_urls = args.urls or []
#
#     if not rss_feeds and not manual_urls:
#         logger.info("Error: Provide --config, --feeds, or --urls")
#         return
#
#     logger.info("=" * 70)
#     logger.info("Blog & Technical Article Harvester")
#     logger.info("=" * 70)
#     logger.info("")
#
#     # Initialize coordinator
#     coordinator = HarvestCoordinator(output_dir=OUTPUT_DIR, registry_db=REGISTRY_DB)
#
#     # Register provider
#     provider = BlogProvider(rss_feeds=rss_feeds, manual_urls=manual_urls)
#     coordinator.register_provider(provider)
#
#     logger.info("📥 Harvesting blog posts...")
#     logger.info("")
#
#     # Harvest
#     results = coordinator.harvest_all(max_docs_per_provider=args.max_docs)
#
#     # Display results
#     provider_stats = results.get("providers", {}).get("blog", {})
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
#     logger.info(f"📂 Files saved to: {OUTPUT_DIR}/blog/")
#     logger.info(f"⏱️  Duration: {results.get('duration_seconds', 0):.2f}s")
#     logger.info("=" * 70)
#
#
# if __name__ == "__main__":
#     main()
