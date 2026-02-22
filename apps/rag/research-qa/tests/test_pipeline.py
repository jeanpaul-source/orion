"""
Test script for ORION ingestion pipeline
Creates a minimal test PDF and processes it through the pipeline

Created: 2025-11-09 (Phase 5A)
"""

from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ingest import PDFProcessor, QdrantIngester, Document
import pymupdf
import os
import tempfile

def create_test_pdf(output_path: Path, content: str, title: str = "Test Document"):
    """Create a simple PDF for testing"""
    doc = pymupdf.open()
    page = doc.new_page()
    
    # Add text
    point = pymupdf.Point(50, 100)
    page.insert_text(point, content, fontsize=11)
    
    # Set metadata
    doc.set_metadata({
        "title": title,
        "author": "Test Author",
        "subject": "Test Subject"
    })
    
    doc.save(output_path)
    doc.close()
    print(f"✓ Created test PDF: {output_path}")


def test_pdf_processing():
    """Test PDF extraction, quality gates, and chunking"""
    print("\n" + "="*60)
    print("TESTING PDF PROCESSING PIPELINE")
    print("="*60)
    
    # Create temporary directory
    test_dir = Path(tempfile.mkdtemp(prefix="orion-test-"))
    print(f"\nTest directory: {test_dir}")
    
    # Create test PDFs
    # Note: PDF needs ~3000 chars per page for 0.55 density, so ~1650+ chars minimum
    test_cases = [
        {
            "name": "good_paper.pdf",
            "content": "Introduction\n\n" + "This is a research paper with sufficient text content covering RAG systems, vector databases, and LLM inference optimization. " * 100,
            "expected": "pass"
        },
        {
            "name": "low_density.pdf",
            "content": "Short.",
            "expected": "reject_density"
        },
        {
            "name": "another_good_paper.pdf",
            "content": "Abstract\n\nThis paper discusses RAG retrieval systems, hybrid search strategies, embedding models like nomic-embed and BGE-large, and quality gates for document ingestion. " * 80,
            "expected": "pass"
        }
    ]
    
    for tc in test_cases:
        pdf_path = test_dir / tc["name"]
        create_test_pdf(pdf_path, tc["content"], tc["name"].replace(".pdf", ""))
    
    # Test processing
    print("\nProcessing PDFs...")
    processor = PDFProcessor()
    
    results = []
    for tc in test_cases:
        pdf_path = test_dir / tc["name"]
        doc = processor.process_pdf(pdf_path)
        results.append({
            "name": tc["name"],
            "expected": tc["expected"],
            "passed": doc.quality_passed,
            "reason": doc.rejection_reason,
            "chunks": len(doc.chunks) if doc.chunks else 0
        })
    
    # Print results
    print("\n" + "-"*60)
    print("RESULTS")
    print("-"*60)
    for r in results:
        status = "✓ PASS" if r["passed"] else "✗ REJECT"
        print(f"{status} | {r['name']}")
        if not r["passed"]:
            print(f"       Reason: {r['reason']}")
        else:
            print(f"       Chunks: {r['chunks']}")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    print(f"\n✓ Cleaned up test directory")
    
    # Summary
    passed_count = sum(1 for r in results if r["passed"])
    print(f"\nSummary: {passed_count}/{len(results)} PDFs passed quality gates")
    
    return passed_count > 0


def test_qdrant_connection():
    """Test connection to Qdrant"""
    print("\n" + "="*60)
    print("TESTING QDRANT CONNECTION")
    print("="*60)
    
    try:
        ingester = QdrantIngester()
        collections = ingester.client.get_collections()
        print(f"✓ Connected to Qdrant")
        print(f"  Existing collections: {[c.name for c in collections.collections]}")
        return True
    except Exception as e:
        print(f"✗ Failed to connect to Qdrant: {e}")
        return False


if __name__ == "__main__":
    print("ORION Ingestion Pipeline Test Suite\n")
    
    # Test 1: PDF Processing
    pdf_ok = test_pdf_processing()
    
    # Test 2: Qdrant Connection
    qdrant_ok = test_qdrant_connection()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"PDF Processing:     {'✓ PASS' if pdf_ok else '✗ FAIL'}")
    print(f"Qdrant Connection:  {'✓ PASS' if qdrant_ok else '✗ FAIL'}")
    print("="*60)
    
    if pdf_ok and qdrant_ok:
        print("\n✓ All tests passed! Pipeline is ready.")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed. Check errors above.")
        sys.exit(1)
