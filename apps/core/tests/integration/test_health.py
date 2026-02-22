"""
Integration test for ORION Core health endpoint.

This test verifies that the /health endpoint returns the correct status
and includes all required fields in the response.
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add parent directory to path so we can import src package
parent_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(parent_path))

from src.main import app  # noqa: E402


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_health_endpoint_returns_200(client):
    """Test that /health endpoint returns HTTP 200 status code."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint_returns_json(client):
    """Test that /health endpoint returns valid JSON."""
    response = client.get("/health")
    assert response.headers["content-type"] == "application/json"


def test_health_endpoint_has_required_fields(client):
    """Test that /health endpoint response contains all required fields."""
    response = client.get("/health")
    data = response.json()

    # Check that all required fields are present
    assert "status" in data, "Response missing 'status' field"
    assert "app" in data, "Response missing 'app' field"
    assert "version" in data, "Response missing 'version' field"
    assert "environment" in data, "Response missing 'environment' field"


def test_health_endpoint_status_value(client):
    """Test that /health endpoint reports 'healthy' status."""
    response = client.get("/health")
    data = response.json()

    assert data["status"] == "healthy"


def test_health_endpoint_app_name(client):
    """Test that /health endpoint reports correct app name."""
    response = client.get("/health")
    data = response.json()

    assert data["app"] == "ORION"
