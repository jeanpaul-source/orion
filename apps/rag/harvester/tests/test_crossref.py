"""Unit tests for Crossref provider.

Tests cover:
- Provider initialization
- Search functionality
- PDF resolution (direct + Unpaywall fallback)
- Year extraction from nested date-parts
- Author name concatenation
- DOI handling
- Error handling
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock

from providers.crossref import CrossrefProvider
from providers.base import Document


class TestCrossrefProvider:
    """Test suite for CrossrefProvider"""

    def test_initialization(self):
        """Test provider initialization"""
        provider = CrossrefProvider()

        assert provider.get_provider_name() == "crossref"
        assert provider.get_provider_type() == "academic"
        assert provider.rate_limit == 1.0
        assert hasattr(provider, 'session')

    def test_initialization_with_custom_rate_limit(self):
        """Test provider initialization with custom rate limit"""
        provider = CrossrefProvider(rate_limit=2.0)

        assert provider.rate_limit == 2.0

    def test_create_session_with_retry(self):
        """Test that session is created with retry logic"""
        provider = CrossrefProvider()
        session = provider.session

        assert session is not None
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('providers.crossref.requests.Session')
    def test_search_with_direct_pdf_link(self, mock_session_class):
        """Test successful search with direct PDF link from Crossref"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Test Paper on Databases"],
                        "DOI": "10.1234/test.doi",
                        "author": [
                            {"given": "John", "family": "Doe"},
                            {"given": "Jane", "family": "Smith"}
                        ],
                        "issued": {
                            "date-parts": [[2023, 5, 15]]
                        },
                        "container-title": ["Test Journal"],
                        "link": [
                            {
                                "URL": "https://example.com/paper.pdf",
                                "content-type": "application/pdf"
                            }
                        ]
                    }
                ]
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("databases", max_results=10)

        assert len(results) == 1
        assert isinstance(results[0], Document)
        assert results[0].title == "Test Paper on Databases"
        assert results[0].url == "https://example.com/paper.pdf"
        assert results[0].content_type == "pdf"
        assert results[0].source_provider == "crossref"
        assert results[0].metadata["year"] == 2023
        assert results[0].metadata["authors"] == "John Doe, Jane Smith"
        assert results[0].metadata["venue"] == "Test Journal"
        assert results[0].metadata["doi"] == "10.1234/test.doi"

    @patch('providers.crossref.requests.Session')
    def test_search_with_unpaywall_fallback(self, mock_session_class):
        """Test Unpaywall fallback when no direct PDF link"""
        # Mock Crossref response (no direct PDF)
        crossref_response = Mock()
        crossref_response.status_code = 200
        crossref_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Test Paper"],
                        "DOI": "10.1234/test.doi",
                        "issued": {"date-parts": [[2023]]},
                        "link": []  # No PDF link
                    }
                ]
            }
        }

        # Mock Unpaywall response
        unpaywall_response = Mock()
        unpaywall_response.status_code = 200
        unpaywall_response.json.return_value = {
            "best_oa_location": {
                "url_for_pdf": "https://unpaywall.org/paper.pdf"
            }
        }

        mock_session = MagicMock()
        mock_session.get.side_effect = [crossref_response, unpaywall_response]
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should have 2 API calls: Crossref + Unpaywall
        assert mock_session.get.call_count == 2
        assert len(results) == 1
        assert results[0].url == "https://unpaywall.org/paper.pdf"

    @patch('providers.crossref.requests.Session')
    def test_resolve_via_unpaywall_success(self, mock_session_class):
        """Test Unpaywall PDF resolution"""
        unpaywall_response = Mock()
        unpaywall_response.status_code = 200
        unpaywall_response.json.return_value = {
            "best_oa_location": {
                "url_for_pdf": "https://example.com/oa-paper.pdf"
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = unpaywall_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        pdf_url = provider._resolve_via_unpaywall("10.1234/test.doi")

        assert pdf_url == "https://example.com/oa-paper.pdf"

        # Verify Unpaywall call
        call_args = mock_session.get.call_args
        assert "10.1234" in call_args[0][0]  # DOI in URL
        assert "email" in call_args[1]["params"]

    @patch('providers.crossref.requests.Session')
    def test_resolve_via_unpaywall_fallback_to_url(self, mock_session_class):
        """Test Unpaywall fallback to 'url' field when 'url_for_pdf' missing"""
        unpaywall_response = Mock()
        unpaywall_response.status_code = 200
        unpaywall_response.json.return_value = {
            "best_oa_location": {
                "url": "https://example.com/landing-page.html"
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = unpaywall_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        pdf_url = provider._resolve_via_unpaywall("10.1234/test.doi")

        assert pdf_url == "https://example.com/landing-page.html"

    @patch('providers.crossref.requests.Session')
    def test_resolve_via_unpaywall_returns_none_on_error(self, mock_session_class):
        """Test Unpaywall returns None on HTTP error"""
        unpaywall_response = Mock()
        unpaywall_response.status_code = 404
        unpaywall_response.raise_for_status.side_effect = Exception("HTTP 404")

        mock_session = MagicMock()
        mock_session.get.return_value = unpaywall_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        pdf_url = provider._resolve_via_unpaywall("10.1234/nonexistent")

        assert pdf_url is None

    @patch('providers.crossref.requests.Session')
    def test_resolve_via_unpaywall_handles_empty_doi(self, mock_session_class):
        """Test Unpaywall handles empty DOI gracefully"""
        provider = CrossrefProvider()

        pdf_url = provider._resolve_via_unpaywall("")
        assert pdf_url is None

        pdf_url = provider._resolve_via_unpaywall(None)
        assert pdf_url is None

    @patch('providers.crossref.requests.Session')
    @patch('providers.crossref.CONTACT_EMAIL', 'test@example.com')
    def test_search_includes_polite_headers(self, mock_session_class):
        """Test that polite crawling headers are included"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"items": []}}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        provider.search("test query")

        # Verify User-Agent header
        call_args = mock_session.get.call_args
        assert "User-Agent" in call_args[1]["headers"]
        assert "OrionHarvester" in call_args[1]["headers"]["User-Agent"]
        assert "test@example.com" in call_args[1]["headers"]["User-Agent"]

    @patch('providers.crossref.requests.Session')
    def test_search_filters_papers_without_pdf(self, mock_session_class):
        """Test that papers without PDF URLs are filtered out"""
        crossref_response = Mock()
        crossref_response.status_code = 200
        crossref_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Paper With PDF"],
                        "DOI": "10.1234/with-pdf",
                        "link": [
                            {"URL": "https://example.com/paper.pdf", "content-type": "application/pdf"}
                        ]
                    },
                    {
                        "title": ["Paper Without PDF"],
                        "DOI": "10.1234/no-pdf",
                        "link": []
                    }
                ]
            }
        }

        # Mock Unpaywall failure for second paper
        unpaywall_response = Mock()
        unpaywall_response.status_code = 404
        unpaywall_response.raise_for_status.side_effect = Exception("Not found")

        mock_session = MagicMock()
        mock_session.get.side_effect = [crossref_response, unpaywall_response]
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Only paper with PDF should be included
        assert len(results) == 1
        assert results[0].title == "Paper With PDF"

    @patch('providers.crossref.requests.Session')
    def test_search_extracts_year_from_date_parts(self, mock_session_class):
        """Test year extraction from nested date-parts"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Paper 1"],
                        "issued": {"date-parts": [[2023, 6, 15]]},
                        "link": [{"URL": "https://example.com/p1.pdf", "content-type": "application/pdf"}]
                    },
                    {
                        "title": ["Paper 2"],
                        "issued": {"date-parts": [[2024]]},
                        "link": [{"URL": "https://example.com/p2.pdf", "content-type": "application/pdf"}]
                    },
                    {
                        "title": ["Paper 3"],
                        "issued": {"date-parts": []},
                        "link": [{"URL": "https://example.com/p3.pdf", "content-type": "application/pdf"}]
                    }
                ]
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 3
        assert results[0].metadata["year"] == 2023
        assert results[1].metadata["year"] == 2024
        assert results[2].metadata["year"] == "unknown"

    @patch('providers.crossref.requests.Session')
    def test_search_concatenates_author_names(self, mock_session_class):
        """Test author name concatenation (given + family)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Test Paper"],
                        "author": [
                            {"given": "John", "family": "Doe"},
                            {"given": "Jane", "family": "Smith"},
                            {"family": "OnlyFamily"},  # Missing given
                            {"given": "OnlyGiven"},  # Missing family
                            {"given": "Fourth", "family": "Author"}  # Should be excluded (limit 3)
                        ],
                        "link": [{"URL": "https://example.com/paper.pdf", "content-type": "application/pdf"}]
                    }
                ]
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        # Should include first 3, handling partial names
        authors = results[0].metadata["authors"]
        assert "John Doe" in authors
        assert "Jane Smith" in authors
        assert "OnlyFamily" in authors
        assert "Fourth Author" not in authors  # 4th author excluded

    @patch('providers.crossref.requests.Session')
    def test_search_handles_missing_authors(self, mock_session_class):
        """Test handling of missing author data"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Test Paper"],
                        "author": [],
                        "link": [{"URL": "https://example.com/paper.pdf", "content-type": "application/pdf"}]
                    }
                ]
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["authors"] == "Unknown"

    @patch('providers.crossref.requests.Session')
    def test_search_extracts_venue_from_container_title(self, mock_session_class):
        """Test venue extraction from container-title"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Paper 1"],
                        "container-title": ["Journal of Testing"],
                        "link": [{"URL": "https://example.com/p1.pdf", "content-type": "application/pdf"}]
                    },
                    {
                        "title": ["Paper 2"],
                        "container-title": ["Journal A", "Journal B"],  # Multiple (use first)
                        "link": [{"URL": "https://example.com/p2.pdf", "content-type": "application/pdf"}]
                    },
                    {
                        "title": ["Paper 3"],
                        "container-title": [],  # Empty
                        "link": [{"URL": "https://example.com/p3.pdf", "content-type": "application/pdf"}]
                    }
                ]
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 3
        assert results[0].metadata["venue"] == "Journal of Testing"
        assert results[1].metadata["venue"] == "Journal A"
        assert results[2].metadata["venue"] == ""

    @patch('providers.crossref.requests.Session')
    def test_search_handles_missing_title(self, mock_session_class):
        """Test handling of missing or empty title"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": [],  # Empty title list
                        "link": [{"URL": "https://example.com/paper.pdf", "content-type": "application/pdf"}]
                    }
                ]
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].title == ""

    @patch('providers.crossref.requests.Session')
    def test_search_http_error(self, mock_session_class):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.crossref.requests.Session')
    def test_search_respects_max_results(self, mock_session_class):
        """Test that max_results parameter is respected"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"items": []}}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        provider.search("test query", max_results=50)

        # Verify rows parameter
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["rows"] == 50

    @patch('providers.crossref.requests.Session')
    def test_search_caps_max_results_at_1000(self, mock_session_class):
        """Test that max_results is capped at 1000"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"items": []}}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        provider.search("test query", max_results=5000)

        # Verify max_results is capped at 1000
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["rows"] == 1000

    @patch('providers.crossref.requests.Session')
    def test_metadata_structure(self, mock_session_class):
        """Test that document metadata has expected structure"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Test Paper"],
                        "DOI": "10.1234/test",
                        "author": [{"given": "John", "family": "Doe"}],
                        "issued": {"date-parts": [[2023]]},
                        "container-title": ["Test Journal"],
                        "link": [{"URL": "https://example.com/paper.pdf", "content-type": "application/pdf"}]
                    }
                ]
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = CrossrefProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        metadata = results[0].metadata

        # Verify all expected metadata fields exist
        assert "year" in metadata
        assert "authors" in metadata
        assert "venue" in metadata
        assert "doi" in metadata
        assert "citation_count" in metadata
        assert "source" in metadata

        # Verify default/expected values
        assert metadata["citation_count"] == 0
        assert metadata["source"] == "crossref"
        assert metadata["doi"] == "10.1234/test"
