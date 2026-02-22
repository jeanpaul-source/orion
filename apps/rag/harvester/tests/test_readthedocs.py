"""Unit tests for ReadTheDocs provider.

Tests cover:
- Provider initialization
- Sitemap discovery
- Link crawling with depth limits
- Link filtering (skip anchors, PDFs, search pages)
- HTML to Markdown conversion
- Quality gates (text density)
- Rate limiting and retries
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from providers.readthedocs import ReadTheDocsProvider
from providers.base import Document


class TestReadTheDocsProvider:
    """Test suite for ReadTheDocsProvider"""

    def test_initialization(self):
        """Test provider initialization"""
        provider = ReadTheDocsProvider(base_url="https://docs.example.com")

        assert provider.get_provider_name() == "readthedocs"
        assert provider.get_provider_type() == "documentation"
        assert provider.base_url == "https://docs.example.com"
        assert provider.max_depth == 3
        assert len(provider.visited_urls) == 0

    def test_initialization_with_custom_params(self):
        """Test provider initialization with custom parameters"""
        provider = ReadTheDocsProvider(
            base_url="https://docs.example.com/",  # With trailing slash
            max_depth=5,
            rate_limit=2.0
        )

        assert provider.base_url == "https://docs.example.com"  # Trailing slash removed
        assert provider.max_depth == 5
        assert provider.rate_limit == 2.0

    @patch('providers.readthedocs.requests.Session')
    def test_is_doc_link_filters_external_links(self, mock_session_class):
        """Test that external links are filtered out"""
        provider = ReadTheDocsProvider(base_url="https://docs.example.com")

        assert provider._is_doc_link("https://docs.example.com/guide/") is True
        assert provider._is_doc_link("https://external.com/page") is False

    @patch('providers.readthedocs.requests.Session')
    def test_is_doc_link_filters_anchors(self, mock_session_class):
        """Test that anchor links are filtered out"""
        provider = ReadTheDocsProvider(base_url="https://docs.example.com")

        assert provider._is_doc_link("https://docs.example.com/page#section") is True
        # URL should be processed without the anchor

    @patch('providers.readthedocs.requests.Session')
    def test_is_doc_link_filters_skip_patterns(self, mock_session_class):
        """Test that non-doc patterns are filtered out"""
        provider = ReadTheDocsProvider(base_url="https://docs.example.com")

        assert provider._is_doc_link("https://docs.example.com/search") is False
        assert provider._is_doc_link("https://docs.example.com/genindex") is False
        assert provider._is_doc_link("https://docs.example.com/file.pdf") is False
        assert provider._is_doc_link("https://docs.example.com/file.zip") is False
        assert provider._is_doc_link("https://docs.example.com/downloads/file") is False

    @patch('providers.readthedocs.requests.Session')
    @patch('providers.readthedocs.BeautifulSoup')
    def test_discover_from_sitemap_success(self, mock_bs, mock_session_class):
        """Test successful sitemap discovery"""
        # Mock sitemap XML response
        sitemap_xml = """<?xml version="1.0"?>
        <urlset>
          <url><loc>https://docs.example.com/page1</loc></url>
          <url><loc>https://docs.example.com/page2</loc></url>
        </urlset>"""

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sitemap_xml.encode()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        # Mock BeautifulSoup parsing
        mock_soup = Mock()
        mock_loc1 = Mock()
        mock_loc1.text = "https://docs.example.com/page1"
        mock_loc2 = Mock()
        mock_loc2.text = "https://docs.example.com/page2"
        mock_soup.find_all.return_value = [mock_loc1, mock_loc2]
        mock_bs.return_value = mock_soup

        provider = ReadTheDocsProvider(base_url="https://docs.example.com")
        urls = provider._discover_from_sitemap()

        assert len(urls) == 2
        assert "https://docs.example.com/page1" in urls
        assert "https://docs.example.com/page2" in urls

    @patch('providers.readthedocs.requests.Session')
    def test_discover_from_sitemap_returns_empty_on_error(self, mock_session_class):
        """Test sitemap discovery returns empty list on error"""
        mock_response = Mock()
        mock_response.status_code = 404

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ReadTheDocsProvider(base_url="https://docs.example.com")
        urls = provider._discover_from_sitemap()

        assert urls == []

    @patch('providers.readthedocs.requests.Session')
    @patch('providers.readthedocs.BeautifulSoup')
    def test_extract_links(self, mock_bs, mock_session_class):
        """Test link extraction from page"""
        # Mock page with links
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html></html>"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        # Mock BeautifulSoup link extraction
        mock_soup = Mock()
        mock_a1 = Mock()
        mock_a1.__getitem__ = lambda self, key: "/page1" if key == "href" else None
        mock_a2 = Mock()
        mock_a2.__getitem__ = lambda self, key: "/page2" if key == "href" else None
        mock_soup.find_all.return_value = [mock_a1, mock_a2]
        mock_bs.return_value = mock_soup

        provider = ReadTheDocsProvider(base_url="https://docs.example.com")
        # Mock _is_doc_link to return True
        provider._is_doc_link = Mock(return_value=True)

        links = provider._extract_links("https://docs.example.com/index")

        assert len(links) == 2

    @patch('providers.readthedocs.requests.Session')
    @patch('providers.readthedocs.HTMLConverter')
    def test_fetch_success(self, mock_converter_class, mock_session_class):
        """Test successful document fetch and conversion"""
        # Mock HTML response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><title>Test Page</title><body>Content</body></html>"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        # Mock HTML converter
        mock_converter = Mock()
        mock_converter.convert.return_value = "# Test Page\n\nContent"
        mock_converter.extract_title.return_value = "Test Page"
        mock_converter.extract_metadata.return_value = {"description": "Test"}
        mock_converter.estimate_text_density.return_value = 0.8
        mock_converter_class.return_value = mock_converter

        provider = ReadTheDocsProvider(base_url="https://docs.example.com")
        doc = provider.fetch("https://docs.example.com/page")

        assert doc is not None
        assert isinstance(doc, Document)
        assert doc.title == "Test Page"
        assert doc.url == "https://docs.example.com/page"
        assert doc.content_type == "html"
        assert doc.source_provider == "readthedocs"

    @patch('providers.readthedocs.requests.Session')
    @patch('providers.readthedocs.HTMLConverter')
    def test_fetch_filters_low_quality_content(self, mock_converter_class, mock_session_class):
        """Test that low-quality content is filtered out"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html></html>"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        # Mock converter with low text density
        mock_converter = Mock()
        mock_converter.convert.return_value = ""
        mock_converter.extract_title.return_value = "Page"
        mock_converter.extract_metadata.return_value = {}
        mock_converter.estimate_text_density.return_value = 0.2  # Below 0.3 threshold
        mock_converter_class.return_value = mock_converter

        provider = ReadTheDocsProvider(base_url="https://docs.example.com")
        doc = provider.fetch("https://docs.example.com/low-quality")

        # Should return None for low quality
        assert doc is None

    @patch('providers.readthedocs.requests.Session')
    @patch('providers.readthedocs.HTMLConverter')
    @patch('providers.readthedocs.time')
    def test_fetch_retries_on_429(self, mock_time, mock_converter_class, mock_session_class):
        """Test retry with exponential backoff on 429 rate limit"""
        # First response: 429, second response: 200
        mock_response_429 = Mock()
        mock_response_429.status_code = 429

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.text = "<html>Content</html>"

        mock_session = MagicMock()
        mock_session.get.side_effect = [mock_response_429, mock_response_200]
        mock_session_class.return_value = mock_session

        # Mock converter
        mock_converter = Mock()
        mock_converter.convert.return_value = "Content"
        mock_converter.extract_title.return_value = "Page"
        mock_converter.extract_metadata.return_value = {}
        mock_converter.estimate_text_density.return_value = 0.8
        mock_converter_class.return_value = mock_converter

        provider = ReadTheDocsProvider(base_url="https://docs.example.com", rate_limit=1.0)
        doc = provider.fetch("https://docs.example.com/page")

        # Should succeed after retry
        assert doc is not None
        # Should have called sleep for backoff
        assert mock_time.sleep.called

    @patch('providers.readthedocs.requests.Session')
    def test_fetch_returns_none_on_http_error(self, mock_session_class):
        """Test that fetch returns None on HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = ReadTheDocsProvider(base_url="https://docs.example.com")
        doc = provider.fetch("https://docs.example.com/error")

        assert doc is None
