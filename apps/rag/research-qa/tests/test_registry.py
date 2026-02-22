"""Unit tests for IngestionRegistry (SQLite document tracking).

Tests cover:
- Database initialization and schema creation
- File processing checks (is_processed)
- Content hashing (compute_file_hash)
- Duplicate detection (is_duplicate_content)
- Document registration (insert and update)
- Document retrieval (get_document)
- Statistics aggregation (get_statistics)
- Rejected document filtering
- Registry clearing (destructive operation)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
import sqlite3
from pathlib import Path

from registry import IngestionRegistry, DocumentRecord


class TestIngestionRegistry:
    """Test suite for IngestionRegistry"""

    def test_initialization_creates_database(self, tmp_path):
        """Test that database file is created on initialization"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        assert db_path.exists()
        assert db_path.is_file()

    def test_initialization_creates_tables(self, tmp_path):
        """Test that required tables are created"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
            )
            assert cursor.fetchone() is not None

    def test_initialization_creates_indexes(self, tmp_path):
        """Test that indexes are created for performance"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
            indexes = [row[0] for row in cursor.fetchall()]

            assert 'idx_file_path' in indexes
            assert 'idx_content_hash' in indexes
            assert 'idx_document_type' in indexes
            assert 'idx_collection' in indexes

    def test_is_processed_returns_false_for_new_file(self, tmp_path):
        """Test that is_processed returns False for unprocessed files"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        test_file = Path("/fake/path/document.pdf")
        assert registry.is_processed(test_file) is False

    def test_is_processed_returns_true_after_registration(self, tmp_path):
        """Test that is_processed returns True after document registration"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        test_file = Path("/fake/path/document.pdf")

        # Register document
        registry.register_document(
            file_path=test_file,
            content_hash="abc123",
            document_type="academic",
            collection_name="test_collection",
            title="Test Document",
            chunk_count=10
        )

        # Should now be processed
        assert registry.is_processed(test_file) is True

    def test_compute_file_hash(self, tmp_path):
        """Test SHA256 hash computation"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Compute hash
        file_hash = registry.compute_file_hash(test_file)

        # Verify it's SHA256 (64 hex characters)
        assert len(file_hash) == 64
        assert all(c in '0123456789abcdef' for c in file_hash)

        # Verify consistency (same file = same hash)
        file_hash2 = registry.compute_file_hash(test_file)
        assert file_hash == file_hash2

    def test_compute_file_hash_differs_for_different_content(self, tmp_path):
        """Test that different content produces different hashes"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        file1 = tmp_path / "file1.txt"
        file1.write_text("Content 1")

        file2 = tmp_path / "file2.txt"
        file2.write_text("Content 2")

        hash1 = registry.compute_file_hash(file1)
        hash2 = registry.compute_file_hash(file2)

        assert hash1 != hash2

    def test_is_duplicate_content_returns_false_for_new_hash(self, tmp_path):
        """Test duplicate detection for new content"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        is_dup = registry.is_duplicate_content("newhash123", "test_collection")
        assert is_dup is False

    def test_is_duplicate_content_returns_true_for_existing_hash(self, tmp_path):
        """Test duplicate detection for existing content"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        # Register document
        registry.register_document(
            file_path=Path("/fake/doc.pdf"),
            content_hash="duplicate_hash",
            document_type="academic",
            collection_name="test_collection",
            title="Document",
            chunk_count=5
        )

        # Check for duplicate in same collection
        is_dup = registry.is_duplicate_content("duplicate_hash", "test_collection")
        assert is_dup is True

    def test_is_duplicate_content_scoped_to_collection(self, tmp_path):
        """Test that duplicate detection is scoped to collection"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        # Register in collection A
        registry.register_document(
            file_path=Path("/fake/doc.pdf"),
            content_hash="same_hash",
            document_type="academic",
            collection_name="collection_a",
            title="Document",
            chunk_count=5
        )

        # Same hash in collection B should NOT be duplicate
        is_dup = registry.is_duplicate_content("same_hash", "collection_b")
        assert is_dup is False

        # Same hash in collection A should be duplicate
        is_dup = registry.is_duplicate_content("same_hash", "collection_a")
        assert is_dup is True

    def test_register_document_inserts_new_record(self, tmp_path):
        """Test document registration creates new record"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        test_file = Path("/fake/path/paper.pdf")

        registry.register_document(
            file_path=test_file,
            content_hash="hash123",
            document_type="academic",
            collection_name="research",
            title="Research Paper",
            chunk_count=15,
            status="ingested",
            metadata={"author": "John Doe"}
        )

        # Verify inserted
        assert registry.is_processed(test_file) is True

        # Verify retrieval
        doc = registry.get_document(test_file)
        assert doc is not None
        assert doc.title == "Research Paper"
        assert doc.chunk_count == 15
        assert doc.metadata["author"] == "John Doe"

    def test_register_document_updates_existing_record(self, tmp_path):
        """Test that re-registering updates the record"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        test_file = Path("/fake/path/doc.pdf")

        # Initial registration
        registry.register_document(
            file_path=test_file,
            content_hash="hash1",
            document_type="academic",
            collection_name="test",
            title="Version 1",
            chunk_count=10
        )

        # Re-register with different data
        registry.register_document(
            file_path=test_file,
            content_hash="hash2",
            document_type="academic",
            collection_name="test",
            title="Version 2",
            chunk_count=20,
            status="ingested",
            error_message="No error"
        )

        # Should update, not create duplicate
        doc = registry.get_document(test_file)
        assert doc.chunk_count == 20
        assert doc.status == "ingested"
        assert doc.error_message == "No error"

    def test_register_document_with_error_status(self, tmp_path):
        """Test registering failed document with error message"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        test_file = Path("/fake/path/failed.pdf")

        registry.register_document(
            file_path=test_file,
            content_hash="hash_error",
            document_type="academic",
            collection_name="test",
            title="Failed Document",
            chunk_count=0,
            status="error",
            error_message="PDF parsing failed"
        )

        doc = registry.get_document(test_file)
        assert doc.status == "error"
        assert doc.error_message == "PDF parsing failed"
        assert doc.chunk_count == 0

    def test_get_document_returns_none_for_missing_file(self, tmp_path):
        """Test that get_document returns None for non-existent file"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        doc = registry.get_document(Path("/nonexistent/file.pdf"))
        assert doc is None

    def test_get_document_returns_complete_record(self, tmp_path):
        """Test that get_document returns all fields"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        test_file = Path("/fake/complete.pdf")

        registry.register_document(
            file_path=test_file,
            content_hash="complete_hash",
            document_type="manuals",
            collection_name="technical_docs",
            title="Complete Document",
            chunk_count=25,
            status="ingested",
            metadata={"year": 2024, "pages": 150}
        )

        doc = registry.get_document(test_file)

        assert isinstance(doc, DocumentRecord)
        assert doc.file_path == str(test_file)
        assert doc.content_hash == "complete_hash"
        assert doc.document_type == "manuals"
        assert doc.collection_name == "technical_docs"
        assert doc.title == "Complete Document"
        assert doc.chunk_count == 25
        assert doc.status == "ingested"
        assert doc.first_processed is not None
        assert doc.last_processed is not None
        assert doc.metadata["year"] == 2024
        assert doc.metadata["pages"] == 150

    def test_get_statistics_empty_database(self, tmp_path):
        """Test statistics on empty database"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        stats = registry.get_statistics()

        assert stats['total_documents'] == 0
        assert stats['total_chunks'] == 0
        assert stats['by_document_type'] == {}
        assert stats['by_collection'] == {}
        assert stats['by_status'] == {}

    def test_get_statistics_with_documents(self, tmp_path):
        """Test statistics aggregation"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        # Register multiple documents
        registry.register_document(
            file_path=Path("/doc1.pdf"),
            content_hash="hash1",
            document_type="academic",
            collection_name="research",
            title="Paper 1",
            chunk_count=10
        )

        registry.register_document(
            file_path=Path("/doc2.pdf"),
            content_hash="hash2",
            document_type="academic",
            collection_name="research",
            title="Paper 2",
            chunk_count=15
        )

        registry.register_document(
            file_path=Path("/manual.pdf"),
            content_hash="hash3",
            document_type="manuals",
            collection_name="technical",
            title="Manual",
            chunk_count=20,
            status="rejected"
        )

        stats = registry.get_statistics()

        assert stats['total_documents'] == 3
        assert stats['total_chunks'] == 45
        assert stats['by_document_type']['academic'] == 2
        assert stats['by_document_type']['manuals'] == 1
        assert stats['by_collection']['research'] == 2
        assert stats['by_collection']['technical'] == 1
        assert stats['by_status']['ingested'] == 2
        assert stats['by_status']['rejected'] == 1

    def test_list_rejected_documents_empty(self, tmp_path):
        """Test listing rejected documents when none exist"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        rejected = registry.list_rejected_documents()
        assert rejected == []

    def test_list_rejected_documents(self, tmp_path):
        """Test listing only rejected documents"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        # Register mix of statuses
        registry.register_document(
            file_path=Path("/good.pdf"),
            content_hash="hash1",
            document_type="academic",
            collection_name="test",
            title="Good",
            chunk_count=10,
            status="ingested"
        )

        registry.register_document(
            file_path=Path("/bad1.pdf"),
            content_hash="hash2",
            document_type="academic",
            collection_name="test",
            title="Bad 1",
            chunk_count=0,
            status="rejected",
            error_message="Low quality"
        )

        registry.register_document(
            file_path=Path("/bad2.pdf"),
            content_hash="hash3",
            document_type="academic",
            collection_name="test",
            title="Bad 2",
            chunk_count=0,
            status="rejected",
            error_message="No text"
        )

        rejected = registry.list_rejected_documents()

        assert len(rejected) == 2
        assert all(doc.status == "rejected" for doc in rejected)
        assert rejected[0].error_message in ["Low quality", "No text"]
        assert rejected[1].error_message in ["Low quality", "No text"]

    def test_clear_registry_requires_confirmation(self, tmp_path):
        """Test that clear_registry requires confirm=True"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        # Add some data
        registry.register_document(
            file_path=Path("/doc.pdf"),
            content_hash="hash",
            document_type="academic",
            collection_name="test",
            title="Document",
            chunk_count=5
        )

        # Should raise without confirm=True
        with pytest.raises(ValueError, match="Must pass confirm=True"):
            registry.clear_registry()

        # Data should still exist
        stats = registry.get_statistics()
        assert stats['total_documents'] == 1

    def test_clear_registry_deletes_all_records(self, tmp_path):
        """Test that clear_registry removes all data"""
        db_path = tmp_path / "test_registry.db"
        registry = IngestionRegistry(db_path=db_path)

        # Add multiple documents
        for i in range(5):
            registry.register_document(
                file_path=Path(f"/doc{i}.pdf"),
                content_hash=f"hash{i}",
                document_type="academic",
                collection_name="test",
                title=f"Document {i}",
                chunk_count=10
            )

        # Verify data exists
        stats = registry.get_statistics()
        assert stats['total_documents'] == 5

        # Clear with confirmation
        registry.clear_registry(confirm=True)

        # Verify all data is gone
        stats = registry.get_statistics()
        assert stats['total_documents'] == 0
        assert stats['total_chunks'] == 0
