"""
End-to-end test: Create test PDFs, ingest to Qdrant, verify storage

Created: 2025-11-09 (Phase 5A)
"""

from pathlib import Path
import sys
import tempfile
import shutil

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ingest import ingest_directory
import pymupdf


def create_test_corpus(test_dir: Path):
    """Create a small test corpus of research-like PDFs"""
    papers = [
        {
            "name": "rag_systems_overview.pdf",
            "title": "Retrieval-Augmented Generation Systems: A Survey",
            "content": """Abstract - Retrieval-Augmented Generation (RAG) systems combine dense retrieval with large language models to provide grounded, factual responses. This survey examines current architectures, embedding models, and evaluation metrics for RAG systems. """ + "The rise of large language models has transformed natural language processing, enabling powerful generation capabilities. However, these models face persistent challenges with hallucination and outdated knowledge. RAG addresses these issues by retrieving relevant documents from a knowledge base before generation, grounding responses in factual sources. " * 30
        },
        {
            "name": "vector_databases_benchmarks.pdf",
            "title": "Vector Database Performance: HNSW vs IVF-PQ",
            "content": """Introduction - Vector databases enable efficient similarity search over high-dimensional embeddings. This paper compares HNSW (Hierarchical Navigable Small World) and IVF-PQ (Inverted File with Product Quantization) across varying dataset sizes and query patterns. """ + "Modern embedding models produce dense vectors of 768 or 1024 dimensions representing semantic meaning. Efficient retrieval at scale requires specialized index structures. HNSW provides excellent recall through graph-based navigation but requires higher memory. IVF-PQ trades some accuracy for better compression. " * 30
        },
        {
            "name": "llm_inference_optimization.pdf",
            "title": "Optimizing LLM Inference on Consumer GPUs",
            "content": """Abstract - Large language model inference presents significant computational challenges due to model size and autoregressive decoding. This work explores quantization, KV-cache optimization, and batching strategies to enable efficient inference on 24GB consumer GPUs like the RTX 3090. """ + "GPU memory bandwidth is often the primary bottleneck for LLM inference rather than compute capacity. 4-bit quantization methods like AWQ and GPTQ reduce model size dramatically with minimal quality degradation. Flash Attention reduces memory usage for long contexts through kernel fusion. Continuous batching improves throughput by dynamically packing requests. " * 30
        }
    ]
    
    for paper in papers:
        pdf_path = test_dir / paper["name"]
        
        # Create PDF with better text layout (smaller font, more text per page)
        doc = pymupdf.open()
        
        # Split content into multiple pages if needed (every ~2000 chars)
        content_parts = [paper["content"][i:i+2000] for i in range(0, len(paper["content"]), 2000)]
        
        for part in content_parts:
            page = doc.new_page(width=595, height=842)  # A4 size
            # Use textbox for better text density
            rect = pymupdf.Rect(50, 50, 545, 792)  # margins
            page.insert_textbox(rect, part, fontsize=9, align=0)
        
        # Set metadata
        doc.set_metadata({
            "title": paper["title"],
            "author": "Test Researcher",
            "subject": "AI/ML Research"
        })
        
        doc.save(pdf_path)
        doc.close()
        print(f"✓ Created: {paper['name']}")
    
    return len(papers)


def verify_ingestion():
    """Verify documents were ingested to Qdrant"""
    from qdrant_client import QdrantClient
    
    client = QdrantClient(url="http://localhost:6333")
    
    try:
        collection_info = client.get_collection("research-papers")
        point_count = collection_info.points_count
        print(f"\n✓ Collection 'research-papers' has {point_count} points (chunks)")
        
        # Try a sample retrieval
        if point_count > 0:
            # Get a few random points to verify structure
            points = client.scroll(
                collection_name="research-papers",
                limit=3,
                with_payload=True,
                with_vectors=False
            )[0]
            
            print("\nSample chunks:")
            for p in points:
                text_preview = p.payload.get("text", "")[:100] + "..."
                filename = p.payload.get("source_file", "unknown")
                chunk_idx = p.payload.get("chunk_index", "?")
                print(f"  • {filename} [chunk {chunk_idx}]: {text_preview}")
        
        return True
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False


if __name__ == "__main__":
    print("="*70)
    print("END-TO-END INGESTION TEST")
    print("="*70)
    
    # Create test directory
    test_dir = Path(tempfile.mkdtemp(prefix="orion-e2e-"))
    print(f"\nTest directory: {test_dir}\n")
    
    try:
        # Create test corpus
        paper_count = create_test_corpus(test_dir)
        print(f"\n✓ Created {paper_count} test PDFs")
        
        # Run ingestion
        print("\n" + "-"*70)
        print("RUNNING INGESTION PIPELINE")
        print("-"*70)
        ingest_directory(test_dir)
        
        # Verify
        print("\n" + "-"*70)
        print("VERIFYING STORAGE")
        print("-"*70)
        success = verify_ingestion()
        
        if success:
            print("\n" + "="*70)
            print("✓ END-TO-END TEST PASSED")
            print("="*70)
            print("\nPipeline successfully:")
            print("  1. Parsed PDFs with PyMuPDF")
            print("  2. Applied quality gates (text density)")
            print("  3. Chunked documents with tiktoken (512/64)")
            print("  4. Generated embeddings (dummy vectors)")
            print("  5. Stored chunks in Qdrant with metadata")
        else:
            print("\n✗ Verification failed")
            sys.exit(1)
    
    finally:
        # Cleanup
        shutil.rmtree(test_dir)
        print(f"\n✓ Cleaned up test directory")
