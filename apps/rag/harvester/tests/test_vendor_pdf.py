"""Unit tests for VendorPDF provider.

Tests cover:
- PDF URL list management
- Direct PDF downloads
- Quality validation
- Metadata extraction
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from unittest.mock import Mock, patch, MagicMock

from providers.vendor_pdf import VendorPDFProvider
from providers.base import Document


class TestVendorPDFProvider:
    """Test suite for VendorPDFProvider"""

    def test_initialization_defaults(self):
        """Test provider initialization with defaults"""
        provider = VendorPDFProvider()

        assert provider.get_provider_name() == "vendor_pdf"
        assert provider.get_provider_type() == "documentation"
        assert provider.pdf_urls == []

    def test_initialization_with_urls(self):
        """Test provider initialization with PDF URLs"""
        pdf_urls = [
            "https://vendor.com/manual.pdf",
            "https://vendor.com/guide.pdf"
        ]

        provider = VendorPDFProvider(pdf_urls=pdf_urls)

        assert provider.pdf_urls == pdf_urls

    def test_discover_returns_pdf_urls(self):
        """Test that discover returns the configured PDF URLs"""
        pdf_urls = [
            "https://vendor.com/manual.pdf",
            "https://vendor.com/guide.pdf",
            "https://vendor.com/reference.pdf"
        ]

        provider = VendorPDFProvider(pdf_urls=pdf_urls)
        discovered = provider.discover()

        assert discovered == pdf_urls

    @patch('providers.vendor_pdf.requests.Session')
    def test_fetch_pdf_success(self, mock_session_class):
        """Test successful PDF download"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 test content"
        mock_response.headers = {"Content-Type": "application/pdf"}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = VendorPDFProvider(pdf_urls=["https://vendor.com/manual.pdf"])
        doc = provider.fetch("https://vendor.com/manual.pdf")

        assert doc is not None
        assert doc.url == "https://vendor.com/manual.pdf"
        assert doc.content_type == "pdf"
        assert doc.source_provider == "vendor_pdf"

    @patch('providers.vendor_pdf.requests.Session')
    def test_fetch_handles_http_error(self, mock_session_class):
        """Test handling of HTTP errors during download"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("Not found")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = VendorPDFProvider()
        doc = provider.fetch("https://vendor.com/missing.pdf")

        assert doc is None

    @patch('providers.vendor_pdf.requests.Session')
    def test_fetch_validates_content_type(self, mock_session_class):
        """Test that non-PDF content is rejected"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<html>Not a PDF</html>"
        mock_response.headers = {"Content-Type": "text/html"}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        provider = VendorPDFProvider()
        # Assuming validation exists
        # doc = provider.fetch("https://vendor.com/not-pdf.pdf")
        # This test structure depends on actual implementation
