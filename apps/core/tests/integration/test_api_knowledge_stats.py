"""
Integration test for ORION Core knowledge stats API.

This test verifies that the /api/knowledge/stats endpoint returns a proper
response without making assumptions about the actual data in Qdrant.
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add parent directory to path so we can import src package
parent_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(parent_path))

from src.main import app  # noqa: E402
from src.router import IntelligenceRouter  # noqa: E402


@pytest.fixture
def client():
    """Create a test client for the FastAPI app with proper initialization."""
    # Initialize the router in app state (normally done in startup event)
    app.state.router = IntelligenceRouter()

    return TestClient(app)


def test_knowledge_stats_endpoint_returns_200(client):
    """Test that /api/knowledge/stats endpoint returns HTTP 200 status code."""
    response = client.get("/api/knowledge/stats")
    assert response.status_code == 200


def test_knowledge_stats_endpoint_returns_json(client):
    """Test that /api/knowledge/stats endpoint returns valid JSON."""
    response = client.get("/api/knowledge/stats")
    assert response.headers["content-type"] == "application/json"


def test_knowledge_stats_has_status_field(client):
    """Test that /api/knowledge/stats response contains a status field."""
    response = client.get("/api/knowledge/stats")
    data = response.json()

    assert "status" in data, "Response missing 'status' field"


def test_knowledge_stats_does_not_crash(client):
    """Test that /api/knowledge/stats endpoint handles requests without crashing."""
    # This test verifies the endpoint is robust even if Qdrant is unavailable
    # or the collection is empty
    response = client.get("/api/knowledge/stats")

    # Should return a valid response (200 or error status)
    assert response.status_code in [200, 500, 503]

    # Should always return valid JSON
    data = response.json()
    assert isinstance(data, dict)

    # Should always have a status field
    assert "status" in data
