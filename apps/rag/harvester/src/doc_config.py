"""Configuration management for ORION Document Harvesters."""

import os
from pathlib import Path
from typing import Dict, Any
import yaml

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    # python-dotenv not installed, will use system environment variables
    pass


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

# Environment-configurable paths (with defaults)
OUTPUT_DIR = Path(os.getenv("ORION_OUTPUT_DIR", "/mnt/nvme1/orion-data/documents/raw"))
REGISTRY_DB = Path(os.getenv("ORION_REGISTRY_DB", "/mnt/nvme1/orion-data/documents/metadata/harvest-registry.db"))

# Service endpoints (configurable via environment)
QDRANT_URL = os.getenv("ORION_QDRANT_URL", "http://localhost:6333")
VLLM_URL = os.getenv("ORION_VLLM_URL", "http://localhost:8000")

# Harvesting settings
DEFAULT_RATE_LIMIT = 1.0  # seconds between requests
DEFAULT_TIMEOUT = 30  # HTTP timeout in seconds
MAX_RETRIES = 3
BATCH_SIZE = 10

# Content quality thresholds
MIN_TEXT_DENSITY = 0.55  # Reject image-heavy documents
MIN_CONTENT_LENGTH = 500  # characters
MAX_CONTENT_LENGTH = 1_000_000  # 1MB text limit

# Refresh intervals (days)
REFRESH_INTERVALS = {
    "readthedocs": 7,
    "github": 30,
    "vendor_pdf": 90,
    "blog": 14,
}


def load_sources_config() -> Dict[str, Any]:
    """Load sources configuration from YAML."""
    config_path = CONFIG_DIR / "sources.yaml"
    if not config_path.exists():
        return {}

    with open(config_path) as f:
        config = yaml.safe_load(f)
        if config is None:
            raise ValueError(f"Empty or malformed YAML file: {config_path}")
        if not isinstance(config, dict):
            raise ValueError(f"Expected dict in YAML config, got {type(config)}: {config_path}")
        return config


def load_schedule_config() -> Dict[str, Any]:
    """Load scheduling configuration from YAML."""
    config_path = CONFIG_DIR / "schedule.yaml"
    if not config_path.exists():
        return {}

    with open(config_path) as f:
        config = yaml.safe_load(f)
        if config is None:
            raise ValueError(f"Empty or malformed YAML file: {config_path}")
        if not isinstance(config, dict):
            raise ValueError(f"Expected dict in YAML config, got {type(config)}: {config_path}")
        return config


# GitHub API token (from KEYS_AND_TOKENS.md)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)

# User agent for web scraping
USER_AGENT = "ORION-Harvester/1.0 (Homelab RAG System; +https://github.com/your-repo)"
