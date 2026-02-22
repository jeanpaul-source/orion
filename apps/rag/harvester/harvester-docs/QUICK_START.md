# Quick Start Guide - Bulk Harvesting

## ✅ System Status: PRODUCTION READY

All API keys configured and tested. Ready to harvest thousands of documents.

---

## Three Options to Choose From

### 🧪 Option 1: Test Harvest (RECOMMENDED FIRST)
**10 terms → ~100-200 documents → 30 minutes**

```bash
# Using unified CLI (recommended)
orion harvest --dry-run --limit 10

# Or via Makefile
make harvest-test
```

Safe way to validate everything works before committing to overnight harvest.

---

### 🚀 Option 2: Full Mega Harvest
**100 terms → ~8,000-10,000 documents → 6-8 hours**

```bash
# Using unified CLI (recommended)
orion harvest --max-results 50

# Or via Makefile in background
nohup make harvest > harvest_$(date +%Y%m%d_%H%M%S).log 2>&1 &
tail -f harvest_*.log
```

Full overnight harvest with all search terms and providers.

---

### 🎯 Option 3: Category-Specific
**Target specific categories → custom → varies**

```bash
# Using unified CLI (recommended)
orion harvest --category gpu-and-cuda --max-results 50

# Or via legacy script
source setup_bulk_harvest.sh
.venv/bin/python3 orion_harvester.py --category gpu-and-cuda
```

Harvest only papers for specific categories.

---

## Current Configuration

```bash
ORION_MAX_RESULTS_PER_TERM=50     # 50 results per term per provider
ORION_MIN_GITHUB_STARS=50         # Accept repos with 50+ stars
ORION_MIN_SO_SCORE=5              # Accept answers with 5+ score
ORION_USE_EMBEDDINGS=false        # Faster without NLP
```

**API Keys Active:**
- ✅ GitHub (5,000 req/hr)
- ✅ Stack Overflow (10,000 req/day)
- ✅ CORE (1,000 req/day)
- ⏳ Semantic Scholar (pending)

---

## Monitoring Commands

```bash
# Check harvest status
orion validate library --stats

# Watch harvest progress
tail -f data/harvester.log

# Count total documents
jq '.downloads | length' data/library_metadata.json

# Count processed documents
jq '[.downloads[] | select(.processing.status == "success")] | length' data/library_metadata.json

# Check disk space
df -h /home/jp/orion_harvester/data/

# View summary report
.venv/bin/python3 orion_harvester.py report
```

---

## Expected Results

**With current 100 terms + MAX_RESULTS=50:**

| Metric | Value |
|--------|-------|
| Total API calls | ~50,000 |
| Documents after filtering | ~8,000-10,000 |
| Disk space needed | ~12 GB |
| Runtime (harvest) | ~1.5 hours |
| Runtime (processing) | ~4.5 hours |
| **TOTAL TIME** | **~6-8 hours** |

---

## Next Steps After Harvest

1. **Review quality**: `.venv/bin/python3 orion_harvester.py report`
2. **Export citations**: `.venv/bin/python3 orion_harvester.py export --format csv --min-citations 50`
3. **Process documents**: `.venv/bin/python3 process_library.py` (converts to AI-ready formats)
4. **Validate processing**: `.venv/bin/python3 scripts/validate_processed_data.py`
5. **Build embeddings**: See [`EMBEDDING_MIGRATION_GUIDE.md`](../EMBEDDING_MIGRATION_GUIDE.md) for complete workflow
   - Token analysis: `scripts/validate_rechunking.py`
   - Sandbox E2E test: `scripts/validate_sandbox_retrieval.py`
   - Full embedding: `scripts/embed_and_index.py` (10-12 hours on RTX 3090 Ti)
6. **Query knowledge base**: `scripts/query_rag.py` (CLI) or `scripts/web_ui.py` (web interface)

---

## Troubleshooting

**If harvest stops:**
```bash
# Resume from where it left off
source setup_bulk_harvest.sh
.venv/bin/python3 orion_harvester.py --new-only
```

**If rate limits hit:**
- Check API keys are set: `echo $ORION_GITHUB_TOKEN`
- Increase delay in `orion_harvester.py` (line 39)

**If disk full:**
- Free up space or reduce MAX_RESULTS_PER_TERM

---

## Documentation

- 📖 **Full guide**: [BULK_HARVEST_GUIDE.md](BULK_HARVEST_GUIDE.md)
- 🧪 **Test results**: [TEST_RESULTS.md](TEST_RESULTS.md)
- 📚 **Main README**: [README.md](README.md)

---

## Ready to Start?

```bash
# Recommended: Start with test harvest
./test_harvest_10_terms.sh

# Once validated: Full mega harvest
./launch_mega_harvest.sh
```

🎉 **Happy harvesting!**
