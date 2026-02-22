"""Unit tests for CORE provider.

Tests cover:
- Provider initialization with API key
- Search functionality
- Bearer token authentication
- PDF URL requirement (downloadUrl)
- Author limiting
- Abstract fallback to description
- Error handling
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock

from providers.core import COREProvider
from providers.base import Document


class TestCOREProvider:
    """Test suite for COREProvider"""

    def test_initialization_default(self):
        """Test provider initialization with defaults"""
        provider = COREProvider()

        assert provider.get_provider_name() == "core"
        assert provider.get_provider_type() == "academic"
        assert provider.rate_limit == 1.0
        assert hasattr(provider, 'session')

    def test_initialization_with_api_key(self):
        """Test provider initialization with API key"""
        provider = COREProvider(api_key="test_api_key")

        assert provider.api_key == "test_api_key"

    def test_initialization_with_custom_rate_limit(self):
        """Test provider initialization with custom rate limit"""
        provider = COREProvider(rate_limit=2.0)

        assert provider.rate_limit == 2.0

    def test_create_session_with_retry(self):
        """Test that session is created with retry logic"""
        provider = COREProvider()
        session = provider.session

        assert session is not None
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('providers.core.requests.Session')
    def test_search_success(self, mock_session_class):
        """Test successful search with valid API response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper on Machine Learning",
                    "downloadUrl": "https://core.ac.uk/download/pdf/123456.pdf",
                    "authors": [
                        {"name": "John Doe"},
                        {"name": "Jane Smith"}
                    ],
                    "yearPublished": 2023,
                    "publisher": "Test Publisher",
                    "abstract": "This is a test abstract about machine learning."
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("machine learning", max_results=10)

        assert len(results) == 1
        assert isinstance(results[0], Document)
        assert results[0].title == "Test Paper on Machine Learning"
        assert results[0].url == "https://core.ac.uk/download/pdf/123456.pdf"
        assert results[0].content_type == "pdf"
        assert results[0].source_provider == "core"
        assert results[0].metadata["year"] == 2023
        assert results[0].metadata["authors"] == "John Doe, Jane Smith"
        assert results[0].metadata["venue"] == "Test Publisher"
        assert "machine learning" in results[0].metadata["abstract"].lower()

    @patch('providers.core.requests.Session')
    def test_search_with_api_key_header(self, mock_session_class):
        """Test that API key is included in Authorization header"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider(api_key="test_bearer_token")
        provider.session = mock_session
        provider.search("test query")

        # Verify Bearer token in headers
        call_args = mock_session.get.call_args
        assert "headers" in call_args[1]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test_bearer_token"

    @patch('providers.core.requests.Session')
    def test_search_filters_papers_without_downloadurl(self, mock_session_class):
        """Test that papers without downloadUrl are filtered out"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Paper With PDF",
                    "downloadUrl": "https://core.ac.uk/download/pdf/123.pdf",
                    "yearPublished": 2023
                },
                {
                    "title": "Paper Without PDF",
                    "downloadUrl": None,
                    "yearPublished": 2023
                },
                {
                    "title": "Paper Missing downloadUrl",
                    # downloadUrl field missing entirely
                    "yearPublished": 2023
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Only paper with valid downloadUrl should be included
        assert len(results) == 1
        assert results[0].title == "Paper With PDF"

    @patch('providers.core.requests.Session')
    def test_search_limits_authors_to_three(self, mock_session_class):
        """Test that author list is limited to first 3 authors"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "downloadUrl": "https://core.ac.uk/download/pdf/123.pdf",
                    "authors": [
                        {"name": "Author 1"},
                        {"name": "Author 2"},
                        {"name": "Author 3"},
                        {"name": "Author 4"},
                        {"name": "Author 5"}
                    ],
                    "yearPublished": 2023
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        authors = results[0].metadata["authors"]
        assert authors == "Author 1, Author 2, Author 3"

    @patch('providers.core.requests.Session')
    def test_search_handles_empty_authors(self, mock_session_class):
        """Test handling of empty authors list"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "downloadUrl": "https://core.ac.uk/download/pdf/123.pdf",
                    "authors": [],
                    "yearPublished": 2023
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["authors"] == "Unknown"

    @patch('providers.core.requests.Session')
    def test_search_uses_abstract_when_available(self, mock_session_class):
        """Test that abstract is used when available"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "downloadUrl": "https://core.ac.uk/download/pdf/123.pdf",
                    "abstract": "This is the abstract",
                    "description": "This is the description",
                    "yearPublished": 2023
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["abstract"] == "This is the abstract"

    @patch('providers.core.requests.Session')
    def test_search_falls_back_to_description(self, mock_session_class):
        """Test fallback to description when abstract is missing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "downloadUrl": "https://core.ac.uk/download/pdf/123.pdf",
                    "abstract": None,
                    "description": "This is the description",
                    "yearPublished": 2023
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["abstract"] == "This is the description"

    @patch('providers.core.requests.Session')
    def test_search_handles_missing_year(self, mock_session_class):
        """Test handling of missing yearPublished"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "downloadUrl": "https://core.ac.uk/download/pdf/123.pdf"
                    # yearPublished missing
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["year"] == "unknown"

    @patch('providers.core.requests.Session')
    def test_search_handles_missing_title(self, mock_session_class):
        """Test handling of missing title"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "downloadUrl": "https://core.ac.uk/download/pdf/123.pdf",
                    "yearPublished": 2023
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].title == "Unknown"

    @patch('providers.core.requests.Session')
    def test_search_http_error(self, mock_session_class):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.core.requests.Session')
    def test_search_respects_max_results(self, mock_session_class):
        """Test that max_results parameter is respected"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        provider.search("test query", max_results=50)

        # Verify limit parameter
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["limit"] == 50

    @patch('providers.core.requests.Session')
    def test_search_caps_max_results_at_100(self, mock_session_class):
        """Test that max_results is capped at 100 (CORE API limit)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        provider.search("test query", max_results=500)

        # Verify max_results is capped at 100
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["limit"] == 100

    @patch('providers.core.requests.Session')
    def test_metadata_structure(self, mock_session_class):
        """Test that document metadata has expected structure"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "downloadUrl": "https://core.ac.uk/download/pdf/123.pdf",
                    "authors": [{"name": "Test Author"}],
                    "yearPublished": 2023,
                    "publisher": "Test Publisher",
                    "abstract": "Test abstract"
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = COREProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        metadata = results[0].metadata

        # Verify all expected metadata fields exist
        assert "year" in metadata
        assert "authors" in metadata
        assert "venue" in metadata
        assert "abstract" in metadata
        assert "citation_count" in metadata
        assert "source" in metadata

        # Verify default/expected values
        assert metadata["citation_count"] == 0  # Free tier doesn't provide citations
        assert metadata["source"] == "core"
