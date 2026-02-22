"""
Utility functions for ORION Harvester.

Session management, filename sanitization, file hashing, and optional semantic relevance checking.
"""

import hashlib
import json
import logging
import os
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import USE_EMBEDDINGS, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)

# Embeddings cache path (for semantic relevance checking)
_HARVESTER_DIR = Path(__file__).parent.parent
_DATA_DIR = Path(os.environ.get("ORION_DATA_DIR", _HARVESTER_DIR / "data"))
EMBEDDINGS_CACHE = _DATA_DIR / "category_embeddings.json"


def get_session() -> requests.Session:
    """
    Create HTTP session with automatic retry logic.

    Returns:
        Session with retry adapter for 429, 500-504 status codes
    """
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def sanitize_filename(title: str) -> str:
    """
    Convert paper title to safe filename.

    Args:
        title: Paper title to sanitize

    Returns:
        Safe filename (alphanumeric, spaces, hyphens, underscores only, max 200 chars)
    """
    safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title)
    return safe[:200]  # Limit length


def file_hash(filepath: Path) -> str:
    """
    Calculate SHA256 hash of file.

    Args:
        filepath: Path to file

    Returns:
        Hex digest of SHA256 hash
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class SemanticRelevanceChecker:
    """
    Check paper relevance using semantic embeddings (optional).

    Requires sentence-transformers package. If not available, falls back to keyword-only filtering.
    """

    def __init__(self) -> None:
        self.model = None
        self.category_embeddings = None
        self._initialized = False

    def _lazy_init(self) -> None:
        """Lazy load the model and category embeddings."""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            logger.info("Loading sentence-transformers model (one-time setup)...")
            self.model = SentenceTransformer("all-MiniLM-L6-v2")  # 80MB, fast

            # Load or create category embeddings
            if EMBEDDINGS_CACHE.exists():
                with open(EMBEDDINGS_CACHE, "r") as f:
                    cached = json.load(f)
                    self.category_embeddings = {k: np.array(v) for k, v in cached.items()}
                logger.info("Loaded cached category embeddings")
            else:
                self._create_category_embeddings()

            self._initialized = True
            logger.info("✅ NLP relevance checking enabled")

        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Install with: pip install sentence-transformers"
            )
            logger.warning("Falling back to keyword-based filtering only")
            self._initialized = False

    def _create_category_embeddings(self) -> None:
        """Create and cache embeddings for category descriptions."""

        # Detailed descriptions for each category
        category_descriptions = {
            "gpu-passthrough-and-vgpu": "GPU computing CUDA kernel programming NVIDIA graphics processing parallel computing tensor cores virtual GPU passthrough VFIO IOMMU vGPU optimization Proxmox",
            "data-persistence-stores": "Database systems SQL PostgreSQL query optimization transaction processing ACID properties replication sharding indexing key-value stores time-series databases",
            "vector-databases": "Vector database embedding similarity search approximate nearest neighbors HNSW Qdrant Milvus Weaviate FAISS semantic search",
            "container-platforms": "Kubernetes Docker container orchestration K3s cloud infrastructure containerization microservices Nomad",
            "llm-serving-and-inference": "Large language model inference vLLM model serving quantization transformer architecture GPU optimization attention mechanism continuous batching",
            "rag-and-knowledge-retrieval": "RAG retrieval augmented generation hybrid search context assembly citation aware semantic search knowledge graphs",
            "observability-and-alerting": "System monitoring observability Prometheus Grafana distributed tracing metrics logging telemetry SRE alerting alert handlers",
            "homelab-networking-security": "Computer networking firewall proxy VPN security authentication TLS encryption network protocols VLANs switches",
            "self-healing-and-remediation": "System reliability SRE chaos engineering fault tolerance resilience self-healing systems incident response remediation playbooks safe actions",
            "workflow-automation-n8n": "Workflow automation orchestration pipeline n8n Temporal workflow engine task scheduling automation webhooks",
            "homelab-infrastructure": "Proxmox VE KVM virtual machines hypervisor ZFS Ceph PBS backup bare metal homelab infrastructure",
        }

        logger.info("Creating category embeddings...")
        self.category_embeddings = {}

        for cat, desc in category_descriptions.items():
            embedding = self.model.encode(desc)
            self.category_embeddings[cat] = embedding

        # Cache embeddings
        cache_data = {k: v.tolist() for k, v in self.category_embeddings.items()}
        with open(EMBEDDINGS_CACHE, "w") as f:
            json.dump(cache_data, f)

        logger.info(f"Cached {len(self.category_embeddings)} category embeddings")

    def check_relevance(
        self, title: str, category: str, threshold: float = SIMILARITY_THRESHOLD
    ) -> tuple:
        """
        Check if paper title is semantically relevant to category.

        Args:
            title: Paper title
            category: Category name
            threshold: Minimum similarity score (default from constants)

        Returns:
            Tuple of (is_relevant: bool, similarity_score: float)
        """
        if not USE_EMBEDDINGS:
            return (True, 1.0)  # Skip NLP check if disabled

        if not self._initialized:
            self._lazy_init()

        if not self._initialized or self.model is None:
            return (True, 1.0)  # Fallback to keyword checking

        try:
            import numpy as np
            from numpy.linalg import norm

            # Encode paper title
            title_embedding = self.model.encode(title)

            # Get category embedding
            category_embedding = self.category_embeddings.get(category)
            if category_embedding is None:
                return (True, 1.0)  # Unknown category, allow it

            # Calculate cosine similarity
            similarity = np.dot(title_embedding, category_embedding) / (
                norm(title_embedding) * norm(category_embedding)
            )

            is_relevant = similarity >= threshold

            return (is_relevant, float(similarity))

        except Exception as e:
            logger.error(f"Error in semantic check: {e}")
            return (True, 1.0)  # On error, fall back to allowing


# Global instance (lazy-loaded)
semantic_checker = SemanticRelevanceChecker()


__all__ = [
    "get_session",
    "sanitize_filename",
    "file_hash",
    "SemanticRelevanceChecker",
    "semantic_checker",
]
