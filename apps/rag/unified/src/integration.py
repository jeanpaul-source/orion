"""
ORION Integration Module

Bridges harvester and research-qa components with shared utilities,
configuration management, and consistent interfaces.

Created: 2025-11-17 (Consolidation Phase)
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class ORIONConfig:
    """Unified ORION configuration"""

    # Base paths
    base_dir: Path
    data_dir: Path
    raw_dir: Path
    metadata_dir: Path
    cache_dir: Path

    # Service URLs
    qdrant_url: str
    anythingllm_url: str
    vllm_url: str

    # API keys (from environment)
    anythingllm_api_key: Optional[str]

    @classmethod
    def from_environment(cls) -> "ORIONConfig":
        """Load configuration from environment variables"""

        # Base directory
        base_dir = Path(os.getenv("ORION_BASE_DIR", "/mnt/nvme1/orion"))

        # Service URLs
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        anythingllm_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        vllm_url = os.getenv("VLLM_URL", "http://localhost:8000")

        # API keys
        anythingllm_api_key = os.getenv("ANYTHINGLLM_API_KEY")
        if not anythingllm_api_key:
            logger.warning(
                "ANYTHINGLLM_API_KEY not set. Some operations may fail. "
                "Set it in .env or export it."
            )

        return cls(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            raw_dir=base_dir / "data" / "raw",
            metadata_dir=base_dir / "data" / "metadata",
            cache_dir=base_dir / "data" / "cache",
            qdrant_url=qdrant_url,
            anythingllm_url=anythingllm_url,
            vllm_url=vllm_url,
            anythingllm_api_key=anythingllm_api_key
        )

    def ensure_directories(self):
        """Create all required directories if they don't exist"""
        for directory in [
            self.data_dir,
            self.raw_dir,
            self.metadata_dir,
            self.cache_dir,
            self.raw_dir / "academic",
            self.raw_dir / "manuals",
            self.raw_dir / "blogs",
            self.raw_dir / "github",
        ]:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")


# ============================================================================
# Domain Mapping
# ============================================================================

# Map domains to Qdrant collections
DOMAIN_TO_COLLECTION = {
    "academic": "research-papers",
    "manuals": "technical-docs",
    "blogs": "technical-docs",
    "github": "code-examples",
}

# Reverse mapping
COLLECTION_TO_DOMAINS = {
    "research-papers": ["academic"],
    "technical-docs": ["manuals", "blogs"],
    "code-examples": ["github"],
}


def get_collection_for_domain(domain: str) -> str:
    """Get the appropriate Qdrant collection for a domain"""
    return DOMAIN_TO_COLLECTION.get(domain, "technical-docs")


def get_domains_for_collection(collection: str) -> List[str]:
    """Get all domains that map to a collection"""
    return COLLECTION_TO_DOMAINS.get(collection, [])


# ============================================================================
# Provider Mapping
# ============================================================================

# Map domains to provider types
DOMAIN_PROVIDERS = {
    "academic": [
        "semantic_scholar",
        "arxiv",
        "openalex",
        "core",
        "pubmed",
    ],
    "manuals": [
        "github",
        "readthedocs",
        "confluence",
    ],
    "blogs": [
        "medium",
        "devto",
        "hashnode",
    ],
    "github": [
        "github",
    ],
}


def get_providers_for_domain(domain: str) -> List[str]:
    """Get provider names for a domain"""
    return DOMAIN_PROVIDERS.get(domain, [])


# ============================================================================
# Quality Gates Integration
# ============================================================================

def get_quality_gate_for_domain(domain: str) -> Dict[str, Any]:
    """
    Get quality gate configuration for a domain.

    This integrates with domains.py configuration.
    """
    from domains import DOMAINS

    if domain not in DOMAINS:
        logger.warning(f"Unknown domain: {domain}, using default quality gates")
        return {
            "min_text_density": 0.3,
            "min_tokens": 100,
            "max_tokens": 1_000_000,
        }

    domain_config = DOMAINS[domain]
    return {
        "min_text_density": domain_config.quality_gates.get("min_text_density", 0.3),
        "min_tokens": domain_config.quality_gates.get("min_tokens", 100),
        "max_tokens": domain_config.quality_gates.get("max_tokens", 1_000_000),
        "chunk_size": domain_config.chunk_size,
        "chunk_overlap": domain_config.chunk_overlap,
    }


# ============================================================================
# Registry Helper
# ============================================================================

class UnifiedRegistry:
    """
    Unified registry helper that provides a single interface to
    the ingestion registry with domain-aware queries.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize unified registry.

        Args:
            db_path: Path to SQLite database (defaults to config)
        """
        from processing.registry import IngestionRegistry

        config = ORIONConfig.from_environment()
        config.ensure_directories()

        if db_path is None:
            db_path = config.metadata_dir / "ingestion.db"

        self.registry = IngestionRegistry(db_path=str(db_path))
        logger.debug(f"Initialized registry at: {db_path}")

    def is_processed(self, file_path: Path, domain: str) -> bool:
        """Check if a file has been processed"""
        return self.registry.is_processed(str(file_path))

    def mark_processed(
        self,
        file_path: Path,
        domain: str,
        status: str = "processed",
        metadata: Optional[Dict] = None
    ):
        """Mark a file as processed"""
        if metadata is None:
            metadata = {}

        metadata["domain"] = domain
        metadata["collection"] = get_collection_for_domain(domain)

        self.registry.mark_processed(
            str(file_path),
            status=status,
            metadata=metadata
        )

    def get_stats(self, domain: Optional[str] = None) -> List[Dict]:
        """Get registry statistics, optionally filtered by domain"""
        stats = self.registry.get_stats()

        if domain:
            stats = [s for s in stats if s.get("domain") == domain]

        return stats


# ============================================================================
# Service Health Checks
# ============================================================================

def check_service_health() -> Dict[str, bool]:
    """
    Check health of all ORION services.

    Returns:
        Dictionary mapping service names to health status
    """
    import requests

    config = ORIONConfig.from_environment()

    health = {}

    # Check Qdrant
    try:
        response = requests.get(f"{config.qdrant_url}/collections", timeout=5)
        health["qdrant"] = response.status_code == 200
    except Exception as e:
        logger.debug(f"Qdrant health check failed: {e}")
        health["qdrant"] = False

    # Check vLLM
    try:
        response = requests.get(f"{config.vllm_url}/health", timeout=5)
        health["vllm"] = response.status_code == 200
    except Exception as e:
        logger.debug(f"vLLM health check failed: {e}")
        health["vllm"] = False

    # Check AnythingLLM
    try:
        response = requests.get(f"{config.anythingllm_url}/api/ping", timeout=5)
        health["anythingllm"] = response.status_code == 200
    except Exception as e:
        logger.debug(f"AnythingLLM health check failed: {e}")
        health["anythingllm"] = False

    return health


# ============================================================================
# Utility Functions
# ============================================================================

def setup_logging(level: str = "INFO"):
    """Configure logging for ORION components"""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def get_file_extension(file_path: Path) -> str:
    """Get normalized file extension"""
    return file_path.suffix.lower().lstrip(".")


def is_supported_document(file_path: Path) -> bool:
    """Check if file type is supported"""
    supported_extensions = {
        "pdf", "html", "htm", "md", "markdown", "txt", "rst"
    }
    return get_file_extension(file_path) in supported_extensions


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Setup logging
    setup_logging("DEBUG")

    # Load configuration
    config = ORIONConfig.from_environment()
    logger.info(f"Base directory: {config.base_dir}")
    logger.info(f"Qdrant URL: {config.qdrant_url}")

    # Ensure directories exist
    config.ensure_directories()

    # Check service health
    logger.info("Checking service health...")
    health = check_service_health()
    for service, is_healthy in health.items():
        status = "✓" if is_healthy else "✗"
        logger.info(f"  {status} {service}: {'healthy' if is_healthy else 'unhealthy'}")

    # Test domain mapping
    logger.info("\nDomain → Collection mapping:")
    for domain in ["academic", "manuals", "blogs", "github"]:
        collection = get_collection_for_domain(domain)
        providers = get_providers_for_domain(domain)
        logger.info(f"  {domain} → {collection} (providers: {', '.join(providers)})")

    # Test registry
    logger.info("\nTesting unified registry...")
    registry = UnifiedRegistry()
    stats = registry.get_stats()
    logger.info(f"  Total documents in registry: {sum(s['count'] for s in stats)}")
