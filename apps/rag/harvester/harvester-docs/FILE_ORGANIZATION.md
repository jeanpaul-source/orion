# File Organization in ORION Harvester

## Current Status: ✅ WORKING

**Last Verified:** 2025-01-22  
**Files on Disk:** 1,434 documents  
**Metadata Entries:** 425 (OUTDATED - needs rebuild)

---

## Directory Structure

```
orion-harvester/
├── data/
│   ├── library/                           # Downloaded documents (organized by category)
│   │   ├── llm-serving-and-inference/     # 200 files (143 HTML, 38 PDF, 19 MD)
│   │   ├── gpu-passthrough-and-vgpu/      # 194 files
│   │   ├── homelab-infrastructure/        # 146 files
│   │   ├── workflow-automation-n8n/       # 141 files
│   │   ├── homelab-networking-security/   # 113 files
│   │   ├── vector-databases/              # 87 files
│   │   ├── self-healing-and-remediation/  # 84 files
│   │   ├── ai-agents-and-multi-agent-systems/ # 83 files
│   │   ├── observability-and-alerting/    # 65 files
│   │   ├── rag-and-knowledge-retrieval/   # 53 files
│   │   └── ... (20 categories total)
│   │
│   └── library_metadata.json              # Metadata tracking (source of truth)
```

---

## How Files Are Organized

### 1. Category-Based Organization

Each downloaded document is stored in a **category subdirectory**:

```
data/library/{category}/{sanitized_title}.{extension}
```

**Example:**
```
data/library/llm-serving-and-inference/vLLM_Efficient_Memory_Management_for_Large_Language_Model_Serving.pdf
data/library/gpu-passthrough-and-vgpu/GPU_Virtualization_with_VFIO_IOMMU.html
data/library/workflow-automation-n8n/n8n-io_n8n _GitHub_.md
```

### 2. File Types

The harvester stores **3 types of documents**:

1. **PDF** (`.pdf`) - Academic papers, technical docs
2. **HTML** (`.html`) - Web pages, blog posts, documentation
3. **Markdown** (`.md`) - GitHub READMEs, Stack Overflow answers

**Example Distribution (llm-serving-and-inference):**
- 143 HTML files (71.5%)
- 38 PDF files (19%)
- 19 Markdown files (9.5%)

### 3. Filename Sanitization

Titles are sanitized to create valid filenames:

```python
def sanitize_filename(title: str) -> str:
    # Remove invalid characters: / \ : * ? " < > |
    # Replace with underscores or remove
    # Truncate to reasonable length
    return safe_filename
```

**Examples:**
- `"vLLM: Efficient Memory Management for LLMs"` → `vLLM_Efficient_Memory_Management_for_LLMs.pdf`
- `"GitHub: vllm-project/vllm"` → `vllm-project_vllm _GitHub_.md`
- `"What is CUDA?"` → `What_is_CUDA.html`

---

## Metadata Tracking

### library_metadata.json Structure

```json
{
  "downloads": [
    {
      "doc_id": "sha256_hash_of_url",
      "title": "vLLM: Efficient Memory Management...",
      "authors": "Kwon et al.",
      "year": "2023",
      "category": "llm-serving-and-inference",
      "source": "arxiv",
      "url": "https://arxiv.org/pdf/2309.06180.pdf",
      "filepath": "data/library/llm-serving-and-inference/vLLM_Efficient_Memory_Management.pdf",
      "citation_count": 245,
      "citations_per_year": 122.5,
      "venue": "arXiv",
      "abstract": "We present vLLM...",
      "status": "downloaded",
      "related_papers": [...]
    }
  ]
}
```

### Key Fields

- **doc_id**: SHA256 hash of URL (prevents duplicates)
- **filepath**: Relative path from repo root
- **category**: Which subdirectory it's stored in
- **source**: Provider (arxiv, github, semantic_scholar, etc.)
- **status**: `downloaded`, `failed`, `skipped`

---

## Current Issues & Resolution

### ⚠️ Metadata Out of Sync

**Problem:** Metadata file only tracks 425 documents, but 1,434 files exist on disk.

**Likely Cause:** 
- Metadata got overwritten during recent testing
- Backup from Nov 2 is outdated (before bulk harvesting)
- Need to rebuild metadata from actual files

**Resolution Options:**

#### Option 1: Rebuild Metadata from Files (Recommended)
```bash
cd /home/jp/orion/orion-harvester
python3 scripts/rebuild_metadata.py  # If script exists
# Or validate and scan:
orion validate --rebuild
```

#### Option 2: Continue with Current State
- Current 425 entries represent papers with full metadata
- Additional 1,009 files are older downloads
- System will skip re-downloading existing files (checks filepath)
- Metadata will grow as new papers are added

#### Option 3: Clean Slate
```bash
# Backup everything first!
cd /home/jp/orion/orion-harvester
tar -czf ~/orion_library_backup_$(date +%Y%m%d).tar.gz data/library/
# Then choose: keep files and rebuild metadata, or start fresh
```

---

## How Organization Works in Practice

### During Harvest

1. **Search** for papers using query term and category
2. **Filter** results by quality (citations, keywords, etc.)
3. **Check duplicates** using `already_downloaded(url)` against metadata
4. **Download** to `data/library/{category}/` 
5. **Save metadata** entry with full details
6. **Report** statistics by category and source

### Example Harvest Flow

```bash
orion harvest --term "vLLM continuous batching" --category llm-serving-and-inference --max-docs 5
```

**What happens:**
1. Searches 14 providers (Semantic Scholar → OpenAlex → arXiv → ...)
2. Finds 5 relevant papers
3. Downloads to `data/library/llm-serving-and-inference/`
4. Creates filenames: `Paper_Title_Here.{pdf|html|md}`
5. Adds 5 entries to `library_metadata.json`
6. Prints summary:
   ```
   By Category:
     llm-serving-and-inference: 5
   By Source:
     semantic_scholar: 2
     arxiv: 2
     openalex: 1
   ```

---

## File Organization Benefits

### ✅ Pros

1. **Easy browsing** - Navigate by topic in file manager
2. **Clear categorization** - Papers organized by homelab domain
3. **Simple backup** - Copy entire category or library
4. **Human-readable** - Filenames match paper titles
5. **Flexible** - Can move files between categories manually

### ⚠️ Cons

1. **Metadata dependency** - Must keep `library_metadata.json` in sync
2. **Duplicate risk** - If metadata is lost, may re-download
3. **Manual moves** - Moving files between categories requires metadata update

---

## Verification Commands

### Check Organization Health

```bash
cd /home/jp/orion/orion-harvester

# Count files by category
for dir in data/library/*/; do
  count=$(ls -1 "$dir" 2>/dev/null | wc -l)
  echo "$count files: $(basename "$dir")"
done | sort -rn

# Check metadata count
python3 -c "import json; print(f'{len(json.load(open(\"data/library_metadata.json\"))[\"downloads\"])} metadata entries')"

# Check file types
find data/library -type f | sed 's/.*\.//' | sort | uniq -c

# Find files without metadata
# (Advanced: requires script to compare filesystem vs metadata)
```

### Validate Integrity

```bash
# Check for corrupt PDFs
find data/library -name "*.pdf" -size -10k  # Suspiciously small PDFs

# Check for missing files referenced in metadata
orion validate --check-files

# Check for orphaned files (on disk but not in metadata)
orion validate --check-orphans
```

---

## Recommended Actions

### Immediate (Before Next Harvest)

1. ✅ Current system is functional - files are organized correctly
2. ⚠️ Metadata is outdated but harvester still works (skips existing files by filepath)
3. 📋 Decision needed: Rebuild metadata or continue with partial tracking?

### For Production Use

1. **Regular backups** - Automate metadata backups before harvests
2. **Validation checks** - Run `orion validate` periodically
3. **Metadata rebuild** - Create script to reconstruct from filesystem if needed

### File Management

- **Moving files:** Update both filepath and category in metadata
- **Deleting files:** Remove from both filesystem and metadata
- **Renaming categories:** Update directory name AND all metadata entries

---

## Summary

**File Organization: ✅ WORKING**
- Files correctly organized into 20 category subdirectories
- 1,434 documents stored (PDF, HTML, Markdown)
- Filenames sanitized from paper titles
- Structure: `data/library/{category}/{title}.{ext}`

**Metadata Tracking: ⚠️ OUT OF SYNC**
- Only 425 entries tracked (vs 1,434 files)
- System still functional (checks filepath, not just metadata)
- Can continue harvesting or rebuild metadata

**Next Harvest Will:**
- Skip existing files (checks `filepath.exists()`)
- Add new documents to correct categories
- Update metadata incrementally
- Work correctly despite metadata gap

---

**Related Docs:**
- [Data Sources](../guides/DATA_SOURCES.md) - Where files come from
- [Harvesting Guide](../guides/QUICK_START.md) - How to harvest papers
- [Validation](../docs/QUALITY.md) - Quality checks
