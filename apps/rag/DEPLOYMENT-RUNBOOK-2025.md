# ORION RAG Deployment Runbook (2025)

**Created:** 2025-11-19
**Purpose:** Step-by-step deployment guide with production best practices
**Config Reference:** `PRODUCTION-CONFIG-2025.md`
**Estimated Time:** 6-8 hours (including test batch)

---

## ⚡ QUICK START (TL;DR)

```bash
# 1. Make configuration changes (ON LAPTOP)
cd /home/user/Laptop-MAIN
# (Files already updated: domains.py, docker-compose.yml)

# 2. Commit and push
git add -A
git commit -m "feat(rag): apply 2025 production config - BGE-M3, optimized chunks, quality gates"
git push origin claude/review-document-pipeline-018oDkKULerUtxVaS4bDdaWT

# 3. Deploy to host (ON HOST)
cd /root/orion/applications/orion-rag/infrastructure
docker compose down
docker compose up -d
docker compose logs -f anythingllm  # Watch BGE-M3 model loading

# 4. Run test batch (ON HOST)
cd /root/orion/applications/orion-rag/research-qa
python3 src/orchestrator.py --dry-run --limit 100

# 5. Start production processing
python3 src/orchestrator.py --batch-size 500
```

---

## 📋 PRE-DEPLOYMENT CHECKLIST

### On Laptop (Source of Truth)

- [ ] **Review configuration changes**
  - [ ] Read `PRODUCTION-CONFIG-2025.md` (understand WHY)
  - [ ] Verify `applications/orion-rag/research-qa/src/domains.py` updated
  - [ ] Verify `applications/orion-rag/infrastructure/docker-compose.yml` updated
  - [ ] Check backup script exists: `scripts/ops/backup-orion-rag.sh`
  - [ ] Check monitoring script exists: `scripts/ops/monitor-ingestion.sh`

- [ ] **Git workflow (CRITICAL - follow laptop-host sync)**
  ```bash
  # Verify you're on correct branch
  git branch
  # Should show: claude/review-document-pipeline-018oDkKULerUtxVaS4bDdaWT

  # Check git status
  git status
  # Should show modified: domains.py, docker-compose.yml, new scripts

  # Review changes
  git diff applications/orion-rag/research-qa/src/domains.py
  git diff applications/orion-rag/infrastructure/docker-compose.yml

  # Stage changes
  git add applications/orion-rag/research-qa/src/domains.py
  git add applications/orion-rag/infrastructure/docker-compose.yml
  git add applications/orion-rag/PRODUCTION-CONFIG-2025.md
  git add applications/orion-rag/DEPLOYMENT-RUNBOOK-2025.md
  git add scripts/ops/backup-orion-rag.sh
  git add scripts/ops/monitor-ingestion.sh

  # Commit with descriptive message
  git commit -m "$(cat <<'EOF'
feat(rag): apply 2025 production best practices

Major changes based on 2025 research:
- Switch embedding model: nomic-embed-text-v1 → BAAI/bge-m3 (1024d)
  Reason: 72% vs 71% accuracy on technical content (2025 benchmarks)

- Optimize chunk sizes:
  * Academic: 1024 tokens (keep) - optimal 800-1200 per arXiv 2025
  * Manuals: 1024→512 tokens - optimal 300-500 per Databricks
  * Blogs: 1024→512 tokens - tighter chunks for shorter content
  * GitHub: 512 tokens (keep) - optimal 256-512 for code

- Increase overlap: 12.5%→20% (industry standard for continuity)

- Lower quality gates (was rejecting good docs):
  * Academic: 0.55→0.40 text density
  * Manuals: 0.35→0.30 text density
  * GitHub: 0.20→0.15 text density

- Add production-grade backup system:
  * Automated Qdrant snapshots
  * Daily backups with 7-day retention
  * Backup verification and manifests

- Add real-time monitoring dashboard

See: applications/orion-rag/PRODUCTION-CONFIG-2025.md
EOF
)"

  # Push to remote (syncs to both GitHub and lab host)
  git push origin claude/review-document-pipeline-018oDkKULerUtxVaS4bDdaWT
  ```

- [ ] **Verify sync completed**
  ```bash
  # Check GitHub push succeeded
  git log origin/claude/review-document-pipeline-018oDkKULerUtxVaS4bDdaWT --oneline -1

  # Check lab host has changes (if accessible)
  # (Or verify after SSH in next section)
  ```

### On Host (Deployment Target)

**SSH into host:**
```bash
ssh lab
```

- [ ] **Verify git sync**
  ```bash
  cd /root/orion
  git fetch origin
  git log origin/claude/review-document-pipeline-018oDkKULerUtxVaS4bDdaWT --oneline -5
  # Should show your recent commit

  # Check if working tree is clean
  git status
  ```

- [ ] **Check disk space**
  ```bash
  df -h /mnt/nvme1  # Should have >50GB free for backups
  df -h /mnt/nvme2  # Should have >20GB free for Qdrant
  ```

- [ ] **Check Docker services**
  ```bash
  cd /root/orion/applications/orion-rag/infrastructure
  docker compose ps
  # All services should be "Up" and "healthy"
  ```

- [ ] **Check current Qdrant state (should be empty)**
  ```bash
  curl -s http://localhost:6333/collections | python3 -c "import sys, json; print(json.dumps(json.load(sys.stdin), indent=2))"
  # Should show: "collections": []
  ```

---

## 🚀 DEPLOYMENT STEPS

### Step 1: Stop Services and Deploy New Configuration

**On Host:**

```bash
cd /root/orion/applications/orion-rag/infrastructure

# Stop all services gracefully
docker compose down

# Verify services stopped
docker ps | grep orion
# Should show nothing

# Pull latest images (if needed)
docker compose pull anythingllm

# Start services with new configuration
docker compose up -d

# Watch startup logs
docker compose logs -f
```

**Watch for:**
- ✅ Qdrant: `Qdrant started successfully`
- ✅ vLLM: `Qwen2.5-14B-Instruct-AWQ loaded successfully`
- ✅ AnythingLLM: **CRITICAL** - Watch for embedding model loading:
  ```
  [INFO] Loading embedding model: BAAI/bge-m3
  [INFO] Model loaded successfully. Dimensions: 1024
  ```

**If you see nomic-embed-text-v1 loading instead:**
```bash
# Docker didn't pick up new environment variable
docker compose down
docker compose rm anythingllm
docker compose up -d anythingllm
docker compose logs -f anythingllm
```

Press Ctrl+C when all services are healthy (2-3 minutes).

### Step 2: Verify BGE-M3 Embedding Model

**On Host:**

```bash
# Check AnythingLLM environment
docker exec orion-anythingllm env | grep EMBEDDING
# Should show:
# EMBEDDING_MODEL_PREF=BAAI/bge-m3
# EMBEDDING_MODEL_MAX_CHUNK_LENGTH=8192
# EMBEDDING_BATCH_SIZE=32

# Test embedding (create test workspace)
curl -X POST "http://localhost:3001/api/v1/workspace/new" \
  -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "test-bge-m3"}'

# Upload a test document and verify dimensions
# (Should create 1024-dimensional vectors)
```

### Step 3: Setup Backup System

**On Host:**

```bash
# Make backup script executable
chmod +x /root/orion/scripts/ops/backup-orion-rag.sh

# Create backup directory
mkdir -p /mnt/nvme1/backups/orion-rag

# Test backup script (dry run)
/root/orion/scripts/ops/backup-orion-rag.sh

# Should output:
# [SUCCESS] Backup Completed Successfully

# Verify backup created
ls -lh /mnt/nvme1/backups/orion-rag/
# Should show:
# - BACKUP_MANIFEST_<timestamp>.txt
# - qdrant/, metadata/, anythingllm/, snapshots/

# Schedule daily backups (cron)
crontab -e
# Add this line:
# 0 3 * * * /root/orion/scripts/ops/backup-orion-rag.sh >> /mnt/nvme2/orion-project/logs/backup-cron.log 2>&1
```

### Step 4: Test Batch (100 Documents)

**On Host (Terminal 1 - Monitoring):**

```bash
# Make monitoring script executable
chmod +x /root/orion/scripts/ops/monitor-ingestion.sh

# Start monitoring dashboard
/root/orion/scripts/ops/monitor-ingestion.sh
```

**On Host (Terminal 2 - Processing):**

```bash
cd /root/orion/applications/orion-rag/research-qa

# Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set API key
export ANYTHINGLLM_API_KEY="<your-key>"

# Run test batch (first 100 documents)
python3 src/orchestrator.py \
  --document-root /mnt/nvme1/orion-data/documents/raw \
  --limit 100 \
  --batch-size 10

# Watch output for:
# - Documents scanned by domain
# - Quality gate pass/fail
# - Upload progress
# - Embedding time
```

**Expected Output:**
```
[INFO] Scanning documents from /mnt/nvme1/orion-data/documents/raw
[INFO] Found 2,521 documents across 4 domains

Domain Breakdown:
  academic: 493 PDFs
  manuals: 1,410 files
  blogs: 508 files
  github: 110 files

[INFO] Processing first 100 documents...

[INFO] [1/100] academic/vector-databases/FAISS_Paper.pdf
  Quality: PASS (density: 0.42, length: 12,450 chars)
  Workspace: research-papers
  Chunks: 38 created
  ✓ Uploaded successfully

[INFO] [2/100] manuals/proxmox/GPU_Passthrough.pdf
  Quality: PASS (density: 0.31, length: 5,200 chars)
  Workspace: technical-docs
  Chunks: 18 created
  ✓ Uploaded successfully

...

[SUCCESS] Test batch complete!
  Processed: 100 documents
  Uploaded: 94 documents
  Rejected: 6 documents (6% - ACCEPTABLE)
  Failed: 0 documents
  Average chunks: 28.5 per document
  Total chunks: 2,679
```

**Switch to Terminal 1 (Monitoring Dashboard)**

Check for:
- ✅ Rejection rate <10% for academic
- ✅ Rejection rate <5% for manuals/blogs
- ✅ No processing errors
- ✅ Qdrant collections created with 1024-dim vectors

### Step 5: Review Test Batch Results

**On Host:**

```bash
# Check Qdrant collections
curl -s http://localhost:6333/collections | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data['result']['collections']:
    print(f\"{c['name']}: {c['points_count']} vectors, {c['config']['params']['vectors']['size']}d\")
"

# Should show:
# research-papers: ~1200 vectors, 1024d
# technical-docs: ~1400 vectors, 1024d
# code-examples: ~80 vectors, 1024d

# Check ingestion registry
sqlite3 /mnt/nvme1/orion-data/documents/metadata/ingestion.db "
SELECT
  status,
  COUNT(*) as count,
  ROUND(AVG(chunk_count), 1) as avg_chunks
FROM documents
GROUP BY status;
"

# Check rejection reasons
sqlite3 /mnt/nvme1/orion-data/documents/metadata/ingestion.db "
SELECT
  error_message,
  COUNT(*) as count
FROM documents
WHERE status = 'rejected'
GROUP BY error_message
ORDER BY count DESC;
"
```

**Decision Point:**
- If rejection rate >15%: STOP, adjust quality gates in domains.py, retest
- If errors >2: STOP, investigate root cause
- If all metrics green: ✅ Proceed to production batch

### Step 6: Backup Before Production

**On Host:**

```bash
# Create backup of test batch
/root/orion/scripts/ops/backup-orion-rag.sh

# Verify backup
ls -lh /mnt/nvme1/backups/orion-rag/
cat /mnt/nvme1/backups/orion-rag/BACKUP_MANIFEST_*.txt
```

### Step 7: Production Batch Processing

**Process in batches of 500 documents:**

**On Host (Terminal 1 - Monitoring):**
```bash
/root/orion/scripts/ops/monitor-ingestion.sh
```

**On Host (Terminal 2 - Processing):**
```bash
cd /root/orion/applications/orion-rag/research-qa
source venv/bin/activate
export ANYTHINGLLM_API_KEY="<your-key>"

# Process next 500 documents
python3 src/orchestrator.py \
  --document-root /mnt/nvme1/orion-data/documents/raw \
  --offset 100 \
  --limit 500 \
  --batch-size 50

# After each batch of 500:
# 1. Check monitoring dashboard for issues
# 2. Run backup: /root/orion/scripts/ops/backup-orion-rag.sh
# 3. Verify metrics still healthy
# 4. Continue next batch
```

**Recommended Schedule:**
- Batch 1 (0-100): ✅ DONE (test batch)
- Batch 2 (100-600): Process, backup, verify (2-3 hours)
- Batch 3 (600-1100): Process, backup, verify (2-3 hours)
- Batch 4 (1100-1600): Process, backup, verify (2-3 hours)
- Batch 5 (1600-2100): Process, backup, verify (2-3 hours)
- Batch 6 (2100-2521): Final batch (1-2 hours)

**Total time: 6-8 hours**

---

## ✅ POST-DEPLOYMENT VALIDATION

### Verify Final State

**On Host:**

```bash
# 1. Check all collections
curl -s http://localhost:6333/collections | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('Collections:')
for c in data['result']['collections']:
    print(f\"  {c['name']}: {c['points_count']:,} vectors ({c['config']['params']['vectors']['size']}d)\")
"

# Expected output:
# Collections:
#   research-papers: ~19,720 vectors (1024d)
#   technical-docs: ~56,400 vectors (1024d)
#   code-examples: ~5,520 vectors (1024d)

# 2. Check ingestion registry
sqlite3 /mnt/nvme1/orion-data/documents/metadata/ingestion.db "
SELECT
  'Total Documents:' as metric,
  COUNT(*) as value
FROM documents
UNION ALL
SELECT
  'Ingested:',
  COUNT(*)
FROM documents
WHERE status = 'ingested'
UNION ALL
SELECT
  'Rejected:',
  COUNT(*)
FROM documents
WHERE status = 'rejected'
UNION ALL
SELECT
  'Total Chunks:',
  SUM(chunk_count)
FROM documents
WHERE status = 'ingested';
"

# 3. Test query quality
curl -X POST "http://localhost:3001/api/v1/workspace/research-papers/chat" \
  -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the best practices for vector database indexing?",
    "mode": "query"
  }' | jq .

# Should return relevant results with source citations

# 4. Verify backup exists
ls -lh /mnt/nvme1/backups/orion-rag/
# Should show latest backup from today
```

### Performance Benchmarks

**Test query latency:**

```bash
# Query response time (should be <2s)
time curl -X POST "http://localhost:3001/api/v1/workspace/technical-docs/chat" \
  -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "How to configure Proxmox GPU passthrough?", "mode": "query"}' \
  > /dev/null

# Embedding generation time (should be <1s for 512 tokens)
time curl -X POST "http://localhost:3001/api/v1/embed" \
  -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"texts": ["test query about kubernetes autoscaling"]}' \
  > /dev/null
```

---

## 🚨 TROUBLESHOOTING

### Issue: Embedding model still showing nomic-embed-text-v1

**Diagnosis:**
```bash
docker exec orion-anythingllm env | grep EMBEDDING_MODEL_PREF
```

**Fix:**
```bash
cd /root/orion/applications/orion-rag/infrastructure
docker compose down
docker compose rm -f anythingllm
docker compose up -d anythingllm
docker compose logs -f anythingllm | grep -i "embedding"
```

### Issue: High rejection rate (>15%)

**Diagnosis:**
```bash
sqlite3 /mnt/nvme1/orion-data/documents/metadata/ingestion.db "
SELECT
  document_type,
  error_message,
  COUNT(*) as count
FROM documents
WHERE status = 'rejected'
GROUP BY document_type, error_message
ORDER BY count DESC;
"
```

**Fix:**
- If "low_density": Lower `min_text_density` in domains.py
- If "short_document": Lower `min_length` in domains.py
- Commit changes to laptop, push, redeploy

### Issue: Qdrant out of memory

**Diagnosis:**
```bash
docker stats orion-qdrant
curl -s http://localhost:6333/metrics
```

**Fix:**
```bash
# Increase memory limit in docker-compose.yml
# Memory needed: ~100MB per 1M vectors for 1024d
# Example: 100K vectors = ~10GB

cd /root/orion/applications/orion-rag/infrastructure
# Edit docker-compose.yml (on laptop first!)
docker compose up -d qdrant
```

### Issue: Processing very slow (<10 docs/min)

**Check bottlenecks:**
```bash
# CPU usage
top -p $(pgrep -f "orchestrator.py")

# Disk I/O
iostat -x 5

# Network (if remote Qdrant)
iftop

# AnythingLLM performance
docker stats orion-anythingllm
```

**Fix:**
- Increase `--batch-size` parameter (try 100)
- Add `EMBEDDING_BATCH_SIZE=64` in docker-compose.yml
- Check vLLM isn't bottlenecked (shouldn't be, only used for queries)

---

## 📊 SUCCESS CRITERIA

### Quantitative Metrics

- ✅ **Total documents processed:** >2,400 (>95% of 2,521 total)
- ✅ **Academic rejection rate:** <10%
- ✅ **Technical rejection rate:** <5%
- ✅ **Processing errors:** 0
- ✅ **Total vectors:** >80,000
- ✅ **Average chunks/doc:** 25-40
- ✅ **Vector dimensions:** 1024 (all collections)
- ✅ **Query latency:** <2s
- ✅ **Backup exists:** Latest within 24h

### Qualitative Checks

- ✅ Test queries return relevant results with citations
- ✅ No duplicate documents in Qdrant
- ✅ Backup restore procedure tested and works
- ✅ Monitoring dashboard shows healthy metrics
- ✅ No critical errors in logs

---

## 📝 POST-DEPLOYMENT TASKS

### Immediate (Day 1)

- [ ] Document actual rejection statistics
- [ ] Test 10 sample queries, rate quality 1-10
- [ ] Schedule daily backups (cron already setup)
- [ ] Create incident response runbook

### Week 1

- [ ] Monitor query patterns, identify gaps
- [ ] Review rejected documents, adjust quality gates if needed
- [ ] Test backup restore procedure
- [ ] Optimize Qdrant indexing parameters if needed

### Month 1

- [ ] Performance review (query latency, accuracy)
- [ ] User feedback collection
- [ ] Identify missing document types
- [ ] Plan incremental updates (add new sources)

---

## 🔗 RELATED DOCUMENTATION

- **Configuration:** `PRODUCTION-CONFIG-2025.md` (WHY these settings)
- **Architecture:** `applications/orion-rag/research-qa/ARCHITECTURE.md`
- **Backup Script:** `scripts/ops/backup-orion-rag.sh`
- **Monitoring:** `scripts/ops/monitor-ingestion.sh`
- **Laptop-Host Sync:** `docs/guides/LAPTOP-HOST-SYNC.md`

---

**Deployment Checklist Summary:**

1. ✅ Review configuration changes
2. ✅ Commit to laptop (source of truth)
3. ✅ Push to host
4. ✅ Deploy new docker-compose
5. ✅ Verify BGE-M3 loaded
6. ✅ Setup backup system
7. ✅ Test batch (100 docs)
8. ✅ Review metrics
9. ✅ Production batches (500 at a time)
10. ✅ Final validation

**Estimated Total Time:** 6-8 hours
**Risk Level:** Low (clean slate, tested configuration, automated backups)
**Rollback Plan:** Restore from backup, revert docker-compose.yml

---

**Ready to deploy!** 🚀

Quality-first. Production-grade. No regrets.
