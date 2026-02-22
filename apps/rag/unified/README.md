# ORION Unified RAG System

**Status:** Production Ready
**Created:** 2025-11-17 (Consolidation Phase)
**Purpose:** Unified pipeline combining harvesting, processing, embedding, and querying

---

## 🎯 Overview

ORION Unified consolidates the harvester and research-qa applications into a **single, streamlined pipeline** running entirely on the host. This eliminates laptop-host sync issues and provides a simple CLI for all RAG operations.

### What It Does

```
┌────────────────────────────────────────────────┐
│  UNIFIED ORION PIPELINE                        │
├────────────────────────────────────────────────┤
│  1. HARVEST   → 15 providers (academic + docs) │
│  2. PROCESS   → Quality gates + chunking       │
│  3. EMBED     → Qdrant vector storage          │
│  4. QUERY     → Hybrid search + reranking      │
└────────────────────────────────────────────────┘
```

### Key Features

- ✅ **Single CLI** - One `orion` command for all operations
- ✅ **Automated Updates** - Weekly systemd timer for dataset refreshes
- ✅ **Smart Deduplication** - Never process the same document twice
- ✅ **Hybrid Search** - Vector + keyword search (30-40% better recall)
- ✅ **Cross-Encoder Reranking** - 20-30% better relevance
- ✅ **Optimized Settings** - 1024 token chunks, 0.85 GPU utilization
- ✅ **Domain-Aware** - Different quality gates per content type

---

## 🚀 Quick Start

### Prerequisites

1. **Host machine** (192.168.5.10) with:
   - RTX 3090 Ti GPU (24GB)
   - Docker services running (vLLM, Qdrant, AnythingLLM)
   - Python 3.10+

2. **Docker services** must be running:

   ```bash
   cd /mnt/nvme2/orion-project/setup
   docker compose ps  # Verify all services are "Up"
   ```

### Installation

**On the host (192.168.5.10):**

```bash
# Option 1: Clone/sync code to host
cd /mnt/nvme1
git clone <your-repo-url> orion-staging
# OR sync from laptop:
# rsync -av laptop:/home/user/Laptop-MAIN/applications/orion-rag/unified/ /mnt/nvme1/orion/

# Option 2: Run setup script
cd /mnt/nvme1/orion-staging/unified/scripts
./setup-host.sh

# This will:
# - Create directory structure at /mnt/nvme1/orion
# - Copy all code components
# - Setup virtual environment
# - Install dependencies (~2-3GB)
# - Configure systemd timer
# - Create CLI symlink
```

### Configuration

Edit `.env` file:

```bash
nano /mnt/nvme1/orion/.env

# Update:
ANYTHINGLLM_API_KEY=your-api-key-here
```

### Verify Installation

```bash
# Test CLI
orion --help

# Check system status
orion status

# Check service health
orion info
```

---

## 📚 Usage Guide

### Basic Commands

#### 1. Harvest Documents

```bash
# Harvest academic papers
orion harvest "kubernetes autoscaling" --domain academic --max-docs 50

# Harvest technical documentation
orion harvest "proxmox gpu passthrough" --domain manuals --max-docs 30

# Only harvest new documents (skip duplicates)
orion harvest "vector databases" --domain academic --new-only
```

**Supported domains:**

- `academic` - Research papers (Semantic Scholar, arXiv, OpenAlex, etc.)
- `manuals` - Technical docs (GitHub, ReadTheDocs, vendor PDFs)
- `blogs` - Blog posts (Medium, Dev.to, Hashnode)
- `github` - GitHub documentation

#### 2. Process Documents

```bash
# Process all documents in a domain
orion process --domain academic

# Process with limits
orion process --domain manuals --max-files 100

# Only process new documents
orion process --domain academic --new-only

# Dry run (see what would be processed)
orion process --domain manuals --dry-run
```

#### 3. Embed Documents

```bash
# Embed to collection
orion embed research-papers

# Only embed new documents
orion embed technical-docs --new-only

# Control batch size
orion embed research-papers --batch-size 64
```

**Collections:**

- `research-papers` - Academic domain
- `technical-docs` - Manuals and blogs
- `code-examples` - GitHub documentation

#### 4. Query Knowledge Base

```bash
# Basic query
orion query "What are Proxmox best practices for GPU passthrough?"

# Advanced options
orion query "kubernetes autoscaling" \
  --collection technical-docs \
  --top-k 10 \
  --use-reranking \
  --use-hybrid

# Disable reranking (faster but less relevant)
orion query "docker swarm" --no-use-reranking

# Vector-only search (no keyword matching)
orion query "vector databases" --no-use-hybrid
```

#### 5. Complete Pipeline

Run harvest → process → embed in one command:

```bash
orion pipeline "kubernetes autoscaling" \
  --domain manuals \
  --max-docs 50

# Automatically determines collection from domain
# Then run: orion query "kubernetes autoscaling"
```

#### 6. System Status

```bash
# Show registry statistics and Qdrant collections
orion status

# Show configuration
orion info
```

---

## 🔄 Automated Updates

### Systemd Timer (Recommended)

The setup script configures a weekly systemd timer:

```bash
# Start timer (runs every Sunday at 2:00 AM)
systemctl start orion-update.timer

# Check timer status
systemctl status orion-update.timer
systemctl list-timers --all | grep orion

# View logs
journalctl -u orion-update.service -f
```

### Manual Updates

```bash
# Run update script manually
/mnt/nvme1/orion/scripts/update-datasets.sh

# Or dry run
/mnt/nvme1/orion/scripts/update-datasets.sh --dry-run

# View logs
tail -f /mnt/nvme1/orion/logs/update_*.log
```

### Customize Updates

Edit the update script to customize datasets:

```bash
nano /mnt/nvme1/orion/scripts/update-datasets.sh

# Modify the update_dataset calls at the end:
update_dataset "your search term" "domain" "collection" max_docs
```

---

## 📊 Monitoring

### Registry Statistics

```bash
# Via CLI
orion status

# Via SQLite
sqlite3 /mnt/nvme1/orion/data/metadata/ingestion.db <<EOF
SELECT
    document_type,
    status,
    COUNT(*) as count,
    SUM(chunk_count) as total_chunks
FROM documents
WHERE status = 'processed'
GROUP BY document_type, status;
EOF
```

### Qdrant Collections

```bash
# Via CLI
orion status

# Via API
curl http://localhost:6333/collections | jq '.result.collections[]'

# Collection details
curl http://localhost:6333/collections/technical-docs | jq
```

### Storage Usage

```bash
# Data directory
du -sh /mnt/nvme1/orion/data/raw/*

# Registry database
du -sh /mnt/nvme1/orion/data/metadata/ingestion.db

# Logs
du -sh /mnt/nvme1/orion/logs/
```

---

## 🔧 Advanced Usage

### Environment Variables

Configure via `.env` or export:

```bash
export ORION_BASE_DIR=/mnt/nvme1/orion
export QDRANT_URL=http://localhost:6333
export ANYTHINGLLM_URL=http://localhost:3001
export VLLM_URL=http://localhost:8000
export ANYTHINGLLM_API_KEY=your-key
export LOG_LEVEL=DEBUG
```

### Quality Gates

Configure per-domain quality thresholds in `src/domains.py`:

```python
DOMAINS = {
    "academic": DomainConfig(
        chunk_size=1024,
        chunk_overlap=128,
        quality_gates={
            "min_text_density": 0.55,  # Strict for papers
            "min_tokens": 500,
        }
    ),
    "manuals": DomainConfig(
        chunk_size=1024,
        chunk_overlap=128,
        quality_gates={
            "min_text_density": 0.35,  # Moderate for docs
            "min_tokens": 100,
        }
    ),
}
```

### Retrieval Settings

Hybrid search and reranking are enabled by default. After installation, configure on the host in `/mnt/nvme1/orion/config/optimal-settings.yaml` (copied from `research-qa/config/` during setup):

```yaml
retrieval:
  hybrid_search:
    enabled: true
    vector_weight: 0.7  # 70% semantic
    keyword_weight: 0.3  # 30% exact matching

  reranking:
    enabled: true
    model: "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k_input: 20  # Rerank top 20
    top_k_output: 5  # Return top 5
```

---

## 🧪 Testing

### Test Harvest

```bash
# Small test batch
orion harvest "kubernetes" --domain manuals --max-docs 5 --dry-run

# Verify downloads
ls -lh /mnt/nvme1/orion/data/raw/manuals/
```

### Test Processing

```bash
# Process test batch
orion process --domain manuals --max-files 5

# Check registry
sqlite3 /mnt/nvme1/orion/data/metadata/ingestion.db \
  "SELECT COUNT(*) FROM documents WHERE status='processed';"
```

### Test Embedding

```bash
# Embed test batch
orion embed technical-docs --max-docs 5

# Verify Qdrant
curl http://localhost:6333/collections/technical-docs | \
  jq '.result.points_count'
```

### Test Query

```bash
# Simple test query
orion query "kubernetes" --top-k 3

# Should return 3 results with scores and sources
```

---

## 🐛 Troubleshooting

### CLI Not Found

```bash
# Check symlink
ls -la /usr/local/bin/orion

# Recreate if needed
ln -sf /mnt/nvme1/orion/src/cli.py /usr/local/bin/orion
```

### Import Errors

```bash
# Activate virtual environment
cd /mnt/nvme1/orion
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Service Connection Errors

```bash
# Check Docker services
docker compose -f /mnt/nvme2/orion-project/setup/docker-compose.yml ps

# Check Qdrant
curl http://localhost:6333/collections

# Check vLLM
curl http://localhost:8000/health

# Check AnythingLLM
curl http://localhost:3001/api/ping
```

### No Results from Query

```bash
# Check collection exists
curl http://localhost:6333/collections | jq

# Check collection has vectors
curl http://localhost:6333/collections/technical-docs | \
  jq '.result.points_count'

# If empty, run embedding:
orion embed technical-docs
```

### Update Script Fails

```bash
# Check logs
tail -50 /mnt/nvme1/orion/logs/update_*.log

# Run manually with dry-run
/mnt/nvme1/orion/scripts/update-datasets.sh --dry-run

# Check systemd service
systemctl status orion-update.service
journalctl -u orion-update.service -n 50
```

---

## 📁 Directory Structure

```
/mnt/nvme1/orion/
├── src/
│   ├── cli.py                 # Main CLI entry point
│   ├── integration.py         # Integration utilities
│   ├── domains.py             # Domain configurations
│   ├── providers/             # Harvester providers (15)
│   ├── processing/            # Document processing
│   │   ├── orchestrator.py
│   │   ├── ingest.py
│   │   ├── registry.py
│   │   └── anythingllm_client.py
│   └── retrieval/             # Intelligence features
│       ├── hybrid_search.py
│       └── reranker.py
│
├── data/
│   ├── raw/                   # Downloaded documents
│   │   ├── academic/
│   │   ├── manuals/
│   │   ├── blogs/
│   │   └── github/
│   ├── metadata/
│   │   └── ingestion.db       # SQLite registry
│   └── cache/                 # Provider cache
│
├── config/                    # Created on host during setup
│   ├── search_terms.csv       # From harvester/config/
│   ├── domains.yaml           # Generated during setup
│   └── optimal-settings.yaml  # From research-qa/config/
│
├── scripts/
│   ├── update-datasets.sh
│   ├── setup-host.sh
│   ├── orion-update.service
│   └── orion-update.timer
│
├── logs/                      # Update logs
├── requirements.txt
├── .env                       # Environment config
└── README.md                  # This file
```

---

## 🎓 Performance Expectations

### Ingestion

- **Processing Speed:** 2-5 PDFs/sec (CPU-only)
- **Acceptance Rate:** >70% (domain-dependent)
- **Avg Chunks per Doc:** 15-30 (with 1024 tokens)
- **Embedding Speed:** 80 vectors/sec (batch_size=32)

### Query

- **Vector Search:** <100ms
- **Keyword Search:** <100ms
- **Hybrid Merge:** <50ms
- **Reranking (20→5):** 200-500ms
- **Total Latency:** <2000ms

### Quality

- **Context per Query:** 5,120 tokens (5 × 1024)
- **Recall Improvement:** +30-40% (hybrid search)
- **Relevance Improvement:** +20-30% (reranking)

---

## 📞 Support

### Documentation

- **Consolidation Plan:** `CONSOLIDATION-PLAN.md`
- **Optimization Guide:** `research-qa/OPTIMIZATION-IMPLEMENTATION-GUIDE.md`
- **Optimal Settings:** `research-qa/config/optimal-settings.yaml` (source, copied to host during setup)

### Logs

- **Update logs:** `/mnt/nvme1/orion/logs/update_*.log`
- **Systemd journal:** `journalctl -u orion-update.service`
- **Docker logs:** `docker compose logs -f <service>`

### Health Check

```bash
# Quick health check
python3 /mnt/nvme1/orion/src/integration.py

# Full system status
orion status
orion info
```

---

## 🔄 Migration from Separate Applications

If you have existing data in the separate harvester/research-qa applications:

```bash
# 1. Export existing data (on laptop)
cd /home/user/Laptop-MAIN/applications/orion-rag
tar czf orion-data-export.tar.gz \
  harvester/data/library/ \
  research-qa/data/

# 2. Transfer to host
scp orion-data-export.tar.gz lab:/tmp/

# 3. Extract on host
ssh lab
cd /mnt/nvme1/orion
tar xzf /tmp/orion-data-export.tar.gz

# 4. Move to proper locations
mv harvester/data/library/* data/raw/academic/
mv research-qa/data/* data/

# 5. Re-process to populate registry
orion process --domain academic
orion embed research-papers
```

---

**Status:** Production Ready ✅
**Maintainer:** ORION Project
**Version:** 1.0.0 (Consolidation)
**Created:** 2025-11-17
