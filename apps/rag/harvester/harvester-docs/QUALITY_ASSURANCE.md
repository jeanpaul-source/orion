# ORION Library Quality Assurance

## Overview
The ORION harvester implements **multi-layered quality gates** to ensure only valid, relevant, high-quality documents enter the library.

**Document Types Harvested:**
- **PDFs**: Academic papers (Semantic Scholar, arXiv, OpenAlex, CORE, DBLP, Crossref, Zenodo, HAL, PubMed, bioRxiv)
- **Markdown**: GitHub READMEs, Stack Overflow answers
- **HTML**: Official documentation, tech blog posts

---

## Quality Gates (In Order)

### 1. **Relevance Filtering** (Pre-Download)
Papers are filtered before download to avoid wasting bandwidth on irrelevant content.

**Checks:**
- ✅ Title/abstract contains category-specific required terms
- ✅ No red flags (medical, astrophysics, sociology keywords in tech searches)
- ✅ Category-specific exclusion terms (e.g., "medical database" in database searches)
- ✅ Optional: Semantic similarity score using sentence-transformers (>0.5 threshold)
- ✅ Venue quality heuristics (IEEE, ACM, arXiv vs predatory journals)
- ✅ Source-specific thresholds (GitHub stars >100, StackOverflow score >10)

**Location:** `orion_harvester.py::is_paper_relevant()`

---

### 2. **Download Integrity** (During Download)
Active validation during the download process.

**Checks:**
- ✅ File size >10KB (catches incomplete/error pages)
- ✅ PDF magic number (`%PDF` header at start of file)
- ✅ PyMuPDF readability test (can open without exceptions)
- ✅ Not encrypted/password-protected
- ✅ Page count >0
- ✅ Network timeout handling (30s max)
- ✅ HTTP error retry with Unpaywall OA resolution

**Location:** `orion_harvester.py::download_pdf()`

---

### 3. **Post-Download Validation** (Optional Deep Check)
After download, run comprehensive validation on the entire library.

**Script:** `scripts/validate_library_quality.py`

**Checks (All File Types):**
- ✅ File exists and is accessible
- ✅ Minimum size thresholds (PDFs >10KB, text files >1KB)
- ✅ Format-specific validation:
  - **PDFs**: Valid structure, not corrupted/truncated, can extract text, not encrypted, page count >0
  - **Markdown/HTML**: UTF-8 readable, not empty, content length >100 chars
- ✅ Duplicate detection by content hash (SHA256)
- ✅ Metadata consistency (file paths match metadata DB)

**Usage:**
```bash
# Quick validation (magic number + readability)
python scripts/validate_library_quality.py --quick

# Deep validation (extract all text to verify content)
python scripts/validate_library_quality.py --deep

# Find duplicates by content hash
python scripts/validate_library_quality.py --check-duplicates

# Quarantine corrupted files automatically
python scripts/validate_library_quality.py --repair
```

---

## Quality Metrics Tracked

### Per-Document Metadata
Each document in `library_metadata.json` includes:
- `doc_id`: SHA256 hash of file content (for deduplication)
- `status`: `downloaded`, `failed`, `skipped`, `quarantined`
- `citation_count`: Academic citations (for papers)
- `source`: Provider (semantic_scholar, arxiv, github, etc.)
- `download_date`: ISO 8601 timestamp
- `filepath`: Relative path in library
- `validation_error`: Error message if corrupted (after repair)

### Library-Wide Statistics
Run `orion validate --quick` to see:
- Total documents by category
- Distribution by source
- Metadata vs filesystem mismatch detection
- PDF file count

---

## Handling Corrupted Files

### Automatic Quarantine
Bad files are moved to `data/quarantine/` instead of deleted:
```bash
python scripts/validate_library_quality.py --repair
```

This:
1. Moves corrupted PDFs to quarantine directory
2. Updates metadata with `status: quarantined` and error message
3. Creates backup of metadata before modifications

### Manual Recovery
Quarantined files can be:
- Deleted if truly corrupted
- Manually fixed (e.g., decrypt, OCR image-only PDFs)
- Restored if false positive

---

## Best Practices

### For Continuous Harvesting
1. **Run quick validation after each harvest:**
   ```bash
   orion harvest --category gpu-and-cuda --max-docs 50
   python scripts/validate_library_quality.py --quick  # Validates all PDFs, MD, HTML
   ```

2. **Weekly deep validation:**
   ```bash
   python scripts/validate_library_quality.py --deep --repair
   ```

3. **Monthly duplicate check:**
   ```bash
   python scripts/validate_library_quality.py --check-duplicates
   ```

### For Large Batches
1. Harvest in small batches (50-100 docs per term)
2. Validate immediately after each batch
3. Fix issues before continuing (prevents cascading problems)

### For Production Deployments
- Enable semantic filtering (`USE_EMBEDDINGS = True` in harvester)
- Set higher citation/star thresholds
- Use Semantic Scholar API key for bulk access
- Run validation as post-download hook in harvest loop

---

## Dependencies

### Core (Already Installed)
- `requests` – HTTP client with retry logic
- `hashlib` – SHA256 hashing for deduplication

### PDF Validation (Required)
- `PyMuPDF` (`fitz`) – Fast PDF parsing and validation
  ```bash
  pip install PyMuPDF>=1.24.0
  ```

### Optional Enhancement
- `sentence-transformers` – Semantic relevance scoring (heavy, ~500MB models)
- `pdfplumber` – Fallback for complex PDFs

---

## Known Limitations

### Current Gaps
1. **No OCR for image-only PDFs** – These are flagged but not fixed
2. **No automatic repair** – Corrupted files quarantined but require manual action
3. **Limited semantic filtering** – OFF by default (model download required)
4. **No citation verification** – Relies on provider-reported counts
5. **No HTML parsing validation** – HTML files checked for readability, not structure/completeness

### Future Enhancements
- Automatic OCR pipeline for image-only PDFs (Tesseract/PaddleOCR)
- Checksum-based deduplication during download (not after)
- Real-time semantic relevance scoring (if model cached locally)
- Automatic retry for failed downloads after backoff

---

## Quality Reports

### Generate Library Quality Report
```bash
cd orion-harvester
python orion_harvester.py report
```

Outputs:
- Total documents by category
- Top cited papers
- Source distribution
- Citation statistics
- Related papers network

### Archive Old Validation Reports
Reports are logged to console only. For persistent tracking:
```bash
python scripts/validate_library_quality.py --deep > data/quality_reports/$(date +%Y%m%d).txt
```

---

## Troubleshooting

### High Failure Rate (>50%)
- Check API keys (GitHub, Semantic Scholar, CORE)
- Verify network connectivity (SSL certs, firewalls)
- Lower quality thresholds temporarily
- Inspect failed entries in metadata (`status: failed`)

### Many Quarantined Files
- Re-download with better link resolution (already implemented)
- Check for rate limiting (increase delays)
- Validate provider URLs (some may be outdated)

### Duplicate Content
- Run `--check-duplicates` to identify
- Keep highest-citation version
- Update metadata to mark duplicates as `status: skipped`

---

## Summary

**Quality-first approach:**
1. ✅ **Filter before download** (relevance, venue quality, thresholds)
2. ✅ **Validate during download** (magic number, readability, encryption)
3. ✅ **Deep validation after download** (content extraction, corruption detection)
4. ✅ **Quarantine bad files** (preserve for manual review vs deletion)
5. ✅ **Track quality metrics** (citations, source, validation errors)

**Result:** High-confidence library with minimal noise, easy to maintain and expand.
