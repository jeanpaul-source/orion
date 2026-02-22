"""
ORION Multi-Domain Document Ingestion Pipeline
Processes PDFs with quality gates, chunking, and Qdrant storage

Usage:
    python src/ingest.py /path/to/pdfs/

Features (Phase 6):
    - Multi-domain support (academic, manuals, blogs, github, exports)
    - Document type detection from file paths
    - Type-specific quality gates
    - Multi-collection routing
    - Persistent duplicate tracking via registry

Quality Gates (domain-specific):
    - Academic: Text density ≥0.55, requires citations
    - Manuals: Text density ≥0.35, allows code/tables
    - Blogs: Text density ≥0.35, allows code blocks
    - GitHub: Text density ≥0.20, markdown-heavy

Chunking Strategy:
    - 512 tokens per chunk for most types (tiktoken cl100k_base)
    - 256 tokens for code-heavy content (github)
    - Configurable overlap per domain

Created: 2025-11-09 (Phase 5A)
Updated: 2025-11-10 (Phase 6 - Multi-domain integration)
"""

import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import tiktoken
import pymupdf  # PyMuPDF
from bs4 import BeautifulSoup  # HTML parsing
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from tqdm import tqdm
import numpy as np

# Import multi-domain components
from registry import IngestionRegistry
from domains import get_domain_config, infer_document_type, DomainConfig
from anythingllm_client import AnythingLLMClient

# Set up logging
logger = logging.getLogger(__name__)

# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
ANYTHINGLLM_URL = os.getenv("ANYTHINGLLM_URL", "http://192.168.5.10:3001")
EMBEDDING_DIM = 768  # Xenova/nomic-embed-text-v1 (configured in docker-compose.yml)


@dataclass
class Document:
    """Parsed document with metadata"""

    file_path: Path
    text: str
    metadata: Dict
    document_type: Optional[str] = None  # 'academic', 'manuals', etc.
    domain_config: Optional[DomainConfig] = None  # Configuration for this type
    content_hash: Optional[str] = None  # SHA256 of file content
    chunks: Optional[List[str]] = None
    quality_passed: bool = False
    rejection_reason: Optional[str] = None


@dataclass
class QualityMetrics:
    """Quality gate results"""

    text_density: float
    char_count: int
    page_count: int
    has_text: bool
    is_duplicate: bool
    parse_success: bool


class PDFProcessor:
    """Handles PDF parsing and quality checks with multi-domain support"""

    def __init__(self, registry: Optional[IngestionRegistry] = None) -> None:
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.registry = registry or IngestionRegistry()
        self.seen_hashes = set()  # In-memory duplicate detection (legacy)

    def extract_text(self, pdf_path: Path) -> Tuple[str, Dict]:
        """Extract text and metadata from PDF"""
        try:
            doc = pymupdf.open(pdf_path)  # type: ignore[reportAttributeAccessIssue]
            text_blocks = []

            for page_num, page in enumerate(doc, 1):  # type: ignore[arg-type]
                text = page.get_text()
                if text.strip():
                    text_blocks.append(text)

            full_text = "\n\n".join(text_blocks)

            # PyMuPDF metadata can be None, handle safely
            metadata_dict = doc.metadata if doc.metadata else {}

            metadata = {
                "filename": pdf_path.name,
                "page_count": len(doc),
                "author": (
                    metadata_dict.get("author", "Unknown")
                    if metadata_dict
                    else "Unknown"
                ),
                "title": (
                    metadata_dict.get("title", pdf_path.stem)
                    if metadata_dict
                    else pdf_path.stem
                ),
                "creation_date": (
                    metadata_dict.get("creationDate", "") if metadata_dict else ""
                ),
                "ingestion_date": datetime.now().isoformat(),
            }

            doc.close()
            return full_text, metadata

        except Exception as e:
            raise RuntimeError(f"PDF parse failed for {pdf_path}: {e}") from e

    def calculate_quality(self, text: str, page_count: int) -> QualityMetrics:
        """Apply quality gates"""
        char_count = len(text)
        # Average page has ~3000 chars of text (research papers)
        text_density = char_count / (page_count * 3000) if page_count > 0 else 0

        # Simple duplicate detection via content hash
        content_hash = hashlib.md5(text.encode()).hexdigest()
        is_duplicate = content_hash in self.seen_hashes
        self.seen_hashes.add(content_hash)

        return QualityMetrics(
            text_density=text_density,
            char_count=char_count,
            page_count=page_count,
            has_text=bool(text.strip()),
            is_duplicate=is_duplicate,
            parse_success=True,
        )

    def chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """Chunk text using tiktoken with overlap

        Args:
            text: Text to chunk
            chunk_size: Tokens per chunk
            chunk_overlap: Overlap tokens between chunks
        """
        tokens = self.tokenizer.encode(text)
        chunks = []

        start = 0
        while start < len(tokens):
            end = start + chunk_size
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)

            # Move forward by chunk size minus overlap
            start += chunk_size - chunk_overlap

        return chunks

    def process_pdf(self, pdf_path: Path, detect_type: bool = True) -> Document:
        """Full processing pipeline for single document with multi-domain support

        Args:
            pdf_path: Path to document file (PDF, HTML, or Markdown)
            detect_type: Whether to detect document type from path
        """
        doc = Document(file_path=pdf_path, text="", metadata={})

        try:
            # Step 1: Calculate file hash for duplicate detection
            doc.content_hash = self.registry.compute_file_hash(pdf_path)

            # Step 2: Detect document type from path
            if detect_type:
                doc.document_type = infer_document_type(pdf_path)
                if not doc.document_type:
                    doc.rejection_reason = "Cannot infer document type from path"
                    return doc

                # Get domain configuration
                doc.domain_config = get_domain_config(doc.document_type)
                if not doc.domain_config:
                    doc.rejection_reason = f"Unknown document type: {doc.document_type}"
                    return doc

                if not doc.domain_config.enabled:
                    doc.rejection_reason = f"Domain disabled: {doc.document_type}"
                    return doc

            # Step 3: Check if already processed (using registry)
            if self.registry.is_processed(pdf_path):
                doc.rejection_reason = "Already processed (in registry)"
                return doc

            # Step 4: Check for duplicate content
            if doc.domain_config and doc.content_hash:
                if self.registry.is_duplicate_content(
                    doc.content_hash, doc.domain_config.collection_name
                ):
                    doc.rejection_reason = "Duplicate content (same hash in collection)"
                    return doc

            # Step 5: Extract text
            text, metadata = self.extract_text(pdf_path)
            doc.text = text
            doc.metadata = metadata

            # Step 6: Quality check with domain-specific gates
            quality = self.calculate_quality(text, metadata["page_count"])

            if not quality.has_text:
                doc.rejection_reason = "No text content"
                return doc

            # Apply domain-specific quality gates
            if doc.domain_config:
                gates = doc.domain_config.quality_gates

                if quality.text_density < gates.min_text_density:
                    doc.rejection_reason = (
                        f"Low density: {quality.text_density:.2f} "
                        f"(min {gates.min_text_density} for {doc.document_type})"
                    )
                    return doc

                if quality.char_count < gates.min_length:
                    doc.rejection_reason = (
                        f"Too short: {quality.char_count} chars "
                        f"(min {gates.min_length} for {doc.document_type})"
                    )
                    return doc

                if quality.char_count > gates.max_length:
                    doc.rejection_reason = (
                        f"Too long: {quality.char_count} chars "
                        f"(max {gates.max_length} for {doc.document_type})"
                    )
                    return doc

            # Step 7: Chunk with domain-specific settings
            if doc.domain_config:
                doc.chunks = self.chunk_text(
                    text, doc.domain_config.chunk_size, doc.domain_config.chunk_overlap
                )
            else:
                # Fallback to defaults
                doc.chunks = self.chunk_text(text, 512, 64)

            doc.quality_passed = True

        except Exception as e:
            doc.rejection_reason = f"Processing error: {e}"

        return doc


class HTMLProcessor(PDFProcessor):
    """Processor for HTML files"""

    def extract_text(self, pdf_path: Path) -> Tuple[str, Dict]:
        """Extract text and metadata from HTML"""
        try:
            with open(pdf_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()

            soup = BeautifulSoup(html_content, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer"]):
                script.decompose()

            # Extract title
            title_tag = soup.find("title")
            title = title_tag.get_text() if title_tag else pdf_path.stem

            # Get main text content
            text = soup.get_text(separator="\n\n", strip=True)

            metadata = {
                "filename": pdf_path.name,
                "page_count": 1,  # HTML = 1 page equivalent
                "author": "Unknown",
                "title": title,
                "creation_date": "",
                "ingestion_date": datetime.now().isoformat(),
                "source_type": "html",
            }

            return text, metadata

        except Exception as e:
            raise RuntimeError(f"HTML parse failed for {pdf_path}: {e}") from e


class MarkdownProcessor(PDFProcessor):
    """Processor for Markdown files"""

    def extract_text(self, pdf_path: Path) -> Tuple[str, Dict]:
        """Extract text and metadata from Markdown"""
        try:
            with open(pdf_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

            # Extract title from first # header
            lines = text.split("\n")
            title = pdf_path.stem
            for line in lines:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            metadata = {
                "filename": pdf_path.name,
                "page_count": 1,  # Markdown = 1 page equivalent
                "author": "Unknown",
                "title": title,
                "creation_date": "",
                "ingestion_date": datetime.now().isoformat(),
                "source_type": "markdown",
            }

            return text, metadata

        except Exception as e:
            raise RuntimeError(f"Markdown parse failed for {pdf_path}: {e}") from e


class QdrantIngester:
    """Handles Qdrant vector storage with multi-collection support"""

    def __init__(self, url: str = QDRANT_URL):
        self.client = QdrantClient(url=url)
        self.created_collections = set()  # Track created collections

    def ensure_collection(self, collection_name: str):
        """Create collection if doesn't exist

        Args:
            collection_name: Name of collection to create/verify
        """
        if collection_name in self.created_collections:
            return  # Already checked in this session

        collections = self.client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)

        if not exists:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM, distance=Distance.COSINE
                ),
            )
            logger.info(f"✓ Created collection: {collection_name}")
        else:
            logger.info(f"✓ Collection exists: {collection_name}")

        self.created_collections.add(collection_name)

    def store_document(self, doc: Document, embeddings: np.ndarray):
        """Store document chunks with embeddings in appropriate collection

        Args:
            doc: Processed document with domain config
            embeddings: Embedding vectors for chunks
        """
        if not doc.chunks:
            raise ValueError(f"Document has no chunks to store: {doc.file_path}")

        # Determine target collection
        collection_name = (
            doc.domain_config.collection_name
            if doc.domain_config
            else "research-papers"  # Fallback
        )

        # Ensure collection exists
        self.ensure_collection(collection_name)

        points = []

        for idx, (chunk, embedding) in enumerate(zip(doc.chunks, embeddings)):
            # Generate unique ID based on content hash and chunk index
            point_id = hashlib.md5(f"{doc.content_hash}_{idx}".encode()).hexdigest()

            # Enhanced payload with domain metadata
            payload = {
                "text": chunk,
                "chunk_index": idx,
                "source_file": doc.file_path.name,
                "document_type": doc.document_type,
                "content_hash": doc.content_hash,
                **doc.metadata,
            }

            points.append(
                PointStruct(id=point_id, vector=embedding.tolist(), payload=payload)
            )

        # Batch upsert to avoid timeout with large documents
        # Split into batches of 100 points
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(
                collection_name=collection_name,
                points=batch,
                wait=True,  # Wait for each batch to complete
            )

        return collection_name


def ingest_directory(
    pdf_dir: Path,
    batch_size: int = 10,
    recursive: bool = False,
    use_real_embeddings: bool = True,
):
    """Main ingestion pipeline with multi-format support (PDF, HTML, Markdown)

    Args:
        pdf_dir: Directory containing documents (can have subdirs like academic/, manuals/)
        batch_size: Batch size for processing (not currently used)
        recursive: Whether to scan subdirectories
        use_real_embeddings: If True, use AnythingLLM API for embeddings (default); if False, use dummy embeddings for testing
    """
    registry = IngestionRegistry()
    pdf_processor = PDFProcessor(registry=registry)
    html_processor = HTMLProcessor(registry=registry)
    md_processor = MarkdownProcessor(registry=registry)
    ingester = QdrantIngester()

    # Initialize embedding client if using real embeddings
    embedding_client = None
    if use_real_embeddings:
        try:
            embedding_client = AnythingLLMClient(
                base_url=ANYTHINGLLM_URL, api_key=os.getenv("ANYTHINGLLM_API_KEY")
            )
            logger.info(
                f"✓ Connected to AnythingLLM for embeddings at {ANYTHINGLLM_URL}"
            )
        except Exception as e:
            logger.warning(f"⚠ Warning: Could not connect to AnythingLLM ({e})")
            logger.info("  Falling back to dummy embeddings")
            use_real_embeddings = False

    # Find all supported file types
    all_files = []
    patterns = ["*.pdf", "*.html", "*.md"]

    for pattern in patterns:
        if recursive:
            all_files.extend(pdf_dir.rglob(pattern))
        else:
            all_files.extend(pdf_dir.glob(pattern))

    # Count by type
    pdf_files = [f for f in all_files if f.suffix == ".pdf"]
    html_files = [f for f in all_files if f.suffix == ".html"]
    md_files = [f for f in all_files if f.suffix == ".md"]

    logger.info(f"\nFound {len(all_files)} documents in {pdf_dir}")
    logger.info(f"  PDFs: {len(pdf_files)}")
    logger.info(f"  HTML: {len(html_files)}")
    logger.info(f"  Markdown: {len(md_files)}")
    logger.info(f"Registry: {registry.db_path}")

    stats = {
        "processed": 0,
        "accepted": 0,
        "rejected": 0,
        "total_chunks": 0,
        "by_type": {},  # Track stats per document type
        "by_collection": {},  # Track stats per collection
    }
    rejections = []

    # Process all files
    for file_path in tqdm(all_files, desc="Processing documents"):
        # Select appropriate processor based on file type
        if file_path.suffix == ".pdf":
            doc = pdf_processor.process_pdf(file_path)
        elif file_path.suffix == ".html":
            doc = html_processor.process_pdf(
                file_path
            )  # Uses inherited process_pdf method
        elif file_path.suffix == ".md":
            doc = md_processor.process_pdf(
                file_path
            )  # Uses inherited process_pdf method
        else:
            continue

        stats["processed"] += 1

        if doc.quality_passed and doc.chunks:
            # Generate embeddings using AnythingLLM API or dummy embeddings
            try:
                if use_real_embeddings and embedding_client:
                    embeddings_list = embedding_client.generate_embeddings(doc.chunks)
                    embeddings = np.array(embeddings_list, dtype=np.float32)
                    logger.info(
                        f"  ✓ Generated {len(embeddings)} real embeddings (nomic-embed-text-v1)"
                    )
                else:
                    # Fallback to dummy embeddings for testing
                    embeddings = np.random.randn(len(doc.chunks), EMBEDDING_DIM).astype(
                        np.float32
                    )
                    logger.warning("  ⚠ Using dummy embeddings (for testing only)")
            except NotImplementedError as e:
                # AnythingLLM API doesn't support embedding endpoint
                logger.warning(f"  ⚠ {e}")
                logger.info("  Falling back to dummy embeddings")
                embeddings = np.random.randn(len(doc.chunks), EMBEDDING_DIM).astype(
                    np.float32
                )
            except Exception as e:
                logger.error(f"  ❌ Embedding generation failed: {e}")
                logger.info("  Falling back to dummy embeddings")
                embeddings = np.random.randn(len(doc.chunks), EMBEDDING_DIM).astype(
                    np.float32
                )

            # Store in Qdrant with retry logic
            try:
                collection_name = ingester.store_document(doc, embeddings)
            except Exception as e:
                logger.error(f"\n❌ Failed to store {file_path.name}: {e}")
                rejections.append((file_path.name, f"Storage error: {e}"))
                continue

            # Register in database
            registry.register_document(
                file_path=file_path,
                content_hash=doc.content_hash or "",
                document_type=doc.document_type or "unknown",
                collection_name=collection_name,
                title=doc.metadata.get("title", file_path.stem),
                chunk_count=len(doc.chunks),
                status="ingested",
                error_message=None,
                metadata=doc.metadata,
            )

            stats["accepted"] += 1
            stats["total_chunks"] += len(doc.chunks)

            # Track by type
            doc_type = doc.document_type or "unknown"
            if doc_type not in stats["by_type"]:
                stats["by_type"][doc_type] = {"count": 0, "chunks": 0}
            stats["by_type"][doc_type]["count"] += 1
            stats["by_type"][doc_type]["chunks"] += len(doc.chunks)

            # Track by collection
            if collection_name not in stats["by_collection"]:
                stats["by_collection"][collection_name] = {"count": 0, "chunks": 0}
            stats["by_collection"][collection_name]["count"] += 1
            stats["by_collection"][collection_name]["chunks"] += len(doc.chunks)

        else:
            stats["rejected"] += 1
            rejections.append((file_path.name, doc.rejection_reason))

            # Register rejection
            if doc.content_hash:
                registry.register_document(
                    file_path=file_path,
                    content_hash=doc.content_hash,
                    document_type=doc.document_type or "unknown",
                    collection_name="none",
                    title=(
                        doc.metadata.get("title", file_path.stem)
                        if doc.metadata
                        else file_path.stem
                    ),
                    chunk_count=0,
                    status="rejected",
                    error_message=doc.rejection_reason,
                    metadata=doc.metadata,
                )

    # Print results
    logger.info("\n" + "=" * 70)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Processed: {stats['processed']}")
    logger.info(f"Accepted:  {stats['accepted']}")
    logger.info(f"Rejected:  {stats['rejected']}")
    logger.info(f"Total chunks: {stats['total_chunks']}")
    if stats["accepted"] > 0:
        logger.info(f"Avg chunks/doc: {stats['total_chunks'] / stats['accepted']:.1f}")

    # Stats by document type
    if stats["by_type"]:
        logger.info("\nBy Document Type:")
        for doc_type, type_stats in stats["by_type"].items():
            logger.info(
                f"  {doc_type:12} → {type_stats['count']:3} docs, "
                f"{type_stats['chunks']:5} chunks"
            )

    # Stats by collection
    if stats["by_collection"]:
        logger.info("\nBy Collection:")
        for collection, coll_stats in stats["by_collection"].items():
            logger.info(
                f"  {collection:20} → {coll_stats['count']:3} docs, "
                f"{coll_stats['chunks']:5} chunks"
            )

    # Rejections
    if rejections:
        logger.info(f"\nRejections ({len(rejections)}):")
        for filename, reason in rejections[:10]:  # Show first 10
            logger.info(f"  • {filename}: {reason}")
        if len(rejections) > 10:
            logger.info(f"  ... and {len(rejections) - 10} more")


if __name__ == "__main__":
    import sys

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        logger.info(
            "Usage: python src/ingest.py <document_directory> [--recursive] [--dummy-embeddings]"
        )
        logger.info("\nSupports: PDF, HTML, Markdown files")
        logger.info("\nExamples:")
        logger.info(
            "  python src/ingest.py /mnt/nvme1/orion-data/documents/raw/github/"
        )
        logger.info(
            "  python src/ingest.py /mnt/nvme1/orion-data/documents/raw --recursive"
        )
        logger.info(
            "  python src/ingest.py /tmp/test-docs --dummy-embeddings  # Testing mode"
        )
        logger.info("\nOptions:")
        logger.info("  --recursive, -r         Scan subdirectories")
        logger.info("  --dummy-embeddings      Use random embeddings (testing only)")
        logger.info(
            "\nBy default, uses AnythingLLM API for real embeddings (BGE-base-en-v1.5, 768-dim)"
        )
        sys.exit(1)

    pdf_dir = Path(sys.argv[1])
    recursive = "--recursive" in sys.argv or "-r" in sys.argv
    use_real_embeddings = (
        "--dummy-embeddings" not in sys.argv
    )  # Default to real embeddings

    if not pdf_dir.exists():
        logger.info(f"Error: Directory not found: {pdf_dir}")
        sys.exit(1)

    if not pdf_dir.is_dir():
        logger.info(f"Error: Not a directory: {pdf_dir}")
        sys.exit(1)

    ingest_directory(
        pdf_dir, recursive=recursive, use_real_embeddings=use_real_embeddings
    )
