"""Vendor PDF harvester for direct downloads.

Downloads PDFs from configured URLs (vendor documentation, whitepapers, etc.)

ELI5: Like downloading PDF manuals directly from companies' websites
when you know the exact URL of the file.
"""

from typing import List, Optional
from pathlib import Path
from datetime import datetime
import requests
import logging

from .base import BaseProvider, Document
from ..doc_config import DEFAULT_RATE_LIMIT, DEFAULT_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)


class VendorPDFProvider(BaseProvider):
    """Harvest PDF documents from direct URLs."""

    def __init__(self, pdf_urls: List[dict], rate_limit: float = DEFAULT_RATE_LIMIT):
        """
        Initialize vendor PDF harvester.

        Args:
            pdf_urls: List of dicts with 'url' and optional 'name' keys
                      Example: [{'url': 'https://...pdf', 'name': 'CUDA Guide'}]
            rate_limit: Seconds between requests
        """
        super().__init__(rate_limit)
        self.pdf_urls = pdf_urls

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
        return "vendor_pdf"

    def get_provider_type(self) -> str:
        """Return provider type."""
        return "documentation"

    def discover(self) -> List[str]:
        """Return configured PDF URLs."""
        return [item["url"] for item in self.pdf_urls]

    def fetch(self, url: str) -> Optional[Document]:
        """
        Download PDF from URL.

        Args:
            url: PDF URL to download

        Returns:
            Document object or None on error
        """
        try:
            self._enforce_rate_limit()

            # Find name from config
            name = None
            for item in self.pdf_urls:
                if item["url"] == url:
                    name = item.get("name")
                    break

            # Download PDF
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)

            if response.status_code != 200:
                return None

            # Verify it's a PDF
            content_type = response.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower():
                # Check magic bytes
                if not response.content.startswith(b"%PDF"):
                    return None

            # Extract filename from URL if no name provided
            if not name:
                name = Path(url).name
                if name.endswith(".pdf"):
                    name = name[:-4]

            # Create document
            metadata = {
                "url": url,
                "filename": Path(url).name,
                "content_length": len(response.content),
                "content_type": content_type,
                "fetch_timestamp": datetime.utcnow().isoformat(),
            }

            doc = Document(
                url=url,
                title=name,
                content_type="pdf",
                source_provider=self.get_provider_name(),
                raw_content=response.content,
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
#     parser = argparse.ArgumentParser(description="Harvest vendor PDFs")
#     parser.add_argument("--config", help="YAML config file with PDF URLs")
#     parser.add_argument("--urls", nargs="+", help="Direct PDF URLs")
#
#     args = parser.parse_args()
#
#     pdf_list = []
#
#     if args.config:
#         with open(args.config) as f:
#             config = yaml.safe_load(f)
#             pdf_list = config.get("vendor_pdfs", [])
#     elif args.urls:
#         pdf_list = [{"url": url} for url in args.urls]
#     else:
#         logger.info("Error: Provide --config or --urls")
#         return
#
#     logger.info("=" * 70)
#     logger.info("Vendor PDF Harvester")
#     logger.info("=" * 70)
#     logger.info("")
#
#     # Initialize coordinator
#     coordinator = HarvestCoordinator(output_dir=OUTPUT_DIR, registry_db=REGISTRY_DB)
#
#     # Register provider
#     provider = VendorPDFProvider(pdf_urls=pdf_list)
#     coordinator.register_provider(provider)
#
#     logger.info("📥 Harvesting vendor PDFs...")
#     logger.info("")
#
#     # Harvest
#     results = coordinator.harvest_all()
#
#     # Display results
#     provider_stats = results.get("providers", {}).get("vendor_pdf", {})
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
#     logger.info(f"📂 Files saved to: {OUTPUT_DIR}/vendor_pdf/")
#     logger.info(f"⏱️  Duration: {results.get('duration_seconds', 0):.2f}s")
#     logger.info("=" * 70)
#
#
# if __name__ == "__main__":
#     main()
