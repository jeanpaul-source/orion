from dataclasses import dataclass
from dotenv import load_dotenv
import os


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


def load() -> Config:
    load_dotenv()
    return Config(
        ollama_host=os.getenv("OLLAMA_HOST", "http://192.168.5.10:11434"),
        chat_model=os.getenv("CHAT_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"),
        embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text:latest"),
        pgvector_dsn=os.getenv(
            "PGVECTOR_DSN",
            "postgresql://kb_user@192.168.5.10:5432/knowledge_base",
        ),
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://192.168.5.10:9091"),
        lab_host=os.getenv("LAB_HOST", "192.168.5.10"),
        lab_user=os.getenv("LAB_USER", "jp"),
        use_ssh_tunnel=os.getenv("USE_SSH_TUNNEL", "false").lower() == "true",
        ntfy_url=os.getenv("NTFY_URL", ""),
        vllm_url=os.getenv("VLLM_URL", "http://localhost:8000"),
        ntopng_url=os.getenv("NTOPNG_URL", "http://localhost:3000"),
    )
