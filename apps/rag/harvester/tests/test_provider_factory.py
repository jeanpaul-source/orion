"""
Tests for ProviderFactory.

Run with: pytest tests/test_provider_factory.py -v
"""

import sys
from pathlib import Path
import pytest

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from provider_factory import ProviderFactory


class TestProviderFactory:
    """Test ProviderFactory functionality"""

    def test_factory_initialization(self):
        """Factory should initialize without errors"""
        factory = ProviderFactory()
        assert factory is not None

    def test_get_all_academic_providers(self):
        """Should return all academic providers"""
        factory = ProviderFactory()
        academic = factory.get_all_academic()

        # Should have multiple academic providers
        assert len(academic) > 5
        assert "semantic_scholar" in academic
        assert "arxiv" in academic
        assert "openalex" in academic

    def test_get_all_documentation_providers(self):
        """Should return all documentation providers"""
        factory = ProviderFactory()
        docs = factory.get_all_documentation()

        # Should have documentation providers
        assert len(docs) > 0
        # GitHub, ReadTheDocs, etc.

    def test_create_semantic_scholar_provider(self):
        """Should create Semantic Scholar provider"""
        factory = ProviderFactory()
        provider = factory.create("semantic_scholar")

        assert provider is not None
        assert hasattr(provider, "search")
        assert provider.get_provider_name() == "semantic_scholar"
        assert provider.get_provider_type() == "academic"

    def test_create_arxiv_provider(self):
        """Should create arXiv provider"""
        factory = ProviderFactory()
        provider = factory.create("arxiv")

        assert provider is not None
        assert hasattr(provider, "search")
        assert provider.get_provider_name() == "arxiv"

    def test_create_invalid_provider(self):
        """Should raise error for invalid provider name"""
        factory = ProviderFactory()

        with pytest.raises(ValueError, match="Unknown provider"):
            factory.create("invalid_provider_name")

    def test_resolve_academic_keyword(self):
        """Should resolve 'academic' to all academic providers"""
        factory = ProviderFactory()
        names = factory.resolve_provider_names(["academic"])

        assert len(names) > 5
        assert "semantic_scholar" in names
        assert "arxiv" in names
        assert "openalex" in names

    def test_resolve_documentation_keyword(self):
        """Should resolve 'documentation' to all doc providers"""
        factory = ProviderFactory()
        names = factory.resolve_provider_names(["documentation"])

        assert len(names) > 0

    def test_resolve_all_keyword(self):
        """Should resolve 'all' to all providers"""
        factory = ProviderFactory()
        names = factory.resolve_provider_names(["all"])

        # Should include both academic and documentation
        assert len(names) > 10
        assert "semantic_scholar" in names
        assert "arxiv" in names

    def test_resolve_specific_provider_names(self):
        """Should pass through specific provider names"""
        factory = ProviderFactory()
        names = factory.resolve_provider_names(["semantic_scholar", "arxiv"])

        assert len(names) == 2
        assert "semantic_scholar" in names
        assert "arxiv" in names

    def test_resolve_mixed_keywords_and_names(self):
        """Should resolve mix of keywords and specific names"""
        factory = ProviderFactory()
        # This might include duplicates which should be removed
        names = factory.resolve_provider_names(["semantic_scholar", "academic"])

        # Should have all academic providers (no duplicates)
        assert "semantic_scholar" in names
        assert len(names) == len(set(names))  # No duplicates

    def test_list_available_providers(self):
        """Should list all available provider names"""
        factory = ProviderFactory()
        available = factory.list_available()

        assert len(available) > 10
        assert "semantic_scholar" in available
        assert "arxiv" in available
        assert "openalex" in available
