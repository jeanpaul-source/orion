"""Unit tests for OpenAlex provider.

Tests cover:
- Provider initialization
- Search functionality
- Inverted index abstract reconstruction
- PDF URL extraction from best_oa_location
- Error handling
- Citation metrics
- Polite crawling headers
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from providers.openalex import OpenAlexProvider, _reconstruct_openalex_abstract
from providers.base import Document


class TestOpenAlexProvider:
    """Test suite for OpenAlexProvider"""

    def test_initialization(self):
        """Test provider initialization"""
        provider = OpenAlexProvider()

        assert provider.get_provider_name() == "openalex"
        assert provider.get_provider_type() == "academic"
        assert provider.rate_limit == 1.0
        assert hasattr(provider, 'session')

    def test_initialization_with_custom_rate_limit(self):
        """Test provider initialization with custom rate limit"""
        provider = OpenAlexProvider(rate_limit=2.0)

        assert provider.rate_limit == 2.0

    def test_create_session_with_retry(self):
        """Test that session is created with retry logic"""
        provider = OpenAlexProvider()
        session = provider.session

        assert session is not None
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('providers.openalex.requests.Session')
    def test_search_success(self, mock_session_class):
        """Test successful search with valid API response"""
        current_year = datetime.now().year
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper on Vector Databases",
                    "best_oa_location": {
                        "pdf_url": "https://example.com/paper.pdf"
                    },
                    "publication_year": current_year - 3,
                    "authorships": [
                        {"author": {"display_name": "John Doe"}},
                        {"author": {"display_name": "Jane Smith"}}
                    ],
                    "host_venue": {
                        "display_name": "Test Journal"
                    },
                    "cited_by_count": 60,
                    "abstract_inverted_index": {
                        "This": [0],
                        "is": [1],
                        "a": [2],
                        "test": [3],
                        "abstract": [4]
                    }
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        results = provider.search("vector databases", max_results=10)

        assert len(results) == 1
        assert isinstance(results[0], Document)
        assert results[0].title == "Test Paper on Vector Databases"
        assert results[0].url == "https://example.com/paper.pdf"
        assert results[0].content_type == "pdf"
        assert results[0].source_provider == "openalex"
        assert results[0].metadata["cited_by_count"] == 60

        # Verify API call
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert "search" in call_args[1]["params"]
        assert call_args[1]["params"]["search"] == "vector databases"

    @patch('providers.openalex.requests.Session')
    @patch('providers.openalex.CONTACT_EMAIL', 'test@example.com')
    def test_search_includes_polite_crawling_headers(self, mock_session_class):
        """Test that polite crawling headers are included"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        provider.search("test query")

        # Verify mailto parameter and User-Agent header
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["mailto"] == "test@example.com"
        assert "User-Agent" in call_args[1]["headers"]
        assert "OrionHarvester" in call_args[1]["headers"]["User-Agent"]
        assert "test@example.com" in call_args[1]["headers"]["User-Agent"]

    @patch('providers.openalex.requests.Session')
    def test_search_filters_open_access_only(self, mock_session_class):
        """Test that search filters for open access papers"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        provider.search("test query")

        # Verify filter parameter
        call_args = mock_session.get.call_args
        assert "filter" in call_args[1]["params"]
        assert "is_oa:true" in call_args[1]["params"]["filter"]
        assert "type:article" in call_args[1]["params"]["filter"]

    @patch('providers.openalex.requests.Session')
    def test_search_sorts_by_citation_count(self, mock_session_class):
        """Test that results are sorted by citation count"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        provider.search("test query")

        # Verify sort parameter
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["sort"] == "cited_by_count:desc"

    @patch('providers.openalex.requests.Session')
    def test_search_uses_primary_location_fallback(self, mock_session_class):
        """Test fallback to primary_location when best_oa_location is missing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "best_oa_location": None,
                    "primary_location": {
                        "pdf_url": "https://example.com/fallback.pdf"
                    },
                    "publication_year": 2020,
                    "cited_by_count": 50
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].url == "https://example.com/fallback.pdf"

    @patch('providers.openalex.requests.Session')
    def test_search_filters_papers_without_pdf(self, mock_session_class):
        """Test that papers without PDF URLs are filtered out"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Paper With PDF",
                    "best_oa_location": {"pdf_url": "https://example.com/paper1.pdf"},
                    "publication_year": 2020,
                    "cited_by_count": 50
                },
                {
                    "title": "Paper Without PDF",
                    "best_oa_location": None,
                    "primary_location": None,
                    "publication_year": 2020,
                    "cited_by_count": 100
                },
                {
                    "title": "Paper With Empty PDF",
                    "best_oa_location": {"pdf_url": None},
                    "primary_location": {},
                    "publication_year": 2020,
                    "cited_by_count": 75
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Only paper with valid PDF should be included
        assert len(results) == 1
        assert results[0].title == "Paper With PDF"

    @patch('providers.openalex.requests.Session')
    def test_search_calculates_citations_per_year(self, mock_session_class):
        """Test citation per year calculation"""
        current_year = datetime.now().year
        paper_year = current_year - 5

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "best_oa_location": {"pdf_url": "https://example.com/paper.pdf"},
                    "publication_year": paper_year,
                    "cited_by_count": 100
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        expected_citations_per_year = 100 / 5
        assert results[0].metadata["citations_per_year"] == round(expected_citations_per_year, 2)

    @patch('providers.openalex.requests.Session')
    def test_search_limits_author_list(self, mock_session_class):
        """Test that author list is limited to first 3 authors"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Paper",
                    "best_oa_location": {"pdf_url": "https://example.com/paper.pdf"},
                    "publication_year": 2020,
                    "authorships": [
                        {"author": {"display_name": "Author 1"}},
                        {"author": {"display_name": "Author 2"}},
                        {"author": {"display_name": "Author 3"}},
                        {"author": {"display_name": "Author 4"}},
                        {"author": {"display_name": "Author 5"}}
                    ],
                    "cited_by_count": 50
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        authors = results[0].metadata["authors"]
        assert authors == "Author 1, Author 2, Author 3"

    @patch('providers.openalex.requests.Session')
    def test_search_http_error(self, mock_session_class):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.openalex.requests.Session')
    def test_search_respects_max_results(self, mock_session_class):
        """Test that max_results parameter is respected"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        provider.search("test query", max_results=50)

        # Verify per-page parameter
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["per-page"] == 50

    @patch('providers.openalex.requests.Session')
    def test_search_caps_max_results_at_100(self, mock_session_class):
        """Test that max_results is capped at 100"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = OpenAlexProvider()
        provider.session = mock_session
        provider.search("test query", max_results=500)

        # Verify max_results is capped at 100
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["per-page"] == 100


class TestReconstructOpenAlexAbstract:
    """Test suite for _reconstruct_openalex_abstract function"""

    def test_reconstruct_simple_abstract(self):
        """Test reconstruction of simple inverted index"""
        inverted_index = {
            "This": [0],
            "is": [1],
            "a": [2],
            "test": [3],
            "abstract": [4]
        }

        result = _reconstruct_openalex_abstract(inverted_index)
        assert result == "This is a test abstract"

    def test_reconstruct_with_repeated_words(self):
        """Test reconstruction with repeated words"""
        inverted_index = {
            "This": [0, 4],
            "is": [1],
            "a": [2],
            "test": [3]
        }

        result = _reconstruct_openalex_abstract(inverted_index)
        assert result == "This is a test This"

    def test_reconstruct_with_gaps(self):
        """Test reconstruction with non-contiguous positions"""
        inverted_index = {
            "Word": [0, 2, 4],
            "Between": [1, 3]
        }

        result = _reconstruct_openalex_abstract(inverted_index)
        assert "Word" in result
        assert "Between" in result

    def test_reconstruct_empty_index(self):
        """Test reconstruction of empty inverted index"""
        result = _reconstruct_openalex_abstract({})
        assert result == ""

    def test_reconstruct_none_index(self):
        """Test reconstruction of None input"""
        result = _reconstruct_openalex_abstract(None)
        assert result == ""

    def test_reconstruct_handles_invalid_positions(self):
        """Test handling of invalid position values"""
        inverted_index = {
            "Valid": [0, 1],
            "Invalid": [-1, 1000000]
        }

        # Should not crash, returns reconstructed text
        result = _reconstruct_openalex_abstract(inverted_index)
        assert "Valid" in result

    def test_reconstruct_preserves_order(self):
        """Test that word order is preserved"""
        inverted_index = {
            "first": [0],
            "second": [1],
            "third": [2],
            "fourth": [3]
        }

        result = _reconstruct_openalex_abstract(inverted_index)
        assert result == "first second third fourth"
