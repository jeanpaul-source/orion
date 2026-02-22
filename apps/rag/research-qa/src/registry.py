"""
Document ingestion registry for tracking processed documents.

Prevents duplicate processing across restarts and tracks ingestion history.

ELI5: Like a library catalog that remembers every document we've processed,
so we don't waste time processing the same file twice.

Database: /mnt/nvme1/orion-data/documents/metadata/ingestion.db
Created: 2025-11-10 (Phase 5-C)
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass
import hashlib
import json


DB_PATH = Path(os.getenv("ORION_INGESTION_DB", "/mnt/nvme1/orion-data/documents/metadata/ingestion.db"))


@dataclass
class DocumentRecord:
    """Record of a processed document."""
    
    file_path: str
    content_hash: str
    document_type: str  # 'academic', 'manuals', 'blogs', 'github', 'exports'
    collection_name: str  # Target Qdrant collection
    title: str
    chunk_count: int
    status: str  # 'ingested', 'rejected', 'error'
    error_message: Optional[str]
    first_processed: str  # ISO timestamp
    last_processed: str  # ISO timestamp
    metadata: Dict


class IngestionRegistry:
    """SQLite-based registry for tracking document ingestion."""
    
    def __init__(self, db_path: Path = DB_PATH):
        """
        Initialize registry database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    content_hash TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    collection_name TEXT NOT NULL,
                    title TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'ingested',
                    error_message TEXT,
                    first_processed TIMESTAMP NOT NULL,
                    last_processed TIMESTAMP NOT NULL,
                    metadata TEXT,
                    UNIQUE(content_hash, collection_name)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_path 
                ON documents(file_path)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_hash 
                ON documents(content_hash)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_type 
                ON documents(document_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_collection 
                ON documents(collection_name)
            """)
            
            conn.commit()
    
    def is_processed(self, file_path: Path) -> bool:
        """Check if file has been processed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE file_path = ?",
                (str(file_path),)
            )
            return cursor.fetchone()[0] > 0
    
    def compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def is_duplicate_content(self, content_hash: str, collection: str) -> bool:
        """Check if content hash exists in the target collection."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT COUNT(*) FROM documents 
                   WHERE content_hash = ? AND collection_name = ?""",
                (content_hash, collection)
            )
            return cursor.fetchone()[0] > 0
    
    def register_document(
        self,
        file_path: Path,
        content_hash: str,
        document_type: str,
        collection_name: str,
        title: str,
        chunk_count: int,
        status: str = 'ingested',
        error_message: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Register a processed document.
        
        Args:
            file_path: Path to source file
            content_hash: SHA256 hash of content
            document_type: Type of document (academic, manuals, etc.)
            collection_name: Target Qdrant collection
            title: Document title
            chunk_count: Number of chunks created
            status: Processing status (ingested/rejected/error)
            error_message: Error details if status is error
            metadata: Additional metadata dict
        """
        now = datetime.now().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("""
                    INSERT INTO documents (
                        file_path, content_hash, document_type, collection_name,
                        title, chunk_count, status, error_message,
                        first_processed, last_processed, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(file_path), content_hash, document_type, collection_name,
                    title, chunk_count, status, error_message,
                    now, now, metadata_json
                ))
                conn.commit()
            except sqlite3.IntegrityError:
                # Already exists, update instead
                conn.execute("""
                    UPDATE documents 
                    SET last_processed = ?,
                        chunk_count = ?,
                        status = ?,
                        error_message = ?,
                        metadata = ?
                    WHERE file_path = ?
                """, (now, chunk_count, status, error_message, metadata_json, str(file_path)))
                conn.commit()
    
    def get_document(self, file_path: Path) -> Optional[DocumentRecord]:
        """Get document record by file path."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM documents WHERE file_path = ?",
                (str(file_path),)
            )
            row = cursor.fetchone()
            if row:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                return DocumentRecord(
                    file_path=row['file_path'],
                    content_hash=row['content_hash'],
                    document_type=row['document_type'],
                    collection_name=row['collection_name'],
                    title=row['title'],
                    chunk_count=row['chunk_count'],
                    status=row['status'],
                    error_message=row['error_message'],
                    first_processed=row['first_processed'],
                    last_processed=row['last_processed'],
                    metadata=metadata
                )
            return None
    
    def get_statistics(self) -> Dict:
        """Get registry statistics."""
        with sqlite3.connect(self.db_path) as conn:
            # Total documents
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            total = cursor.fetchone()[0]
            
            # By document type
            cursor = conn.execute("""
                SELECT document_type, COUNT(*) as count 
                FROM documents 
                GROUP BY document_type
            """)
            by_type = dict(cursor.fetchall())
            
            # By collection
            cursor = conn.execute("""
                SELECT collection_name, COUNT(*) as count 
                FROM documents 
                GROUP BY collection_name
            """)
            by_collection = dict(cursor.fetchall())
            
            # By status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count 
                FROM documents 
                GROUP BY status
            """)
            by_status = dict(cursor.fetchall())
            
            # Total chunks
            cursor = conn.execute("SELECT SUM(chunk_count) FROM documents")
            total_chunks = cursor.fetchone()[0] or 0
            
            return {
                'total_documents': total,
                'total_chunks': total_chunks,
                'by_document_type': by_type,
                'by_collection': by_collection,
                'by_status': by_status
            }
    
    def list_rejected_documents(self) -> List[DocumentRecord]:
        """Get all documents that were rejected during ingestion."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM documents WHERE status = 'rejected' ORDER BY last_processed DESC"
            )
            
            results = []
            for row in cursor.fetchall():
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                results.append(DocumentRecord(
                    file_path=row['file_path'],
                    content_hash=row['content_hash'],
                    document_type=row['document_type'],
                    collection_name=row['collection_name'],
                    title=row['title'],
                    chunk_count=row['chunk_count'],
                    status=row['status'],
                    error_message=row['error_message'],
                    first_processed=row['first_processed'],
                    last_processed=row['last_processed'],
                    metadata=metadata
                ))
            return results
    
    def clear_registry(self, confirm: bool = False):
        """
        Clear all records from registry.
        
        WARNING: This is destructive!
        
        Args:
            confirm: Must be True to actually clear
        """
        if not confirm:
            raise ValueError("Must pass confirm=True to clear registry")
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM documents")
            conn.commit()
