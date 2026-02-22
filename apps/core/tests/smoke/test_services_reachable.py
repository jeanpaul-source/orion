"""
Smoke Tests - Service Reachability

Verifies that all external services ORION Core depends on are reachable.
These are the most basic tests - if these fail, nothing else will work.

Run with: pytest tests/smoke/test_services_reachable.py -v

Requirements:
- Services must be running (docker compose up -d)
- Network must be configured (orion-net)
- Host must be accessible (lab host or localhost)
"""

import pytest
import httpx
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import config


@pytest.mark.smoke
def test_vllm_service_reachable():
    """
    Test that vLLM service is reachable.

    vLLM provides LLM inference for intent classification and chat.
    Expected endpoint: http://vllm:8000 or http://192.168.5.10:8000
    """
    try:
        response = httpx.get(
            f"{config.vllm_url}/health", timeout=5.0, follow_redirects=True
        )
        assert (
            response.status_code == 200
        ), f"vLLM health check failed: {response.status_code}"
        print(f"✅ vLLM reachable at {config.vllm_url}")
    except httpx.ConnectError as e:
        pytest.fail(f"❌ Cannot connect to vLLM at {config.vllm_url}: {e}")
    except httpx.TimeoutException:
        pytest.fail(f"❌ Timeout connecting to vLLM at {config.vllm_url}")


@pytest.mark.smoke
def test_qdrant_service_reachable():
    """
    Test that Qdrant service is reachable.

    Qdrant provides vector storage for RAG system.
    Expected endpoint: http://qdrant:6333 or http://192.168.5.10:6333
    """
    try:
        response = httpx.get(
            f"{config.qdrant_url}/", timeout=5.0, follow_redirects=True
        )
        # Qdrant returns 200 with HTML page on root
        assert (
            response.status_code == 200
        ), f"Qdrant unreachable: {response.status_code}"
        print(f"✅ Qdrant reachable at {config.qdrant_url}")
    except httpx.ConnectError as e:
        pytest.fail(f"❌ Cannot connect to Qdrant at {config.qdrant_url}: {e}")
    except httpx.TimeoutException:
        pytest.fail(f"❌ Timeout connecting to Qdrant at {config.qdrant_url}")


@pytest.mark.smoke
def test_qdrant_collections_api():
    """
    Test that Qdrant collections API works.

    This verifies we can query Qdrant's REST API, not just reach the service.
    """
    try:
        response = httpx.get(f"{config.qdrant_url}/collections", timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        assert "result" in data

        collections = data["result"]["collections"]
        print(f"✅ Qdrant API working. Found {len(collections)} collections")

        # Check if our collection exists
        collection_names = [c["name"] for c in collections]
        if config.qdrant_collection in collection_names:
            print(f"✅ Collection '{config.qdrant_collection}' exists")
        else:
            print(f"⚠️  Collection '{config.qdrant_collection}' NOT FOUND")
            print(f"   Available: {collection_names}")

    except httpx.ConnectError as e:
        pytest.fail(f"❌ Cannot connect to Qdrant API: {e}")
    except Exception as e:
        pytest.fail(f"❌ Error querying Qdrant collections: {e}")


@pytest.mark.smoke
def test_anythingllm_service_reachable():
    """
    Test that AnythingLLM service is reachable.

    AnythingLLM provides RAG pipeline (embedding + search + generation).
    Expected endpoint: http://anythingllm:3001 or http://192.168.5.10:3001
    """
    try:
        # Try ping endpoint first (fast, no auth)
        response = httpx.get(
            f"{config.anythingllm_url}/api/v1/system/ping",
            timeout=5.0,
            follow_redirects=True,
        )

        # 200 = success, 401 = auth required (but service is up)
        if response.status_code in [200, 401]:
            print(f"✅ AnythingLLM reachable at {config.anythingllm_url}")
        else:
            pytest.fail(f"❌ AnythingLLM unexpected status: {response.status_code}")

    except httpx.ConnectError as e:
        pytest.fail(
            f"❌ Cannot connect to AnythingLLM at {config.anythingllm_url}: {e}"
        )
    except httpx.TimeoutException:
        pytest.fail(f"❌ Timeout connecting to AnythingLLM at {config.anythingllm_url}")


@pytest.mark.smoke
def test_anythingllm_api_key_valid():
    """
    Test that AnythingLLM API key is valid.

    This verifies we can authenticate with the AnythingLLM API.
    """
    if not config.anythingllm_api_key:
        pytest.skip("AnythingLLM API key not configured")

    try:
        headers = {"Authorization": f"Bearer {config.anythingllm_api_key}"}
        response = httpx.get(
            f"{config.anythingllm_url}/api/v1/workspaces", headers=headers, timeout=5.0
        )

        if response.status_code == 200:
            workspaces = response.json().get("workspaces", [])
            print(f"✅ AnythingLLM API key valid. Found {len(workspaces)} workspaces")

            # Check if our workspace exists
            workspace_slugs = [w["slug"] for w in workspaces]
            if config.qdrant_collection in workspace_slugs:
                print(f"✅ Workspace '{config.qdrant_collection}' exists")
            else:
                print(f"⚠️  Workspace '{config.qdrant_collection}' NOT FOUND")
                print(f"   Available: {workspace_slugs}")
        elif response.status_code == 401:
            pytest.fail("❌ AnythingLLM API key is INVALID")
        else:
            pytest.fail(f"❌ AnythingLLM API error: {response.status_code}")

    except Exception as e:
        pytest.fail(f"❌ Error testing AnythingLLM API key: {e}")


@pytest.mark.smoke
def test_all_services_summary():
    """
    Summary test that reports status of all services.

    This is a convenience test that runs after all others to show overall status.
    """
    print("\n" + "=" * 70)
    print("ORION Core Services Status Summary")
    print("=" * 70)

    services = {
        "vLLM (LLM Inference)": config.vllm_url,
        "Qdrant (Vector DB)": config.qdrant_url,
        "AnythingLLM (RAG)": config.anythingllm_url,
    }

    for name, url in services.items():
        print(f"{name:25} → {url}")

    print("=" * 70)
    print("\nIf all smoke tests passed, services are reachable!")
    print("Next: Run integration tests with real API calls")
    print("=" * 70)
