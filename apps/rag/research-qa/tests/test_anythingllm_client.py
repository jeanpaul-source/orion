"""Unit tests for AnythingLLM API client.

Tests cover:
- Client initialization and API key handling
- Session creation with retry logic
- Connection testing
- Workspace listing
- Authentication headers
- Error handling
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock

from anythingllm_client import AnythingLLMClient, UploadResult


class TestAnythingLLMClient:
    """Test suite for AnythingLLMClient"""

    def test_initialization_with_api_key(self):
        """Test client initialization with explicit API key"""
        client = AnythingLLMClient(
            base_url="http://localhost:3001",
            api_key="test_api_key"
        )

        assert client.base_url == "http://localhost:3001"
        assert client.api_key == "test_api_key"
        assert "Authorization" in client.headers
        assert client.headers["Authorization"] == "Bearer test_api_key"

    @patch.dict('os.environ', {'ANYTHINGLLM_API_KEY': 'env_api_key'})
    def test_initialization_from_env_var(self):
        """Test client initialization from environment variable"""
        client = AnythingLLMClient(base_url="http://localhost:3001")

        assert client.api_key == "env_api_key"
        assert client.headers["Authorization"] == "Bearer env_api_key"

    @patch.dict('os.environ', {}, clear=True)
    def test_initialization_without_api_key_raises_error(self):
        """Test that missing API key raises ValueError"""
        with pytest.raises(ValueError, match="API key required"):
            AnythingLLMClient(base_url="http://localhost:3001")

    def test_initialization_strips_trailing_slash(self):
        """Test that trailing slash is removed from base URL"""
        client = AnythingLLMClient(
            base_url="http://localhost:3001/",
            api_key="test_key"
        )

        assert client.base_url == "http://localhost:3001"

    def test_session_created_with_retry_logic(self):
        """Test that session has retry adapters"""
        client = AnythingLLMClient(
            base_url="http://localhost:3001",
            api_key="test_key"
        )

        assert hasattr(client, 'session')
        assert 'http://' in client.session.adapters
        assert 'https://' in client.session.adapters

    @patch('anythingllm_client.requests.Session')
    def test_test_connection_success(self, mock_session_class):
        """Test successful connection test"""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = AnythingLLMClient(
            base_url="http://localhost:3001",
            api_key="test_key"
        )
        client.session = mock_session

        result = client.test_connection()

        assert result is True
        mock_session.get.assert_called_once()

    @patch('anythingllm_client.requests.Session')
    def test_test_connection_failure(self, mock_session_class):
        """Test failed connection test"""
        mock_response = Mock()
        mock_response.status_code = 401

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = AnythingLLMClient(
            base_url="http://localhost:3001",
            api_key="bad_key"
        )
        client.session = mock_session

        result = client.test_connection()

        assert result is False

    @patch('anythingllm_client.requests.Session')
    def test_test_connection_handles_exception(self, mock_session_class):
        """Test connection test handles exceptions gracefully"""
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Network error")
        mock_session_class.return_value = mock_session

        client = AnythingLLMClient(
            base_url="http://localhost:3001",
            api_key="test_key"
        )
        client.session = mock_session

        result = client.test_connection()

        assert result is False

    @patch('anythingllm_client.requests.Session')
    def test_list_workspaces_success(self, mock_session_class):
        """Test successful workspace listing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workspaces": [
                {"slug": "workspace1", "name": "Workspace 1"},
                {"slug": "workspace2", "name": "Workspace 2"}
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = AnythingLLMClient(
            base_url="http://localhost:3001",
            api_key="test_key"
        )
        client.session = mock_session

        workspaces = client.list_workspaces()

        assert len(workspaces) == 2
        assert workspaces[0]["slug"] == "workspace1"
        assert workspaces[1]["slug"] == "workspace2"

    @patch('anythingllm_client.requests.Session')
    def test_list_workspaces_empty(self, mock_session_class):
        """Test listing workspaces when none exist"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"workspaces": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = AnythingLLMClient(
            base_url="http://localhost:3001",
            api_key="test_key"
        )
        client.session = mock_session

        workspaces = client.list_workspaces()

        assert workspaces == []

    @patch('anythingllm_client.requests.Session')
    def test_list_workspaces_includes_auth_header(self, mock_session_class):
        """Test that workspace listing includes authorization header"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"workspaces": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = AnythingLLMClient(
            base_url="http://localhost:3001",
            api_key="test_key"
        )
        client.session = mock_session

        client.list_workspaces()

        # Verify headers were passed
        call_args = mock_session.get.call_args
        assert "headers" in call_args[1]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test_key"

    def test_upload_result_dataclass(self):
        """Test UploadResult dataclass structure"""
        result = UploadResult(
            success=True,
            document_id="doc123",
            workspace_slug="workspace1",
            chunks_created=10
        )

        assert result.success is True
        assert result.document_id == "doc123"
        assert result.workspace_slug == "workspace1"
        assert result.chunks_created == 10
        assert result.error is None

    def test_upload_result_with_error(self):
        """Test UploadResult with error"""
        result = UploadResult(
            success=False,
            error="Upload failed"
        )

        assert result.success is False
        assert result.error == "Upload failed"
        assert result.document_id is None
        assert result.chunks_created == 0
