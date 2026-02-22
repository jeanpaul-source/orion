
# Set up logging
logger = logging.getLogger(__name__)

"""
Multi-Domain Ingestion Pipeline for ORION

Extends the base ingestion pipeline with:
- Multi-collection routing based on document type
- Persistent duplicate tracking across restarts
- Per-domain quality gates
- Registry-based processing status

Usage:
    python src/ingest_multi.py --type academic /path/to/pdfs/
    python src/ingest_multi.py --type manuals /path/to/docs/
    python src/ingest_multi.py --auto-detect /mnt/nvme1/orion-data/documents/raw/

Created: 2025-11-10 (Phase 5-C)
"""

import argparse
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from ingest import PDFProcessor, Document, QualityMetrics
from registry import IngestionRegistry
from domains import get_domain_config, infer_document_type, DOMAINS, DomainConfig
from anythingllm_client import AnythingLLMClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import hashlib
import numpy as np
from tqdm import tqdm
import logging


QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
ANYTHINGLLM_URL = os.getenv("ANYTHINGLLM_URL", "http://192.168.5.10:3001")
EMBEDDING_DIM = 768


@dataclass
class MultiDomainDocument(Document):
    """Extended document with domain routing"""
    document_type: Optional[str] = None
    target_collection: Optional[str] = None
    content_hash: Optional[str] = None


class MultiDomainProcessor(PDFProcessor):
    """Enhanced processor with domain-specific quality gates"""
    
    domain_config: DomainConfig  # Type annotation - never None after __init__
    
    def __init__(self, document_type: str):
        super().__init__()
        self.document_type = document_type
        self.domain_config = get_domain_config(document_type)  # type: ignore
        
        if not self.domain_config:
            raise ValueError(f"Invalid document type: {document_type}")
        
        if not self.domain_config.enabled:
            raise ValueError(f"Domain not enabled: {document_type}")
        
        self.registry = IngestionRegistry()
    
    def check_quality(self, text: str, page_count: int, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Apply domain-specific quality gates.
        
        Returns:
            (passed, rejection_reason) - rejection_reason is None if passed
        """
        gates = self.domain_config.quality_gates
        char_count = len(text)
        
        # Length checks
        if char_count < gates.min_length:
            return False, f"Too short: {char_count} < {gates.min_length} chars"
        
        if char_count > gates.max_length:
            return False, f"Too long: {char_count} > {gates.max_length} chars"
        
        # Text density
        avg_chars_per_page = 3000  # Baseline for research papers
        text_density = char_count / (page_count * avg_chars_per_page) if page_count > 0 else 0
        
        if text_density < gates.min_text_density:
            return False, f"Low density: {text_density:.2f} < {gates.min_text_density}"
        
        # Citation check (for academic papers)
        if gates.require_citations:
            has_citations = any(marker in text for marker in ['[1]', '[2]', 'et al.', 'References'])
            if not has_citations:
                return False, "No citation markers found"
        
        # Duplicate check (content-based)
        content_hash = self.registry.compute_file_hash(file_path)
        if self.registry.is_duplicate_content(content_hash, self.domain_config.collection_name):
            return False, "Duplicate content hash"
        
        # File path check (already processed?)
        if self.registry.is_processed(file_path):
            return False, "Already processed (in registry)"
        
        return True, None
    
    def process_pdf_multi(self, pdf_path: Path) -> MultiDomainDocument:
        """Process PDF with domain-specific settings"""
        doc = MultiDomainDocument(
            file_path=pdf_path,
            text="",
            metadata={},
            document_type=self.document_type,
            target_collection=self.domain_config.collection_name
        )
        
        try:
            # Extract
            text, metadata = self.extract_text(pdf_path)
            doc.text = text
            doc.metadata = metadata
            doc.content_hash = self.registry.compute_file_hash(pdf_path)
            
            # Check if has text
            if not text.strip():
                doc.rejection_reason = "No text content"
                return doc
            
            # Apply domain-specific quality gates
            passed, reason = self.check_quality(text, metadata["page_count"], pdf_path)
            
            if not passed:
                doc.rejection_reason = reason
                return doc
            
            # Chunk using domain-specific settings
            doc.chunks = self.chunk_text_domain(text)
            doc.quality_passed = True
            
        except Exception as e:
            doc.rejection_reason = f"Processing error: {e}"
        
        return doc
    
    def chunk_text_domain(self, text: str) -> List[str]:
        """Chunk text using domain-specific chunk size and overlap"""
        tokens = self.tokenizer.encode(text)
        chunks = []
        
        chunk_size = self.domain_config.chunk_size
        chunk_overlap = self.domain_config.chunk_overlap
        
        start = 0
        while start < len(tokens):
            end = start + chunk_size
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)
            
            start += chunk_size - chunk_overlap
        
        return chunks


class MultiCollectionIngester:
    """Handles ingestion to multiple Qdrant collections"""
    
    def __init__(self, url: str = QDRANT_URL):
        self.client = QdrantClient(url=url)
        self.registry = IngestionRegistry()
    
    def ensure_collection(self, collection_name: str):
        """Create collection if doesn't exist"""
        collections = self.client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
        
        if not exists:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"✓ Created collection: {collection_name}")
        else:
            logger.info(f"✓ Collection exists: {collection_name}")
    
    def store_document_multi(self, doc: MultiDomainDocument, embeddings: np.ndarray):
        """Store document chunks in target collection"""
        if not doc.chunks:
            raise ValueError("Document has no chunks to store")
            
        points = []
        
        for idx, (chunk, embedding) in enumerate(zip(doc.chunks, embeddings)):
            point_id = hashlib.md5(f"{doc.file_path.name}_{idx}".encode()).hexdigest()
            
            points.append(PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload={
                    "text": chunk,
                    "chunk_index": idx,
                    "source_file": doc.file_path.name,
                    "document_type": doc.document_type,
                    "collection": doc.target_collection,
                    **doc.metadata
                }
            ))
        
        self.client.upsert(
            collection_name=doc.target_collection,
            points=points
        )
        
        # Register in database
        self.registry.register_document(
            file_path=doc.file_path,
            content_hash=doc.content_hash or "unknown",
            document_type=doc.document_type or "unknown",
            collection_name=doc.target_collection or "unknown",
            title=doc.metadata.get('title', doc.file_path.stem) if doc.metadata else doc.file_path.stem,
            chunk_count=len(doc.chunks) if doc.chunks else 0,
            status='ingested',
            metadata=doc.metadata or {}
        )


def ingest_with_routing(pdf_dir: Path, document_type: Optional[str] = None, auto_detect: bool = False, use_real_embeddings: bool = True):
    """Main multi-domain ingestion pipeline
    
    Args:
        pdf_dir: Directory containing documents
        document_type: Document type (academic, manuals, etc.) or None for auto-detect
        auto_detect: Auto-detect document type from path
        use_real_embeddings: Use AnythingLLM API for embeddings (default True)
    """
    
    # Auto-detect if requested
    if auto_detect:
        detected_type = infer_document_type(pdf_dir)
        if detected_type:
            document_type = detected_type
            logger.info(f"✓ Auto-detected document type: {document_type}")
        elif not document_type:
            logger.info("Error: Could not auto-detect type and no type specified")
            return
    
    # Ensure document_type is set
    if not document_type:
        logger.info("Error: document_type must be specified or auto-detected")
        return
    
    processor = MultiDomainProcessor(document_type)
    ingester = MultiCollectionIngester()
    
    # Initialize embedding client if using real embeddings
    embedding_client = None
    if use_real_embeddings:
        try:
            embedding_client = AnythingLLMClient(
                base_url=ANYTHINGLLM_URL,
                api_key=os.getenv('ANYTHINGLLM_API_KEY')
            )
            logger.info(f"✓ Connected to AnythingLLM for embeddings at {ANYTHINGLLM_URL}")
        except Exception as e:
            logger.warning(f"⚠ Warning: Could not connect to AnythingLLM ({e})")
            logger.info(f"  Falling back to dummy embeddings")
            use_real_embeddings = False
    
    # Ensure target collection exists
    ingester.ensure_collection(processor.domain_config.collection_name)
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    logger.info(f"\nProcessing {len(pdf_files)} PDFs from {pdf_dir}")
    logger.info(f"Document type: {document_type}")
    logger.info(f"Target collection: {processor.domain_config.collection_name}")
    logger.info(f"Quality gates: density≥{processor.domain_config.quality_gates.min_text_density}")
    
    stats = {"processed": 0, "accepted": 0, "rejected": 0, "skipped": 0, "total_chunks": 0}
    rejections = []
    
    for pdf_path in tqdm(pdf_files, desc="Processing"):
        # Check registry first (fast skip)
        if processor.registry.is_processed(pdf_path):
            stats["skipped"] += 1
            continue
        
        doc = processor.process_pdf_multi(pdf_path)
        stats["processed"] += 1
        
        if doc.quality_passed:
            # Generate embeddings using AnythingLLM API or dummy embeddings
            if not doc.chunks:
                logger.warning(f"  ⚠ Document has no chunks, skipping")
                continue
                
            try:
                if use_real_embeddings and embedding_client:
                    embeddings_list = embedding_client.generate_embeddings(doc.chunks)
                    embeddings = np.array(embeddings_list, dtype=np.float32)
                else:
                    # Fallback to dummy embeddings for testing
                    embeddings = np.random.randn(len(doc.chunks), EMBEDDING_DIM).astype(np.float32)
            except NotImplementedError as e:
                logger.warning(f"  ⚠ {e}")
                logger.info(f"  Falling back to dummy embeddings")
                embeddings = np.random.randn(len(doc.chunks), EMBEDDING_DIM).astype(np.float32)
            except Exception as e:
                logger.error(f"  ❌ Embedding generation failed: {e}")
                embeddings = np.random.randn(len(doc.chunks), EMBEDDING_DIM).astype(np.float32)
            
            ingester.store_document_multi(doc, embeddings)
            stats["accepted"] += 1
            stats["total_chunks"] += len(doc.chunks)
        else:
            stats["rejected"] += 1
            rejections.append((pdf_path.name, doc.rejection_reason))
            
            # Register rejection
            processor.registry.register_document(
                file_path=pdf_path,
                content_hash=doc.content_hash or "unknown",
                document_type=document_type or "unknown",
                collection_name="none",
                title=pdf_path.stem,
                chunk_count=0,
                status='rejected',
                error_message=doc.rejection_reason,
                metadata={}
            )
    
    # Print results
    logger.info("\n" + "="*70)
    logger.info("INGESTION COMPLETE")
    logger.info("="*70)
    logger.info(f"Processed: {stats['processed']}")
    logger.info(f"Accepted:  {stats['accepted']}")
    logger.info(f"Rejected:  {stats['rejected']}")
    logger.info(f"Skipped:   {stats['skipped']} (already in registry)")
    logger.info(f"Total chunks: {stats['total_chunks']}")
    
    if rejections:
        logger.info(f"\nRejections ({len(rejections)}):")
        for name, reason in rejections[:10]:
            logger.info(f"  • {name}: {reason}")


def main():
    parser = argparse.ArgumentParser(description='Multi-Domain ORION Ingestion')
    parser.add_argument('directory', type=Path, help='Directory containing PDFs')
    parser.add_argument('--type', dest='doc_type', choices=list(DOMAINS.keys()),
                       help='Document type (academic/manuals/blogs/github/exports)')
    parser.add_argument('--auto-detect', action='store_true',
                       help='Auto-detect type from directory path')
    parser.add_argument('--dummy-embeddings', action='store_true',
                       help='Use dummy embeddings for testing (default: use AnythingLLM API)')
    
    args = parser.parse_args()
    
    if not args.directory.exists():
        logger.info(f"Error: Directory not found: {args.directory}")
        return
    
    if not args.auto_detect and not args.doc_type:
        logger.info("Error: Must specify --type or --auto-detect")
        return
    
    use_real_embeddings = not args.dummy_embeddings
    ingest_with_routing(args.directory, args.doc_type, args.auto_detect, use_real_embeddings)


if __name__ == "__main__":
    main()
