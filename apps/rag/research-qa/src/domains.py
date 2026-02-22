"""
Multi-domain configuration for ORION document processing.

Defines quality gates, collection routing, and processing rules per document type.

ELI5: Like a rulebook that says "research papers go here with strict rules,
blog posts go there with relaxed rules" - different types get different treatment.

Created: 2025-11-10 (Phase 5-C)
Updated: 2025-11-19 (Optimized for 2025 best practices - see PRODUCTION-CONFIG-2025.md)
"""

from dataclasses import dataclass
from typing import Dict, Optional
from pathlib import Path


@dataclass
class QualityGates:
    """Quality threshold configuration for a document type."""

    min_text_density: float  # Minimum ratio of text to total content
    min_length: int  # Minimum characters
    max_length: int  # Maximum characters (reject huge files)
    require_citations: bool  # Must have citation markers ([1], et al., etc.)
    allow_tables: bool  # Tables count toward density
    allow_code_blocks: bool  # Code blocks count toward density


@dataclass
class DomainConfig:
    """Configuration for a document domain/type."""

    name: str  # 'academic', 'manuals', 'blogs', 'github', 'exports'
    display_name: str
    collection_name: str  # Target Qdrant collection
    quality_gates: QualityGates
    chunk_size: int  # Tokens per chunk
    chunk_overlap: int  # Overlap tokens
    enabled: bool  # Can disable domains


# Multi-domain configuration
DOMAINS: Dict[str, DomainConfig] = {
    "academic": DomainConfig(
        name="academic",
        display_name="Academic Research Papers",
        collection_name="research-papers",
        quality_gates=QualityGates(
            min_text_density=0.40,  # 2025 STANDARD: Lowered from 0.55 (was too strict)
            min_length=3000,  # 2025 STANDARD: Lowered from 5000 (short papers valid)
            max_length=5_000_000,
            require_citations=True,
            allow_tables=True,
            allow_code_blocks=False,
        ),
        chunk_size=1024,  # 2025 OPTIMAL: Research shows 800-1200 for academic (arXiv 2025)
        chunk_overlap=200,  # 2025 STANDARD: 20% overlap (was 12.5% - improved continuity)
        enabled=True,
    ),
    "manuals": DomainConfig(
        name="manuals",
        display_name="Technical Manuals & Documentation",
        collection_name="technical-docs",
        quality_gates=QualityGates(
            min_text_density=0.30,  # 2025 STANDARD: Lowered from 0.35 (diagrams are valid)
            min_length=800,  # 2025 STANDARD: Lowered from 1000 (short procedures valid)
            max_length=10_000_000,
            require_citations=False,
            allow_tables=True,
            allow_code_blocks=True,
        ),
        chunk_size=512,  # 2025 OPTIMAL: Research shows 300-500 for procedures (Databricks 2025)
        chunk_overlap=100,  # 2025 STANDARD: 20% overlap (improved from 12.5%)
        enabled=True,
    ),
    "blogs": DomainConfig(
        name="blogs",
        display_name="Technical Blog Posts",
        collection_name="technical-docs",  # Same collection as manuals
        quality_gates=QualityGates(
            min_text_density=0.30,  # 2025 STANDARD: Lowered from 0.35 (images are common)
            min_length=500,  # 2025 STANDARD: Lowered from 800 (quick tips are valuable)
            max_length=1_000_000,
            require_citations=False,
            allow_tables=False,
            allow_code_blocks=True,
        ),
        chunk_size=512,  # 2025 OPTIMAL: Blog posts are shorter, need tighter chunks
        chunk_overlap=100,  # 2025 STANDARD: 20% overlap (improved from 12.5%)
        enabled=True,
    ),
    "github": DomainConfig(
        name="github",
        display_name="GitHub READMEs & Documentation",
        collection_name="code-examples",
        quality_gates=QualityGates(
            min_text_density=0.15,  # 2025 STANDARD: Lowered from 0.20 (READMEs markdown-heavy)
            min_length=300,  # 2025 STANDARD: Lowered from 500 (short READMEs matter)
            max_length=500_000,
            require_citations=False,
            allow_tables=True,
            allow_code_blocks=True,
        ),
        chunk_size=512,  # 2025 OPTIMAL: Research shows 256-512 for code contexts
        chunk_overlap=100,  # 2025 STANDARD: 20% overlap (code spans multiple lines)
        enabled=True,
    ),
    "exports": DomainConfig(
        name="exports",
        display_name="Structured Data Exports",
        collection_name="structured-data",
        quality_gates=QualityGates(
            min_text_density=0.10,  # CSV/JSON heavy
            min_length=100,
            max_length=50_000_000,
            require_citations=False,
            allow_tables=True,
            allow_code_blocks=False,
        ),
        chunk_size=1024,
        chunk_overlap=128,
        enabled=False,  # Not implemented yet
    ),
}


def get_domain_config(document_type: str) -> Optional[DomainConfig]:
    """Get configuration for a document type."""
    return DOMAINS.get(document_type)


def infer_document_type(file_path: Path) -> Optional[str]:
    """
    Infer document type from file path.

    Maps topic directories to document domains:
    - PDFs in topic dirs → manuals (technical documentation)
    - HTML/MD in /github/ → github
    - Files in /academic/ → academic
    - Files in /blogs/ → blogs
    - Everything else → manuals (default)

    Args:
        file_path: Path to document file

    Returns:
        Document type ('academic', 'manuals', etc.) or None
    """
    path_str = str(file_path)

    # Check for exact domain matches first
    for domain_name in DOMAINS.keys():
        if f"/{domain_name}/" in path_str or f"\\{domain_name}\\" in path_str:
            return domain_name

    # Default: all technical topic directories map to 'manuals' domain
    # These are technical documentation from various sources
    if "/raw/" in path_str or "\\raw\\" in path_str:
        # If it's in the raw/ directory but not in a specific domain folder,
        # treat it as technical manual/documentation
        return "manuals"

    return None


def get_collection_for_type(document_type: str) -> Optional[str]:
    """Get target Qdrant collection for a document type."""
    config = get_domain_config(document_type)
    return config.collection_name if config else None


def list_enabled_domains() -> list[str]:
    """Get list of enabled domain names."""
    return [name for name, config in DOMAINS.items() if config.enabled]


def get_domain_statistics() -> Dict:
    """Get summary of domain configuration."""
    return {
        "total_domains": len(DOMAINS),
        "enabled_domains": len(list_enabled_domains()),
        "domains": {
            name: {
                "enabled": config.enabled,
                "collection": config.collection_name,
                "chunk_size": config.chunk_size,
            }
            for name, config in DOMAINS.items()
        },
    }
