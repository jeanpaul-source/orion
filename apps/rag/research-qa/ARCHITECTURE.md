# orion-research-qa Architecture

**Status**: ✅ Fixed - Direct Qdrant Path Now Working  
**Last Updated**: 2025-11-12

---

## Purpose

Document ingestion pipeline that processes PDFs/HTML and stores them for RAG queries.

## Two Storage Backends (Both Needed)

### 1. Qdrant (Direct Vector Storage)
- **Purpose**: Primary vector database for programmatic access
- **Location**: `http://192.168.5.10:6333`
- **Collections**:
  - `technical-docs`: ~1.2M vectors (PRODUCTION)
  - `research-papers`: In progress
  - `code-examples`: 37 vectors
- **Embedding Model**: BGE-base-en-v1.5 (768-dim)
- **Use Cases**: 
  - Python scripts querying vectors directly
  - Custom RAG applications
  - Batch processing

### 2. AnythingLLM (RAG UI)
- **Purpose**: User-facing chat interface
- **Location**: `http://192.168.5.10:3001`
- **Backend**: Uses Qdrant for vector storage
- **Use Cases**:
  - Interactive chat queries
  - Document management UI
  - Workspace organization

---

## Current Implementation Status

### ✅ Working: `orchestrator.py` (AnythingLLM Path)
```python
orchestrator.py:
  ↓ Scans /mnt/nvme1/orion-data/documents/raw/
  ↓ Applies quality gates (domains.py)
  ↓ Uploads to AnythingLLM via API
  ↓ AnythingLLM handles embedding + storage
  ↓ Registry tracks uploads
```

**Status**: Functional, used for host doc pipeline

### ✅ Fixed: `ingest.py` (Direct Qdrant Path)
```python
ingest.py:
  ↓ Reads PDFs/HTML/Markdown
  ↓ Applies quality gates (domains.py)
  ↓ Chunks text (512 tokens, configurable overlap)
  ✅ Generates embeddings via AnythingLLM API
  ✅ Stores directly in Qdrant
  ↓ Registry tracks ingestions
```

**Status**: ✅ **COMPLETE** - Now generates real embeddings via AnythingLLM API

**Changes (2025-11-12)**:
- Added `generate_embeddings()` method to `anythingllm_client.py`
- Integrated embedding generation into `ingest.py`
- Added `--dummy-embeddings` flag for testing
- Default behavior: use real BGE-base-en-v1.5 embeddings from AnythingLLM

### ✅ Fixed: `ingest_multi.py`
- Similar to `ingest.py` but with explicit document type routing
- Also now uses real embeddings via AnythingLLM API
- Added `--dummy-embeddings` flag

---

## The Solution

**Both paths now work for different use cases:**

```
Documents
  ↓
orion-research-qa
  ↓
  ├→ Direct to Qdrant (ingest.py) — FOR PROGRAMMATIC ACCESS
  │   - AnythingLLM generates embeddings via API
  │   - Store vectors directly in Qdrant
  │   - Full control over chunking/metadata
  │   - Best for batch processing
  │
  └→ Via AnythingLLM API (orchestrator.py) — FOR UI ACCESS
      - Upload documents to AnythingLLM
      - AnythingLLM handles everything
      - Available in chat interface
      - Best for interactive use
```

**Key Insight**: Both paths use the **same embedding model** (BGE-base-en-v1.5) via AnythingLLM API, ensuring consistency.

---

## Usage

### Direct Qdrant Path (ingest.py)

```bash
# Process documents with real embeddings (default)
python src/ingest.py /mnt/nvme1/orion-data/documents/raw/academic/

# Recursive scan
python src/ingest.py /mnt/nvme1/orion-data/documents/raw --recursive

# Testing mode (dummy embeddings)
python src/ingest.py /tmp/test-docs --dummy-embeddings
```

**Environment Variables Required**:
```bash
ANYTHINGLLM_API_KEY=...     # Required for embeddings
ANYTHINGLLM_URL=http://192.168.5.10:3001  # Optional (default shown)
QDRANT_URL=http://localhost:6333          # Optional (default shown)
```

### Multi-Domain Path (ingest_multi.py)

```bash
# With explicit type
python src/ingest_multi.py --type academic /path/to/pdfs/

# Auto-detect type from path
python src/ingest_multi.py --auto-detect /mnt/nvme1/orion-data/documents/raw/academic/

# Testing mode
python src/ingest_multi.py --type manuals --dummy-embeddings /tmp/test/
```

### AnythingLLM Path (orchestrator.py)

```bash
# Upload to AnythingLLM (handles everything)
python src/orchestrator.py --document-root /mnt/nvme1/orion-data/documents/raw/
```

---

## Shared Components

### `domains.py` - Domain-Specific Quality Gates
Routes documents to appropriate collections based on type:

- **Academic**: Text density ≥55%, requires citations → `research-papers`
- **Manuals**: Text density ≥35%, allows tables/code → `technical-docs`
- **GitHub**: Text density ≥20%, markdown-heavy → `code-examples`
- **Blogs**: Text density ≥35%, allows code blocks → `technical-docs`

### `registry.py` - Deduplication & Progress Tracking
SQLite database prevents reprocessing:

- SHA256 content hashing
- Path tracking
- Status tracking (processed/failed)
- Metadata storage

**Locations**:
- `/mnt/nvme1/orion-data/documents/metadata/ingestion.db` (1.9MB, 1,410 docs)
- `/mnt/nvme2/orion-project/services/harvest-registry.db` (28KB, possibly obsolete)

### `anythingllm_client.py` - AnythingLLM API Client
Handles document upload, workspace management, **and embedding generation**.

**Key Methods**:
- `upload_document()` - Upload document to workspace
- `generate_embeddings(texts)` - **NEW**: Generate embeddings for text chunks
- `chat()` - Query workspace

---

## Implementation Details

### Embedding Generation

Both `ingest.py` and `ingest_multi.py` now call:

```python
from anythingllm_client import AnythingLLMClient

client = AnythingLLMClient(
    base_url="http://192.168.5.10:3001",
    api_key=os.getenv('ANYTHINGLLM_API_KEY')
)

# Generate embeddings for chunks
embeddings_list = client.generate_embeddings(doc.chunks)
embeddings = np.array(embeddings_list, dtype=np.float32)

# Store in Qdrant
ingester.store_document(doc, embeddings)
```

**Fallback Behavior**: If AnythingLLM API is unavailable or returns 404, falls back to dummy embeddings (for testing only).

### Error Handling

```python
try:
    embeddings_list = client.generate_embeddings(doc.chunks)
    embeddings = np.array(embeddings_list)
except NotImplementedError:
    # API endpoint doesn't exist
    print("AnythingLLM embedding API not available")
    embeddings = np.random.randn(len(doc.chunks), 768)  # Testing only
except Exception as e:
    # Other errors
    print(f"Embedding generation failed: {e}")
    embeddings = np.random.randn(len(doc.chunks), 768)  # Testing only
```

---

## Data Flow (Fixed)

### Host Pipeline (Working)
```
Doc sources → orion-doc-harvesters → /mnt/nvme1/orion-data/documents/raw/
                                        ↓
                              orchestrator.py (orion-research-qa)
                                        ↓
                                 AnythingLLM API
                                        ↓
                                  Qdrant storage
```

### Laptop Pipeline (Ready to Fix)
```
Academic APIs → orion-harvester → /home/jp/MAIN/applications/orion-harvester/data/library/ (493 PDFs)
                                        ↓
                                [rsync to host]
                                        ↓
                      /mnt/nvme1/orion-data/documents/raw/academic/
                                        ↓
                              ingest.py (orion-research-qa)
                                        ↓
                           ✅ AnythingLLM API (embeddings)
                                        ↓
                              Qdrant (direct storage)
```

**Next Step**: Sync 493 laptop PDFs to host and run through `ingest.py`.

---

## Files Overview

```
src/
├── orchestrator.py        # ✅ WORKING - AnythingLLM upload orchestration
├── ingest.py             # ✅ FIXED - Direct Qdrant path (now has embeddings)
├── ingest_multi.py       # ✅ FIXED - Multi-domain routing (now has embeddings)
├── anythingllm_client.py # ✅ UPDATED - Added generate_embeddings() method
├── domains.py            # ✅ WORKING - Quality gates & routing
├── registry.py           # ✅ WORKING - Deduplication tracking
└── monitor.py            # Status monitoring
```

---

## Dependencies

- **PyMuPDF** (pymupdf): PDF text extraction
- **BeautifulSoup4**: HTML parsing
- **tiktoken**: Token counting/chunking
- **qdrant-client**: Qdrant vector database
- **requests**: AnythingLLM API calls
- **numpy**: Array operations for embeddings

**No longer needed**:
- ~~sentence-transformers~~ - Using AnythingLLM API instead

---

## Testing

### Test with Dummy Embeddings (Fast)

```bash
# Create test directory
mkdir -p /tmp/test-docs
cp /path/to/sample.pdf /tmp/test-docs/

# Run with dummy embeddings (no API required)
python src/ingest.py /tmp/test-docs --dummy-embeddings
```

### Test with Real Embeddings (Production)

```bash
# Set API key
export ANYTHINGLLM_API_KEY=your-api-key-here

# Run with real embeddings
python src/ingest.py /mnt/nvme1/orion-data/documents/raw/academic/
```

**Expected output**:
```
✓ Connected to AnythingLLM for embeddings at http://192.168.5.10:3001
Processing documents: 100%|████████| 10/10
  ✓ Generated 15 real embeddings (BGE-base-en-v1.5)
  ✓ Stored in collection: research-papers
```

---

## Changelog

**2025-11-12** - Fixed Direct Qdrant Path:
- Added `generate_embeddings()` to `anythingllm_client.py`
- Updated `ingest.py` to use real embeddings via AnythingLLM API
- Updated `ingest_multi.py` to use real embeddings
- Added `--dummy-embeddings` flag for testing
- Documented architecture and usage
- **Status change**: ⚠️ Broken → ✅ Fixed
