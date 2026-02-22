# ORION RAG - Unified Host Consolidation Plan

**Created:** 2025-11-17
**Status:** Implementation Ready
**Goal:** Consolidate harvester + research-qa into unified pipeline on host

---

## 🎯 **What We're Building**

**Unified ORION pipeline** running entirely on host (192.168.5.10):

```
┌────────────────────────────────────────────────┐
│  Host: 192.168.5.10 (RTX 3090, 64GB RAM)      │
├────────────────────────────────────────────────┤
│                                                │
│  UNIFIED ORION PIPELINE                        │
│  ━━━━━━━━━━━━━━━━━━━━━                        │
│                                                │
│  1. HARVEST                                    │
│     ├─ 15 providers (academic + docs)          │
│     ├─ Quality gates (domain-specific)         │
│     └─ Download → /mnt/nvme1/raw/              │
│                                                │
│  2. PROCESS                                    │
│     ├─ Extract text (PDF/HTML/MD)              │
│     ├─ Apply quality gates                     │
│     └─ Semantic chunk (1024 tokens)            │
│                                                │
│  3. EMBED                                      │
│     ├─ nomic-embed-text-v1 (8192 capacity)     │
│     └─ Store in Qdrant                         │
│                                                │
│  4. QUERY                                      │
│     ├─ Hybrid search (vector + keyword)        │
│     ├─ Cross-encoder reranking                 │
│     └─ vLLM inference (Qwen2.5-14B)            │
│                                                │
│  SINGLE REGISTRY: ingestion.db                 │
│  SINGLE CONFIG: domains.py                     │
│  SCHEDULED UPDATES: cron/systemd               │
└────────────────────────────────────────────────┘
```

---

## 📂 **Target Directory Structure**

```
/mnt/nvme1/orion/                              # All code on host
├── src/
│   ├── providers/                             # From harvester (15 providers)
│   │   ├── base.py
│   │   ├── semantic_scholar.py
│   │   ├── arxiv.py
│   │   └── ... (13 more)
│   │
│   ├── processing/                            # From research-qa
│   │   ├── orchestrator.py                    # UNIFIED coordinator
│   │   ├── ingest.py                          # PDF/HTML processing
│   │   ├── chunker.py                         # Semantic chunking
│   │   └── registry.py                        # Single SQLite registry
│   │
│   ├── retrieval/                             # Intelligence features
│   │   ├── hybrid_search.py                   # Vector + keyword
│   │   └── reranker.py                        # Cross-encoder
│   │
│   ├── domains.py                             # Quality gates + config
│   └── cli.py                                 # Unified CLI
│
├── data/
│   ├── raw/                                   # Downloaded docs
│   │   ├── academic/
│   │   ├── manuals/
│   │   ├── blogs/
│   │   └── github/
│   ├── metadata/
│   │   └── ingestion.db                       # Single registry
│   └── cache/                                 # Provider cache
│
├── config/
│   ├── search_terms.csv                       # Harvest queries
│   ├── domains.yaml                           # Domain configs
│   └── optimal-settings.yaml                  # Reference config
│
├── scripts/
│   ├── update-datasets.sh                     # Weekly update job
│   └── verify-pipeline.sh                     # Health check
│
└── requirements.txt                           # All dependencies
```

---

## 🔧 **Implementation Steps**

### **Phase 1: Setup Host Environment (30 min)**

```bash
# SSH to host
ssh lab

# Create unified directory structure
mkdir -p /mnt/nvme1/orion/{src,data,config,scripts}
mkdir -p /mnt/nvme1/orion/data/{raw/{academic,manuals,blogs,github},metadata,cache}
mkdir -p /mnt/nvme1/orion/src/{providers,processing,retrieval}

# Clone repo to host (if not already there)
cd /mnt/nvme1
git clone <repo-url> orion-staging
# OR sync from laptop
rsync -av /home/user/Laptop-MAIN/applications/orion-rag/ lab:/mnt/nvme1/orion-staging/
```

### **Phase 2: Merge Code Components (1-2 hours)**

#### **2.1 Copy Providers (from harvester)**

```bash
# On host
cd /mnt/nvme1/orion

# Copy provider modules
cp -r orion-staging/harvester/src/providers/ src/
cp orion-staging/harvester/src/provider_factory.py src/providers/

# Verify all 15 providers present
ls src/providers/
# Should see: base.py, semantic_scholar.py, arxiv.py, openalex.py, etc.
```

#### **2.2 Copy Processing (from research-qa)**

```bash
# Copy processing modules
cp orion-staging/research-qa/src/orchestrator.py src/processing/
cp orion-staging/research-qa/src/ingest.py src/processing/
cp orion-staging/research-qa/src/registry.py src/processing/
cp orion-staging/research-qa/src/anythingllm_client.py src/processing/

# Copy optimized components
cp orion-staging/research-qa/src/domains.py src/
cp orion-staging/research-qa/src/hybrid_search.py src/retrieval/
cp orion-staging/research-qa/src/reranker.py src/retrieval/
```

#### **2.3 Copy Configurations**

```bash
# Search terms for harvesting
cp orion-staging/harvester/config/search_terms.csv config/

# Optimal settings reference
cp orion-staging/research-qa/config/optimal-settings.yaml config/

# Docker infrastructure (already in place)
# applications/orion-rag/infrastructure/docker-compose.yml
```

#### **2.4 Merge Requirements**

```bash
# Combine dependencies
cat orion-staging/harvester/requirements.txt > requirements.txt
cat orion-staging/research-qa/requirements.txt >> requirements.txt

# Remove duplicates (manual review)
sort requirements.txt | uniq > requirements-merged.txt
mv requirements-merged.txt requirements.txt
```

### **Phase 3: Create Unified CLI (1 hour)**

Create single entry point for all operations:

```python
# src/cli.py
import typer
from typing import Optional

app = typer.Typer()

@app.command()
def harvest(
    term: str,
    domain: str = "academic",
    max_docs: int = 50,
    new_only: bool = False
):
    """Harvest documents from providers"""
    from providers.provider_factory import ProviderFactory
    from processing.registry import IngestionRegistry

    registry = IngestionRegistry()
    factory = ProviderFactory()

    # Get providers for domain
    providers = factory.get_providers_for_domain(domain)

    for provider in providers:
        docs = provider.search(term, max_results=max_docs)

        for doc in docs:
            # Skip if already harvested
            if new_only and registry.is_harvested(doc.url):
                continue

            # Download and save
            download_document(doc, domain)
            registry.mark_harvested(doc.url)

@app.command()
def process(
    domain: str = "academic",
    max_files: Optional[int] = None,
    new_only: bool = False
):
    """Process raw documents"""
    from processing.orchestrator import ORIONOrchestrator
    from processing.registry import IngestionRegistry

    registry = IngestionRegistry()
    orchestrator = ORIONOrchestrator(registry)

    # Process documents
    raw_dir = f"/mnt/nvme1/orion/data/raw/{domain}"
    orchestrator.run(raw_dir, max_files=max_files, new_only=new_only)

@app.command()
def embed(
    collection: str,
    max_docs: Optional[int] = None,
    new_only: bool = False
):
    """Embed and index to Qdrant"""
    from processing.orchestrator import ORIONOrchestrator

    orchestrator = ORIONOrchestrator()
    orchestrator.embed_collection(collection, max_docs, new_only)

@app.command()
def query(
    question: str,
    collection: str = "technical-docs",
    top_k: int = 5,
    use_reranking: bool = True
):
    """Query the knowledge base"""
    from retrieval.hybrid_search import hybrid_search
    from retrieval.reranker import Reranker
    from processing.anythingllm_client import AnythingLLMClient
    from qdrant_client import QdrantClient

    qdrant = QdrantClient(url="http://localhost:6333")
    llm_client = AnythingLLMClient()

    # Hybrid search
    candidates = hybrid_search(
        qdrant, llm_client,
        collection_name=collection,
        query=question,
        top_k=20 if use_reranking else top_k
    )

    # Rerank if enabled
    if use_reranking:
        reranker = Reranker()
        results = reranker.rerank(question, candidates, top_k=top_k)
    else:
        results = candidates[:top_k]

    # Display results
    for i, r in enumerate(results, 1):
        print(f"\n{i}. Score: {r.score:.3f}")
        print(f"   {r.text[:200]}...")

@app.command()
def pipeline(
    query: str,
    domain: str = "academic",
    collection: str = "research-papers",
    max_docs: int = 50
):
    """Run complete pipeline: harvest → process → embed"""
    import typer

    typer.echo(f"🔍 Step 1/3: Harvesting documents for '{query}'")
    harvest(term=query, domain=domain, max_docs=max_docs, new_only=True)

    typer.echo(f"⚙️  Step 2/3: Processing documents")
    process(domain=domain, new_only=True)

    typer.echo(f"🧠 Step 3/3: Embedding and indexing")
    embed(collection=collection, new_only=True)

    typer.echo(f"✅ Pipeline complete! Query with: orion query '{query}'")

if __name__ == "__main__":
    app()
```

### **Phase 4: Create Update Scripts (30 min)**

#### **4.1 Weekly Update Script**

```bash
# scripts/update-datasets.sh
#!/bin/bash
set -euo pipefail

LOG_DIR="/mnt/nvme1/orion/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/update_${TIMESTAMP}.log"

# Function: update dataset
update_dataset() {
    local TERM="$1"
    local DOMAIN="$2"
    local COLLECTION="$3"

    echo "[$(date)] Updating: $TERM ($DOMAIN)" | tee -a "$LOG_FILE"

    # Harvest new documents
    orion harvest --term "$TERM" --domain "$DOMAIN" --new-only 2>&1 | tee -a "$LOG_FILE"

    # Process new documents
    orion process --domain "$DOMAIN" --new-only 2>&1 | tee -a "$LOG_FILE"

    # Embed new documents
    orion embed --collection "$COLLECTION" --new-only 2>&1 | tee -a "$LOG_FILE"

    echo "[$(date)] ✅ Completed: $TERM" | tee -a "$LOG_FILE"
}

# Update datasets
echo "==================================" | tee -a "$LOG_FILE"
echo "ORION Weekly Update: $(date)" | tee -a "$LOG_FILE"
echo "==================================" | tee -a "$LOG_FILE"

update_dataset "kubernetes autoscaling" "manuals" "technical-docs"
update_dataset "proxmox gpu passthrough" "manuals" "technical-docs"
update_dataset "vector databases" "academic" "research-papers"
update_dataset "qdrant optimization" "technical" "technical-docs"

echo "==================================" | tee -a "$LOG_FILE"
echo "✅ All updates complete!" | tee -a "$LOG_FILE"
echo "==================================" | tee -a "$LOG_FILE"
```

#### **4.2 Systemd Timer (Scheduled Updates)**

```ini
# /etc/systemd/system/orion-update.service
[Unit]
Description=ORION Dataset Update
After=network.target docker.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/mnt/nvme1/orion
ExecStart=/mnt/nvme1/orion/scripts/update-datasets.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/orion-update.timer
[Unit]
Description=ORION Weekly Dataset Update
Requires=orion-update.service

[Timer]
OnCalendar=Sun *-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# Enable timer
systemctl daemon-reload
systemctl enable orion-update.timer
systemctl start orion-update.timer

# Check status
systemctl status orion-update.timer
systemctl list-timers --all | grep orion
```

### **Phase 5: Install Dependencies (15 min)**

```bash
# On host
cd /mnt/nvme1/orion

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Verify critical packages
python -c "from sentence_transformers import CrossEncoder; print('✓ Reranking ready')"
python -c "from langchain.text_splitter import RecursiveCharacterTextSplitter; print('✓ Semantic chunking ready')"
python -c "from qdrant_client import QdrantClient; print('✓ Qdrant client ready')"
python -c "import tiktoken; print('✓ Tokenizer ready')"
```

### **Phase 6: Test End-to-End (30 min)**

```bash
# Activate environment
cd /mnt/nvme1/orion
source .venv/bin/activate

# Make CLI executable
chmod +x src/cli.py
ln -s /mnt/nvme1/orion/src/cli.py /usr/local/bin/orion

# Test 1: Harvest small batch
orion harvest \
  --term "kubernetes autoscaling" \
  --domain manuals \
  --max-docs 10

# Verify downloads
ls -lh data/raw/manuals/

# Test 2: Process documents
orion process --domain manuals --max-files 10

# Verify registry
sqlite3 data/metadata/ingestion.db "SELECT COUNT(*) FROM documents;"

# Test 3: Embed to Qdrant
orion embed --collection technical-docs --max-docs 10

# Verify Qdrant
curl http://localhost:6333/collections/technical-docs | jq '.result.points_count'

# Test 4: Query
orion query "kubernetes autoscaling best practices"

# Should return results with sources!
```

---

## 🔄 **Migration from Laptop**

If you have existing data on laptop:

### **One-Time Data Migration**

```bash
# On laptop - package existing data
cd /home/user/Laptop-MAIN/applications/orion-rag
tar czf orion-data-export.tar.gz \
  harvester/data/library/ \
  research-qa/data/

# Transfer to host
scp orion-data-export.tar.gz lab:/tmp/

# On host - extract to new location
ssh lab
cd /mnt/nvme1/orion
tar xzf /tmp/orion-data-export.tar.gz

# Move to proper locations
mv harvester/data/library/* data/raw/academic/
mv research-qa/data/* data/

# Re-process to populate registry
orion process --domain academic --all
```

---

## 📊 **Usage Patterns**

### **Daily Operations**

```bash
# Check system health
systemctl status orion-update.timer
tail -f /mnt/nvme1/orion/logs/update_*.log

# Manual harvest for specific topic
orion harvest --term "vector databases" --domain academic --max-docs 50
orion process --domain academic --new-only
orion embed --collection research-papers --new-only

# Query knowledge base
orion query "What are Qdrant best practices?"
```

### **Weekly Maintenance**

```bash
# Check update logs
cd /mnt/nvme1/orion/logs
ls -lht | head -10

# Review registry stats
sqlite3 data/metadata/ingestion.db <<EOF
SELECT
    document_type,
    collection_name,
    COUNT(*) as count,
    SUM(chunk_count) as total_chunks
FROM documents
WHERE status = 'processed'
GROUP BY document_type, collection_name;
EOF

# Check Qdrant collections
curl http://localhost:6333/collections | jq '.result.collections[] | {name, points_count}'
```

### **Monthly Review**

```bash
# Acceptance rates by domain
sqlite3 data/metadata/ingestion.db <<EOF
SELECT
    document_type,
    status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY document_type), 1) as percentage
FROM documents
GROUP BY document_type, status;
EOF

# Storage usage
du -sh data/raw/*
du -sh data/metadata/
```

---

## ✅ **Verification Checklist**

Before going to production:

### **Infrastructure**
- [ ] Docker services running (vLLM, Qdrant, AnythingLLM)
- [ ] GPU accessible (`nvidia-smi` shows RTX 3090)
- [ ] vLLM at 0.85 GPU utilization
- [ ] Qdrant collections created

### **Code**
- [ ] All providers copied to `/mnt/nvme1/orion/src/providers/`
- [ ] Processing modules in `/mnt/nvme1/orion/src/processing/`
- [ ] Retrieval modules in `/mnt/nvme1/orion/src/retrieval/`
- [ ] Unified CLI working (`orion --help`)
- [ ] All dependencies installed

### **Configuration**
- [ ] `domains.py` shows 1024 token chunks
- [ ] `search_terms.csv` available
- [ ] `optimal-settings.yaml` reviewed
- [ ] Registry database initialized

### **Testing**
- [ ] Harvest 10 test documents ✓
- [ ] Process test documents ✓
- [ ] Embed to Qdrant ✓
- [ ] Query returns results ✓
- [ ] Hybrid search works ✓
- [ ] Reranking works ✓

### **Automation**
- [ ] Update script created (`scripts/update-datasets.sh`)
- [ ] Systemd timer configured
- [ ] Timer enabled and scheduled
- [ ] Test run successful

---

## 🎯 **Success Metrics**

After consolidation, you should have:

✅ **Single unified system** on host (no laptop dependency)
✅ **Automated updates** (weekly via systemd timer)
✅ **Multiple datasets** (kubernetes, proxmox, vector-db, etc.)
✅ **Smart deduplication** (registry prevents re-processing)
✅ **Production quality** (1024 tokens, hybrid search, reranking)
✅ **Simple operations** (single `orion` command)

---

## 📞 **Next Steps**

1. **Review this plan** - Make sure it matches your vision
2. **Execute Phase 1-3** - Set up host environment and merge code
3. **Test with small batch** - Verify pipeline works end-to-end
4. **Set up automation** - Configure systemd timer for updates
5. **Go to production** - Start harvesting and building knowledge base

**Estimated Total Time:** 4-6 hours for complete consolidation

---

**Status:** Ready for implementation ✅
**Risk Level:** Low (clean slate, no migration pain)
**Complexity:** Medium (consolidation + testing)
**Reward:** Unified, production-grade RAG system
