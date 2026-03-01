import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    ollama_host: str
    chat_model: str
    embed_model: str
    pgvector_dsn: str
    prometheus_url: str
    lab_host: str
    lab_user: str
    use_ssh_tunnel: bool
    ntfy_url: str  # e.g. https://ntfy.sh/your-topic — empty string disables alerts
    vllm_url: str  # vLLM OpenAI-compatible API endpoint
    ntopng_url: str  # ntopng community REST base, e.g. http://localhost:3000
    telegram_bot_token: str  # from @BotFather — empty string disables bot
    telegram_allowed_user_id: int  # Telegram numeric user ID; 0 = reject all
    tavily_api_key: str  # Tavily web search — empty string disables web_search tool
    # Harvest topology — override only when your lab layout differs from defaults
    infra_base: (
        str  # base dir for compose/config files; default /opt/homelab-infrastructure
    )
    static_docs_root: (
        str  # pre-scraped documents root; default /data/orion/orion-data/documents/raw
    )
    harvest_systemd_units: str  # space-separated unit names to ingest; default "ollama.service pgvector-kb-api.service"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} must be set in .env — copy .env.example and fill required values"
        )
    return value


def load() -> Config:
    load_dotenv()
    return Config(
        ollama_host=_required_env("OLLAMA_HOST"),
        chat_model=os.getenv("CHAT_MODEL", "Qwen/Qwen2.5-32B-Instruct-AWQ"),
        embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text:latest"),
        pgvector_dsn=_required_env("PGVECTOR_DSN"),
        prometheus_url=_required_env("PROMETHEUS_URL"),
        lab_host=_required_env("LAB_HOST"),
        lab_user=_required_env("LAB_USER"),
        use_ssh_tunnel=os.getenv("USE_SSH_TUNNEL", "false").lower() == "true",
        ntfy_url=os.getenv("NTFY_URL", ""),
        vllm_url=os.getenv("VLLM_URL", "http://localhost:8000"),
        ntopng_url=os.getenv("NTOPNG_URL", "http://localhost:3000"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_allowed_user_id=int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0")),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        infra_base=os.getenv("INFRA_BASE", "/opt/homelab-infrastructure"),
        static_docs_root=os.getenv(
            "STATIC_DOCS_ROOT", "/data/orion/orion-data/documents/raw"
        ),
        harvest_systemd_units=os.getenv(
            "HARVEST_SYSTEMD_UNITS", "ollama.service pgvector-kb-api.service"
        ),
    )
