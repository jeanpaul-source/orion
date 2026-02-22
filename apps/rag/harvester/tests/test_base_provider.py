"""
Tests for BaseProvider class and common provider functionality.

Run with: pytest tests/test_base_provider.py -v
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import Mock, patch
import time

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from providers.base import BaseProvider, Document


class TestBaseProvider:
    """Test BaseProvider abstract class functionality"""

    def test_base_provider_rate_limiting(self):
        """Rate limiting should enforce delays between requests"""
        # Create a concrete implementation for testing
        class TestProvider(BaseProvider):
            def get_provider_name(self):
                return "test"

            def get_provider_type(self):
                return "academic"

        provider = TestProvider(rate_limit=0.1)  # 100ms delay

        start = time.time()
        provider._enforce_rate_limit()
        provider._enforce_rate_limit()
        elapsed = time.time() - start

        # Should have waited at least 100ms
        assert elapsed >= 0.1, f"Rate limit not enforced: {elapsed}s < 0.1s"

    def test_base_provider_default_rate_limit(self):
        """BaseProvider should have default rate limit"""
        class TestProvider(BaseProvider):
            def get_provider_name(self):
                return "test"

            def get_provider_type(self):
                return "academic"

        provider = TestProvider()
        assert provider.rate_limit > 0, "Default rate limit should be positive"

    def test_base_provider_custom_rate_limit(self):
        """BaseProvider should accept custom rate limit"""
        class TestProvider(BaseProvider):
            def get_provider_name(self):
                return "test"

            def get_provider_type(self):
                return "academic"

        custom_limit = 2.5
        provider = TestProvider(rate_limit=custom_limit)
        assert provider.rate_limit == custom_limit


class TestDocument:
    """Test Document dataclass"""

    def test_document_creation(self):
        """Document should be created with required fields"""
        doc = Document(
            url="https://example.com/test",
            title="Test Document",
            content_type="pdf",
            source_provider="test_provider",
            raw_content=b"test content"
        )

        assert doc.url == "https://example.com/test"
        assert doc.title == "Test Document"
        assert doc.content_type == "pdf"
        assert doc.source_provider == "test_provider"
        assert doc.raw_content == b"test content"

    def test_document_with_metadata(self):
        """Document should accept metadata dict"""
        metadata = {"author": "Test Author", "year": 2024}
        doc = Document(
            url="https://example.com/test",
            title="Test",
            content_type="pdf",
            source_provider="test",
            raw_content=b"test",
            metadata=metadata
        )

        assert doc.metadata == metadata
        assert doc.metadata["author"] == "Test Author"

    def test_document_discovered_at(self):
        """Document should have discovery timestamp"""
        from datetime import datetime

        doc = Document(
            url="https://example.com/test",
            title="Test",
            content_type="pdf",
            source_provider="test",
            raw_content=b"test"
        )

        assert doc.discovered_at is not None
        assert isinstance(doc.discovered_at, datetime)
