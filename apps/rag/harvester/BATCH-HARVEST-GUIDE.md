# ORION Batch Harvester Guide

**Created:** November 20, 2025
**Purpose:** Overnight batch harvesting of academic papers from multiple sources
**Estimated Time:** 2-4 hours for 272 search terms

---

## 🎯 Overview

The batch harvester processes all search terms from `config/search_terms.csv` and downloads academic papers from multiple providers overnight.

### Features

✅ **Checkpoint/Resume** - Resume processing from any point
✅ **Progress Tracking** - Structured reports every 25 terms
✅ **Error Classification** - Automatic categorization and summary
✅ **Multi-Provider Support** - 14 academic APIs (Semantic Scholar, arXiv, OpenAlex, etc.)
✅ **Deduplication** - Automatic via library_metadata.json
✅ **Monitoring Tools** - Track progress without SSH

---

## 📋 Quick Start

### Option 1: Using the Overnight Script (Recommended)

```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/harvester

# Run overnight batch (academic providers, 50 docs per term)
./scripts/overnight-harvest.sh

# Or run in background with nohup
nohup ./scripts/overnight-harvest.sh > /tmp/harvest-wrapper.log 2>&1 &

# Or use screen/tmux
screen -S harvest
./scripts/overnight-harvest.sh
# Press Ctrl+A, D to detach
```

### Option 2: Direct Python Execution

```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/harvester

# Activate virtual environment
source activate.sh

# Run batch harvest
python scripts/batch_harvest.py \
  --providers academic \
  --max-docs 50 \
  --checkpoint /tmp/orion-harvest-checkpoint.json
```

---

## 📊 Monitoring Progress

### Quick Status Check

```bash
# View latest progress
./scripts/monitor-harvest.sh

# Full summary
./scripts/monitor-harvest.sh --summary

# Watch live updates
./scripts/monitor-harvest.sh --watch
```

### Manual Log Commands

```bash
# Find latest log
LOG=$(ls -t /tmp/orion-harvest-logs/harvest-*.log | head -1)

# View latest progress report
grep "PROGRESS REPORT" "$LOG" | tail -1

# Count processed terms
grep "Terms processed:" "$LOG" | tail -1

# Count downloaded documents
grep "Documents downloaded:" "$LOG" | tail -1

# View recent searches
grep "^\[" "$LOG" | grep -E "\[[0-9]+/[0-9]+\]" | tail -10

# Check if completed
grep "BATCH HARVEST COMPLETE" "$LOG"

# Tail live output
tail -f "$LOG"
```

---

## 🔄 Resume After Interruption

If the harvest is interrupted, resume from the last checkpoint:

```bash
# Using the bash script
./scripts/overnight-harvest.sh --resume

# Or directly with Python
python scripts/batch_harvest.py \
  --checkpoint /tmp/orion-harvest-checkpoint.json
```

The checkpoint file tracks:
- All successfully processed search terms
- Failed terms with error messages
- Download statistics
- Last save timestamp

**Checkpoint saves automatically every 10 terms.**

---

## ⚙️ Configuration

### Environment Variables

```bash
# Customize provider list (default: academic)
export ORION_PROVIDERS="semantic_scholar,arxiv,openalex"

# Or use all providers (includes GitHub, ReadTheDocs, etc.)
export ORION_PROVIDERS="all"

# Maximum documents per search term (default: 50)
export ORION_MAX_DOCS=100

# Then run
./scripts/overnight-harvest.sh
```

### Command-Line Options

```bash
# Process only first 10 terms (testing)
python scripts/batch_harvest.py --limit 10

# Dry run (no downloads)
python scripts/batch_harvest.py --dry-run

# Specific providers
python scripts/batch_harvest.py --providers semantic_scholar,arxiv

# Higher doc limit
python scripts/batch_harvest.py --max-docs 100

# Custom terms file
python scripts/batch_harvest.py --terms-file custom_terms.csv
```

---

## 📈 Expected Timeline

**For 272 search terms (config/search_terms.csv):**

```
Time     Progress    Status
------   ----------  ---------------------------
20:00    Start       Loading search terms
20:15    25 terms    Progress report (9%)
21:00    100 terms   Progress report (37%)
22:00    175 terms   Progress report (64%)
23:00    250 terms   Progress report (92%)
23:30    272 terms   COMPLETE
```

**Conservative estimate:** 2-4 hours
**Processing rate:** ~1-2 terms/minute (varies by provider response time)

**Factors affecting speed:**
- Provider API response times
- Number of results per term
- Network latency
- Download speeds

---

## 📋 Progress Reports

Every 25 search terms, you'll see a structured report:

```
======================================================================
📊 PROGRESS REPORT - 21:15:32
======================================================================
Processed:       100 /   272 (36.8%)
Found:          4250
Downloaded:     2150
Skipped:        1800 (already have)
Failed:          300
Rate:            1.5 terms/min
Elapsed:         66.7 minutes
ETA:            114.7 minutes (~1.9 hours)
======================================================================
```

---

## 🐛 Error Handling

### Automatic Error Classification

Errors are automatically categorized:

- `no_results` - No documents found for search term (expected)
- `rate_limit` - API rate limiting (auto-retry with backoff)
- `timeout` - Request timeout (auto-retry)
- `network_error` - Connection issues (auto-retry)
- `api_error` - API authentication or quota issues
- `download_failed` - Document download failed
- `other` - Uncategorized errors

### Error Summary Report

At the end of processing:

```
======================================================================
ERROR SUMMARY
======================================================================

Errors by Type:
  no_results          :   85 (31.2%)
    - obscure technical term 1 (category)
    - obscure technical term 2 (category)
  rate_limit          :   12 (4.4%)
  timeout             :    8 (2.9%)

Errors by Category:
  homelab-infrastructure          :   45
  rag-and-knowledge-retrieval     :   30
======================================================================
```

---

## 🔍 Search Terms

The harvester processes all terms from `config/search_terms.csv`:

**Categories (11 total):**
- homelab-infrastructure (50+ terms)
- rag-and-knowledge-retrieval (40+ terms)
- llm-serving-and-inference (25+ terms)
- vector-databases (20+ terms)
- gpu-passthrough-and-vgpu (20+ terms)
- observability-and-alerting (20+ terms)
- homelab-networking-security (25+ terms)
- workflow-automation-n8n (15+ terms)
- self-healing-and-remediation (15+ terms)
- data-persistence-stores (15+ terms)
- container-platforms (15+ terms)

**Total: 272 search terms**

### Example Terms

```
Proxmox VE clustering high availability hypervisor
GPU passthrough VFIO IOMMU virtualization
Qdrant vector database HNSW indexing
vLLM continuous batching inference serving
LangChain LCEL expression language patterns
Kubernetes GPU scheduling device plugin
```

---

## 📁 Output Structure

Downloaded papers are organized by category:

```
data/library/
├── homelab-infrastructure/
│   ├── paper1.pdf
│   ├── paper2.pdf
│   └── ...
├── rag-and-knowledge-retrieval/
│   ├── paper1.pdf
│   └── ...
├── vector-databases/
│   └── ...
└── library_metadata.json  # Deduplication registry
```

---

## 📊 Available Providers

### Academic Providers (Default: `--providers academic`)

- **semantic_scholar** - 200M+ papers, best coverage
- **arxiv** - Open access preprints (CS, physics, math)
- **openalex** - 250M+ works, open access
- **core** - 200M+ research papers
- **dblp** - Computer science bibliography
- **crossref** - 130M+ scholarly records
- **pubmed** - Biomedical literature
- **biorxiv** - Biology preprints
- **medrxiv** - Medical preprints
- **zenodo** - Research outputs
- **hal** - French open archive

### Documentation Providers (`--providers all`)

Adds these to academic providers:
- **github** - GitHub repository READMEs
- **readthedocs** - Technical documentation
- **blog** - Technical blog posts
- **vendor_pdf** - Vendor documentation PDFs

---

## ✅ Pre-Flight Checklist

Before starting overnight harvest:

```bash
# 1. Check search terms file
cat config/search_terms.csv | wc -l
# Should show 273 lines (272 terms + header)

# 2. Check current library size
find data/library -name "*.pdf" | wc -l
# Shows how many papers already downloaded

# 3. Check disk space
df -h data/
# Need at least 5GB free

# 4. Test with dry-run
python scripts/batch_harvest.py --limit 5 --dry-run

# 5. Test actual download
python scripts/batch_harvest.py --limit 3
```

---

## 🚀 Usage Examples

### Basic Usage

```bash
# Default: academic providers, 50 docs per term
./scripts/overnight-harvest.sh

# Resume from checkpoint
./scripts/overnight-harvest.sh --resume

# Dry run
./scripts/overnight-harvest.sh --dry-run
```

### Advanced Usage

```bash
# Specific providers with higher limit
python scripts/batch_harvest.py \
  --providers semantic_scholar,arxiv \
  --max-docs 100

# Process only 10 terms (testing)
python scripts/batch_harvest.py --limit 10

# All providers (academic + documentation)
python scripts/batch_harvest.py --providers all

# Custom checkpoint location
python scripts/batch_harvest.py \
  --checkpoint /path/to/custom/checkpoint.json

# Combine options
python scripts/batch_harvest.py \
  --providers academic \
  --max-docs 75 \
  --limit 50 \
  --checkpoint /tmp/test-checkpoint.json
```

---

## 🔧 Troubleshooting

### Problem: No progress for >10 minutes

```bash
# Check if process is still running
ps aux | grep batch_harvest.py

# Check latest progress
grep "PROGRESS REPORT" /tmp/orion-harvest-logs/harvest-*.log | tail -1

# If hung, kill and resume
pkill -f batch_harvest.py
./scripts/overnight-harvest.sh --resume
```

### Problem: High failure rate

```bash
# View error summary
grep "ERROR SUMMARY" -A 20 /tmp/orion-harvest-logs/harvest-*.log | tail -25

# Common causes:
# - API rate limiting (normal, will retry)
# - Network issues (temporary, will retry)
# - No results found (expected for some terms)
```

### Problem: Deduplication not working

```bash
# Check metadata registry
ls -lh data/library_metadata.json

# View registry contents
python -c "import json; print(json.dumps(json.load(open('data/library_metadata.json')), indent=2))" | head -50
```

---

## 📝 Files Created

1. **scripts/batch_harvest.py** - Main batch harvesting script
2. **scripts/overnight-harvest.sh** - Wrapper script for overnight execution
3. **scripts/monitor-harvest.sh** - Progress monitoring tool
4. **BATCH-HARVEST-GUIDE.md** - This guide

---

## 🎓 Tips for Success

1. **Test first** - Run with `--limit 10` to verify everything works
2. **Monitor early** - Check first 25 terms before going to bed
3. **Use screen/tmux** - Survives terminal disconnections
4. **Check logs in morning** - Use `./scripts/monitor-harvest.sh --summary`
5. **Don't worry about errors** - 10-20% no results is normal
6. **Resume is your friend** - Always use checkpoint for large batches

---

## 📞 Integration with Ingestion Pipeline

After harvesting completes, run the ingestion pipeline:

```bash
# Papers are now in data/library/*/*.pdf
# Run ingestion to process and embed them
cd ../research-qa
./scripts/overnight-batch-ingest.sh
```

**Complete workflow:**
1. **Harvest** - Collect papers (`overnight-harvest.sh`)
2. **Ingest** - Process and embed (`overnight-batch-ingest.sh` in research-qa)
3. **Query** - Use ORION RAG for Q&A

---

## 📚 Related Documentation

- [Harvester README](README.md) - Main harvester documentation
- [CLI Usage Guide](harvester-docs/CLI_USAGE.md) - Complete CLI reference
- [ORION System Guide](../../../CLAUDE.md) - Full system overview
- [Ingestion Guide](../research-qa/OVERNIGHT-PROCESSING-GUIDE.md) - Document processing

---

**Happy harvesting! 🌾**
