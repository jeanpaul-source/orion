"""Unit tests for arXiv provider.

Tests cover:
- Provider initialization
- Search functionality
- XML response parsing
- PDF link extraction
- Error handling
- Rate limiting
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock

from providers.arxiv import ArxivProvider
from providers.base import Document


class TestArxivProvider:
    """Test suite for ArxivProvider"""

    def test_initialization(self):
        """Test provider initialization"""
        provider = ArxivProvider()

        assert provider.get_provider_name() == "arxiv"
        assert provider.get_provider_type() == "academic"
        assert provider.rate_limit == 1.0
        assert hasattr(provider, 'session')

    def test_initialization_with_custom_rate_limit(self):
        """Test provider initialization with custom rate limit"""
        provider = ArxivProvider(rate_limit=2.0)

        assert provider.rate_limit == 2.0

    def test_create_session_with_retry(self):
        """Test that session is created with retry logic"""
        provider = ArxivProvider()
        session = provider.session

        assert session is not None
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @patch('providers.arxiv.requests.Session')
    def test_search_success(self, mock_session_class, mock_arxiv_response):
        """Test successful search with valid XML response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = mock_arxiv_response.encode('utf-8')

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("machine learning", max_results=10)

        assert len(results) == 1
        assert isinstance(results[0], Document)
        assert results[0].title == "Test Paper: Machine Learning"
        assert results[0].url == "http://arxiv.org/pdf/2401.12345v1"
        assert results[0].content_type == "pdf"
        assert results[0].source_provider == "arxiv"
        assert results[0].metadata["year"] == "2024"
        assert results[0].metadata["venue"] == "arXiv"

        # Verify API call
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert "search_query" in call_args[1]["params"]
        assert call_args[1]["params"]["search_query"] == "all:machine learning"

    @patch('providers.arxiv.requests.Session')
    def test_search_filters_entries_without_pdf(self, mock_session_class):
        """Test that entries without PDF links are filtered out"""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Paper With PDF</title>
    <summary>Abstract text</summary>
    <published>2024-01-15T00:00:00Z</published>
    <link href="http://arxiv.org/pdf/2401.12345v1" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.67890v1</id>
    <title>Paper Without PDF</title>
    <summary>Another abstract</summary>
    <published>2024-01-16T00:00:00Z</published>
    <link href="http://arxiv.org/abs/2401.67890v1" type="text/html"/>
  </entry>
</feed>"""

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = xml_response.encode('utf-8')

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Only paper with PDF link should be included
        assert len(results) == 1
        assert results[0].title == "Paper With PDF"

    @patch('providers.arxiv.requests.Session')
    def test_search_filters_entries_without_title(self, mock_session_class):
        """Test that entries without titles are filtered out"""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <summary>Abstract without title</summary>
    <published>2024-01-15T00:00:00Z</published>
    <link href="http://arxiv.org/pdf/2401.12345v1" type="application/pdf"/>
  </entry>
</feed>"""

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = xml_response.encode('utf-8')

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Entry without title should be filtered out
        assert len(results) == 0

    @patch('providers.arxiv.requests.Session')
    def test_search_extracts_year_from_published_date(self, mock_session_class):
        """Test year extraction from published date"""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Test Paper</title>
    <summary>Abstract</summary>
    <published>2023-06-15T12:30:00Z</published>
    <link href="http://arxiv.org/pdf/2401.12345v1" type="application/pdf"/>
  </entry>
</feed>"""

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = xml_response.encode('utf-8')

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["year"] == "2023"

    @patch('providers.arxiv.requests.Session')
    def test_search_handles_missing_published_date(self, mock_session_class):
        """Test handling of missing published date"""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Test Paper</title>
    <summary>Abstract</summary>
    <link href="http://arxiv.org/pdf/2401.12345v1" type="application/pdf"/>
  </entry>
</feed>"""

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = xml_response.encode('utf-8')

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["year"] == "unknown"

    @patch('providers.arxiv.requests.Session')
    def test_search_normalizes_abstract_whitespace(self, mock_session_class):
        """Test that abstract whitespace is normalized"""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Test Paper</title>
    <summary>This    is   an
    abstract  with
    multiple   spaces   and
    newlines.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <link href="http://arxiv.org/pdf/2401.12345v1" type="application/pdf"/>
  </entry>
</feed>"""

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = xml_response.encode('utf-8')

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        # Whitespace should be normalized to single spaces
        abstract = results[0].metadata["abstract"]
        assert "  " not in abstract  # No double spaces
        assert "\n" not in abstract  # No newlines

    @patch('providers.arxiv.requests.Session')
    def test_search_handles_missing_summary(self, mock_session_class):
        """Test handling of missing summary/abstract"""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Test Paper</title>
    <published>2024-01-15T00:00:00Z</published>
    <link href="http://arxiv.org/pdf/2401.12345v1" type="application/pdf"/>
  </entry>
</feed>"""

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = xml_response.encode('utf-8')

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        assert len(results) == 1
        assert results[0].metadata["abstract"] == ""

    @patch('providers.arxiv.requests.Session')
    def test_search_http_error(self, mock_session_class):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500 Error")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on error
        assert results == []

    @patch('providers.arxiv.requests.Session')
    def test_search_xml_parse_error(self, mock_session_class):
        """Test handling of invalid XML"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<invalid>xml<no_close>"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        results = provider.search("test query")

        # Should return empty list on parse error
        assert results == []

    @patch('providers.arxiv.requests.Session')
    def test_search_respects_max_results(self, mock_session_class):
        """Test that max_results parameter is respected"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        provider.search("test query", max_results=50)

        # Verify max_results is passed correctly
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["max_results"] == 50

    @patch('providers.arxiv.requests.Session')
    def test_search_uses_relevance_sorting(self, mock_session_class):
        """Test that results are sorted by relevance"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        provider.search("test query")

        # Verify sortBy parameter
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["sortBy"] == "relevance"

    @patch('providers.arxiv.requests.Session')
    def test_search_formats_query_correctly(self, mock_session_class):
        """Test that search query is formatted with 'all:' prefix"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
        provider.session = mock_session
        provider.search("vector databases")

        # Verify query formatting
        call_args = mock_session.get.call_args
        assert call_args[1]["params"]["search_query"] == "all:vector databases"

    @patch('providers.arxiv.requests.Session')
    def test_metadata_structure(self, mock_session_class, mock_arxiv_response):
        """Test that document metadata has expected structure"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = mock_arxiv_response.encode('utf-8')

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ArxivProvider()
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

        # Verify default values
        assert metadata["authors"] == "arXiv"
        assert metadata["venue"] == "arXiv"
        assert metadata["citation_count"] == 0
        assert metadata["source"] == "arxiv"
