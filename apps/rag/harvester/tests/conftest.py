"""
Pytest configuration and shared fixtures for ORION harvester tests.

This file provides:
- Test data fixtures
- Mock API responses
- Common test utilities
"""

import sys
from pathlib import Path
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

# Add src/ to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ============================================================================
# Mock API Response Fixtures
# ============================================================================

@pytest.fixture
def mock_semantic_scholar_response():
    """Mock Semantic Scholar API response"""
    return {
        "data": [
            {
                "paperId": "test123",
                "title": "Test Paper on Vector Databases",
                "abstract": "This is a test abstract about vector databases.",
                "authors": [{"name": "John Doe"}, {"name": "Jane Smith"}],
                "year": 2024,
                "citationCount": 42,
                "url": "https://semanticscholar.org/paper/test123",
                "publicationDate": "2024-01-15",
                "venue": "Test Conference",
            }
        ],
        "total": 1,
    }


@pytest.fixture
def mock_arxiv_response():
    """Mock arXiv API response"""
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Test Paper: Machine Learning</title>
    <summary>This is a test abstract.</summary>
    <author><name>Test Author</name></author>
    <published>2024-01-15T00:00:00Z</published>
    <link href="http://arxiv.org/pdf/2401.12345v1"/>
  </entry>
</feed>"""


@pytest.fixture
def mock_github_readme():
    """Mock GitHub README content"""
    return {
        "name": "README.md",
        "path": "README.md",
        "content": "IyBUZXN0IFByb2plY3QKClRoaXMgaXMgYSB0ZXN0IFJFQURNRS4=",  # base64 "# Test Project\n\nThis is a test README."
        "encoding": "base64",
        "html_url": "https://github.com/test/repo/blob/main/README.md",
    }


# ============================================================================
# Document Fixtures
# ============================================================================

@pytest.fixture
def sample_document():
    """Sample document for testing"""
    return {
        "title": "Test Document",
        "content": "This is test content for a document.",
        "metadata": {
            "author": "Test Author",
            "year": 2024,
            "source": "test",
        },
        "url": "https://example.com/test-doc",
    }


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a temporary PDF file for testing"""
    pdf_file = tmp_path / "test.pdf"
    # Create a minimal PDF (just for testing file existence)
    pdf_file.write_bytes(b"%PDF-1.4\n%Test PDF\n%%EOF")
    return pdf_file


# ============================================================================
# Provider Fixtures
# ============================================================================

@pytest.fixture
def mock_provider():
    """Mock base provider for testing"""
    provider = Mock()
    provider.get_provider_name.return_value = "test_provider"
    provider.get_provider_type.return_value = "academic"
    provider.rate_limit = 1.0
    return provider


# ============================================================================
# Registry Fixtures
# ============================================================================

@pytest.fixture
def temp_registry_db(tmp_path):
    """Temporary SQLite database for testing"""
    db_path = tmp_path / "test_registry.db"
    return db_path


# ============================================================================
# Environment Fixtures
# ============================================================================

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing"""
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("ANYTHINGLLM_URL", "http://localhost:3001")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    return {
        "QDRANT_URL": "http://localhost:6333",
        "ANYTHINGLLM_URL": "http://localhost:3001",
        "LOG_LEVEL": "DEBUG",
    }


# ============================================================================
# API Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_requests_get(monkeypatch):
    """Mock requests.get for API testing"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}
    mock_response.text = "Mock response"

    mock_get = Mock(return_value=mock_response)
    monkeypatch.setattr("requests.get", mock_get)
    return mock_get


@pytest.fixture
def mock_requests_post(monkeypatch):
    """Mock requests.post for API testing"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}

    mock_post = Mock(return_value=mock_response)
    monkeypatch.setattr("requests.post", mock_post)
    return mock_post


@pytest.fixture
def mock_api_error_response():
    """Mock API error response (500, network errors, etc.)"""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.text = "Internal Server Error"
    mock_response.raise_for_status.side_effect = Exception("HTTP 500 Internal Server Error")
    return mock_response


@pytest.fixture
def mock_api_rate_limit_response():
    """Mock API rate limit response (429 Too Many Requests)"""
    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.json.return_value = {
        "error": "Rate limit exceeded",
        "retry_after": 60
    }
    mock_response.headers = {"Retry-After": "60"}
    return mock_response


@pytest.fixture
def mock_session_with_retry():
    """Mock requests.Session with retry logic for testing HTTP resilience"""
    from unittest.mock import MagicMock

    session = MagicMock()
    session.get.return_value = Mock(
        status_code=200,
        json=lambda: {"success": True},
        text="Mock response"
    )
    session.post.return_value = Mock(
        status_code=200,
        json=lambda: {"success": True}
    )
    return session
