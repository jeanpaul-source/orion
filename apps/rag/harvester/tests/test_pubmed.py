"""Unit tests for PubMed provider.

Tests cover:
- Provider initialization
- Two-step search process (search → fetch summaries)
- PMC ID extraction
- PDF URL construction
- Error handling
- Rate limiting
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock

from providers.pubmed import PubMedProvider
from providers.base import Document


class TestPubMedProvider:
    """Test suite for PubMedProvider"""

    def test_initialization(self):
        """Test provider initialization"""
        provider = PubMedProvider()

        assert provider.get_provider_name() == "pubmed"
        assert provider.get_provider_type() == "academic"
        assert provider.rate_limit == 1.0
        assert hasattr(provider, 'session')

    def test_initialization_with_custom_rate_limit(self):
        """Test provider initialization with custom rate limit"""
        provider = PubMedProvider(rate_limit=2.0)

        assert provider.rate_limit == 2.0

    def test_create_session_with_retry(self):
        """Test that session is created with retry logic"""
        provider = PubMedProvider()
        session = provider.session

        assert session is not None
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('providers.pubmed.requests.Session')
    def test_search_success_two_step_process(self, mock_session_class):
        """Test successful two-step search: esearch → esummary"""
        # Mock Step 1: Search response
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {
                "idlist": ["12345", "67890"]
            }
        }

        # Mock Step 2: Summary response
        summary_response = Mock()
        summary_response.status_code = 200
        summary_response.json.return_value = {
            "result": {
                "12345": {
                    "title": "Test Paper on COVID-19",
                    "authors": [
                        {"name": "John Doe"},
                        {"name": "Jane Smith"}
                    ],
                    "pubdate": "2023 Jan",
                    "fulljournalname": "Journal of Testing"
                },
                "67890": {
                    "title": "Another Medical Paper",
                    "authors": [{"name": "Bob Johnson"}],
                    "pubdate": "2024 Feb",
                    "fulljournalname": "Medical Review"
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.side_effect = [search_response, summary_response]
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("COVID-19", max_results=10)

        # Verify results
        assert len(results) == 2

        # Verify first result
        assert isinstance(results[0], Document)
        assert results[0].title == "Test Paper on COVID-19"
        assert results[0].url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12345/pdf/"
        assert results[0].content_type == "pdf"
        assert results[0].source_provider == "pubmed"
        assert results[0].metadata["year"] == "2023"
        assert results[0].metadata["authors"] == "John Doe, Jane Smith"
        assert results[0].metadata["venue"] == "Journal of Testing"
        assert results[0].metadata["pmc_id"] == "12345"

        # Verify second result
        assert results[1].title == "Another Medical Paper"
        assert results[1].url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC67890/pdf/"
        assert results[1].metadata["year"] == "2024"
        assert results[1].metadata["authors"] == "Bob Johnson"

        # Verify two API calls were made
        assert mock_session.get.call_count == 2

    @patch('providers.pubmed.requests.Session')
    def test_search_step1_params(self, mock_session_class):
        """Test parameters for Step 1 (esearch)"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": []}
        }

        mock_session = MagicMock()
        mock_session.get.return_value = search_response
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        provider.search("test query", max_results=20)

        # Verify search parameters
        call_args = mock_session.get.call_args_list[0]
        params = call_args[1]["params"]

        assert params["db"] == "pmc"
        assert params["term"] == "test query"
        assert params["retmax"] == 20
        assert params["retmode"] == "json"
        assert params["sort"] == "relevance"

    @patch('providers.pubmed.requests.Session')
    def test_search_caps_max_results_at_30(self, mock_session_class):
        """Test that max_results is capped at 30"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": []}
        }

        mock_session = MagicMock()
        mock_session.get.return_value = search_response
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        provider.search("test query", max_results=100)

        # Verify max_results is capped at 30
        call_args = mock_session.get.call_args_list[0]
        assert call_args[1]["params"]["retmax"] == 30

    @patch('providers.pubmed.requests.Session')
    def test_search_returns_empty_when_no_ids(self, mock_session_class):
        """Test that empty list is returned when no PMC IDs found"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": []}
        }

        mock_session = MagicMock()
        mock_session.get.return_value = search_response
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("nonexistent query")

        # Should return empty list and not proceed to Step 2
        assert results == []
        assert mock_session.get.call_count == 1  # Only Step 1 called

    @patch('providers.pubmed.requests.Session')
    def test_search_step2_params(self, mock_session_class):
        """Test parameters for Step 2 (esummary)"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": ["111", "222", "333"]}
        }

        summary_response = Mock()
        summary_response.status_code = 200
        summary_response.json.return_value = {
            "result": {
                "111": {"title": "Paper 1", "authors": [], "pubdate": "2023", "fulljournalname": "Journal"},
                "222": {"title": "Paper 2", "authors": [], "pubdate": "2024", "fulljournalname": "Journal"},
                "333": {"title": "Paper 3", "authors": [], "pubdate": "2025", "fulljournalname": "Journal"}
            }
        }

        mock_session = MagicMock()
        mock_session.get.side_effect = [search_response, summary_response]
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        provider.search("test query")

        # Verify summary parameters (second call)
        call_args = mock_session.get.call_args_list[1]
        params = call_args[1]["params"]

        assert params["db"] == "pmc"
        assert params["id"] == "111,222,333"
        assert params["retmode"] == "json"

    @patch('providers.pubmed.requests.Session')
    def test_search_extracts_year_from_pubdate(self, mock_session_class):
        """Test year extraction from various pubdate formats"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": ["1", "2", "3"]}
        }

        summary_response = Mock()
        summary_response.status_code = 200
        summary_response.json.return_value = {
            "result": {
                "1": {"title": "Paper 1", "pubdate": "2023 Jan 15", "authors": [], "fulljournalname": ""},
                "2": {"title": "Paper 2", "pubdate": "2024", "authors": [], "fulljournalname": ""},
                "3": {"title": "Paper 3", "pubdate": "", "authors": [], "fulljournalname": ""}
            }
        }

        mock_session = MagicMock()
        mock_session.get.side_effect = [search_response, summary_response]
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 3
        assert results[0].metadata["year"] == "2023"  # First token
        assert results[1].metadata["year"] == "2024"  # Just year
        assert results[2].metadata["year"] == "unknown"  # Empty

    @patch('providers.pubmed.requests.Session')
    def test_search_constructs_pdf_url_correctly(self, mock_session_class):
        """Test PDF URL construction from PMC ID"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": ["9876543"]}
        }

        summary_response = Mock()
        summary_response.status_code = 200
        summary_response.json.return_value = {
            "result": {
                "9876543": {
                    "title": "Test Paper",
                    "authors": [],
                    "pubdate": "2023",
                    "fulljournalname": "Test Journal"
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.side_effect = [search_response, summary_response]
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9876543/pdf/"
        assert results[0].metadata["pmc_id"] == "9876543"

    @patch('providers.pubmed.requests.Session')
    def test_search_handles_non_dict_items(self, mock_session_class):
        """Test that non-dict items in result are skipped"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": ["1", "2"]}
        }

        summary_response = Mock()
        summary_response.status_code = 200
        summary_response.json.return_value = {
            "result": {
                "1": {"title": "Valid Paper", "authors": [], "pubdate": "2023", "fulljournalname": ""},
                "2": "invalid_data"  # Not a dict
            }
        }

        mock_session = MagicMock()
        mock_session.get.side_effect = [search_response, summary_response]
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Only valid paper should be included
        assert len(results) == 1
        assert results[0].title == "Valid Paper"

    @patch('providers.pubmed.requests.Session')
    def test_search_handles_missing_authors(self, mock_session_class):
        """Test handling of missing or invalid author data"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": ["1"]}
        }

        summary_response = Mock()
        summary_response.status_code = 200
        summary_response.json.return_value = {
            "result": {
                "1": {
                    "title": "Paper",
                    "authors": [
                        {"name": "John Doe"},
                        "invalid_author",  # Not a dict
                        {"name": "Jane Smith"}
                    ],
                    "pubdate": "2023",
                    "fulljournalname": ""
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.side_effect = [search_response, summary_response]
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should skip invalid author
        assert len(results) == 1
        assert results[0].metadata["authors"] == "John Doe, Jane Smith"

    @patch('providers.pubmed.requests.Session')
    def test_search_http_error_step1(self, mock_session_class):
        """Test handling of HTTP error in Step 1"""
        search_response = Mock()
        search_response.status_code = 500
        search_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.return_value = search_response
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.pubmed.requests.Session')
    def test_search_http_error_step2(self, mock_session_class):
        """Test handling of HTTP error in Step 2"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": ["123"]}
        }

        summary_response = Mock()
        summary_response.status_code = 500
        summary_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.side_effect = [search_response, summary_response]
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.pubmed.requests.Session')
    def test_metadata_structure(self, mock_session_class):
        """Test that document metadata has expected structure"""
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "esearchresult": {"idlist": ["123"]}
        }

        summary_response = Mock()
        summary_response.status_code = 200
        summary_response.json.return_value = {
            "result": {
                "123": {
                    "title": "Test Paper",
                    "authors": [{"name": "Test Author"}],
                    "pubdate": "2023 Jan",
                    "fulljournalname": "Test Journal"
                }
            }
        }

        mock_session = MagicMock()
        mock_session.get.side_effect = [search_response, summary_response]
        mock_session_class.return_value = mock_session

        provider = PubMedProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        metadata = results[0].metadata

        # Verify all expected metadata fields exist
        assert "year" in metadata
        assert "authors" in metadata
        assert "venue" in metadata
        assert "pmc_id" in metadata
        assert "citation_count" in metadata
        assert "source" in metadata

        # Verify default/expected values
        assert metadata["citation_count"] == 0
        assert metadata["source"] == "pubmed"
        assert metadata["pmc_id"] == "123"
