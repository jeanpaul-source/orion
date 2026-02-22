"""
Test script for multi-domain architecture.

Verifies:
- Registry operations
- Domain configuration
- Collection routing logic
- Quality gate differences per domain

Run: python tests/test_multi_domain.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from registry import IngestionRegistry, DocumentRecord
from domains import (
    get_domain_config,
    infer_document_type,
    get_collection_for_type,
    list_enabled_domains,
    get_domain_statistics
)
import tempfile


def test_registry():
    """Test registry operations"""
    print("Testing Registry...")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
        registry = IngestionRegistry(Path(tf.name))
        
        # Register a document
        registry.register_document(
            file_path=Path("/test/doc1.pdf"),
            content_hash="abc123",
            document_type="academic",
            collection_name="research-papers",
            title="Test Paper",
            chunk_count=10,
            status="ingested",
            metadata={"pages": 15}
        )
        
        # Test retrieval
        doc = registry.get_document(Path("/test/doc1.pdf"))
        assert doc is not None
        assert doc.title == "Test Paper"
        assert doc.chunk_count == 10
        
        # Test is_processed
        assert registry.is_processed(Path("/test/doc1.pdf"))
        assert not registry.is_processed(Path("/test/doc2.pdf"))
        
        # Test duplicate content
        assert registry.is_duplicate_content("abc123", "research-papers")
        assert not registry.is_duplicate_content("xyz789", "research-papers")
        
        # Test statistics
        stats = registry.get_statistics()
        assert stats['total_documents'] == 1
        assert stats['by_document_type']['academic'] == 1
        
        print("  ✓ Registry operations working")


def test_domain_config():
    """Test domain configuration"""
    print("\nTesting Domain Configuration...")
    
    # Test get_domain_config
    academic = get_domain_config('academic')
    assert academic is not None
    assert academic.collection_name == 'research-papers'
    assert academic.quality_gates.min_text_density == 0.55
    assert academic.quality_gates.require_citations == True
    
    manuals = get_domain_config('manuals')
    assert manuals is not None
    assert manuals.collection_name == 'technical-docs'
    assert manuals.quality_gates.min_text_density == 0.35
    assert manuals.quality_gates.require_citations == False
    
    github = get_domain_config('github')
    assert github is not None
    assert github.quality_gates.min_text_density == 0.20  # Lower for markdown
    
    print("  ✓ Domain configs correct")
    
    # Test infer_document_type
    assert infer_document_type(Path("/data/raw/academic/paper.pdf")) == "academic"
    assert infer_document_type(Path("/data/raw/manuals/guide.pdf")) == "manuals"
    assert infer_document_type(Path("/data/raw/blogs/post.pdf")) == "blogs"
    
    print("  ✓ Type inference working")
    
    # Test collection routing
    assert get_collection_for_type('academic') == 'research-papers'
    assert get_collection_for_type('manuals') == 'technical-docs'
    assert get_collection_for_type('blogs') == 'technical-docs'
    assert get_collection_for_type('github') == 'code-examples'
    
    print("  ✓ Collection routing correct")
    
    # Test enabled domains
    enabled = list_enabled_domains()
    assert 'academic' in enabled
    assert 'manuals' in enabled
    assert 'exports' not in enabled  # Disabled
    
    print("  ✓ Enabled domain filtering working")
    
    # Test domain statistics
    stats = get_domain_statistics()
    assert stats['total_domains'] == 5
    assert stats['enabled_domains'] == 4
    
    print("  ✓ Domain statistics correct")


def test_quality_gates():
    """Test quality gate differences"""
    print("\nTesting Quality Gates...")
    
    academic = get_domain_config('academic')
    manuals = get_domain_config('manuals')
    github = get_domain_config('github')
    
    # Academic has strictest gates
    assert academic.quality_gates.min_text_density > manuals.quality_gates.min_text_density
    assert academic.quality_gates.min_text_density > github.quality_gates.min_text_density
    
    # Academic requires citations
    assert academic.quality_gates.require_citations == True
    assert manuals.quality_gates.require_citations == False
    
    # Length requirements differ
    assert academic.quality_gates.min_length == 5000  # Longer for papers
    assert manuals.quality_gates.min_length == 1000
    assert github.quality_gates.min_length == 500  # Shortest for READMEs
    
    print("  ✓ Quality gates correctly differentiated")


def test_chunking_config():
    """Test chunking configuration"""
    print("\nTesting Chunking Configuration...")
    
    academic = get_domain_config('academic')
    github = get_domain_config('github')
    
    # Academic uses larger chunks
    assert academic.chunk_size == 512
    assert academic.chunk_overlap == 64
    
    # GitHub uses smaller chunks for code
    assert github.chunk_size == 256
    assert github.chunk_overlap == 32
    
    print("  ✓ Chunking configs correct")


def main():
    """Run all tests"""
    print("="*60)
    print("MULTI-DOMAIN ARCHITECTURE TESTS")
    print("="*60)
    
    try:
        test_registry()
        test_domain_config()
        test_quality_gates()
        test_chunking_config()
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED ✓")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
