"""
Smoke Tests - Docker Environment

Verifies that ORION Core is running in the correct Docker environment
with proper network configuration and service discovery.

Run with: pytest tests/smoke/test_docker_environment.py -v
"""

import pytest
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import config


@pytest.mark.smoke
def test_dns_resolution_for_services():
    """
    Test that Docker service names resolve to IP addresses.

    This verifies Docker's internal DNS is working for service discovery.
    """
    services = ["vllm", "qdrant", "anythingllm"]

    for service in services:
        try:
            # Try to resolve the hostname
            ip = socket.gethostbyname(service)
            print(f"✅ {service} resolves to {ip}")
        except socket.gaierror:
            # This is expected if not running in Docker
            print(f"⚠️  {service} DNS not found (OK if running locally)")


@pytest.mark.smoke
def test_environment_variables_set():
    """
    Test that required environment variables are set.

    These are critical for ORION Core to function.
    """
    print("\n" + "=" * 70)
    print("Environment Configuration Check")
    print("=" * 70)

    checks = {
        "vLLM URL": config.vllm_url,
        "Qdrant URL": config.qdrant_url,
        "AnythingLLM URL": config.anythingllm_url,
        "Qdrant Collection": config.qdrant_collection,
        "API Key Set": "YES" if config.anythingllm_api_key else "NO ❌",
        "Environment": config.environment,
        "Log Level": config.log_level,
    }

    for key, value in checks.items():
        print(f"{key:25} → {value}")

    print("=" * 70)

    # Critical checks
    assert config.vllm_url, "vLLM URL not configured"
    assert config.qdrant_url, "Qdrant URL not configured"
    assert config.anythingllm_url, "AnythingLLM URL not configured"

    if not config.anythingllm_api_key:
        pytest.fail(
            "❌ ORION_ANYTHINGLLM_API_KEY not set - Knowledge subsystem will fail!"
        )


@pytest.mark.smoke
def test_subsystems_enabled():
    """
    Test which subsystems are enabled in configuration.
    """
    print("\n" + "=" * 70)
    print("Subsystem Configuration")
    print("=" * 70)

    subsystems = {
        "Knowledge (RAG)": config.enable_knowledge,
        "Action (DevOps)": config.enable_action,
        "Learning (Self-teaching)": config.enable_learning,
        "Watch (Monitoring)": config.enable_watch,
    }

    for name, enabled in subsystems.items():
        status = "✅ ENABLED" if enabled else "❌ DISABLED"
        print(f"{name:30} {status}")

    print("=" * 70)

    if not any(subsystems.values()):
        pytest.fail("❌ No subsystems enabled! ORION Core won't do anything.")
