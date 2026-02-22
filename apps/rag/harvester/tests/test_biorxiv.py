"""Unit tests for bioRxiv provider.

Tests cover:
- Provider initialization
- Date range URL construction
- Client-side query filtering
- PDF URL construction from DOI
- Year extraction from date
- Max results limiting
- Error handling
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from providers.biorxiv import BiorxivProvider
from providers.base import Document


class TestBiorxivProvider:
    """Test suite for BiorxivProvider"""

    def test_initialization(self):
        """Test provider initialization"""
        provider = BiorxivProvider()

        assert provider.get_provider_name() == "biorxiv"
        assert provider.get_provider_type() == "academic"
        assert provider.rate_limit == 1.0
        assert hasattr(provider, 'session')

    def test_initialization_with_custom_rate_limit(self):
        """Test provider initialization with custom rate limit"""
        provider = BiorxivProvider(rate_limit=2.0)

        assert provider.rate_limit == 2.0

    def test_create_session_with_retry(self):
        """Test that session is created with retry logic"""
        provider = BiorxivProvider()
        session = provider.session

        assert session is not None
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('providers.biorxiv.requests.Session')
    @patch('providers.biorxiv.datetime')
    def test_search_constructs_date_range_url(self, mock_datetime, mock_session_class):
        """Test that URL includes date range (last 5 years)"""
        # Mock current date
        mock_now = datetime(2025, 1, 15)
        mock_datetime.now.return_value = mock_now

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"collection": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        provider.search("test query")

        # Verify URL construction
        call_args = mock_session.get.call_args
        url = call_args[0][0]

        # Should include start date (5 years ago) and end date (now)
        expected_end = "2025-01-15"
        expected_start = "2020-01-15"  # ~5 years ago (1825 days)
        assert expected_start in url
        assert expected_end in url

    @patch('providers.biorxiv.requests.Session')
    def test_search_filters_by_query_terms(self, mock_session_class):
        """Test client-side filtering by query terms"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "CRISPR Gene Editing in Plants",
                    "abstract": "This study explores CRISPR applications.",
                    "doi": "10.1101/2023.01.001",
                    "date": "2023-01-15",
                    "authors": "Smith et al."
                },
                {
                    "title": "Neural Network Architecture",
                    "abstract": "Deep learning study.",
                    "doi": "10.1101/2023.02.002",
                    "date": "2023-02-20",
                    "authors": "Doe et al."
                },
                {
                    "title": "CRISPR Applications in Medicine",
                    "abstract": "Medical applications of gene editing.",
                    "doi": "10.1101/2023.03.003",
                    "date": "2023-03-10",
                    "authors": "Johnson et al."
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("CRISPR")

        # Should only return papers matching "CRISPR"
        assert len(results) == 2
        assert "CRISPR" in results[0].title or "CRISPR" in results[0].metadata["abstract"]
        assert "CRISPR" in results[1].title or "CRISPR" in results[1].metadata["abstract"]

    @patch('providers.biorxiv.requests.Session')
    def test_search_case_insensitive_filtering(self, mock_session_class):
        """Test that query filtering is case-insensitive"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "Study on crispr gene editing",  # lowercase
                    "abstract": "CRISPR applications.",  # uppercase
                    "doi": "10.1101/2023.01.001",
                    "date": "2023-01-15",
                    "authors": "Test Author"
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session

        # Query with different case
        results = provider.search("CRISPR")
        assert len(results) == 1

        results = provider.search("crispr")
        assert len(results) == 1

    @patch('providers.biorxiv.requests.Session')
    def test_search_constructs_pdf_url_from_doi(self, mock_session_class):
        """Test PDF URL construction from DOI"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "Test Paper",
                    "abstract": "Test abstract",
                    "doi": "10.1101/2023.01.15.123456",
                    "date": "2023-01-15",
                    "authors": "Test Author"
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("test")

        assert len(results) == 1
        expected_url = "https://www.biorxiv.org/content/10.1101/2023.01.15.123456v1.full.pdf"
        assert results[0].url == expected_url

    @patch('providers.biorxiv.requests.Session')
    def test_search_filters_papers_without_doi(self, mock_session_class):
        """Test that papers without DOI are filtered out"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "Paper With DOI",
                    "abstract": "test content",
                    "doi": "10.1101/2023.01.001",
                    "date": "2023-01-15",
                    "authors": "Test Author"
                },
                {
                    "title": "Paper Without DOI",
                    "abstract": "test content",
                    "doi": "",  # Empty DOI
                    "date": "2023-02-20",
                    "authors": "Test Author"
                },
                {
                    "title": "Paper Missing DOI",
                    "abstract": "test content",
                    # DOI field missing
                    "date": "2023-03-10",
                    "authors": "Test Author"
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("test")

        # Only paper with DOI should be included
        assert len(results) == 1
        assert results[0].title == "Paper With DOI"

    @patch('providers.biorxiv.requests.Session')
    def test_search_extracts_year_from_date(self, mock_session_class):
        """Test year extraction from date field (YYYY-MM-DD format)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "Paper 1",
                    "abstract": "test",
                    "doi": "10.1101/2023.01.001",
                    "date": "2023-05-15",
                    "authors": "Author"
                },
                {
                    "title": "Paper 2",
                    "abstract": "test",
                    "doi": "10.1101/2024.02.002",
                    "date": "2024",  # Year only
                    "authors": "Author"
                },
                {
                    "title": "Paper 3",
                    "abstract": "test",
                    "doi": "10.1101/2025.03.003",
                    "date": "",  # Empty date
                    "authors": "Author"
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("test")

        assert len(results) == 3
        assert results[0].metadata["year"] == "2023"
        assert results[1].metadata["year"] == "2024"
        assert results[2].metadata["year"] == "unknown"

    @patch('providers.biorxiv.requests.Session')
    def test_search_respects_max_results(self, mock_session_class):
        """Test that max_results parameter limits returned documents"""
        # Create 10 matching papers
        collection = []
        for i in range(10):
            collection.append({
                "title": f"Paper {i} about biology",
                "abstract": "Biology research",
                "doi": f"10.1101/2023.01.{i:03d}",
                "date": "2023-01-15",
                "authors": "Test Author"
            })

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"collection": collection}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("biology", max_results=5)

        # Should return only 5 results
        assert len(results) == 5

    @patch('providers.biorxiv.requests.Session')
    def test_search_filters_then_limits(self, mock_session_class):
        """Test that filtering happens before limiting results"""
        # Mix of matching and non-matching papers
        collection = []
        for i in range(5):
            collection.append({
                "title": f"CRISPR Paper {i}",
                "abstract": "CRISPR study",
                "doi": f"10.1101/2023.01.{i:03d}",
                "date": "2023-01-15",
                "authors": "Test Author"
            })
        for i in range(5, 10):
            collection.append({
                "title": f"Unrelated Paper {i}",
                "abstract": "Different topic",
                "doi": f"10.1101/2023.02.{i:03d}",
                "date": "2023-02-20",
                "authors": "Test Author"
            })

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"collection": collection}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("CRISPR", max_results=3)

        # Should return 3 CRISPR papers (filtered), not first 3 papers
        assert len(results) == 3
        for result in results:
            assert "CRISPR" in result.title

    @patch('providers.biorxiv.requests.Session')
    def test_search_http_error(self, mock_session_class):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.biorxiv.requests.Session')
    def test_search_empty_collection(self, mock_session_class):
        """Test handling of empty collection"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"collection": []}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert results == []

    @patch('providers.biorxiv.requests.Session')
    def test_search_multi_word_query(self, mock_session_class):
        """Test filtering with multi-word queries (OR logic)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "CRISPR Gene Editing",
                    "abstract": "Study on gene editing",
                    "doi": "10.1101/2023.01.001",
                    "date": "2023-01-15",
                    "authors": "Author"
                },
                {
                    "title": "Machine Learning Applications",
                    "abstract": "ML study",
                    "doi": "10.1101/2023.02.002",
                    "date": "2023-02-20",
                    "authors": "Author"
                },
                {
                    "title": "Protein Folding",
                    "abstract": "Unrelated",
                    "doi": "10.1101/2023.03.003",
                    "date": "2023-03-10",
                    "authors": "Author"
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session

        # Multi-word query uses OR logic (any term matches)
        results = provider.search("CRISPR machine")

        assert len(results) == 2  # Papers with CRISPR or machine

    @patch('providers.biorxiv.requests.Session')
    def test_metadata_structure(self, mock_session_class):
        """Test that document metadata has expected structure"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "Test Paper",
                    "abstract": "Test abstract",
                    "doi": "10.1101/2023.01.001",
                    "date": "2023-01-15",
                    "authors": "John Doe, Jane Smith"
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = BiorxivProvider()
        provider.session = mock_session
        results = provider.search("test")

        assert len(results) == 1
        metadata = results[0].metadata

        # Verify all expected metadata fields exist
        assert "year" in metadata
        assert "authors" in metadata
        assert "venue" in metadata
        assert "abstract" in metadata
        assert "doi" in metadata
        assert "citation_count" in metadata
        assert "source" in metadata

        # Verify default/expected values
        assert metadata["venue"] == "bioRxiv"
        assert metadata["citation_count"] == 0
        assert metadata["source"] == "biorxiv"
        assert metadata["authors"] == "John Doe, Jane Smith"
