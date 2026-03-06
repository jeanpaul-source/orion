"""Structured health checks for all HAL backend components.

Each check function returns a ``ComponentHealth`` result with:
- ok: component is fully functional
- degraded: component is running but not fully healthy
- down: component is unreachable or broken

Every check has a configurable timeout and catches all exceptions
so that a single failing check never crashes the health check suite.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import requests

import hal.config as cfg

# Re-use the watchdog's authoritative list of critical containers.
from hal.watchdog import CRITICAL_CONTAINERS

Status = Literal["ok", "degraded", "down"]

_DEFAULT_TIMEOUT = 5  # seconds


@dataclass(frozen=True)
class ComponentHealth:
    """Result of a single component health check."""

    name: str
    status: Status
    detail: str
    latency_ms: float


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def check_vllm(config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT) -> ComponentHealth:
    """Check vLLM health endpoint and verify the expected model is loaded."""
    start = time.monotonic()
    try:
        r = requests.get(f"{config.vllm_url}/health", timeout=timeout)
        if r.status_code != 200:
            return ComponentHealth(
                "vLLM",
                "down",
                f"/health returned {r.status_code}",
                _elapsed_ms(start),
            )
        # Verify model is loaded
        mr = requests.get(f"{config.vllm_url}/v1/models", timeout=timeout)
        if mr.status_code != 200:
            return ComponentHealth(
                "vLLM",
                "degraded",
                f"/v1/models returned {mr.status_code}",
                _elapsed_ms(start),
            )
        models = mr.json().get("data", [])
        model_ids = [m.get("id", "") for m in models]
        if config.chat_model in model_ids:
            return ComponentHealth(
                "vLLM",
                "ok",
                f"{config.chat_model} loaded",
                _elapsed_ms(start),
            )
        return ComponentHealth(
            "vLLM",
            "degraded",
            f"expected {config.chat_model}, found {model_ids}",
            _elapsed_ms(start),
        )
    except Exception as exc:
        return ComponentHealth("vLLM", "down", str(exc), _elapsed_ms(start))


def check_ollama(
    config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT
) -> ComponentHealth:
    """Check Ollama is reachable and the embed model is available."""
    start = time.monotonic()
    try:
        r = requests.get(f"{config.ollama_host}/api/tags", timeout=timeout)
        if r.status_code != 200:
            return ComponentHealth(
                "Ollama",
                "down",
                f"/api/tags returned {r.status_code}",
                _elapsed_ms(start),
            )
        models = [m.get("name", "") for m in r.json().get("models", [])]
        # Match with or without tag suffix
        embed_base = config.embed_model.split(":")[0]
        if any(embed_base in m for m in models):
            return ComponentHealth(
                "Ollama",
                "ok",
                f"{config.embed_model} available",
                _elapsed_ms(start),
            )
        return ComponentHealth(
            "Ollama",
            "degraded",
            f"expected {config.embed_model}, found {models}",
            _elapsed_ms(start),
        )
    except Exception as exc:
        return ComponentHealth("Ollama", "down", str(exc), _elapsed_ms(start))


def check_pgvector(
    config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT
) -> ComponentHealth:
    """Check pgvector is reachable and count KB chunks."""
    start = time.monotonic()
    try:
        import psycopg2

        conn = psycopg2.connect(config.pgvector_dsn, connect_timeout=timeout)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.execute("SELECT COUNT(*) FROM documents")
                count = cur.fetchone()[0]
            return ComponentHealth(
                "pgvector",
                "ok",
                f"{count:,} documents",
                _elapsed_ms(start),
            )
        finally:
            conn.close()
    except Exception as exc:
        return ComponentHealth("pgvector", "down", str(exc), _elapsed_ms(start))


def check_prometheus(
    config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT
) -> ComponentHealth:
    """Check Prometheus readiness endpoint."""
    start = time.monotonic()
    try:
        r = requests.get(f"{config.prometheus_url}/-/ready", timeout=timeout)
        if r.status_code == 200:
            return ComponentHealth("Prometheus", "ok", "ready", _elapsed_ms(start))
        return ComponentHealth(
            "Prometheus",
            "degraded",
            f"/-/ready returned {r.status_code}",
            _elapsed_ms(start),
        )
    except Exception as exc:
        return ComponentHealth("Prometheus", "down", str(exc), _elapsed_ms(start))


def check_containers(
    config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT
) -> ComponentHealth:
    """Check Docker containers against the critical set from watchdog."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--format",
                "{{.Names}}:{{.Status}}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return ComponentHealth(
                "Containers",
                "down",
                f"docker ps failed: {result.stderr.strip()}",
                _elapsed_ms(start),
            )
        running: dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            if ":" in line:
                name, status = line.split(":", 1)
                running[name.strip()] = status.strip()

        missing = CRITICAL_CONTAINERS - set(running.keys())
        if missing:
            names = ", ".join(sorted(missing))
            return ComponentHealth(
                "Containers",
                "degraded",
                f"missing: {names}",
                _elapsed_ms(start),
            )
        return ComponentHealth(
            "Containers",
            "ok",
            f"all {len(CRITICAL_CONTAINERS)} critical running",
            _elapsed_ms(start),
        )
    except Exception as exc:
        return ComponentHealth("Containers", "down", str(exc), _elapsed_ms(start))


def check_pushgateway(
    config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT
) -> ComponentHealth:
    """Check Pushgateway readiness."""
    start = time.monotonic()
    # Pushgateway runs on port 9092 per system prompt; derive from prometheus_url
    # Convention: pushgateway is at same host as prometheus, port 9092
    from urllib.parse import urlparse

    parsed = urlparse(config.prometheus_url)
    host = parsed.hostname or "localhost"
    pg_url = f"http://{host}:9092"
    try:
        r = requests.get(f"{pg_url}/-/ready", timeout=timeout)
        if r.status_code == 200:
            return ComponentHealth("Pushgateway", "ok", "ready", _elapsed_ms(start))
        return ComponentHealth(
            "Pushgateway",
            "degraded",
            f"/-/ready returned {r.status_code}",
            _elapsed_ms(start),
        )
    except Exception as exc:
        return ComponentHealth("Pushgateway", "down", str(exc), _elapsed_ms(start))


def check_grafana(
    config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT
) -> ComponentHealth:
    """Check Grafana health endpoint (port 3001 per system prompt)."""
    start = time.monotonic()
    from urllib.parse import urlparse

    parsed = urlparse(config.prometheus_url)
    host = parsed.hostname or "localhost"
    grafana_url = f"http://{host}:3001"
    try:
        r = requests.get(f"{grafana_url}/api/health", timeout=timeout)
        if r.status_code == 200:
            return ComponentHealth("Grafana", "ok", "healthy", _elapsed_ms(start))
        return ComponentHealth(
            "Grafana",
            "degraded",
            f"/api/health returned {r.status_code}",
            _elapsed_ms(start),
        )
    except Exception as exc:
        return ComponentHealth("Grafana", "down", str(exc), _elapsed_ms(start))


def check_ntopng(
    config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT
) -> ComponentHealth:
    """Check ntopng is reachable."""
    start = time.monotonic()
    try:
        r = requests.get(
            f"{config.ntopng_url}/lua/rest/v2/get/ntopng/interfaces.lua",
            timeout=timeout,
        )
        # ntopng returns 200 even without auth for some endpoints; any HTTP
        # response means the service is up.
        if r.status_code < 500:
            return ComponentHealth("ntopng", "ok", "reachable", _elapsed_ms(start))
        return ComponentHealth(
            "ntopng",
            "degraded",
            f"returned {r.status_code}",
            _elapsed_ms(start),
        )
    except Exception as exc:
        return ComponentHealth("ntopng", "down", str(exc), _elapsed_ms(start))


# ---------------------------------------------------------------------------
# Registry and runner
# ---------------------------------------------------------------------------

# Ordered list of (name, check_fn) — controls display order
CheckFn = Callable[[cfg.Config, int], ComponentHealth]
HEALTH_CHECKS: list[tuple[str, CheckFn]] = [
    ("vLLM", check_vllm),
    ("Ollama", check_ollama),
    ("pgvector", check_pgvector),
    ("Prometheus", check_prometheus),
    ("Containers", check_containers),
    ("Pushgateway", check_pushgateway),
    ("Grafana", check_grafana),
    ("ntopng", check_ntopng),
]


def run_all_checks(
    config: cfg.Config, timeout: int = _DEFAULT_TIMEOUT
) -> list[ComponentHealth]:
    """Run every registered health check and return results.

    Each check is independent — a failure in one never affects another.
    """
    return [check_fn(config, timeout) for _name, check_fn in HEALTH_CHECKS]


def format_health_table(results: list[ComponentHealth]) -> str:
    """Format health check results as a human-readable table."""
    lines = [f"{'Component':<14} | {'Status':<8} | Detail"]
    lines.append("-" * 60)
    lines.extend(
        f"{r.name:<14} | {r.status:<8} | {r.detail} ({r.latency_ms:.0f}ms)"
        for r in results
    )
    return "\n".join(lines)


def summary_line(results: list[ComponentHealth]) -> str:
    """Return a one-line summary like 'All 8 components healthy' or '2 degraded, 1 down'."""
    by_status: dict[str, int] = {"ok": 0, "degraded": 0, "down": 0}
    for r in results:
        by_status[r.status] += 1
    total = len(results)
    if by_status["ok"] == total:
        return f"All {total} components healthy."
    parts: list[str] = []
    if by_status["ok"]:
        parts.append(f"{by_status['ok']} ok")
    if by_status["degraded"]:
        parts.append(f"{by_status['degraded']} degraded")
    if by_status["down"]:
        parts.append(f"{by_status['down']} down")
    return f"{total} components: {', '.join(parts)}."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _elapsed_ms(start: float) -> float:
    return (time.monotonic() - start) * 1000
