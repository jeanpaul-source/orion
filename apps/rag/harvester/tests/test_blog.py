"""Unit tests for Blog provider.

Tests cover:
- RSS feed parsing
- Manual URL handling
- HTML to Markdown conversion
- Quality filtering
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock

from providers.blog import BlogProvider
from providers.base import Document


class TestBlogProvider:
    """Test suite for BlogProvider"""

    def test_initialization_defaults(self):
        """Test provider initialization with defaults"""
        provider = BlogProvider()

        assert provider.get_provider_name() == "blog"
        assert provider.get_provider_type() == "documentation"
        assert provider.rss_feeds == []
        assert provider.manual_urls == []

    def test_initialization_with_feeds_and_urls(self):
        """Test provider initialization with RSS feeds and manual URLs"""
        rss_feeds = ["https://blog.example.com/feed.xml"]
        manual_urls = ["https://blog.example.com/article1", "https://blog.example.com/article2"]

        provider = BlogProvider(rss_feeds=rss_feeds, manual_urls=manual_urls)

        assert provider.rss_feeds == rss_feeds
        assert provider.manual_urls == manual_urls

    @patch('providers.blog.feedparser')
    def test_discover_from_rss_feed(self, mock_feedparser):
        """Test URL discovery from RSS feed"""
        # Mock RSS feed with entries
        mock_feed = Mock()
        entry1 = Mock()
        entry1.link = "https://blog.example.com/post1"
        entry2 = Mock()
        entry2.link = "https://blog.example.com/post2"
        mock_feed.entries = [entry1, entry2]

        mock_feedparser.parse.return_value = mock_feed

        rss_feeds = ["https://blog.example.com/feed.xml"]
        provider = BlogProvider(rss_feeds=rss_feeds)
        urls = provider.discover()

        assert len(urls) == 2
        assert "https://blog.example.com/post1" in urls
        assert "https://blog.example.com/post2" in urls

    @patch('providers.blog.feedparser')
    def test_discover_combines_rss_and_manual(self, mock_feedparser):
        """Test that RSS and manual URLs are combined"""
        # Mock RSS feed
        mock_feed = Mock()
        entry1 = Mock()
        entry1.link = "https://blog.example.com/rss-post"
        mock_feed.entries = [entry1]
        mock_feedparser.parse.return_value = mock_feed

        rss_feeds = ["https://blog.example.com/feed.xml"]
        manual_urls = ["https://blog.example.com/manual-post"]

        provider = BlogProvider(rss_feeds=rss_feeds, manual_urls=manual_urls)
        urls = provider.discover()

        assert len(urls) == 2
        assert "https://blog.example.com/rss-post" in urls
        assert "https://blog.example.com/manual-post" in urls

    @patch('providers.blog.feedparser')
    def test_discover_handles_feed_error(self, mock_feedparser):
        """Test that feed parsing errors are handled gracefully"""
        mock_feedparser.parse.side_effect = Exception("Feed parse error")

        rss_feeds = ["https://blog.example.com/bad-feed.xml"]
        manual_urls = ["https://blog.example.com/manual-post"]

        provider = BlogProvider(rss_feeds=rss_feeds, manual_urls=manual_urls)
        urls = provider.discover()

        # Should still return manual URLs
        assert len(urls) == 1
        assert urls[0] == "https://blog.example.com/manual-post"

    @patch('providers.blog.requests.Session')
    @patch('providers.blog.HTMLConverter')
    def test_fetch_success(self, mock_converter_class, mock_session_class):
        """Test successful blog post fetch"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><title>Blog Post</title><body>Content</body></html>"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        mock_converter = Mock()
        mock_converter.convert.return_value = "# Blog Post\n\nContent"
        mock_converter.extract_title.return_value = "Blog Post"
        mock_converter.extract_metadata.return_value = {"author": "Test"}
        mock_converter.estimate_text_density.return_value = 0.7
        mock_converter_class.return_value = mock_converter

        provider = BlogProvider()
        doc = provider.fetch("https://blog.example.com/post")

        assert doc is not None
        assert doc.title == "Blog Post"
        assert doc.content_type == "html"
        assert doc.source_provider == "blog"
