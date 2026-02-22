"""
Phase 6 Integration Tests - Multi-Domain Pipeline

Tests the complete integrated pipeline with:
- Registry duplicate detection
- Document type inference from paths
- Type-specific quality gates
- Multi-collection routing
- Registry recording

Run: pytest tests/test_phase6_integration.py -v
"""

import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import hashlib

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
import numpy as np

from ingest import PDFProcessor, QdrantIngester, Document, ingest_directory
from registry import IngestionRegistry
from domains import get_domain_config


@pytest.fixture
def temp_registry():
    """Create temporary registry for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
        registry = IngestionRegistry(Path(tf.name))
        yield registry
        Path(tf.name).unlink()


@pytest.fixture
def temp_pdf_structure():
    """Create temporary directory structure with PDFs by type"""
    temp_dir = Path(tempfile.mkdtemp())
    
    # Create directory structure
    (temp_dir / "raw" / "academic").mkdir(parents=True)
    (temp_dir / "raw" / "manuals").mkdir(parents=True)
    (temp_dir / "raw" / "blogs").mkdir(parents=True)
    (temp_dir / "raw" / "github").mkdir(parents=True)
    
    # Create dummy PDF files (just empty files for path testing)
    (temp_dir / "raw" / "academic" / "paper1.pdf").touch()
    (temp_dir / "raw" / "academic" / "paper2.pdf").touch()
    (temp_dir / "raw" / "manuals" / "guide1.pdf").touch()
    (temp_dir / "raw" / "blogs" / "post1.pdf").touch()
    (temp_dir / "raw" / "github" / "readme.pdf").touch()
    
    yield temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir)


class TestDocumentTypeDetection:
    """Test document type inference from paths"""
    
    def test_academic_detection(self):
        """Test detection of academic papers"""
        path = Path("/mnt/nvme1/orion-data/documents/raw/academic/paper.pdf")
        from domains import infer_document_type
        assert infer_document_type(path) == "academic"
    
    def test_manuals_detection(self):
        """Test detection of technical manuals"""
        path = Path("/mnt/nvme1/orion-data/documents/raw/manuals/guide.pdf")
        from domains import infer_document_type
        assert infer_document_type(path) == "manuals"
    
    def test_blogs_detection(self):
        """Test detection of blog posts"""
        path = Path("/mnt/nvme1/orion-data/documents/raw/blogs/post.pdf")
        from domains import infer_document_type
        assert infer_document_type(path) == "blogs"
    
    def test_github_detection(self):
        """Test detection of GitHub docs"""
        path = Path("/mnt/nvme1/orion-data/documents/raw/github/readme.pdf")
        from domains import infer_document_type
        assert infer_document_type(path) == "github"
    
    def test_unknown_type(self):
        """Test handling of unknown types"""
        path = Path("/some/random/path/file.pdf")
        from domains import infer_document_type
        assert infer_document_type(path) is None


class TestQualityGatesByType:
    """Test that different document types have different quality gates"""
    
    def test_academic_strict_gates(self):
        """Academic papers should have strictest quality gates"""
        config = get_domain_config('academic')
        assert config.quality_gates.min_text_density == 0.55
        assert config.quality_gates.require_citations == True
        assert config.quality_gates.min_length == 5000
    
    def test_manuals_relaxed_gates(self):
        """Manuals should allow diagrams (lower density)"""
        config = get_domain_config('manuals')
        assert config.quality_gates.min_text_density == 0.35
        assert config.quality_gates.require_citations == False
        assert config.quality_gates.allow_tables == True
        assert config.quality_gates.allow_code_blocks == True
    
    def test_github_lowest_density(self):
        """GitHub docs should have lowest density (markdown-heavy)"""
        config = get_domain_config('github')
        assert config.quality_gates.min_text_density == 0.20
        assert config.quality_gates.min_length == 500
        assert config.chunk_size == 256  # Smaller chunks for code


class TestCollectionRouting:
    """Test that documents route to correct collections"""
    
    def test_academic_to_research_papers(self):
        """Academic papers should route to research-papers collection"""
        config = get_domain_config('academic')
        assert config.collection_name == 'research-papers'
    
    def test_manuals_to_technical_docs(self):
        """Manuals should route to technical-docs collection"""
        config = get_domain_config('manuals')
        assert config.collection_name == 'technical-docs'
    
    def test_blogs_to_technical_docs(self):
        """Blogs should also route to technical-docs"""
        config = get_domain_config('blogs')
        assert config.collection_name == 'technical-docs'
    
    def test_github_to_code_examples(self):
        """GitHub docs should route to code-examples collection"""
        config = get_domain_config('github')
        assert config.collection_name == 'code-examples'


class TestRegistryIntegration:
    """Test registry integration in processing pipeline"""
    
    def test_skip_already_processed(self, temp_registry, temp_pdf_structure):
        """Should skip documents already in registry"""
        pdf_path = temp_pdf_structure / "raw" / "academic" / "paper1.pdf"
        
        # Pre-register the document
        temp_registry.register_document(
            file_path=pdf_path,
            content_hash="abc123",
            document_type="academic",
            collection_name="research-papers",
            title="Already Processed",
            chunk_count=10,
            status="ingested"
        )
        
        # Try to process - should skip
        processor = PDFProcessor(registry=temp_registry)
        
        # Mock the file content for hash calculation
        with patch.object(temp_registry, 'compute_file_hash', return_value="abc123"):
            with patch.object(processor, 'extract_text', return_value=("test", {"page_count": 1})):
                doc = processor.process_pdf(pdf_path)
        
        assert doc.quality_passed == False
        assert "Already processed" in doc.rejection_reason
    
    def test_duplicate_content_detection(self, temp_registry):
        """Should detect duplicate content by hash"""
        # Register a document
        temp_registry.register_document(
            file_path=Path("/test/doc1.pdf"),
            content_hash="same_hash_123",
            document_type="academic",
            collection_name="research-papers",
            title="Original",
            chunk_count=10,
            status="ingested"
        )
        
        # Check duplicate
        assert temp_registry.is_duplicate_content("same_hash_123", "research-papers")
        assert not temp_registry.is_duplicate_content("different_hash", "research-papers")


class TestMultiCollectionStorage:
    """Test that documents are stored in correct collections"""
    
    @patch('ingest.QdrantClient')
    def test_creates_multiple_collections(self, mock_qdrant_client):
        """Should create different collections for different types"""
        mock_client = Mock()
        mock_qdrant_client.return_value = mock_client
        
        # Mock get_collections to return empty list
        mock_client.get_collections.return_value = Mock(collections=[])
        
        ingester = QdrantIngester()
        
        # Ensure different collections
        ingester.ensure_collection('research-papers')
        ingester.ensure_collection('technical-docs')
        ingester.ensure_collection('code-examples')
        
        # Should have created 3 collections
        assert mock_client.create_collection.call_count == 3
        
        collection_names = [
            call[1]['collection_name'] 
            for call in mock_client.create_collection.call_args_list
        ]
        
        assert 'research-papers' in collection_names
        assert 'technical-docs' in collection_names
        assert 'code-examples' in collection_names
    
    @patch('ingest.QdrantClient')
    def test_routes_to_correct_collection(self, mock_qdrant_client):
        """Should store documents in their designated collection"""
        mock_client = Mock()
        mock_qdrant_client.return_value = mock_client
        mock_client.get_collections.return_value = Mock(collections=[])
        
        ingester = QdrantIngester()
        
        # Create academic document
        academic_doc = Document(
            file_path=Path("/test/paper.pdf"),
            text="test",
            metadata={"title": "Test"},
            document_type="academic",
            domain_config=get_domain_config('academic'),
            content_hash="hash123",
            chunks=["chunk1", "chunk2"],
            quality_passed=True
        )
        
        embeddings = np.random.randn(2, 768)
        collection_name = ingester.store_document(academic_doc, embeddings)
        
        assert collection_name == 'research-papers'
        
        # Verify upsert was called with correct collection
        assert mock_client.upsert.called
        call_args = mock_client.upsert.call_args
        assert call_args[1]['collection_name'] == 'research-papers'


class TestEndToEndIntegration:
    """Test complete pipeline from directory to storage"""
    
    def test_multi_domain_structure(self, temp_pdf_structure):
        """Test that multi-domain directory structure is correct"""
        raw_dir = temp_pdf_structure / "raw"
        
        # Verify all domain directories exist
        assert (raw_dir / "academic").exists()
        assert (raw_dir / "manuals").exists()
        assert (raw_dir / "blogs").exists()
        assert (raw_dir / "github").exists()
        
        # Verify test PDFs exist in each domain
        assert (raw_dir / "academic" / "paper1.pdf").exists()
        assert (raw_dir / "manuals" / "guide1.pdf").exists()
        assert (raw_dir / "blogs" / "post1.pdf").exists()
        assert (raw_dir / "github" / "readme.pdf").exists()


class TestRegistryRecording:
    """Test that registry records all document results"""
    
    def test_records_ingested_documents(self, temp_registry):
        """Should record successfully ingested documents"""
        temp_registry.register_document(
            file_path=Path("/test/doc.pdf"),
            content_hash="hash123",
            document_type="academic",
            collection_name="research-papers",
            title="Test Paper",
            chunk_count=15,
            status="ingested",
            metadata={"pages": 10}
        )
        
        doc = temp_registry.get_document(Path("/test/doc.pdf"))
        assert doc.status == "ingested"
        assert doc.chunk_count == 15
    
    def test_records_rejected_documents(self, temp_registry):
        """Should record rejected documents with reason"""
        temp_registry.register_document(
            file_path=Path("/test/rejected.pdf"),
            content_hash="hash456",
            document_type="academic",
            collection_name="none",
            title="Bad PDF",
            chunk_count=0,
            status="rejected",
            error_message="Low text density: 0.20 (min 0.55 for academic)"
        )
        
        doc = temp_registry.get_document(Path("/test/rejected.pdf"))
        assert doc.status == "rejected"
        assert doc.chunk_count == 0
        assert "Low text density" in doc.error_message


class TestChunkingByDomain:
    """Test that different domains use different chunking strategies"""
    
    def test_academic_uses_512_tokens(self):
        """Academic papers should use 512 token chunks"""
        config = get_domain_config('academic')
        assert config.chunk_size == 512
        assert config.chunk_overlap == 64
    
    def test_github_uses_256_tokens(self):
        """GitHub docs should use smaller 256 token chunks"""
        config = get_domain_config('github')
        assert config.chunk_size == 256
        assert config.chunk_overlap == 32


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
