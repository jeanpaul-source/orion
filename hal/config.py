import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

log = logging.getLogger(__name__)


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
    # Prompt identity — override to describe your specific lab
    lab_hostname: str  # human-readable host name shown in system prompt, e.g. "the-lab"; empty = use lab_host IP only
    lab_hardware_summary: (
        str  # one-line hardware description for system prompt; empty = omit from prompt
    )
    # Web UI authentication — bearer token for /chat endpoint
    hal_web_token: (
        str  # required for LAN access; empty string disables auth (localhost-only use)
    )
    # Judge extensions — additive only; cannot weaken base security rules
    judge_extra_sensitive_paths: (
        str  # colon-separated absolute path prefixes to treat as sensitive; default ""
    )
    # LLM sampling — Qwen-recommended defaults + min_p to suppress CJK language mixing
    llm_temperature: float  # default 0.7 (Qwen generation_config)
    llm_top_p: float  # default 0.8 (Qwen generation_config)
    llm_min_p: float  # default 0.05 (community fix for Chinese token leakage)
    llm_repetition_penalty: float  # default 1.05 (Qwen generation_config)
    # Multi-host inventory — additional SSH targets beyond the primary lab host
    extra_hosts: str  # comma-separated "name:user@host" entries; default ""
    # Sandbox execution — isolated Docker container for code execution
    sandbox_enabled: bool  # master kill-switch; default true
    sandbox_timeout: int  # execution timeout in seconds; default 30
    sandbox_image: str  # Docker image name; default "orion-sandbox:latest"
    # Watchdog proactive trend thresholds — rate-of-change that triggers an early alert
    watchdog_disk_rate_pct_per_hour: float  # default 5.0
    watchdog_mem_rate_pct_per_hour: float  # default 5.0
    watchdog_swap_rate_pct_per_hour: float  # default 10.0
    watchdog_gpu_vram_rate_pct_per_hour: float  # default 5.0

    @property
    def host_registry(self) -> dict[str, tuple[str, str]]:
        """Return {name: (host, user)} for all configured hosts.

        The primary lab host is always present as "lab".
        Additional hosts come from EXTRA_HOSTS (comma-separated "name:user@host").
        """
        hosts: dict[str, tuple[str, str]] = {"lab": (self.lab_host, self.lab_user)}
        for entry in self.extra_hosts.split(","):
            entry = entry.strip()
            if not entry:
                continue
            # Expected format: "name:user@host"
            if ":" not in entry or "@" not in entry:
                log.warning("Malformed EXTRA_HOSTS entry skipped: %r", entry)
                continue  # silently skip malformed entries
            name, userhost = entry.split(":", 1)
            if "@" not in userhost:
                log.warning("Malformed EXTRA_HOSTS entry skipped (no @): %r", entry)
                continue
            user, host = userhost.split("@", 1)
            hosts[name.strip()] = (host.strip(), user.strip())
        return hosts


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
        lab_hostname=os.getenv("LAB_HOSTNAME", ""),
        lab_hardware_summary=os.getenv("LAB_HARDWARE_SUMMARY", ""),
        hal_web_token=os.getenv("HAL_WEB_TOKEN", ""),
        judge_extra_sensitive_paths=os.getenv("JUDGE_EXTRA_SENSITIVE_PATHS", ""),
        extra_hosts=os.getenv("EXTRA_HOSTS", ""),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        llm_top_p=float(os.getenv("LLM_TOP_P", "0.8")),
        llm_min_p=float(os.getenv("LLM_MIN_P", "0.05")),
        llm_repetition_penalty=float(os.getenv("LLM_REPETITION_PENALTY", "1.05")),
        sandbox_enabled=os.getenv("SANDBOX_ENABLED", "true").lower() == "true",
        sandbox_timeout=int(os.getenv("SANDBOX_TIMEOUT", "30")),
        sandbox_image=os.getenv("SANDBOX_IMAGE", "orion-sandbox:latest"),
        watchdog_disk_rate_pct_per_hour=float(
            os.getenv("WATCHDOG_DISK_RATE_PCT_PER_HOUR", "5.0")
        ),
        watchdog_mem_rate_pct_per_hour=float(
            os.getenv("WATCHDOG_MEM_RATE_PCT_PER_HOUR", "5.0")
        ),
        watchdog_swap_rate_pct_per_hour=float(
            os.getenv("WATCHDOG_SWAP_RATE_PCT_PER_HOUR", "10.0")
        ),
        watchdog_gpu_vram_rate_pct_per_hour=float(
            os.getenv("WATCHDOG_GPU_VRAM_RATE_PCT_PER_HOUR", "5.0")
        ),
    )
