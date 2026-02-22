"""Unit tests for DBLP provider.

Tests cover:
- Provider initialization
- Search functionality
- Nested JSON response parsing (result.hits.hit[].info)
- Author handling (dict vs list)
- DOI vs URL preference
- Error handling
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock

from providers.dblp import DBLPProvider
from providers.base import Document


class TestDBLPProvider:
    """Test suite for DBLPProvider"""

    def test_initialization(self):
        """Test provider initialization"""
        provider = DBLPProvider()

        assert provider.get_provider_name() == "dblp"
        assert provider.get_provider_type() == "academic"
        assert provider.rate_limit == 1.0
        assert hasattr(provider, 'session')

    def test_initialization_with_custom_rate_limit(self):
        """Test provider initialization with custom rate limit"""
        provider = DBLPProvider(rate_limit=2.0)

        assert provider.rate_limit == 2.0

    def test_create_session_with_retry(self):
        """Test that session is created with retry logic"""
        provider = DBLPProvider()
        session = provider.session

        assert session is not None
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('providers.dblp.requests.Session')
    def test_search_success(self, mock_session_class):
        """Test successful search with valid JSON response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Test Paper on Databases",
                                "authors": {
                                    "author": [
                                        {"text": "John Doe"},
                                        {"text": "Jane Smith"}
                                    ]
                                },
                                "year": "2023",
                                "venue": "VLDB",
                                "doi": "10.1234/test.doi",
                                "url": "https://dblp.org/rec/test"
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("databases", max_results=10)

        assert len(results) == 1
        assert isinstance(results[0], Document)
        assert results[0].title == "Test Paper on Databases"
        assert results[0].url == "10.1234/test.doi"  # DOI preferred
        assert results[0].content_type == "pdf"
        assert results[0].source_provider == "dblp"
        assert results[0].metadata["year"] == "2023"
        assert results[0].metadata["authors"] == "John Doe, Jane Smith"
        assert results[0].metadata["venue"] == "VLDB"
        assert results[0].metadata["doi"] == "10.1234/test.doi"

    @patch('providers.dblp.requests.Session')
    def test_search_prefers_doi_over_url(self, mock_session_class):
        """Test that DOI is preferred over URL for document URL"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Paper with DOI",
                                "doi": "10.1234/test.doi",
                                "url": "https://dblp.org/rec/test",
                                "year": "2023",
                                "authors": {"author": []}
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].url == "10.1234/test.doi"

    @patch('providers.dblp.requests.Session')
    def test_search_uses_url_when_no_doi(self, mock_session_class):
        """Test that URL is used when DOI is missing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Paper without DOI",
                                "doi": "",
                                "url": "https://dblp.org/rec/test",
                                "year": "2023",
                                "authors": {"author": []}
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].url == "https://dblp.org/rec/test"

    @patch('providers.dblp.requests.Session')
    def test_search_handles_authors_as_list(self, mock_session_class):
        """Test handling of authors as list"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Test Paper",
                                "authors": {
                                    "author": [
                                        {"text": "Author One"},
                                        {"text": "Author Two"},
                                        {"text": "Author Three"}
                                    ]
                                },
                                "year": "2023",
                                "doi": "10.1234/test"
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["authors"] == "Author One, Author Two, Author Three"

    @patch('providers.dblp.requests.Session')
    def test_search_handles_authors_as_single_dict(self, mock_session_class):
        """Test handling of authors as single dict (not list)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Single Author Paper",
                                "authors": {
                                    "author": {"text": "Solo Author"}
                                },
                                "year": "2023",
                                "doi": "10.1234/test"
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["authors"] == "Solo Author"

    @patch('providers.dblp.requests.Session')
    def test_search_handles_authors_as_strings(self, mock_session_class):
        """Test handling of authors as plain strings"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Test Paper",
                                "authors": {
                                    "author": [
                                        "String Author 1",
                                        {"text": "Dict Author"},
                                        "String Author 2"
                                    ]
                                },
                                "year": "2023",
                                "doi": "10.1234/test"
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        authors = results[0].metadata["authors"]
        assert "String Author 1" in authors
        assert "Dict Author" in authors
        assert "String Author 2" in authors

    @patch('providers.dblp.requests.Session')
    def test_search_handles_empty_authors(self, mock_session_class):
        """Test handling of empty authors list"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Test Paper",
                                "authors": {"author": []},
                                "year": "2023",
                                "doi": "10.1234/test"
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["authors"] == ""

    @patch('providers.dblp.requests.Session')
    def test_search_handles_missing_fields(self, mock_session_class):
        """Test handling of missing optional fields"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Minimal Paper"
                                # All other fields missing
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].title == "Minimal Paper"
        assert results[0].url == ""  # Empty DOI and URL
        assert results[0].metadata["year"] == "unknown"
        assert results[0].metadata["authors"] == ""
        assert results[0].metadata["venue"] == ""
        assert results[0].metadata["doi"] == ""

    @patch('providers.dblp.requests.Session')
    def test_search_handles_empty_result(self, mock_session_class):
        """Test handling of empty search results"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": []
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("nonexistent query")

        assert results == []

    @patch('providers.dblp.requests.Session')
    def test_search_handles_missing_hits(self, mock_session_class):
        """Test handling of malformed response (missing hits)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {}
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert results == []

    @patch('providers.dblp.requests.Session')
    def test_search_http_error(self, mock_session_class):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.dblp.requests.Session')
    def test_search_respects_max_results(self, mock_session_class):
        """Test that max_results parameter is respected"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"hits": {"hit": []}}
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        provider.search("test query", max_results=20)

        # Verify h parameter (hits)
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["h"] == 20

    @patch('providers.dblp.requests.Session')
    def test_search_caps_max_results_at_30(self, mock_session_class):
        """Test that max_results is capped at 30"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"hits": {"hit": []}}
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        provider.search("test query", max_results=100)

        # Verify max_results is capped at 30
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["h"] == 30

    @patch('providers.dblp.requests.Session')
    def test_search_uses_correct_params(self, mock_session_class):
        """Test that correct query parameters are used"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"hits": {"hit": []}}
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
        provider.session = mock_session
        provider.search("machine learning")

        # Verify parameters
        call_args = mock_session.get.call_args
        params = call_args[1]["params"]
        assert params["q"] == "machine learning"
        assert params["format"] == "json"

    @patch('providers.dblp.requests.Session')
    def test_metadata_structure(self, mock_session_class):
        """Test that document metadata has expected structure"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Test Paper",
                                "authors": {"author": [{"text": "Test Author"}]},
                                "year": "2023",
                                "venue": "Test Conference",
                                "doi": "10.1234/test",
                                "url": "https://dblp.org/rec/test"
                            }
                        }
                    ]
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = DBLPProvider()
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
        assert metadata["source"] == "dblp"
