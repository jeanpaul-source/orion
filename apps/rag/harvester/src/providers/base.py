"""Unified base provider interface for all ORION harvesters.

Supports both query-based (academic) and discovery-based (documentation) providers.

ELI5: This is like a contract that says "every collector (academic or docs) must 
know how to find documents and follow rules about how fast to work."

Created: 2025-11-12 - Unified academic + doc harvesters
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import time


@dataclass
class Document:
    """Metadata for a harvested document (academic or documentation)."""
    
    url: str
    title: str
    content_type: str  # 'pdf', 'html', 'markdown'
    source_provider: str  # 'semantic_scholar', 'github', etc.
    raw_content: Optional[bytes] = None  # Optional for query results
    metadata: Optional[Dict[str, Any]] = None
    discovered_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.discovered_at is None:
            self.discovered_at = datetime.now()
    
    def get_identifier(self) -> str:
        """Get unique identifier for deduplication."""
        return self.url


@dataclass
class HarvestResult:
    """Result of a harvest operation."""
    
    success: bool
    documents_discovered: int
    documents_fetched: int
    documents_skipped: int
    errors: List[str]
    duration_seconds: float


class BaseProvider(ABC):
    """Abstract base class for all document providers (academic + docs)."""
    
    def __init__(self, rate_limit: float = 1.0):
        """
        Initialize provider.
        
        Args:
            rate_limit: Minimum seconds between requests
        """
        self.rate_limit = rate_limit
        self._last_request_time = 0.0
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return unique provider identifier (e.g., 'semantic_scholar', 'github')."""
        pass
    
    @abstractmethod
    def get_provider_type(self) -> str:
        """
        Return provider type: 'academic' or 'documentation'.
        
        This determines which harvesting mode the provider supports.
        """
        pass
    
    # ========================================================================
    # QUERY-BASED INTERFACE (for academic providers)
    # ========================================================================
    
    def search(self, query: str, max_results: int = 10) -> List[Document]:
        """
        Search provider with query string (academic providers).
        
        Args:
            query: Search query
            max_results: Maximum results to return
            
        Returns:
            List of Document objects
            
        Raises:
            NotImplementedError: If provider doesn't support search
        """
        raise NotImplementedError(
            f"{self.get_provider_name()} doesn't support query-based search. "
            f"Use discover() instead."
        )
    
    # ========================================================================
    # DISCOVERY-BASED INTERFACE (for documentation providers)
    # ========================================================================
    
    def discover(self) -> List[str]:
        """
        Discover available documents from this source (doc providers).
        
        Returns:
            List of document URLs
            
        Example:
            ReadTheDocs: Parse sitemap.xml
            GitHub: Query API for starred repos
            VendorPDF: Load from config file
            
        Raises:
            NotImplementedError: If provider doesn't support discovery
        """
        raise NotImplementedError(
            f"{self.get_provider_name()} doesn't support discovery. "
            f"Use search(query) instead."
        )
    
    def fetch(self, url: str) -> Optional[Document]:
        """
        Fetch a single document from URL (doc providers).
        
        Args:
            url: Document URL to fetch
            
        Returns:
            Document object if successful, None on error
            
        Note:
            Should handle retries and error logging internally
            
        Raises:
            NotImplementedError: If provider doesn't support fetch
        """
        raise NotImplementedError(
            f"{self.get_provider_name()} doesn't support fetch. "
            f"This is typically used by discovery-based providers."
        )
    
    # ========================================================================
    # SHARED UTILITIES
    # ========================================================================
    
    def _enforce_rate_limit(self):
        """Sleep if necessary to respect rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()
    
    def harvest(self, max_docs: Optional[int] = None) -> HarvestResult:
        """
        Full harvest workflow for discovery-based providers.
        
        Workflow: discover() → fetch() → return results
        
        Args:
            max_docs: Optional limit on documents to fetch
            
        Returns:
            HarvestResult with statistics
            
        Note:
            This is primarily for discovery-based (doc) providers.
            Query-based (academic) providers use search() directly.
        """
        start_time = time.time()
        errors = []
        fetched = 0
        skipped = 0
        
        try:
            # Discovery phase
            urls = self.discover()
            discovered = len(urls)
            
            if max_docs:
                urls = urls[:max_docs]
            
            # Fetch phase
            for url in urls:
                try:
                    self._enforce_rate_limit()
                    doc = self.fetch(url)
                    if doc:
                        fetched += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append(f"{url}: {str(e)}")
                    skipped += 1
            
            duration = time.time() - start_time
            
            return HarvestResult(
                success=len(errors) == 0,
                documents_discovered=discovered,
                documents_fetched=fetched,
                documents_skipped=skipped,
                errors=errors,
                duration_seconds=duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return HarvestResult(
                success=False,
                documents_discovered=0,
                documents_fetched=0,
                documents_skipped=0,
                errors=[f"Discovery failed: {str(e)}"],
                duration_seconds=duration
            )
