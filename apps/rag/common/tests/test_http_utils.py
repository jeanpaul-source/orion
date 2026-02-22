"""
Tests for HTTP utilities.

Tests the consolidated HTTP session creation and resilient request functions.
"""

import pytest
import requests
from unittest.mock import Mock, patch

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from http_utils import create_session, get_session, resilient_get, resilient_post


class TestCreateSession:
    """Test HTTP session creation with retry logic."""

    def test_create_session_default(self):
        """Test session creation with default parameters."""
        session = create_session()

        assert isinstance(session, requests.Session)
        assert session.adapters["http://"]
        assert session.adapters["https://"]

    def test_create_session_custom_retries(self):
        """Test session with custom retry count."""
        session = create_session(total_retries=5, backoff_factor=2.0)

        assert isinstance(session, requests.Session)
        # Session is configured (hard to test retry config directly)

    def test_create_session_custom_status_codes(self):
        """Test session with custom status forcelist."""
        session = create_session(status_forcelist=[429, 503])

        assert isinstance(session, requests.Session)

    def test_get_session_alias(self):
        """Test get_session is an alias for create_session."""
        session = get_session()

        assert isinstance(session, requests.Session)


class TestResilientRequests:
    """Test resilient GET/POST request functions."""

    @patch("http_utils.create_session")
    def test_resilient_get_success(self, mock_create_session):
        """Test successful GET request."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_session.get.return_value = mock_response
        mock_create_session.return_value = mock_session

        response = resilient_get("https://example.com/api")

        assert response.status_code == 200
        mock_session.get.assert_called_once()

    @patch("http_utils.create_session")
    def test_resilient_get_failure(self, mock_create_session):
        """Test GET request with failure."""
        mock_session = Mock()
        mock_session.get.side_effect = requests.RequestException("Connection failed")
        mock_create_session.return_value = mock_session

        with pytest.raises(requests.RequestException):
            resilient_get("https://example.com/api")

    @patch("http_utils.create_session")
    def test_resilient_post_success(self, mock_create_session):
        """Test successful POST request."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 201
        mock_session.post.return_value = mock_response
        mock_create_session.return_value = mock_session

        response = resilient_post("https://example.com/api", json={"key": "value"})

        assert response.status_code == 201
        mock_session.post.assert_called_once()
