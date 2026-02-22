# ORION Document Ingestion System

Complete document processing pipeline with AnythingLLM integration.

This application orchestrates the ORION document ingestion pipeline, handling:

- Document harvesting from multiple sources
- Domain-specific quality gates
- Automated ingestion via AnythingLLM API
- Deduplication and progress tracking
- Qdrant vector database population

> **Note:** This directory was originally planned as `orion-research-qa` (academic
> paper Q&A system) but currently serves as the complete document ingestion
> orchestrator. See `ARCHITECTURE.md` for implementation details.

---

## Quick Start

### Prerequisites

```bash
# Ensure services are running on host
ssh lab "docker ps | grep -E 'vllm|qdrant|anythingllm'"

# Activate Python environment (if working locally)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

**Environment variables are automatically loaded from `.env`** (symlinked to repository root):

```bash
# .env is symlinked to /home/jp/Laptop-MAIN/.env
# This ensures all ORION components use the same configuration
ls -la .env  # Shows: .env -> ../../../.env

# Required variables (already set if .env exists):
# - ANYTHINGLLM_API_KEY
# - ANYTHINGLLM_URL
# - QDRANT_URL
# - ORION_DOCUMENT_ROOT
# - ORION_INGESTION_DB
```

**Manual override** (optional, for testing):

```bash
# AnythingLLM connection
export ANYTHINGLLM_API_URL=http://192.168.5.10:3001/api
export ANYTHINGLLM_API_KEY=<from KEYS_AND_TOKENS.md>
export ANYTHINGLLM_WORKSPACE=research-papers

# Qdrant connection
export QDRANT_URL=http://192.168.5.10:6333
export QDRANT_COLLECTION=orion_research
```

### Run Ingestion

```bash
# Full pipeline run (from repository root)
cd applications/orion-rag/research-qa
python src/orchestrator.py --document-root /mnt/nvme1/orion-data/documents/raw 2>&1 | tee /tmp/orion-ingestion.log
```

### Bulk AnythingLLM Upload Helper

When you simply need to push the existing document archive into the three
AnythingLLM workspaces (without running the full orchestrator), use the helper
script at `scripts/bulk_anythingllm_ingest.py`.

> **Recommendation:** Execute the script directly on the host (`ssh lab`) so it
> can stream files from `/mnt/nvme1/orion-data` without copying them back to the
> laptop.

Dry-run to inspect counts:

```bash
cd /root/orion/applications/orion-rag/research-qa
python scripts/bulk_anythingllm_ingest.py --dry-run
```

Upload one workspace (limit to first 25 files for a smoke test):

```bash
python scripts/bulk_anythingllm_ingest.py \
  --workspace technical-docs \
  --limit 25
```

Full bulk import with automatic resume (uses `~/.orion_anythingllm_manifest.json`):

```bash
python scripts/bulk_anythingllm_ingest.py
```

Key flags:

- `--workspace` / `--category`: limit to specific workspace(s) or category folders.
- `--limit`: stop after *n* successful uploads per workspace (great for validation batches).
- `--manifest`: override the resume manifest location if you want per-run tracking.
- `--upload-timeout` / `--embed-timeout`: bump HTTP timeouts when AnythingLLM is busy rebuilding embeddings.
- `--embed-retries` / `--embed-retry-delay`: control how aggressively the helper retries the
  embedding call before marking a file as failed.
- The helper now prints `[workspace] [current/total] uploading <file>...` before each API call,
  so you always see a heartbeat even if AnythingLLM takes a minute to respond.

---

## Architecture

### Data Flow

```
Documents (raw/)
  ↓
  → Quality Gates (domains.py)
  ↓
  → AnythingLLM API (anythingllm_client.py)
  ↓
  → Qdrant Collections (code-examples, research-papers, technical-docs)
  ↓
  → Registry Tracking (ingestion.db)
```

### Key Components

**`orchestrator.py`** - Master coordinator

- Scans document directories
- Applies quality gates
- Routes to appropriate workspaces
- Tracks progress and errors

**`anythingllm_client.py`** - API client

- Document upload to AnythingLLM
- Workspace management
- Embedding generation via AnythingLLM's native embedder

**`registry.py`** - Deduplication system

- SQLite database at `/mnt/nvme1/orion-data/documents/metadata/ingestion.db`
- Tracks processed documents by file path and content hash
- Prevents duplicate ingestion

**`domains.py`** - Quality gate configurations

- Domain-specific thresholds (github, manuals, academic, blogs, exports)
- Text density, file size, token count validation

**`ingest.py`** - Document processors

- PDFProcessor: Extract text from PDFs using PyMuPDF
- HTMLProcessor: Parse HTML/Markdown using BeautifulSoup4

---

## Configuration

### Workspace Mapping

Documents are automatically routed to AnythingLLM workspaces by domain:

| Domain | Workspace | Qdrant Collection |
|--------|-----------|-------------------|
| github | Code Examples | code-examples |
| manuals | Technical Documentation | technical-docs |
| academic | Research Papers | research-papers |
| blogs | Technical Documentation | technical-docs |
| exports | Technical Documentation | technical-docs |

### Quality Gates

Each domain has specific thresholds defined in `src/domains.py`:

- **github**: High standards (text density > 0.3, min tokens: 200)
- **manuals**: Flexible (text density > 0.15, min tokens: 100)
- **academic**: Strict (text density > 0.4, min tokens: 500)
- **blogs**: Moderate (text density > 0.2, min tokens: 150)

---

## Common Operations

### 🔴 Reset Everything (Full Pipeline Reset)

**Warning:** This deletes ALL processed documents and embeddings. Use only when starting fresh.

```bash
# 1. Stop orchestrator if running
pkill -f orchestrator.py

# 2. Delete registry database
rm /mnt/nvme1/orion-data/documents/metadata/ingestion.db
echo "✓ Registry cleared"

# 3. Delete Qdrant collections
curl -X DELETE http://localhost:6333/collections/code-examples
curl -X DELETE http://localhost:6333/collections/research-papers
curl -X DELETE http://localhost:6333/collections/technical-docs
echo "✓ Collections deleted"

# 4. Clear AnythingLLM workspace documents (via UI)
# - Login to http://localhost:3001
# - Go to each workspace settings
# - Remove all documents from workspace

# 5. Re-run ingestion
cd applications/orion-rag/research-qa
export ANYTHINGLLM_API_KEY="<set-from-keys-and-tokens>"
python src/orchestrator.py --document-root /mnt/nvme1/orion-data/documents/raw
```

### Check Ingestion Status

```bash
# View live progress
tail -f /tmp/orion-ingestion.log

# Check registry database
sqlite3 /mnt/nvme1/orion-data/documents/metadata/ingestion.db "SELECT COUNT(*) FROM documents;"

# Check Qdrant collections
curl -s http://localhost:6333/collections/code-examples | jq '.result.points_count'
curl -s http://localhost:6333/collections/research-papers | jq '.result.points_count'
curl -s http://localhost:6333/collections/technical-docs | jq '.result.points_count'

# Check AnythingLLM workspaces
curl -s -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  http://localhost:3001/api/v1/workspaces | jq '.workspaces[] | {name, totalDocuments}'
```

---

## Project Structure

```
research-qa/
├── src/
│   ├── __init__.py
│   ├── config.py                  # AnythingLLM API, Qdrant endpoints
│   ├── orchestrator.py            # Main ingestion coordinator
│   ├── anythingllm_client.py      # AnythingLLM API wrapper
│   ├── registry.py                # Deduplication tracking
│   ├── domains.py                 # Quality gate configuration
│   ├── ingest.py                  # PDF/HTML processors
│   └── ingest_multi.py            # Multi-document type handler
│
├── tests/
│   ├── test_ingest.py             # Processor tests
│   └── test_registry.py           # Registry tests
│
├── requirements.txt               # Python dependencies
├── README.md                      # This file
└── ARCHITECTURE.md                # Detailed architecture docs
```

---

## Known Issues

- Laptop has 493 academic PDFs not yet synced to host (need rsync to `/mnt/nvme1/orion-data/documents/raw/academic/`)
- Sync required before these can be ingested

---

## Development Roadmap

**Current Status:** ✅ Phase 8 Complete - Full pipeline operational

**Future Enhancement:** 🚧 Research Q&A System

- Academic-specific query interface
- Citation formatting (APA/MLA/Chicago)
- Methodology extraction
- Citation graph traversal

---

## Related Documentation

- `ARCHITECTURE.md` - Detailed system architecture and data flow
- `../orion-harvester/README.md` - Document harvesting pipeline
- `../../CLAUDE.md` - AI assistant guide for the entire ORION project
