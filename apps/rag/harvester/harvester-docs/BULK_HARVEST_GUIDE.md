# Bulk Overnight Harvest Guide

This guide explains how to dramatically scale up document collection to **thousands of reference documents** for overnight harvesting.

## Quick Start for Thousands of Documents

### 1. Configure for Maximum Results

```bash
# Set environment variable to get 50 results per term per provider
export ORION_MAX_RESULTS_PER_TERM=50

# With 100 search terms × 10 providers × 50 results = 50,000 potential documents
# (After dedup + relevance filtering, expect ~5,000-10,000 high-quality docs)
```

### 2. Get API Keys (Critical for Scale)

Without API keys, you'll hit rate limits quickly. **These are required for overnight harvesting:**

```bash
# GitHub (5,000 requests/hour vs 60 unauthenticated)
export ORION_GITHUB_TOKEN="ghp_xxxxx"
# Get at: https://github.com/settings/tokens (needs 'public_repo' scope)

# Stack Overflow (10,000 requests/day vs 300 unauthenticated)
export ORION_SO_API_KEY="xxxxx"
# Get at: https://stackapps.com/apps/oauth/register

# Semantic Scholar (optional, higher limits)
export ORION_S2_API_KEY="xxxxx"
# Request at: https://www.semanticscholar.org/product/api#api-key-form

# CORE (1,000 requests/day free tier)
export ORION_CORE_API_KEY="xxxxx"
# Get at: https://core.ac.uk/services/api

# Contact email (polite API headers)
export ORION_CONTACT_EMAIL="your@email.com"
```

### 3. Expand Your Search Terms

Current: 100 terms → Target: 200-500 terms

```bash
# Add more search terms to search_terms.csv
# Each term × 10 providers × 50 results = 500 potential documents per term
```

**Strategy for term expansion:**
- Add **broader terms** (e.g., "machine learning GPU", "database optimization")
- Add **specific sub-topics** (e.g., "CUDA warp scheduling", "PostgreSQL MVCC")
- Add **tool names** (e.g., "Kubernetes CRD", "Docker BuildKit")
- Add **architecture patterns** (e.g., "event sourcing", "CQRS pattern")
- Add **vendor-specific** (e.g., "NVIDIA Hopper architecture", "AMD RDNA3")

### 4. Launch Overnight Harvest

```bash
# Using unified CLI (recommended)
nohup orion harvest --max-results 50 > harvest_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Or via Makefile
nohup make harvest > harvest_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Follow progress in real-time
tail -f data/harvester.log

# Check status
orion validate library --stats

# Legacy script method (still supported):
# nohup bash -c '
#   export ORION_MAX_RESULTS_PER_TERM=50
#   export ORION_GITHUB_TOKEN="ghp_xxxxx"
#   export ORION_SO_API_KEY="xxxxx"
#   export ORION_CONTACT_EMAIL="your@email.com"
#   ./harvest_and_process.sh > harvest_$(date +%Y%m%d_%H%M%S).log 2>&1
# ' &
```

## Scaling Strategies

### Low Scale (1,000 documents)
```bash
export ORION_MAX_RESULTS_PER_TERM=10
# 100 terms × 10 providers × 10 results = 10,000 candidates
# After filtering: ~1,000 high-quality documents
```

### Medium Scale (5,000 documents)
```bash
export ORION_MAX_RESULTS_PER_TERM=30
# 100 terms × 10 providers × 30 results = 30,000 candidates
# After filtering: ~5,000 high-quality documents
```

### High Scale (10,000+ documents)
```bash
export ORION_MAX_RESULTS_PER_TERM=50
# Add 200+ search terms
# 200 terms × 10 providers × 50 results = 100,000 candidates
# After filtering: ~10,000-15,000 high-quality documents
```

### Provider-Specific Limits

The harvester respects API limits:
- **Semantic Scholar**: Max 100 per query (enforced)
- **arXiv**: No hard limit (use your ORION_MAX_RESULTS_PER_TERM)
- **CORE**: Max 100 per query (enforced)
- **OpenAlex**: No strict limit (use your ORION_MAX_RESULTS_PER_TERM)
- **Crossref**: Max 1000 per query (enforced)
- **Zenodo**: Max 500 per page (enforced)
- **GitHub**: Max 100 per page (enforced), pagination possible
- **Stack Overflow**: Max 100 per page (enforced)
- **Official Docs**: Limited by search implementation
- **Tech Blogs**: Limited by RSS feed entries

## Rate Limiting & Timing

### Conservative (Default)
```bash
# 5 second delay between API calls
# ~720 requests/hour
# Full CSV (100 terms × 10 providers = 1000 requests) = ~1.5 hours
```

### Aggressive (with API keys)
```bash
# 1 second delay (only with authentication!)
export ORION_RATE_LIMIT_DELAY=1  # TODO: Add this env var support

# ~3,600 requests/hour
# Full CSV (100 terms × 10 providers) = ~15 minutes
```

## Quality vs Quantity Tradeoffs

### Maximum Quality (Current Default)
```bash
export ORION_MAX_RESULTS_PER_TERM=5
export ORION_MIN_GITHUB_STARS=100
export ORION_MIN_SO_SCORE=10
export ORION_USE_EMBEDDINGS=true
# Result: Highly curated, 100% relevant documents
```

### Balanced (Recommended for Bulk)
```bash
export ORION_MAX_RESULTS_PER_TERM=30
export ORION_MIN_GITHUB_STARS=50
export ORION_MIN_SO_SCORE=5
export ORION_USE_EMBEDDINGS=false  # Faster without embeddings
# Result: Good quality, 3-6x more documents
```

### Maximum Coverage (Research/Exploration)
```bash
export ORION_MAX_RESULTS_PER_TERM=100
export ORION_MIN_GITHUB_STARS=10
export ORION_MIN_SO_SCORE=1
export ORION_USE_EMBEDDINGS=false
# Result: Comprehensive coverage, manual review needed
```

## Monitoring Long-Running Harvests

### Check Progress
```bash
# Watch harvester log
tail -f data/harvester.log

# Count documents so far
jq '.downloads | length' data/library_metadata.json

# Check processing status
jq '[.downloads[] | select(.processing.status == "success")] | length' data/library_metadata.json

# See what's being downloaded
ls -lh data/library/*/ | tail -20
```

### Disk Space Requirements

Estimate: **~1MB per document average**

- 1,000 documents: ~1 GB raw + ~500 MB processed = **1.5 GB**
- 5,000 documents: ~5 GB raw + ~2.5 GB processed = **7.5 GB**
- 10,000 documents: ~10 GB raw + ~5 GB processed = **15 GB**

Check available space:
```bash
df -h /home/jp/orion_harvester/data/
```

## Stopping and Resuming

### Graceful Stop
```bash
# Press Ctrl+C once (will finish current download)
# Or send SIGTERM:
pkill -TERM -f "orion_harvester.py"
```

### Resume from Where You Left Off
```bash
# The harvester automatically skips already-downloaded papers
.venv/bin/python3 orion_harvester.py --new-only

# Or continue with harvest_and_process.sh
./harvest_and_process.sh --new-only
```

## Troubleshooting

### Rate Limit Errors
```
Solution: Add API keys (see section 2 above)
Workaround: Increase RATE_LIMIT_DELAY in orion_harvester.py
```

### Disk Full
```
Solution: Mount additional storage
Workaround: Reduce MAX_RESULTS_PER_TERM
```

### Low Relevance
```
Solution: Enable embeddings (export ORION_USE_EMBEDDINGS=true)
Workaround: Tighten thresholds (MIN_GITHUB_STARS, MIN_SO_SCORE)
Check: Use --dry-run --diagnostics on sample terms first
```

### Slow Processing
```
Solution: Processing runs sequentially; it's I/O bound
Parallelization: Run multiple process_library.py --category X in parallel
```

## Example: Overnight 10K Document Harvest

```bash
#!/bin/bash
# save as: mega_harvest.sh

# 1. Set aggressive configuration
export ORION_MAX_RESULTS_PER_TERM=50
export ORION_MIN_GITHUB_STARS=50
export ORION_MIN_SO_SCORE=5
export ORION_USE_EMBEDDINGS=false  # Faster
export ORION_CONTACT_EMAIL="your@email.com"

# 2. Add your API keys
export ORION_GITHUB_TOKEN="ghp_xxxxxxxxxxxxx"
export ORION_SO_API_KEY="xxxxxxxxxxxxxx"
export ORION_S2_API_KEY="xxxxxxxxxxxxxx"
export ORION_CORE_API_KEY="xxxxxxxxxxxxxx"

# 3. Ensure enough disk space (15GB+)
df -h /home/jp/orion_harvester/data/

# 4. Launch harvest + processing
echo "Starting mega harvest at $(date)"
.venv/bin/python3 orion_harvester.py > "mega_harvest_$(date +%Y%m%d_%H%M%S).log" 2>&1

# 5. Process all documents
echo "Processing documents at $(date)"
.venv/bin/python3 process_library.py >> "mega_harvest_$(date +%Y%m%d_%H%M%S).log" 2>&1

echo "Completed at $(date)"

# 6. Generate final report
.venv/bin/python3 orion_harvester.py report
```

Run it:
```bash
chmod +x mega_harvest.sh
nohup ./mega_harvest.sh &
```

## Expected Results

### With Current 100 Terms + MAX_RESULTS=50:

| Provider | Results/Term | Total Candidates | After Filtering |
|----------|--------------|------------------|-----------------|
| Papers (6 APIs) | 50 × 6 = 300 | 30,000 | ~8,000 |
| GitHub | 50 | 5,000 | ~2,000 |
| Stack Overflow | 50 | 5,000 | ~1,500 |
| Official Docs | 50 | 5,000 | ~1,000 |
| Tech Blogs | 50 | 5,000 | ~500 |
| **TOTAL** | **500/term** | **50,000** | **~13,000** |

**Reality check:** After deduplication + relevance filtering, expect **5,000-8,000 high-quality documents** from 50,000 candidates (10-16% acceptance rate).

## Post-Harvest Analysis

```bash
# Summary report
.venv/bin/python3 orion_harvester.py report

# Export high-value papers
.venv/bin/python3 orion_harvester.py export --format csv --min-citations 100 --output highly_cited.csv

# Check category distribution
jq '[.downloads[] | .category] | group_by(.) | map({category: .[0], count: length}) | sort_by(-.count)' data/library_metadata.json

# Find processing failures
jq '[.downloads[] | select(.processing.status != "success")] | length' data/library_metadata.json
```

## Post-Harvest Processing & Embedding Pipeline

### 1. Process Documents (Required Before Embedding)

**If using GPU host for acceleration (recommended):**

```bash
# Sync library to host with GPU
rsync -az --info=progress2 data/library/ root@192.168.5.10:/tmp/orion_pipeline/data/library/
rsync -az data/library_metadata.json root@192.168.5.10:/tmp/orion_pipeline/data/

# Process on 20-core host (much faster than workstation)
ssh root@192.168.5.10 << 'EOF'
cd /tmp/orion_pipeline
source .venv/bin/activate
python process_library.py
EOF

# Expected: 100% success rate, ~10 minutes for 1,403 docs on Intel Core Ultra 7 265K
```

**Local processing (slower):**
```bash
.venv/bin/python3 process_library.py
# Processes all documents in data/library/
# Outputs: data/processed/{markdown,text,structured}/
```

### 2. Validate Processing Quality

```bash
# Check processing results
.venv/bin/python3 scripts/validate_processed_data.py

# Quick failure analysis
.venv/bin/python3 scripts/analyze_broken_simple.py

# Expected: 100% success, 0 failures
```

### 3. Build RAG Embeddings (Quality-First Approach)

**⚠️ CRITICAL: Do NOT skip validation steps**

The embedding pipeline uses **token-aware re-chunking** to avoid quality loss:
- Original chunks: ~721 tokens avg (from processing)
- BGE-large limit: 512 tokens max
- Solution: Split into 512-token sub-chunks with 64 overlap
- Result: ~2.1× more vectors but no truncation

**Step 3a: Analyze Token Distributions (Safe, No Embedding)**

```bash
# On GPU host
ssh root@192.168.5.10 << 'EOF'
cd /tmp/orion_pipeline
source .venv/bin/activate

# Full corpus analysis
python scripts/validate_rechunking.py --max-tokens 512 --overlap 64

# Or sample for quick check
python scripts/embed_and_index.py --analyze --sample 200
EOF

# Expected output:
# - Avg tokens per chunk
# - Projected sub-chunk count
# - ETA estimate
# - JSON report saved to reports/
```

**Step 3b: Sandbox E2E Quality Test (Requires Approval)**

```bash
# Small embedding test with real queries
ssh root@192.168.5.10 << 'EOF'
cd /tmp/orion_pipeline
source .venv/bin/activate

python scripts/validate_sandbox_retrieval.py \
  --per-category 3 \
  --max-files 15 \
  --topk 5
EOF

# Expected output:
# - Precision@5 for 5 ORION domain queries
# - Pass/fail status (need P@5 ≥ 0.6 for 4/5 queries)
# - Temp collection name for inspection

# Cleanup temp collection after review:
ssh root@192.168.5.10 "curl -X DELETE http://localhost:6333/collections/orion_homelab_sandbox_XXXXXXXX"
```

**Step 3c: Full Embedding Run (Only After Validation Passes)**

```bash
# Start full embedding (10-12 hours for 1.95M vectors)
ssh root@192.168.5.10 << 'EOF'
cd /tmp/orion_pipeline
source .venv/bin/activate

nohup python scripts/embed_and_index.py > embedding_run_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > embedding_run.pid
echo "Embedding started with PID: $(cat embedding_run.pid)"
EOF

# Monitor progress (from workstation)
ssh root@192.168.5.10 'tail -f /tmp/orion_pipeline/embedding_run_*.log'

# Check GPU utilization
ssh root@192.168.5.10 'watch -n 30 nvidia-smi'

# Check Qdrant vector count growth
while true; do
  ssh root@192.168.5.10 "curl -s http://localhost:6333/collections/orion_homelab | jq -r '.result.points_count'"
  sleep 300  # Every 5 minutes
done
```

**Step 3d: Post-Embedding Validation**

```bash
# Verify final collection state
ssh root@192.168.5.10 "curl -s http://localhost:6333/collections/orion_homelab | jq '.result'"

# Test retrieval
ssh root@192.168.5.10 << 'EOF'
cd /tmp/orion_pipeline
source .venv/bin/activate
python scripts/query_rag.py "vLLM continuous batching configuration"
EOF

# Sync results back to workstation
rsync -az root@192.168.5.10:/tmp/orion_pipeline/data/qdrant_storage/ data/qdrant_storage/
rsync -az root@192.168.5.10:/tmp/orion_pipeline/embedding_run_*.log logs/
```

### 4. Quality Audit & Filter Tuning

```bash
# Summary report
.venv/bin/python3 orion_harvester.py report

# Export high-value papers
.venv/bin/python3 orion_harvester.py export --format csv --min-citations 100 --output highly_cited.csv

# Check category distribution
jq '[.downloads[] | .category] | group_by(.) | map({category: .[0], count: length}) | sort_by(-.count)' data/library_metadata.json

# Find processing failures (should be 0)
jq '[.downloads[] | select(.processing.status != "success")] | length' data/library_metadata.json
```

### 5. Launch RAG Query Interface

```bash
# CLI query tool
ssh root@192.168.5.10 << 'EOF'
cd /tmp/orion_pipeline
source .venv/bin/activate
python scripts/query_rag.py "How do I configure Proxmox for bare metal GPU access?"
EOF

# Web UI (Gradio interface)
ssh root@192.168.5.10 << 'EOF'
cd /tmp/orion_pipeline
source .venv/bin/activate
python scripts/web_ui.py
EOF
# Then open http://192.168.5.10:7860 in browser
```

## Important Notes for Embedding Pipeline

- **Token re-chunking is mandatory** - Avg chunks are 721 tokens, model max is 512
- **Validation before full run** - 10-12 hour embedding time requires confidence
- **Quality gates must pass** - P@5 ≥ 0.6 for ORION queries
- **GPU acceleration recommended** - RTX 3090 Ti: ~50-60 chunks/sec (CPU: ~5 chunks/sec)
- **Complete guide:** See [`../EMBEDDING_MIGRATION_GUIDE.md`](../EMBEDDING_MIGRATION_GUIDE.md)

---

**Pro Tip:** Start with `MAX_RESULTS_PER_TERM=20` on a subset of terms (10-20 terms) to validate your filtering is working correctly before committing to a full overnight harvest of thousands of documents.
