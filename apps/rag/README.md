# 🔭 ORION - Two-Machine RAG System

<!-- markdownlint-disable MD013 MD036 -->

**ORION (Operational Reference Intelligence for Orchestrated Navigation)** is a production-grade RAG (Retrieval-Augmented Generation) system designed to eliminate homelab mistakes by learning from experts before problems happen.

**Status:** 🔄 Infrastructure Ready, Knowledge Base Rebuild Required (Nov 17, 2025)
**Architecture:** Two-machine (laptop + GPU host)
**Knowledge Pipeline:** Qdrant collection cleared Nov 17; run `bash automation/scripts/ops/rebuild-rag.sh` to restore

## What is ORION?

ORION answers technical questions by querying a comprehensive knowledge base of:

- **Academic Research:** 493 papers from 15 academic APIs
- **Technical Documentation:** 2,028 docs from GitHub, ReadTheDocs, vendor PDFs, blogs
- **RAG Inference:** vLLM (Qwen2.5-14B), Qdrant (rebuild pending), AnythingLLM UI

**Example Query:**
*"What are Proxmox VE best practices for GPU passthrough?"*

**Answer:**
Returns cited answers from official Proxmox docs, GitHub issues, academic papers on virtualization, and community discussions - all from your local knowledge base.

## System Components

ORION consists of three integrated applications:

```
┌──────────────────────────────────────────────────────┐
│                 ORION Architecture                    │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────┐  │
│  │  Harvester  │──▶│ Research-QA  │──▶│   Infra  │  │
│  │             │   │              │   │          │  │
│  │ Collect     │   │  Process     │   │ Services │  │
│  │ Academic    │   │  Ingest      │   │ vLLM     │  │
│  │ & Tech Docs │   │  Quality     │   │ Qdrant   │  │
│  │             │   │  Gates       │   │ UI       │  │
│  └─────────────┘   └──────────────┘   └──────────┘  │
│                                                       │
│  493 Papers ──▶ 2,028 Docs ──▶ Embeddings (rebuild pending) ──▶ RAG │
└──────────────────────────────────────────────────────┘
```

### 1. [harvester/](harvester/) - Academic & Documentation Harvesting

**Purpose:** Collect high-quality technical content from multiple sources

**Features:**

- 15 academic API providers (Semantic Scholar, arXiv, OpenAlex, etc.)
- Technical documentation (GitHub, ReadTheDocs, vendor PDFs)
- Quality filtering (minimum stars, scores, text density)
- Deduplication via SHA256 hashing
- 272 curated search terms across 11 categories

**Status:** ✅ 493 papers collected, processing pipeline ready

**Quick Start:**

```bash
cd harvester/
source .venv/bin/activate
orion harvest --term "kubernetes" --category container-platforms
orion process --max-files 50
```

[Read more →](harvester/README.md)

### 2. [research-qa/](research-qa/) - Document Processing & Ingestion

**Purpose:** Process raw documents and ingest into RAG system

**Features:**

- AnythingLLM integration (API client with retry logic)
- SQLite registry for deduplication
- Domain-specific quality gates (GitHub/academic/manuals)
- Orchestrated ingestion pipeline
- Progress tracking and error recovery

**Status:** ✅ 1,410 documents processed, 1.2M vectors in Qdrant

**Quick Start:**

```bash
cd research-qa/
source venv/bin/activate
export ANYTHINGLLM_API_KEY="YOUR-ANYTHINGLLM-API-KEY" # pragma: allowlist secret
python src/orchestrator.py --document-root /path/to/docs
```

[Read more →](research-qa/README.md)

### 3. [infrastructure/](infrastructure/) - Docker Services

**Purpose:** Run RAG stack (vLLM, Qdrant, AnythingLLM, n8n)

**Services:**

- **vLLM:** LLM inference (Qwen2.5-14B-Instruct-AWQ) on RTX 3090 Ti
- **Qdrant:** Vector database (1.2M vectors, 768-dim embeddings)
- **AnythingLLM:** RAG orchestration & web UI
- **n8n:** Workflow automation (optional)

**Status:** ✅ Running on host (192.168.5.10)

**Quick Start:**

```bash
cd infrastructure/
cp .env.example .env
# Edit .env with API keys
docker compose up -d
```

[Read more →](infrastructure/README.md)

## Two-Machine Architecture

ORION is designed for a two-machine setup:

```
┌───────────────────────┐         ┌────────────────────────┐
│   Laptop (Orchestration)    │         │    Host (GPU Compute)     │
│   192.168.5.25               │         │    192.168.5.10            │
├───────────────────────┤         ├────────────────────────┤
│ • VS Code + Git       │         │ • RTX 3090 Ti (24GB)   │
│ • Ansible control     │         │ • 64GB RAM             │
│ • harvester/          │         │ • 3x 1.8TB NVMe        │
│ • research-qa/        │◀───SSH──▶│ • Docker Services:     │
│ • Code development    │         │   - vLLM (port 8000)   │
│                       │         │   - Qdrant (port 6333) │
│                       │         │   - AnythingLLM (3001) │
│                       │         │   - n8n (port 5678)    │
└───────────────────────┘         └────────────────────────┘
```

**⚠️ CRITICAL INVARIANT:** GPU workloads NEVER run on laptop. Laptop = orchestration only.

## Quick Start (Full Stack)

### Prerequisites

**Laptop:**

- Python 3.10+
- Git
- SSH access to host

**Host:**

- Docker + Docker Compose
- NVIDIA GPU with 24GB+ VRAM
- nvidia-docker runtime

### 1. Clone Repository

```bash
git clone <repo-url>
cd Laptop-MAIN/applications/orion-rag
```

### 2. Setup Infrastructure (Host)

```bash
# On host machine
cd infrastructure/
cp .env.example .env
# Generate strong keys:
openssl rand -hex 32  # For VLLM_API_KEY
openssl rand -hex 32  # For QDRANT_API_KEY
openssl rand -base64 32  # For N8N_ADMIN_PASSWORD
# Edit .env with these keys

# Start services
docker compose up -d

# Verify
docker compose ps
```

### 3. Setup Harvester (Laptop)

```bash
# On laptop
cd harvester/
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Configure (optional, increases rate limits)
cp .env.example .env
# Add API keys for academic sources

# Test
orion --version
orion query --test
```

### 4. Setup Research-QA (Laptop)

```bash
cd research-qa/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Set ANYTHINGLLM_API_KEY from AnythingLLM UI

# Test
python src/anythingllm_client.py  # Verify connection
```

### 5. Harvest & Process Documents

```bash
# Harvest academic papers
cd harvester/
orion harvest --term "vector databases" --category databases

# Process PDFs
orion process --max-files 50

# Ingest into RAG
cd ../research-qa/
python src/orchestrator.py --document-root ../harvester/data/library/
```

### 6. Query Knowledge Base

Access AnythingLLM UI: <http://192.168.5.10:3001>

Or use CLI:

```bash
cd harvester/
orion query "What are Qdrant best practices?"
```

## Data Flow

```
Academic APIs ──▶ Harvester ──▶ Raw PDFs ──▶ Research-QA ──▶ Vector DB
     │               │             │              │              │
  15 Sources    493 Papers    Dedup Registry  Quality Gates  Qdrant
     │               │             │              │              │
     ▼               ▼             ▼              ▼              ▼
GitHub/Docs ──▶  2,028 Docs  ──▶ SQLite ──▶ AnythingLLM ──▶ 1.2M Vectors
```

## Current Status

| Component | Status | Progress |
|-----------|--------|----------|
| **Harvester** | ✅ Complete | 493 papers, 2,028 docs collected |
| **Research-QA** | ✅ Complete | 1,410 docs processed |
| **Infrastructure** | ✅ Running | All services healthy |
| **Vector DB** | ✅ Populated | 1.2M vectors |
| **RAG Queries** | ✅ Working | AnythingLLM UI functional |

**Overall:** 99% Complete

## Configuration

Each component has its own `.env.example`:

- [harvester/.env.example](harvester/.env.example) - API keys, quality thresholds
- [research-qa/.env.example](research-qa/.env.example) - AnythingLLM, Qdrant config
- [infrastructure/.env.example](infrastructure/.env.example) - Docker service keys

## Development

### Running Tests

```bash
# Harvester tests
cd harvester/
pytest tests/ -v

# Research-QA tests
cd research-qa/
pytest tests/ -v
```

### Code Quality

```bash
# Linting
ruff check .

# Formatting
black .

# Type checking
mypy src/
```

## Troubleshooting

### Common Issues

**"Connection refused to AnythingLLM"**

```bash
# Check if services are running
ssh host "cd /mnt/nvme2/orion-project/setup && docker compose ps"

# Restart services
ssh host "cd /mnt/nvme2/orion-project/setup && docker compose restart"
```

**"CUDA out of memory"**

```bash
# Check GPU usage
ssh host "nvidia-smi"

# Restart vLLM
ssh host "docker compose restart vllm"
```

**"Documents not appearing in Qdrant"**

```bash
# Check vector count
ssh host "curl http://localhost:6333/collections/technical-docs"

# Check ingestion registry
ssh host "sqlite3 /mnt/nvme1/orion-data/documents/metadata/ingestion.db 'SELECT COUNT(*) FROM documents;'"
```

## Integration with Other Systems

ORION integrates with:

- **DevOps Agent (devia):** CLI queries ORION knowledge base automatically
- **n8n Workflows:** Automated document processing pipelines
- **Ansible:** Infrastructure orchestration from laptop

## Documentation

- [ORION Overview](../../README.md) - Main project README
- [Harvester Documentation](harvester/README.md) - Academic API usage
- [Research-QA Documentation](research-qa/README.md) - Processing pipeline
- [Infrastructure Documentation](infrastructure/README.md) - Docker services
- [CLAUDE.md](../../CLAUDE.md) - AI assistant development guide
- [Complete Systems Map](../../docs/archive/2025-11/COMPLETE-SYSTEMS-MAP-2025-11-16.md)

## Architecture Decisions

See [ARCHITECTURE-CLARIFICATION-2025-11-16.md](../../docs/archive/2025-11/ARCHITECTURE-CLARIFICATION-2025-11-16.md) for detailed system relationships.

## License

Part of the Laptop-MAIN homelab ecosystem.

## Maintainers

- Laptop-MAIN Project Team

---

**Last Updated:** November 16, 2025
**Version:** 1.0 (99% Complete)
