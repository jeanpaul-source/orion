"""
Default constants for ORION ecosystem.

Centralized configuration defaults to eliminate hardcoded values
scattered throughout the codebase.

This module consolidates hardcoded IPs, ports, and paths found in:
- harvester/src/doc_config.py
- research-qa/src/anythingllm_client.py
- devops-agent/devia/config.py
- ai-lab-manager/ai-lab-manager.py

Author: ORION Consolidation Initiative
Date: November 17, 2025
"""

from pathlib import Path

# ============================================================================
# NETWORK INFRASTRUCTURE
# ============================================================================

# Host IP addresses
DEFAULT_HOST_IP = "192.168.5.10"      # GPU-enabled host (RTX 3090 Ti)
DEFAULT_LAPTOP_IP = "192.168.5.25"    # Development laptop

# ============================================================================
# SERVICE PORTS
# ============================================================================

# ORION RAG Stack
DEFAULT_QDRANT_PORT = 6333           # Vector database
DEFAULT_VLLM_PORT = 8000             # LLM inference (vLLM)
DEFAULT_ANYTHINGLLM_PORT = 3001      # RAG web UI
DEFAULT_N8N_PORT = 5678              # Workflow automation

# Ollama LLM
DEFAULT_OLLAMA_PORT = 11434          # Ollama API

# Web Services
DEFAULT_HAL_PORT = 5001              # HAL orchestrator (if deployed)
DEFAULT_LAB_MANAGER_PORT = 8000      # AI Lab Manager (if deployed)

# ============================================================================
# SERVICE URLS (Composed from IPs + Ports)
# ============================================================================

# Localhost URLs (for host-side services)
DEFAULT_QDRANT_URL_LOCAL = f"http://localhost:{DEFAULT_QDRANT_PORT}"
DEFAULT_VLLM_URL_LOCAL = f"http://localhost:{DEFAULT_VLLM_PORT}"
DEFAULT_ANYTHINGLLM_URL_LOCAL = f"http://localhost:{DEFAULT_ANYTHINGLLM_PORT}"
DEFAULT_OLLAMA_URL_LOCAL = f"http://localhost:{DEFAULT_OLLAMA_PORT}"

# Remote URLs (for laptop accessing host services)
DEFAULT_QDRANT_URL_REMOTE = f"http://{DEFAULT_HOST_IP}:{DEFAULT_QDRANT_PORT}"
DEFAULT_VLLM_URL_REMOTE = f"http://{DEFAULT_HOST_IP}:{DEFAULT_VLLM_PORT}"
DEFAULT_ANYTHINGLLM_URL_REMOTE = f"http://{DEFAULT_HOST_IP}:{DEFAULT_ANYTHINGLLM_PORT}"
DEFAULT_OLLAMA_URL_REMOTE = f"http://{DEFAULT_HOST_IP}:{DEFAULT_OLLAMA_PORT}"

# ============================================================================
# STORAGE PATHS
# ============================================================================

# Host storage (NVMe drives)
DEFAULT_ORION_DATA_ROOT = Path("/mnt/nvme1/orion-data")
DEFAULT_DOCUMENTS_RAW = DEFAULT_ORION_DATA_ROOT / "documents" / "raw"
DEFAULT_DOCUMENTS_METADATA = DEFAULT_ORION_DATA_ROOT / "documents" / "metadata"
DEFAULT_LIBRARY_DIR = DEFAULT_ORION_DATA_ROOT / "library"

# Laptop storage
DEFAULT_LAPTOP_BASE = Path.home() / "Laptop-MAIN"
DEFAULT_LAPTOP_ORION = DEFAULT_LAPTOP_BASE / "applications" / "orion-rag"

# ============================================================================
# DATABASE PATHS
# ============================================================================

DEFAULT_HARVEST_REGISTRY_DB = DEFAULT_DOCUMENTS_METADATA / "harvest-registry.db"
DEFAULT_INGESTION_DB = DEFAULT_DOCUMENTS_METADATA / "ingestion.db"
DEFAULT_LIBRARY_METADATA_JSON = DEFAULT_LIBRARY_DIR / "library_metadata.json"

# ============================================================================
# COLLECTION NAMES
# ============================================================================

DEFAULT_QDRANT_COLLECTION = "orion_homelab"
DEFAULT_TECHNICAL_DOCS_COLLECTION = "technical-docs"
DEFAULT_ACADEMIC_PAPERS_COLLECTION = "academic-papers"

# ============================================================================
# API SETTINGS
# ============================================================================

# Rate limiting
DEFAULT_RATE_LIMIT_CALLS = 10
DEFAULT_RATE_LIMIT_PERIOD = 60  # seconds

# Timeouts
DEFAULT_HTTP_TIMEOUT = 10  # seconds
DEFAULT_EMBEDDING_TIMEOUT = 30  # seconds
DEFAULT_LLM_TIMEOUT = 60  # seconds

# Retry settings
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 1.0

# ============================================================================
# PROCESSING LIMITS
# ============================================================================

DEFAULT_MAX_RESULTS_PER_TERM = 50
DEFAULT_MAX_FILES_PER_BATCH = 100
DEFAULT_CHUNK_SIZE = 512  # tokens
DEFAULT_CHUNK_OVERLAP = 50  # tokens

# ============================================================================
# EMBEDDING MODELS
# ============================================================================

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
DEFAULT_EMBEDDING_DIM = 768

# Alternative models
EMBEDDING_MODEL_LARGE = "BAAI/bge-large-en-v1.5"
EMBEDDING_MODEL_LARGE_DIM = 1024

# ============================================================================
# LLM MODELS
# ============================================================================

DEFAULT_VLLM_MODEL = "Qwen/Qwen2.5-14B-Instruct-AWQ"
DEFAULT_OLLAMA_MODEL = "qwen2.5:32b"

# ============================================================================
# QUALITY THRESHOLDS
# ============================================================================

# Document quality gates
MIN_TEXT_DENSITY_ACADEMIC = 0.4
MIN_TEXT_DENSITY_TECHNICAL = 0.3
MIN_TEXT_DENSITY_MANUALS = 0.15

MIN_TOKENS_ACADEMIC = 500
MIN_TOKENS_TECHNICAL = 200
MIN_TOKENS_MANUALS = 100

# ============================================================================
# LOGGING
# ============================================================================

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_service_url(service: str, local: bool = True) -> str:
    """
    Get service URL based on deployment location.

    Args:
        service: Service name (qdrant, vllm, anythingllm, ollama)
        local: If True, use localhost; if False, use remote host IP

    Returns:
        Service URL string

    Example:
        >>> get_service_url("qdrant", local=True)
        'http://localhost:6333'
        >>> get_service_url("qdrant", local=False)
        'http://192.168.5.10:6333'
    """
    service_map_local = {
        "qdrant": DEFAULT_QDRANT_URL_LOCAL,
        "vllm": DEFAULT_VLLM_URL_LOCAL,
        "anythingllm": DEFAULT_ANYTHINGLLM_URL_LOCAL,
        "ollama": DEFAULT_OLLAMA_URL_LOCAL,
    }

    service_map_remote = {
        "qdrant": DEFAULT_QDRANT_URL_REMOTE,
        "vllm": DEFAULT_VLLM_URL_REMOTE,
        "anythingllm": DEFAULT_ANYTHINGLLM_URL_REMOTE,
        "ollama": DEFAULT_OLLAMA_URL_REMOTE,
    }

    if local:
        return service_map_local.get(service.lower(), "")
    else:
        return service_map_remote.get(service.lower(), "")


def get_collection_name(collection_type: str) -> str:
    """
    Get Qdrant collection name by type.

    Args:
        collection_type: Type of collection (homelab, technical, academic)

    Returns:
        Collection name string

    Example:
        >>> get_collection_name("academic")
        'academic-papers'
    """
    collection_map = {
        "homelab": DEFAULT_QDRANT_COLLECTION,
        "technical": DEFAULT_TECHNICAL_DOCS_COLLECTION,
        "academic": DEFAULT_ACADEMIC_PAPERS_COLLECTION,
    }
    return collection_map.get(collection_type.lower(), DEFAULT_QDRANT_COLLECTION)
