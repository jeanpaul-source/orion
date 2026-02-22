"""
Quick test to verify provider structure works.

Run with: python -m pytest tests/test_providers_quick.py -v
"""

import sys
from pathlib import Path

# Add src/ to path (ORION pattern)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from provider_factory import ProviderFactory


def test_provider_factory_import():
    """ProviderFactory should import cleanly."""
    factory = ProviderFactory()
    assert factory is not None


def test_get_all_academic():
    """Should return 11 academic providers."""
    factory = ProviderFactory()
    academic = factory.get_all_academic()
    assert len(academic) == 11


def test_create_semantic_scholar():
    """Should create semantic_scholar provider."""
    factory = ProviderFactory()
    provider = factory.create("semantic_scholar")
    assert provider is not None
    assert hasattr(provider, "search")


def test_create_arxiv():
    """Should create arxiv provider."""
    factory = ProviderFactory()
    provider = factory.create("arxiv")
    assert provider is not None
    assert hasattr(provider, "search")


def test_resolve_academic_keyword():
    """Should resolve 'academic' keyword to 11 providers."""
    factory = ProviderFactory()
    names = factory.resolve_provider_names(["academic"])
    assert len(names) == 11
    assert "semantic_scholar" in names
    assert "arxiv" in names
