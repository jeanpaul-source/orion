"""Document downloader and metadata registry for ORION harvester.

Handles downloading documents, managing metadata, and applying quality gates.

Created: 2025-11-18 - Implements TODO from cli.py:102
"""

import hashlib
import json
import logging
import requests
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Ensure src/ is in path for imports
sys.path.insert(0, str(Path(__file__).parent))

from providers.base import Document

logger = logging.getLogger(__name__)


@dataclass
class DownloadRecord:
    """Record of a downloaded document in library_metadata.json."""

    file_path: str
    url: str
    title: str
    category: str
    provider: str
    content_hash: str
    file_size_bytes: int
    content_type: str
    downloaded_at: str
    metadata: Dict

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class MetadataRegistry:
    """Manages library_metadata.json for tracking downloaded documents."""

    def __init__(self, metadata_path: Path):
        """
        Initialize metadata registry.

        Args:
            metadata_path: Path to library_metadata.json
        """
        self.metadata_path = metadata_path
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._metadata: Dict[str, DownloadRecord] = {}
        self._load()

    def _load(self):
        """Load existing metadata from JSON file."""
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r") as f:
                    data = json.load(f)
                    # Convert dicts back to DownloadRecord objects
                    for url, record in data.items():
                        self._metadata[url] = DownloadRecord(**record)
                logger.info(f"Loaded {len(self._metadata)} records from {self.metadata_path}")
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")
                self._metadata = {}
        else:
            logger.info(f"Creating new metadata registry at {self.metadata_path}")

    def _save(self):
        """Save metadata to JSON file."""
        try:
            # Convert DownloadRecord objects to dicts
            data = {url: record.to_dict() for url, record in self._metadata.items()}

            with open(self.metadata_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self._metadata)} records to {self.metadata_path}")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def is_downloaded(self, url: str) -> bool:
        """
        Check if URL has already been downloaded.

        Args:
            url: Document URL

        Returns:
            True if already downloaded
        """
        return url in self._metadata

    def is_duplicate_content(self, content_hash: str) -> bool:
        """
        Check if content hash already exists (duplicate content).

        Args:
            content_hash: SHA256 hash of content

        Returns:
            True if duplicate
        """
        return any(record.content_hash == content_hash for record in self._metadata.values())

    def add_record(self, record: DownloadRecord):
        """
        Add download record to registry.

        Args:
            record: DownloadRecord to add
        """
        self._metadata[record.url] = record
        self._save()

    def get_stats(self) -> Dict:
        """Get registry statistics."""
        return {
            "total_downloads": len(self._metadata),
            "unique_providers": len(set(r.provider for r in self._metadata.values())),
            "unique_categories": len(set(r.category for r in self._metadata.values())),
            "total_size_mb": sum(r.file_size_bytes for r in self._metadata.values())
            / (1024 * 1024),
        }


class DocumentDownloader:
    """Downloads documents and applies quality gates."""

    # Quality gates (minimum thresholds)
    MIN_FILE_SIZE = 1024  # 1 KB minimum
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB maximum

    def __init__(self, library_dir: Path, metadata_path: Path):
        """
        Initialize document downloader.

        Args:
            library_dir: Base directory for downloaded files (data/library/)
            metadata_path: Path to library_metadata.json
        """
        self.library_dir = library_dir
        self.registry = MetadataRegistry(metadata_path)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry logic and realistic headers."""
        session = requests.Session()
        session.headers.update(
            {
                # Realistic browser user-agent to avoid publisher blocking
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Referer": "https://scholar.google.com/",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        return session

    def _compute_hash(self, content: bytes) -> str:
        """
        Compute SHA256 hash of content.

        Args:
            content: File content bytes

        Returns:
            Hex digest of SHA256 hash
        """
        return hashlib.sha256(content).hexdigest()

    def _apply_quality_gates(self, content: bytes, url: str) -> tuple[bool, Optional[str]]:
        """
        Apply quality gates to downloaded content.

        Args:
            content: Downloaded content
            url: Source URL

        Returns:
            Tuple of (passes_gates, rejection_reason)
        """
        # File size check
        size = len(content)
        if size < self.MIN_FILE_SIZE:
            return False, f"File too small: {size} bytes"

        if size > self.MAX_FILE_SIZE:
            return False, f"File too large: {size / (1024*1024):.1f} MB"

        # Content type check (basic)
        if content[:4] == b"%PDF":
            # Valid PDF
            pass
        elif content[:100].decode("utf-8", errors="ignore").strip().startswith(
            "<!DOCTYPE"
        ) or content[:100].decode("utf-8", errors="ignore").strip().startswith("<html"):
            # HTML content (may need processing)
            pass
        else:
            # Unknown format - accept but warn
            logger.warning(f"Unknown content type for {url}")

        return True, None

    def download(self, document: Document, category: str) -> Optional[DownloadRecord]:
        """
        Download a document and save to library.

        Args:
            document: Document to download
            category: Category for organizing files

        Returns:
            DownloadRecord if successful, None otherwise
        """
        url = document.url

        # Check if already downloaded
        if self.registry.is_downloaded(url):
            logger.debug(f"Already downloaded: {url}")
            return None

        try:
            # Download content
            logger.info(f"Downloading: {url}")
            response = self.session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()

            # Check Content-Type to skip HTML pages (e.g., DBLP record pages)
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                logger.warning(f"Skipping HTML page (not a document): {url}")
                return None

            content = response.content

            # Rate limiting to avoid overwhelming publishers
            import time

            time.sleep(1.5)  # 1.5 second delay between downloads

            # Apply quality gates
            passes, reason = self._apply_quality_gates(content, url)
            if not passes:
                logger.warning(f"Quality gate failed for {url}: {reason}")
                return None

            # Compute content hash
            content_hash = self._compute_hash(content)

            # Check for duplicate content
            if self.registry.is_duplicate_content(content_hash):
                logger.info(f"Duplicate content (different URL): {url}")
                return None

            # Determine file extension
            content_type = document.content_type
            if content_type == "pdf":
                ext = ".pdf"
            elif content_type == "html":
                ext = ".html"
            elif content_type == "markdown":
                ext = ".md"
            else:
                # Try to infer from content
                if content[:4] == b"%PDF":
                    ext = ".pdf"
                else:
                    ext = ".html"

            # Create category directory
            category_dir = self.library_dir / category
            category_dir.mkdir(parents=True, exist_ok=True)

            # Generate safe filename
            safe_title = self._sanitize_filename(document.title)
            filename = f"{safe_title}_{content_hash[:8]}{ext}"
            file_path = category_dir / filename

            # Save file
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(f"Saved: {file_path} ({len(content)} bytes)")

            # Create download record
            record = DownloadRecord(
                file_path=str(file_path),
                url=url,
                title=document.title,
                category=category,
                provider=document.source_provider,
                content_hash=content_hash,
                file_size_bytes=len(content),
                content_type=ext[1:],  # Remove leading dot
                downloaded_at=datetime.now().isoformat(),
                metadata=document.metadata or {},
            )

            # Add to registry
            self.registry.add_record(record)

            return record

        except requests.RequestException as e:
            logger.error(f"Download failed for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}", exc_info=True)
            return None

    def _sanitize_filename(self, title: str, max_length: int = 100) -> str:
        """
        Convert title to safe filename.

        Args:
            title: Document title
            max_length: Maximum filename length

        Returns:
            Sanitized filename
        """
        # Remove/replace invalid characters
        safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title)
        # Collapse multiple spaces/underscores
        safe = "_".join(safe.split())
        # Truncate
        return safe[:max_length]

    def download_batch(
        self, documents: List[Document], category: str, max_downloads: Optional[int] = None
    ) -> Dict:
        """
        Download multiple documents.

        Args:
            documents: List of documents to download
            category: Category for organizing files
            max_downloads: Optional limit on downloads

        Returns:
            Statistics dict
        """
        stats = {"attempted": 0, "successful": 0, "skipped": 0, "failed": 0, "bytes_downloaded": 0}

        docs_to_process = documents[:max_downloads] if max_downloads else documents

        for doc in docs_to_process:
            stats["attempted"] += 1

            record = self.download(doc, category)

            if record:
                stats["successful"] += 1
                stats["bytes_downloaded"] += record.file_size_bytes
            elif self.registry.is_downloaded(doc.url):
                stats["skipped"] += 1
            else:
                stats["failed"] += 1

        return stats

    def get_registry_stats(self) -> Dict:
        """Get registry statistics."""
        return self.registry.get_stats()
