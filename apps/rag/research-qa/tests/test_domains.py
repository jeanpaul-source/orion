"""Unit tests for domain configuration and quality gates.

Tests cover:
- Domain configuration retrieval
- Document type inference from paths
- Collection routing
- Enabled domain filtering
- Domain statistics
- Quality gate configurations
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from pathlib import Path

from domains import (
    get_domain_config,
    infer_document_type,
    get_collection_for_type,
    list_enabled_domains,
    get_domain_statistics,
    DOMAINS,
    DomainConfig,
    QualityGates
)


class TestDomainConfiguration:
    """Test suite for domain configuration"""

    def test_get_domain_config_academic(self):
        """Test retrieving academic domain configuration"""
        config = get_domain_config("academic")

        assert config is not None
        assert config.name == "academic"
        assert config.display_name == "Academic Research Papers"
        assert config.collection_name == "research-papers"
        assert config.enabled is True

    def test_get_domain_config_manuals(self):
        """Test retrieving manuals domain configuration"""
        config = get_domain_config("manuals")

        assert config is not None
        assert config.name == "manuals"
        assert config.collection_name == "technical-docs"
        assert config.enabled is True

    def test_get_domain_config_invalid_domain(self):
        """Test that invalid domain returns None"""
        config = get_domain_config("nonexistent")
        assert config is None

    def test_academic_quality_gates(self):
        """Test academic domain has strict quality gates"""
        config = get_domain_config("academic")

        assert config.quality_gates.min_text_density == 0.55
        assert config.quality_gates.min_length == 5000
        assert config.quality_gates.require_citations is True
        assert config.quality_gates.allow_tables is True
        assert config.quality_gates.allow_code_blocks is False

    def test_manuals_quality_gates(self):
        """Test manuals domain has relaxed quality gates"""
        config = get_domain_config("manuals")

        assert config.quality_gates.min_text_density == 0.35
        assert config.quality_gates.min_length == 1000
        assert config.quality_gates.require_citations is False
        assert config.quality_gates.allow_code_blocks is True

    def test_github_quality_gates(self):
        """Test GitHub domain has lowest text density"""
        config = get_domain_config("github")

        assert config.quality_gates.min_text_density == 0.20
        assert config.quality_gates.min_length == 500
        assert config.quality_gates.allow_code_blocks is True
        assert config.chunk_size == 512  # Optimized for code

    def test_infer_document_type_academic(self):
        """Test inferring academic document type from path"""
        paths = [
            Path("/data/documents/academic/paper.pdf"),
            Path("/home/user/academic/research.pdf"),
            Path("C:\\Documents\\academic\\study.pdf")
        ]

        for path in paths:
            doc_type = infer_document_type(path)
            assert doc_type == "academic"

    def test_infer_document_type_github(self):
        """Test inferring github document type from path"""
        paths = [
            Path("/data/documents/github/README.md"),
            Path("/home/user/github/docs.md"),
            Path("C:\\Documents\\github\\guide.md")
        ]

        for path in paths:
            doc_type = infer_document_type(path)
            assert doc_type == "github"

    def test_infer_document_type_blogs(self):
        """Test inferring blogs document type from path"""
        paths = [
            Path("/data/documents/blogs/article.html"),
            Path("/home/user/blogs/post.md"),
        ]

        for path in paths:
            doc_type = infer_document_type(path)
            assert doc_type == "blogs"

    def test_infer_document_type_manuals_default(self):
        """Test that raw/ directory defaults to manuals"""
        paths = [
            Path("/data/documents/raw/kubernetes/guide.pdf"),
            Path("/data/documents/raw/docker/manual.pdf"),
        ]

        for path in paths:
            doc_type = infer_document_type(path)
            assert doc_type == "manuals"

    def test_infer_document_type_exports(self):
        """Test inferring exports document type from path"""
        paths = [
            Path("/data/documents/exports/data.csv"),
            Path("/home/user/exports/export.json"),
        ]

        for path in paths:
            doc_type = infer_document_type(path)
            assert doc_type == "exports"

    def test_infer_document_type_returns_none_for_unknown(self):
        """Test that unknown paths return None"""
        paths = [
            Path("/random/path/file.txt"),
            Path("/home/user/downloads/doc.pdf"),
        ]

        for path in paths:
            doc_type = infer_document_type(path)
            assert doc_type is None

    def test_get_collection_for_type_academic(self):
        """Test collection routing for academic"""
        collection = get_collection_for_type("academic")
        assert collection == "research-papers"

    def test_get_collection_for_type_manuals(self):
        """Test collection routing for manuals"""
        collection = get_collection_for_type("manuals")
        assert collection == "technical-docs"

    def test_get_collection_for_type_blogs_shares_with_manuals(self):
        """Test that blogs and manuals share the same collection"""
        blogs_collection = get_collection_for_type("blogs")
        manuals_collection = get_collection_for_type("manuals")

        assert blogs_collection == manuals_collection
        assert blogs_collection == "technical-docs"

    def test_get_collection_for_type_github(self):
        """Test collection routing for github"""
        collection = get_collection_for_type("github")
        assert collection == "code-examples"

    def test_get_collection_for_type_invalid_returns_none(self):
        """Test that invalid type returns None"""
        collection = get_collection_for_type("invalid")
        assert collection is None

    def test_list_enabled_domains(self):
        """Test listing enabled domains"""
        enabled = list_enabled_domains()

        assert "academic" in enabled
        assert "manuals" in enabled
        assert "blogs" in enabled
        assert "github" in enabled

        # exports is disabled by default
        assert "exports" not in enabled

    def test_list_enabled_domains_excludes_disabled(self):
        """Test that disabled domains are excluded"""
        enabled = list_enabled_domains()

        # Verify exports is disabled
        exports_config = get_domain_config("exports")
        assert exports_config.enabled is False

        # Verify it's not in enabled list
        assert "exports" not in enabled

    def test_get_domain_statistics_structure(self):
        """Test domain statistics structure"""
        stats = get_domain_statistics()

        assert "total_domains" in stats
        assert "enabled_domains" in stats
        assert "domains" in stats

        assert isinstance(stats["total_domains"], int)
        assert isinstance(stats["enabled_domains"], int)
        assert isinstance(stats["domains"], dict)

    def test_get_domain_statistics_counts(self):
        """Test domain statistics counts"""
        stats = get_domain_statistics()

        assert stats["total_domains"] == len(DOMAINS)

        # Count enabled
        enabled_count = sum(1 for config in DOMAINS.values() if config.enabled)
        assert stats["enabled_domains"] == enabled_count

    def test_get_domain_statistics_domain_details(self):
        """Test domain statistics include details for each domain"""
        stats = get_domain_statistics()

        for domain_name in DOMAINS.keys():
            assert domain_name in stats["domains"]

            domain_info = stats["domains"][domain_name]
            assert "enabled" in domain_info
            assert "collection" in domain_info
            assert "chunk_size" in domain_info

    def test_chunk_size_configurations(self):
        """Test chunk size varies by domain"""
        academic = get_domain_config("academic")
        github = get_domain_config("github")

        assert academic.chunk_size == 1024
        assert github.chunk_size == 512  # Smaller for code

    def test_chunk_overlap_configurations(self):
        """Test chunk overlap varies by domain"""
        academic = get_domain_config("academic")
        github = get_domain_config("github")

        assert academic.chunk_overlap == 128
        assert github.chunk_overlap == 64  # Smaller overlap for code

    def test_max_length_varies_by_domain(self):
        """Test max length limits vary by domain"""
        academic = get_domain_config("academic")
        manuals = get_domain_config("manuals")
        exports = get_domain_config("exports")

        assert academic.quality_gates.max_length == 5_000_000
        assert manuals.quality_gates.max_length == 10_000_000
        assert exports.quality_gates.max_length == 50_000_000
