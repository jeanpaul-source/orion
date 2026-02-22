# MC/DC Testing Targets for orion-rag/harvester

**Generated:** 2025-11-22

## Compound Conditions Found

### downloader.py

```python
210:        elif content[:100].decode("utf-8", errors="ignore").strip().startswith(
340:        safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title)
369:            if record:
```

### converters/pdf_converter.py

```python
40:            if not text or len(text.strip()) < 100:
117:        if not text or len(text.strip()) < 100:
127:        # Check for OCR artifacts (random characters, bad spacing)
157:        avg_word_length = sum(len(w) for w in words) / len(words) if words else 0
158:        word_score = 1.0 if 3 <= avg_word_length <= 8 else 0.5
185:        if metadata.get('author'):
```

### converters/html_converter.py

```python
39:        # Parse with BeautifulSoup for pre-cleaning
131:        if soup.title and soup.title.string:
164:        if soup.find('meta', attrs={'name': 'author'}):
```

### providers/arxiv.py

```python
65:                if title_elem is None or title_elem.text is None:
82:                    if published_elem is not None and published_elem.text
87:                if summary_elem is not None and summary_elem.text:
```

### providers/crossref.py

```python
87:                    year = parts[0] if parts and parts[0] else None
99:                    if link.get("content-type") == "application/pdf" and link.get("URL"):
104:                if not pdf_url and doi:
117:                        "authors": ", ".join(authors) if authors else "Unknown",
```

### providers/github.py

```python
203:    if "error" in rate_status:
234:    if errors:
```

### providers/zenodo.py

```python
71:                    if (f.get("type") == "pdf") or (f.get("mimetype") == "application/pdf"):
```

### providers/blog.py

```python
182:#     if not rss_feeds and not manual_urls:
```

### providers/semantic_scholar.py

```python
70:                if not (paper.get("openAccessPdf") and paper["openAccessPdf"].get("url")):
79:                if citation_count and year:
```

### providers/dblp.py

```python
64:                if isinstance(authors, dict):
67:                    a.get("text", "") if isinstance(a, dict) else str(a) for a in authors
75:                if doi and doi.startswith("10."):
```

### providers/readthedocs.py

```python
132:            if url in self.visited_urls or depth > self.max_depth:
177:        """Check if URL is a documentation page (not external/anchor)."""
```

### providers/biorxiv.py

```python
71:                if not any(term in content for term in query_terms):
```

### providers/medrxiv.py

```python
71:                if not any(term in content for term in query_terms):
```

### providers/base.py

```python
1:"""Unified base provider interface for all ORION harvesters.
38:        """Get unique identifier for deduplication."""
136:            Document object if successful, None on error
```

### providers/openalex.py

```python
29:                if 0 <= pos < len(words):
84:                if best_location and best_location.get("pdf_url"):
105:                if citation_count and year:
```

### utils.py

```python
52:    safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title)
152:        Check if paper title is semantically relevant to category.
168:        if not self._initialized or self.model is None:
180:            if category_embedding is None:
```

### filters.py

```python
63:    Check if term appears in text using word boundaries.
73:        True if term found with word boundaries, False otherwise
93:    7. Source-specific gates (GitHub stars, SO score) → quality thresholds
168:    if required_terms and not matched_terms:
196:            if preferred and any(token in venue_lower for token in preferred):
198:            elif any(bad in venue_lower for bad in LOW_QUALITY_VENUE_KEYWORDS):
```

### cli.py

```python
183:        if provider_class in [p.__class__ for p in academic]:
188:        if provider_class not in [p.__class__ for p in academic]:
```

### provider_factory.py

```python
169:        if not names or "all" in names:
```
