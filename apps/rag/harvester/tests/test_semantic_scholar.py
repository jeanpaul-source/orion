"""Unit tests for Semantic Scholar provider.

Tests cover:
- Provider initialization
- Search functionality
- API response handling
- Error handling
- Rate limiting
- Citation metrics calculation
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from providers.semantic_scholar import SemanticScholarProvider
from providers.base import Document


class TestSemanticScholarProvider:
    """Test suite for SemanticScholarProvider"""

    def test_initialization_default(self):
        """Test provider initialization with defaults"""
        provider = SemanticScholarProvider()

        assert provider.get_provider_name() == "semantic_scholar"
        assert provider.get_provider_type() == "academic"
        assert provider.rate_limit == 1.0
        assert hasattr(provider, 'session')

    def test_initialization_with_custom_params(self):
        """Test provider initialization with custom parameters"""
        provider = SemanticScholarProvider(api_key="test_key", rate_limit=2.0)

        assert provider.api_key == "test_key"
        assert provider.rate_limit == 2.0

    def test_create_session_with_retry(self):
        """Test that session is created with retry logic"""
        provider = SemanticScholarProvider()
        session = provider.session

        # Check that session has adapters mounted
        assert session is not None
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_success(self, mock_session_class):
        """Test successful search with valid API response"""
        # Setup mock
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "title": "Test Paper on Vector Databases",
                    "abstract": "This paper discusses vector databases.",
                    "authors": [{"name": "John Doe"}, {"name": "Jane Smith"}],
                    "year": 2020,
                    "venue": "Test Conference",
                    "citationCount": 100,
                    "influentialCitationCount": 20,
                    "openAccessPdf": {
                        "url": "https://example.com/paper.pdf"
                    }
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        # Execute
        provider = SemanticScholarProvider()
        provider.session = mock_session
        results = provider.search("vector databases", max_results=10)

        # Verify
        assert len(results) == 1
        assert isinstance(results[0], Document)
        assert results[0].title == "Test Paper on Vector Databases"
        assert results[0].url == "https://example.com/paper.pdf"
        assert results[0].content_type == "pdf"
        assert results[0].source_provider == "semantic_scholar"
        assert results[0].metadata["year"] == 2020
        assert results[0].metadata["citation_count"] == 100
        assert results[0].metadata["influential_citation_count"] == 20

        # Verify API call
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert "query" in call_args[1]["params"]
        assert call_args[1]["params"]["query"] == "vector databases"

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_with_api_key(self, mock_session_class):
        """Test that API key is included in headers when provided"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider(api_key="test_api_key")
        provider.session = mock_session
        provider.search("test query")

        # Verify API key in headers
        call_args = mock_session.get.call_args
        assert "headers" in call_args[1]
        assert call_args[1]["headers"]["X-API-KEY"] == "test_api_key"

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_filters_papers_without_pdf(self, mock_session_class):
        """Test that papers without open access PDFs are filtered out"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "title": "Paper With PDF",
                    "openAccessPdf": {"url": "https://example.com/paper1.pdf"},
                    "year": 2020,
                    "citationCount": 50
                },
                {
                    "title": "Paper Without PDF",
                    "openAccessPdf": None,
                    "year": 2020,
                    "citationCount": 100
                },
                {
                    "title": "Paper With Empty PDF",
                    "openAccessPdf": {},
                    "year": 2020,
                    "citationCount": 75
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Only paper with valid PDF should be included
        assert len(results) == 1
        assert results[0].title == "Paper With PDF"

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_calculates_citations_per_year(self, mock_session_class):
        """Test citation per year calculation"""
        current_year = datetime.now().year
        paper_year = current_year - 5  # 5 years old

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "title": "Test Paper",
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                    "year": paper_year,
                    "citationCount": 100,
                    "influentialCitationCount": 20
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Verify citations per year is calculated
        assert len(results) == 1
        expected_citations_per_year = 100 / 5  # 20.0
        assert results[0].metadata["citations_per_year"] == round(expected_citations_per_year, 2)

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_handles_missing_year(self, mock_session_class):
        """Test handling of papers with missing year"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "title": "Test Paper",
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                    "year": None,
                    "citationCount": 100
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["year"] == "unknown"
        assert results[0].metadata["citations_per_year"] == 0.0

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_limits_author_list(self, mock_session_class):
        """Test that author list is limited to first 3 authors"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "title": "Test Paper",
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                    "year": 2020,
                    "authors": [
                        {"name": "Author 1"},
                        {"name": "Author 2"},
                        {"name": "Author 3"},
                        {"name": "Author 4"},
                        {"name": "Author 5"}
                    ],
                    "citationCount": 50
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        authors = results[0].metadata["authors"]
        assert authors == "Author 1, Author 2, Author 3"

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_http_error(self, mock_session_class):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_rate_limit_error(self, mock_session_class, mock_api_rate_limit_response):
        """Test handling of rate limit errors (429)"""
        mock_session = MagicMock()
        mock_session.get.return_value = mock_api_rate_limit_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on rate limit
        assert results == []

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_respects_max_results(self, mock_session_class):
        """Test that max_results parameter is respected"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        provider.search("test query", max_results=50)

        # Verify max_results is passed as limit
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["limit"] == 50

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_caps_max_results_at_100(self, mock_session_class):
        """Test that max_results is capped at 100"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        provider.search("test query", max_results=500)

        # Verify max_results is capped at 100
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["limit"] == 100

    @patch('providers.semantic_scholar.requests.Session')
    def test_search_includes_all_required_fields(self, mock_session_class):
        """Test that search requests all required fields"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = SemanticScholarProvider()
        provider.session = mock_session
        provider.search("test query")

        # Verify required fields are requested
        call_args = mock_session.get.call_args
        fields = call_args[1]["params"]["fields"]
        assert "title" in fields
        assert "abstract" in fields
        assert "authors" in fields
        assert "year" in fields
        assert "citationCount" in fields
        assert "influentialCitationCount" in fields
        assert "openAccessPdf" in fields
