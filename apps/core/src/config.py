"""
ORION Core Configuration

Manages configuration for the unified AI entity running entirely on lab host.
All services communicate via Docker internal network.

Author: ORION Project
Date: November 17, 2025
"""

import json
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings

from . import __version__


class ORIONConfig(BaseSettings):
    """
    ORION Core configuration.

    All services run on lab host (192.168.5.10) in Docker.
    Internal communication uses Docker service names.
    """

    # ========================================================================
    # APPLICATION INFO
    # ========================================================================
    app_name: str = Field(default="ORION", description="Application name")
    version: str = Field(default=__version__, description="ORION version")
    environment: str = Field(default="production", description="Environment")

    # ========================================================================
    # SERVER CONFIGURATION
    # ========================================================================
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=5000, description="Server port")

    # ========================================================================
    # SERVICE URLS (Docker Internal Network)
    # ========================================================================
    # LLM Inference
    vllm_url: str = Field(
        default="http://vllm:8000",
        description="vLLM service URL (internal Docker network)",
    )

    ollama_url: str = Field(
        default="http://host.docker.internal:11434", description="Ollama service URL"
    )

    # RAG Stack
    qdrant_url: str = Field(
        default="http://qdrant:6333", description="Qdrant vector database URL"
    )

    anythingllm_url: str = Field(
        default="http://anythingllm:3001", description="AnythingLLM RAG service URL"
    )

    anythingllm_api_key: Optional[str] = Field(
        default=None, description="AnythingLLM API key (from Settings → API Keys)"
    )

    vllm_api_key: Optional[str] = Field(
        default=None, description="vLLM API key (optional-api-key for homelab)"
    )

    # Workflow automation
    n8n_url: str = Field(
        default="http://n8n:5678", description="n8n workflow automation URL"
    )

    # ========================================================================
    # LLM MODEL CONFIGURATION
    # ========================================================================
    vllm_model: str = Field(
        default="Qwen/Qwen2.5-14B-Instruct-AWQ", description="vLLM model name"
    )

    ollama_model: str = Field(default="qwen2.5:32b", description="Ollama model name")

    # LLM generation parameters
    default_temperature: float = Field(default=0.7, description="LLM temperature")
    default_max_tokens: int = Field(default=2048, description="Max output tokens")

    # ========================================================================
    # RAG CONFIGURATION
    # ========================================================================
    qdrant_collection: str = Field(
        default="technical-docs",
        description="Primary Qdrant collection / AnythingLLM workspace name",
    )

    rag_top_k: int = Field(
        default=5, description="Number of documents to retrieve for RAG"
    )

    # ========================================================================
    # STORAGE PATHS (Docker Volumes)
    # ========================================================================
    data_dir: Path = Field(
        default=Path("/data"),
        description="Data directory (mounted from /mnt/nvme1/orion-data or ~/.orion/data for local dev)",
    )

    logs_dir: Path = Field(default=Path("/data/logs"), description="Logs directory")

    cache_dir: Path = Field(default=Path("/data/cache"), description="Cache directory")

    conversations_db: Path = Field(
        default=Path("/data/conversations.db"),
        description="SQLite database for conversation history",
    )

    # ========================================================================
    # LOGGING
    # ========================================================================
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="detailed", description="Log format (simple, detailed, structured)"
    )

    # ========================================================================
    # SECURITY
    # ========================================================================
    cors_origins: list[str] | str = Field(
        default_factory=lambda: ["*"], description="CORS allowed origins"
    )

    require_auth: bool = Field(
        default=False, description="Require authentication (future)"
    )

    # ========================================================================
    # PERFORMANCE
    # ========================================================================
    enable_cache: bool = Field(default=True, description="Enable response caching")
    cache_ttl: int = Field(default=3600, description="Cache TTL in seconds")

    max_concurrent_requests: int = Field(
        default=10, description="Max concurrent LLM requests"
    )

    request_timeout: int = Field(default=60, description="Request timeout in seconds")

    # ========================================================================
    # FEATURES
    # ========================================================================
    enable_tracing: bool = Field(
        default=True, description="Enable OpenTelemetry / AI Toolkit tracing"
    )
    tracing_endpoint: str = Field(
        default="http://localhost:4318/v1/traces",
        description="OTLP HTTP endpoint for exporting traces",
    )
    enable_knowledge: bool = Field(default=True, description="Enable RAG knowledge")
    enable_action: bool = Field(default=True, description="Enable tool execution")
    enable_learning: bool = Field(default=True, description="Enable self-teaching")
    enable_watch: bool = Field(default=True, description="Enable monitoring")

    # ========================================================================
    # INTENT CLASSIFICATION
    # ========================================================================
    intent_threshold: float = Field(
        default=0.6, description="Confidence threshold for intent classification"
    )

    # ========================================================================
    # TELEGRAM BOT
    # ========================================================================
    telegram_enabled: bool = Field(
        default=False, description="Enable Telegram bot integration"
    )

    telegram_bot_token: Optional[str] = Field(
        default=None, description="Telegram bot token from @BotFather"
    )

    telegram_allowed_users: list = Field(
        default=[], description="List of allowed Telegram user IDs (security whitelist)"
    )

    telegram_notification_enabled: bool = Field(
        default=True, description="Enable push notifications to Telegram"
    )

    # Pydantic config
    class Config:
        env_prefix = "ORION_"
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def __init__(self, **data):
        """Initialize configuration and create directories."""
        super().__init__(**data)

        self._normalize_cors_origins()

        # If data_dir is /data and doesn't exist (not in Docker), use ~/.orion/data
        if self.data_dir == Path("/data") and not self.data_dir.exists():
            home_dir = Path.home()
            self.data_dir = home_dir / ".orion" / "data"
            self.logs_dir = self.data_dir / "logs"
            self.cache_dir = self.data_dir / "cache"
            self.conversations_db = self.data_dir / "conversations.db"

        # Create directories if they don't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_service_health_urls(self) -> dict:
        """Get health check URLs for all services."""
        return {
            "vllm": f"{self.vllm_url}/health",
            "qdrant": f"{self.qdrant_url}/",
            "anythingllm": f"{self.anythingllm_url}/api/v1/system/ping",
        }

    def get_summary(self) -> str:
        """Get configuration summary for logging."""
        return f"""
ORION Core Configuration:
  Version: {self.version}
  Environment: {self.environment}
  Server: {self.host}:{self.port}

Services:
  vLLM: {self.vllm_url}
  Qdrant: {self.qdrant_url}
  AnythingLLM: {self.anythingllm_url}

Features:
  Knowledge: {'Enabled' if self.enable_knowledge else 'Disabled'}
  Action: {'Enabled' if self.enable_action else 'Disabled'}
  Learning: {'Enabled' if self.enable_learning else 'Disabled'}
  Watch: {'Enabled' if self.enable_watch else 'Disabled'}
        """.strip()

    def _normalize_cors_origins(self) -> None:
        """Ensure cors_origins is always a list of strings.

        Accepts values defined as:
        - A JSON array (e.g. '["https://example.com"]')
        - A comma-separated string ('https://a.com,https://b.com')
        - A single wildcard '*'
        - Already-parsed lists from environment files
        """

        value = self.cors_origins

        def _as_list(raw: str) -> list[str]:
            if not raw:
                return []
            if raw == "*":
                return ["*"]
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return [item.strip() for item in raw.split(",") if item.strip()]
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            if isinstance(parsed, str):
                cleaned = parsed.strip()
                return [cleaned] if cleaned else []
            return [str(parsed)]

        if isinstance(value, str):
            normalized = _as_list(value.strip())
        elif isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
        else:
            normalized = [str(value).strip()] if str(value).strip() else []

        if not normalized:
            normalized = ["*"]

        self.cors_origins = normalized


# Global config instance
config = ORIONConfig()
