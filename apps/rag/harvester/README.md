# ORION Harvester — Knowledge Collection & Processing

> **Part of the [ORION Autonomous Homelab AI System](../README.md)**

Automatically downloads research papers from multiple academic APIs, with **citation analysis**, **related paper discovery**, **NLP-based relevance filtering**, and **trend tracking**. Organizes papers into a structured library for ORION's autonomous infrastructure management system.

**🚀 Primary Interface:** Unified `orion` CLI for intuitive multi-machine orchestration

---

## 📚 Quick Navigation

**New to ORION?** Start with the [top-level README](../README.md) for system overview and architecture.

**Harvester-Specific Docs:**

- **[CLI Usage Guide](harvester-docs/CLI_USAGE.md)** - Complete command reference
- **[Configuration Guide](config/README.md)** - Search terms and profiles
- **[Requirements & Dependencies](requirements/)** - Package dependencies
- **[Test Suite](tests/)** - Unit and integration tests
- **[Immutable Timeline](SESSION_HANDOFF.md)** - Architectural history

**Parent Documentation:**

- **[ORION Overview](../README.md)** - Complete system architecture
- **[AI Agent Instructions](../../../.github/copilot-instructions.md)** - Copilot guide
- **[CLAUDE.md](../../../CLAUDE.md)** - AI assistant development guide

---

## 🎯 What This Repo Does

**ORION Harvester** is the **primary repository** for the ORION system, containing:

1. **Knowledge Collection** (Stage 1-3)
   - Harvest papers from 14 sources (Semantic Scholar, arXiv, OpenAlex, CORE, DBLP, Crossref, Zenodo, HAL, PubMed, bioRxiv, GitHub, Stack Overflow, official docs, tech blogs)
   - Multi-layer quality filtering (38% acceptance rate)
   - Metadata tracking and citation analysis

2. **Document Processing** (Stage 4)
   - Convert PDFs → 3 formats (Markdown, Text, JSON)
   - Page-aware chunking (~1000 tokens, 200 overlap)
   - Structured metadata with page citations

3. **Unified CLI** (All Stages)
   - Single `orion` command for all operations
   - Profile system (host/laptop/dev)
   - Quality gates and safety checks

4. **Shared Infrastructure**
   - `packages/orion-common` - Config, utilities (used by all repos)
   - `config/orion.toml` - Profile definitions
   - Data storage (symlinked to orion-rag, orion-processor)

**Current Status:**

- ✅ 1,403 papers harvested and processed (967,339 initial chunks → 991,553 sub-chunks)
- ✅ Stage 5 in progress: Embedding 991k vectors to Qdrant on host (`orion_homelab`, status green)
  - Production pipeline: 80 vec/s sustained with blocking uploads (wait=True)
  - Two-phase design: CPU tokenization (286s) → GPU embedding + reliable uploads
  - ETA: ~3.5 hours for full completion (verified stable at scale)
- ✅ Stage 6 complete: vLLM inference (Qwen2.5-Coder-7B) + RAG query pipeline operational
- ✅ Unified CLI with 7 commands
- ⏳ Next: Complete Stage 5 embedding → Stage 7 (n8n orchestration) + Stage 8 (safe actions)

---

## Quick Start (Unified CLI)

The `orion` CLI is the recommended way to interact with the ORION pipeline. It enforces host-only compute by default and provides intuitive commands for all operations.

### 1. Install

```bash
# From orion-harvester/ directory

# One-time setup
python3 -m venv .venv
pip install -e .

# REQUIRED: Enable auto-activation (choose ONE):

# Option A: direnv (recommended - automatic)
sudo apt install direnv
echo 'eval "$(direnv hook bash)"' >> ~/.bashrc
source ~/.bashrc
direnv allow  # Run this in orion-harvester/ directory

# Option B: Manual in each terminal
source activate.sh  # Must run every time you open a new terminal

# Option C: Shell profile auto-activation
echo 'export ORION_AUTO_ACTIVATE=1' >> ~/.bashrc
echo 'source ~/Laptop-MAIN/applications/orion-rag/harvester/.autorc' >> ~/.bashrc
source ~/.bashrc

# Verify installation
orion --help
orion version
```

**Why this is required:** ORION has strict venv checks to prevent using wrong Python environments. All scripts will fail if the wrong venv is active.

### 2. Query knowledge base

```bash
# Test query (uses host for embeddings, Qdrant, and LLM)
orion query --test --top-k 8

# Ask a real question
orion query "What are Proxmox VE best practices?"

# With verbose mode to see loaded config
orion --verbose query --test
```

### 3. Process PDFs

```bash
# Convert PDFs to AI-ready formats (markdown, text, structured JSON)
orion process --max-files 50

# Custom paths
orion process --input data/library --output data/processed
```

### 4. Generate embeddings and index

```bash
# Embed and index to Qdrant (uses host embedding service)
orion embed-index --collection orion_homelab

# Custom batch size
orion embed-index --batch-size 64 --limit 100
```

### 5. Validate data quality

```bash
# Quick validation
orion validate --quick

# Full validation with summary
orion validate --summary
```

### 6. Host operations

```bash
# Check embedding server health
orion ops embed-health

# Start embedding server (run on host)
orion ops embed-serve

# Sync to host
orion ops sync
```

### Profiles (Multi-machine architecture)

ORION supports profiles for different environments:

```bash
# Default: host profile (all compute on host)
orion query --test

# Laptop profile (enforces CPU-only safety)
orion --profile laptop query --test

# Dev profile (local services for testing)
orion --profile dev query --test

# Environment variable
export ORION_PROFILE=laptop
orion query --test
```

**See [harvester-docs/CLI_USAGE.md](harvester-docs/CLI_USAGE.md) for complete CLI documentation.**

## Makefile Shortcuts

```bash
# Show available commands
make help

# Query
make query ARGS="--test --top-k 8"

# Process library
make process ARGS="--max-files 50"

# Check embedding server
make ops-health

# With laptop profile
make query PROFILE=laptop ARGS="--test"
```

## Legacy Quick Start (Script-based)

**⚠️ DEPRECATED:** The script-based workflow using `orion_harvester.py` has been replaced by the unified `orion` CLI. The scripts have been migrated into the `src/` package structure. Use the unified CLI (above) for all new operations.

### 3. Multi-Format Export

- **BibTeX** - For LaTeX workflows (`\cite{}`)
- **CSV** - For spreadsheets and analysis
- **JSON** - For programmatic access
- Supports filtering by category and citation threshold
- Export to file or stdout

### 4. NLP-Based Relevance Scoring (Optional)

- Uses **sentence-transformers** (all-MiniLM-L6-v2, 80MB model)
- Semantic similarity threshold: 0.65 cosine similarity
- Category embeddings cached for speed
- Enable with: `export ORION_USE_EMBEDDINGS=true`
- Falls back to keyword matching if unavailable

### 5. Trend Tracking & Emerging Topics

- Month-over-month growth rate analysis per category
- Identifies **hot topics** (>50% growth)
- Visual timeline with activity bars
- Publication velocity tracking

### 6. Text Extraction & AI-Ready Formats (Phase 1) ✨ NEW

Now supports processing of non-PDF sources (Markdown and HTML) in addition to PDFs.

### 7. Phase 2 Harvester Optimizations ✨ NEW

**Enhanced CLI Flags:**

- `--dry-run` - Preview candidates without downloading
- `--auto-process` - Automatically run `process_library.py --file <pdf>` after successful download and record status in metadata (`processing` field)
- `--new-only` - Skip already-downloaded papers (checks both title and URL)
- `--min-citations <n>` - Enforce citation threshold on results
- `--term <query>` + `--category <name>` - Single-term harvest mode (skip CSV)
- `--providers <list>` - Comma-separated providers. Options: `papers` (default), `github`, `stackoverflow`, `official-docs`, `tech-blogs`, or `all` for everything
- `--since <YYYY-MM-DD>` - With GitHub and blog providers, filter for recent content

**Improved Relevance Filtering:**

- Title + abstract analysis (not just title)
- **Word-boundary matching** prevents false positives (e.g., "ann" won't match "annotated")
- Expanded red flags: medical, physics, biology, agriculture
- Category-specific required terms + secondary synonyms
- Category-specific exclusion terms (e.g., "medical" excluded from databases)
- Venue quality heuristics (bias to VLDB/SIGMOD/NeurIPS/etc.)
- Relevance diagnostics stored in metadata for debugging

**3 New Search Sources:**

- Crossref API with Unpaywall DOI resolution
- Unpaywall standalone resolver for open access PDFs
- Zenodo open access repository
- Total 6 providers with graceful fallback sequence

- **Converts PDFs/Markdown/HTML → Markdown, Text, JSON** for AI/LLM consumption
- **918,008 chunks** generated from 1,403 documents (~655 chunks/document)
- **Page-aware chunking** - each chunk tracks source pages (PDFs)
- Extraction via PyMuPDF (primary), pdfplumber (fallback), BeautifulSoup4 (HTML)
- Token counting with tiktoken (GPT-4 tokenizer)
- **100% success rate** on current library (1,403/1,403 files)
- Processing time: ~10 minutes on 20-core host (Intel Core Ultra 7 265K)
- Run with: `.venv/bin/python3 process_library.py`

### 8. RAG Embedding Pipeline (Phase 2) ✨ NEW

**Status:** Ready for validation, NO embedding started (awaiting approval)

**Token-Aware Re-Chunking:**

- Original chunks average **721 tokens** (from processing pipeline)
- BGE-large-en-v1.5 max: **512 tokens** (silent truncation if exceeded)
- Solution: Split into 512-token sub-chunks with 64-token overlap
- Result: **1,950,767 projected vectors** (2.1× increase for quality)
- No quality loss, better retrieval granularity

**GPU-Accelerated Embedding:**

- Model: BAAI/bge-large-en-v1.5 (1024-dim embeddings)
- Hardware: RTX 3090 Ti (24GB VRAM), 20-core CPU @ 192.168.5.10
- Streaming pipeline: Embed batch 512, upsert batch 1000 to Qdrant
- Conservative ETA: ~10-12 hours for 1.95M sub-chunks
- Scripts: `scripts/embed_and_index.py` (main), `scripts/validate_*.py` (quality gates)

**Quality-First Validation:**

- Corpus-wide token analysis (safe, no embeddings)
- Sandbox E2E retrieval test (small subset with real embeddings)
- Acceptance criteria: Precision@5 ≥ 0.6 for 4/5 ORION domain queries
- **⚠️ NO EMBEDDING without explicit approval** - See [`EMBEDDING_MIGRATION_GUIDE.md`](EMBEDDING_MIGRATION_GUIDE.md)

**Target System:**

- Vector DB: Qdrant v1.15.5 (Docker, localhost:6333)
- Collection: `orion_homelab` (hybrid semantic + BM25)
- Query interface: `scripts/query_rag.py` (CLI) + `scripts/web_ui.py` (Gradio)
- Integration: vLLM API @ <http://localhost:8000/v1> for LLM reasoning

### Current Library Stats (Updated Nov 2, 2025)

- **1,403 documents** (post-bulk harvest)
  - 465 PDFs (academic papers, processed via PyMuPDF)
  - 819 HTML files (official docs, tech blogs, processed via BeautifulSoup4)
  - 119 Markdown files (GitHub READMEs, Stack Overflow Q&A)
- **100% processed** to AI-ready formats (markdown/text/JSON)
- **918,008 total chunks** from processing pipeline
- **~1.95M projected vectors** after token-aware re-chunking
- **272 active search terms** across 11 categories
- **10 content sources** (6 academic APIs + GitHub + Stack Overflow + Official Docs + Tech Blogs)
- **11 specialized categories** (aligned to ORION Endgame vision)
- All files deduplicated by SHA256 hash + title/URL
- Quality filtering: red flags + word-boundary matching + venue heuristics + optional NLP

## Project Structure

```
harvester/
├── � src/                         # Python package source code
│   ├── cli.py                      # Unified CLI entry point
│   ├── providers/                  # 15 provider implementations
│   ├── converters/                 # Document format converters
│   ├── doc_config.py               # Quality gates configuration
│   ├── downloader.py               # Download orchestration
│   └── filters.py                  # Relevance filtering
│
├── 📁 scripts/                     # Executable helper scripts
│   ├── batch_harvest.py            # Batch processing automation
│   ├── monitor-harvest.sh          # Harvest progress monitoring
│   └── overnight-harvest.sh        # Overnight batch execution
│
├── 📁 config/                      # Configuration
│   ├── orion.toml                  # Profile definitions (laptop/host/dev)
│   ├── search_terms.csv            # 272 search terms (11 categories)
│   └── profiles/                   # Profile-specific settings
│
├── 📁 harvester-docs/              # User documentation
│   ├── CLI_USAGE.md                # Complete CLI reference
│   ├── QUICK_START.md              # Fast track to first harvest
│   ├── BULK_HARVEST_GUIDE.md       # Overnight bulk harvesting
│   ├── CATEGORY_MANAGEMENT.md      # Category management
│   └── DATA_SOURCES.md             # Provider documentation
│
├── 📁 tests/                       # Test suite (pytest)
│
├── 📁 requirements/                # Python dependencies
│   ├── requirements.txt            # Production dependencies
│   └── requirements-dev.txt        # Development dependencies
│
├── BATCH-HARVEST-GUIDE.md          # Production batch operations
├── Makefile                        # Convenience commands
├── pyproject.toml                  # Package configuration
├── activate.sh                     # venv activation helper
└── README.md                       # This file
│   ├── RAG_OPTIMIZATION_PLAN.md  # Full RAG implementation plan ✨ NEW
│   ├── OPTIMIZATION_SUMMARY.md
│   └── ORION_Super_Homelab_Vision.txt
├── archive/                    # Deprecated/historical files
│   ├── ORION References/       # Original curated papers (merged)
│   └── ...
└── .github/
    └── copilot-instructions.md # AI agent guidance
```

## Configuration

### Environment Variables (Optional)

**API Keys & Tokens** (recommended for production):

```bash
export ORION_CONTACT_EMAIL="your@email.com"       # Polite API headers
export ORION_GITHUB_TOKEN="ghp_xxxxx"             # GitHub: 60 → 5,000 req/hr
export ORION_SO_API_KEY="xxxxx"                   # Stack Overflow: 300 → 10,000 req/day
export ORION_S2_API_KEY="xxxxx"                   # Semantic Scholar: higher limits
export ORION_CORE_API_KEY="xxxxx"                 # CORE: 1,000 req/day free tier
```

### Reproducible install (optional)

To use the exact versions we tested on 2025-11-02, install with constraints:

```bash
.venv/bin/pip install -r requirements.txt -c constraints.txt
```

**Quality Thresholds** (customize filtering):

```bash
export ORION_MIN_GITHUB_STARS="100"               # Default: 100 stars minimum
export ORION_MIN_SO_SCORE="10"                    # Default: 10 score minimum
export ORION_USE_EMBEDDINGS="true"                # Enable NLP semantic filtering
```

### File Paths

Key constants in legacy scripts:

- `BASE_DIR`: Library storage location (now managed by unified CLI config)
- `RATE_LIMIT_DELAY`: Seconds between API calls (default: 5)
- `SEARCH_CSV`: Path to search terms file
- `METADATA_DB`: Path to downloads metadata JSON (`library_metadata.json`)

## Search Terms Format

CSV file with headers `term,category`:

```csv
term,category
"GPU passthrough VFIO IOMMU",gpu-passthrough-and-vgpu
"PostgreSQL replication streaming",data-persistence-stores
"Kubernetes GPU scheduling",container-platforms
"RAG retrieval hybrid search",rag-and-knowledge-retrieval
"Qdrant vector database clustering",vector-databases
```

### Available Categories (11 focused categories)

- `container-platforms` - Docker, Kubernetes, container orchestration
- `data-persistence-stores` - Databases, key-value stores, persistence layers
- `gpu-passthrough-and-vgpu` - GPU virtualization, VFIO, vGPU configuration
- `homelab-infrastructure` - Proxmox, virtualization, bare metal setup
- `homelab-networking-security` - Network config, firewalls, security hardening
- `llm-serving-and-inference` - vLLM, model serving, inference optimization
- `observability-and-alerting` - Prometheus, Grafana, monitoring, alerting
- `rag-and-knowledge-retrieval` - Retrieval patterns, embeddings, context assembly
- `self-healing-and-remediation` - Automated recovery, safe actions, rollbacks
- `vector-databases` - Qdrant, Milvus, similarity search, HNSW
- `workflow-automation-n8n` - n8n workflows, orchestration, integrations

## Output Structure

Papers are saved as:

```
data/library/
├── rag-and-knowledge-retrieval/
│   ├── RAG_hybrid_search_optimization.pdf
│   └── Context_assembly_citation_aware.pdf
├── gpu-passthrough-and-vgpu/
│   ├── GPU_passthrough_VFIO_IOMMU.pdf
│   └── vGPU_configuration_Proxmox.pdf
├── data-persistence-stores/
│   └── PostgreSQL_replication_streaming.pdf
├── vector-databases/
│   └── Qdrant_vector_database_clustering.pdf
└── container-platforms/
    └── Kubernetes_GPU_scheduling.pdf
```

## Metadata Tracking

`library_metadata.json` contains:

```json
{
  "downloads": [
    {
      "term": "GPU passthrough VFIO IOMMU",
      "title": "Efficient GPU Passthrough with VFIO",
      "source": "semantic_scholar",
      "url": "https://example.com/paper.pdf",
      "category": "gpu-passthrough-and-vgpu",
   "filepath": "data/library/gpu-passthrough-and-vgpu/Efficient_GPU_Passthrough.pdf",
      "file_hash": "abc123...",
      "downloaded_at": "2025-11-01 10:30:15"
    }
  ],
  "migration_info": {
    "migrated_from_auto": 172,
    "migrated_from_curated": 95,
    "duplicates_skipped": 1,
    "total_papers": 267
  }
}
```

## Processing Library (Phase 1)

Convert library files (PDF/Markdown/HTML) to AI-ready formats for RAG/search:

```bash
# Process all 257 PDFs (~3-5 minutes)
python3 process_library.py

# Test on 5 random samples first
python3 process_library.py --sample 5

# Process one category only
python3 process_library.py --category gpu-passthrough-and-vgpu

# Process a single file (PDF/Markdown/HTML)
python3 process_library.py --file data/library/data-persistence-stores/paper.pdf
```

**Output formats:**

- **Markdown** (`data/processed/markdown/`): Human-readable with title, authors, page markers
- **Text** (`data/processed/text/`): Plain text for embedding generation
- **JSON** (`data/processed/structured/`): Complete metadata + chunks with page ranges

**Quality features:**

- PyMuPDF primary extraction (fast, reliable)
- pdfplumber fallback for complex layouts
- Auto-detects low-quality extractions (<30% valid pages)
- Chunks are ~1000 tokens with 200-token overlap
- Each chunk tracks source page ranges (page_start, page_end)
- Processing log saved to `data/processed/processing_log.json`

**Example output:**

```json
{
  "paper_id": "1112f620086b09ee",
  "title": "GPU Passthrough with VFIO on Proxmox",
  "author": "Alex Williamson; et al.",
  "category": "gpu-passthrough-and-vgpu",
  "page_count": 15,
  "extraction_method": "pymupdf",
  "chunk_count": 47,
  "chunks": [
    {
      "chunk_id": 0,
      "text": "...",
      "token_count": 1024,
      "page_start": 1,
      "page_end": 2
    }
  ]
}
```

## Troubleshooting

### Harvester Issues

- **"Search CSV not found"**: Create `search_terms.csv` with proper headers
- **No results found**: Check search terms, APIs may be rate-limited (wait 5-10 mins)
- **Download failures**: Check `harvester.log` for detailed error messages
- **Duplicate prevention**: Papers with identical titles or URLs are automatically skipped
- **False positive papers**: Check `relevance` field in metadata for diagnostics; adjust `CATEGORY_REQUIRED_TERMS` or `GENERAL_RED_FLAGS` as needed

### Rate Limit Issues

**Symptoms**: 429 errors, empty results, "rate limit" warnings in logs

**Solutions by provider**:

- **GitHub**: Set `ORION_GITHUB_TOKEN` (60 → 5,000 req/hr)
  - Generate at: <https://github.com/settings/tokens>
  - Requires `public_repo` scope
- **Stack Overflow**: Set `ORION_SO_API_KEY` (300 → 10,000 req/day)
  - Register at: <https://stackapps.com/apps/oauth/register>
  - Note: Each question makes 2 API calls (search + answer fetch)
- **Semantic Scholar**: Set `ORION_S2_API_KEY` for higher limits
  - Contact: <https://www.semanticscholar.org/product/api>
- **All providers**: Reduce concurrency, increase `RATE_LIMIT_DELAY`, or use `--dry-run` to test without hitting limits

**Quick fix**: The harvester automatically falls back to next source when rate-limited

### Processing Issues

- **Import errors**: Run `pip install PyMuPDF pdfplumber langchain-text-splitters tiktoken`
- **Low extraction quality**: Check `processing.log` for warnings - may need OCR for scanned PDFs
- **Memory issues**: Process by category with `--category` flag instead of all at once
- **Partial processing**: Delete `data/processed/` and re-run to start fresh

## Development

- **Rate limiting**: 5-second delays between API calls prevent blocking
- **PDF validation**: Files <10KB or without `%PDF` header are rejected
- **Retry logic**: HTTP requests use exponential backoff for resilience
- **Deduplication**: Title-based checking prevents duplicate downloads

## API Sources

The harvester tries sources in order of quality until it finds results:

1. **Semantic Scholar** (primary): High-quality metadata, citation data, open access PDFs
   - Optional API key via `ORION_S2_API_KEY` env var (higher rate limits)
   - Polite usage: Set `ORION_CONTACT_EMAIL` env var (recommended)
2. **OpenAlex** (secondary): 250M+ scholarly works, comprehensive coverage, **FREE**
   - No API key required, polite mailto header recommended
3. **CORE** (tertiary): 250M+ open access papers, broad academic corpus, **FREE**
   - Optional API key via `ORION_CORE_API_KEY` env var (1000 requests/day free tier)
4. **arXiv** (fallback): Research preprints, good for CS/physics, broader search, **FREE**
5. **Crossref + Unpaywall**: DOI metadata with open access PDF resolution, **FREE**
   - Crossref provides metadata, Unpaywall resolves DOIs to PDFs
6. **Zenodo**: Open access repository (EU-funded), preprints, datasets, **FREE**

7. **GitHub (optional)**: High-signal repositories discovered via stars and recent activity; downloads README.md as markdown documentation, **FREE**
   - **Rate Limits**: 60 req/hr (unauthenticated) → 5,000 req/hr (with token)
   - **Recommended**: Set `ORION_GITHUB_TOKEN` for production use
   - Generate token: <https://github.com/settings/tokens> (select `public_repo` scope)
   - Use with: `--providers github` or combined: `--providers papers,github,stackoverflow`
   - Date filter: `--since YYYY-MM-DD` biases search to recent activity
   - Quality gate: Minimum 100 stars (configurable via `ORION_MIN_GITHUB_STARS` env var)

8. **Stack Overflow (optional)**: High-quality accepted answers from the community, **FREE**
   - **Rate Limits**: 300 req/day (unauthenticated) → 10,000 req/day (with key)
   - **Recommended**: Set `ORION_SO_API_KEY` for bulk harvesting
   - Register app: <https://stackapps.com/apps/oauth/register>
   - Filters questions by category-relevant tags (e.g., cuda, postgresql, kubernetes)
   - Only includes accepted answers with score ≥ 10 (configurable via `ORION_MIN_SO_SCORE`)
   - Converts HTML to markdown format with Q&A structure
   - Maps answer score to citation_count for unified ranking
   - Use with: `--providers stackoverflow` or combined with other providers

9. **Official Documentation (optional)**: Allow-listed authoritative documentation, **FREE**
   - Searches trusted domains: kubernetes.io, postgresql.org, docker.com, nvidia.com, redis.io, mongodb.com, etc.
   - Currently hardcoded for common queries (Kubernetes, PostgreSQL, Docker)
   - Future: Full web search integration with robots.txt compliance
   - Quality gate: Domain allowlist + recency checks
   - Use with: `--providers official-docs`

10. **Tech Blogs (optional)**: RSS feeds from reputable engineering teams, **FREE**

- Sources: Meta Engineering, AWS Blog, Netflix Tech Blog, GitHub Blog, Stack Overflow Blog, Cloudflare Blog
- Parses RSS/Atom feeds, filters by query relevance
- Applies recency filter with `--since YYYY-MM-DD`
- Converts blog post HTML to markdown
- Quality gate: Domain allowlist (only known-good blogs)
- Use with: `--providers tech-blogs`

**Rate Limiting:**

- 5-second delay between all API calls (polite usage)
- Respects 429/503 HTTP status codes with exponential backoff
- Set `ORION_CONTACT_EMAIL="your@email.com"` for polite API headers

All sources are **free** with generous rate limits. Optional API keys boost performance but aren't required.

## Migration History

**November 1, 2025** - Library Consolidation

- Merged manually curated papers from `ORION References/` (95 papers)
- Migrated auto-downloaded papers from previous library location (172 papers)
- Centralized all papers to unified `data/library/` structure
- Updated category names to kebab-case for consistency
- Added 4 new specialized categories (llm-infrastructure, system-reliability, vector-databases, workflow-automation)
- Implemented SHA256 deduplication (1 duplicate removed)
- Total unique papers: 267

---
*Last updated: November 1, 2025*
