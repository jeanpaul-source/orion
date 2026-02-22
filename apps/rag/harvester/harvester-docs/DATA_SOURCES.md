# Data Sources for ORION Harvester

This document lists all data sources (APIs and scrapers) used by ORION Harvester for collecting academic papers and technical documentation.

## Current Active Sources (14 Total)

### Academic Paper APIs

#### No Authentication Required ✅

1. **arXiv** - Physics, math, CS preprints
   - API: `http://export.arxiv.org/api/query`
   - Rate Limit: 3 requests/second
   - Coverage: 2M+ papers
   - Quality: High (authoritative preprint server)

2. **OpenAlex** - Comprehensive academic database
   - API: `https://api.openalex.org/works`
   - Rate Limit: Polite (email in User-Agent recommended)
   - Coverage: 250M+ papers
   - Quality: High (replaces Microsoft Academic)

3. **Crossref** - DOI metadata
   - API: `https://api.crossref.org/works`
   - Rate Limit: 50 req/sec with email in User-Agent
   - Coverage: 130M+ DOIs
   - Quality: High (official DOI registry)

4. **Zenodo** - Research data repository
   - API: `https://zenodo.org/api/records`
   - Rate Limit: 100 req/hour (unauthenticated)
   - Coverage: 6M+ records
   - Quality: Medium-High (CERN-backed)

5. **DBLP** - Computer Science bibliography
   - API: `https://dblp.org/search/publ/api`
   - Rate Limit: Reasonable (no hard limit)
   - Coverage: 6M+ CS papers
   - Quality: High (curated CS database)

6. **HAL** - French open archive
   - API: `https://api.archives-ouvertes.fr/search`
   - Rate Limit: Reasonable
   - Coverage: 1M+ papers (French/European)
   - Quality: Medium-High

7. **PubMed Central** - Life sciences papers
   - API: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils`
   - Rate Limit: 3 req/sec (no key), 10 req/sec (with key)
   - Coverage: 8M+ full-text papers
   - Quality: High (NIH/NCBI)

8. **bioRxiv** - Biology preprints
   - API: `https://api.biorxiv.org/details/biorxiv`
   - Rate Limit: Reasonable
   - Coverage: 200K+ preprints
   - Quality: Medium-High

#### Require Free API Keys 🔑

9. **Semantic Scholar** - AI-powered paper search
   - API: `https://api.semanticscholar.org/graph/v1/paper/search`
   - **Key Required**: For >100 requests/5min
   - **Get Key**: https://www.semanticscholar.org/product/api#api-key-form
   - Rate Limit: 5000 req/5min (with key)
   - Coverage: 200M+ papers
   - Quality: Very High (citation graphs, AI recommendations)
   - **Set**: `export ORION_S2_API_KEY="your_key_here"`

10. **CORE** - Academic aggregator
    - API: `https://api.core.ac.uk/v3/search/works`
    - **Key Required**: Yes (free registration)
    - **Get Key**: https://core.ac.uk/services/api/
    - Rate Limit: 10 req/sec (Standard), 1000 req/sec (Premium free)
    - Coverage: 240M+ papers
    - Quality: High
    - **Set**: `export ORION_CORE_API_KEY="your_key_here"`

### Code & Documentation Sources

#### No Authentication Required ✅

11. **Official Documentation** - Vendor docs (scraping)
    - Sources: Kubernetes, Docker, PyTorch, etc.
    - Rate Limit: Respectful delays (5 sec)
    - Quality: Very High (authoritative)

12. **Tech Blogs** - Engineering blogs (RSS feeds)
    - Sources: AWS, Google Cloud, Meta Engineering, etc.
    - Rate Limit: RSS polling (respectful)
    - Quality: High (official vendor content)

#### Higher Rate Limits with Free Keys 🔑

13. **GitHub** - Code repositories and docs
    - API: `https://api.github.com`
    - **Key Optional**: 60 req/hr (no key) → 5000 req/hr (with token)
    - **Get Token**: https://github.com/settings/tokens (select `public_repo` scope)
    - Coverage: 300M+ repositories
    - Quality: High (code + documentation)
    - **Set**: `export ORION_GITHUB_TOKEN="your_token_here"`

14. **Stack Overflow** - Q&A with code samples
    - API: `https://api.stackexchange.com/2.3/search/advanced`
    - **Key Optional**: 300 req/day (no key) → 10,000 req/day (with key)
    - **Get Key**: https://stackapps.com/apps/oauth/register
    - Coverage: 50M+ questions
    - Quality: Medium-High (community-driven)
    - **Set**: `export ORION_SO_API_KEY="your_key_here"`

---

## Potential Future Sources

### Require Paid Subscription 💰

- **IEEE Xplore** - Engineering papers (IEEE Xplore API key requires institutional access)
- **ACM Digital Library** - Computing papers (ACM membership required)
- **Elsevier/ScienceDirect** - Multidisciplinary (API requires subscription)
- **SpringerLink** - Academic books/journals (API requires license)
- **Web of Science** - Citation database (Clarivate subscription)

### Considered but Not Added

- **Papers with Code** - ML papers + code implementations
  - API: `https://paperswithcode.com/api/v1/papers`
  - Status: API is documented but rate limits unclear
  - Consideration: May add if needed for ML/AI category

- **ACL Anthology** - NLP/linguistics papers
  - URL: `https://aclanthology.org/`
  - Status: No official API, would require scraping
  - Consideration: DBLP covers most ACL papers

- **medRxiv** - Medical preprints
  - API: Same as bioRxiv (`https://api.biorxiv.org/details/medrxiv`)
  - Status: Could add as separate source
  - Consideration: Covered by bioRxiv API

- **SSRN** - Social sciences
  - URL: `https://papers.ssrn.com/`
  - Status: No public API
  - Consideration: Not primary focus for homelab/infra

---

## How to Configure API Keys

### 1. Set Environment Variables

Create or edit `orion-harvester/.envrc`:

```bash
# Required for higher rate limits
export ORION_S2_API_KEY="your_semantic_scholar_key"
export ORION_CORE_API_KEY="your_core_api_key"

# Optional for higher rate limits
export ORION_GITHUB_TOKEN="your_github_token"
export ORION_SO_API_KEY="your_stackoverflow_key"

# Recommended for Unpaywall/Crossref
export ORION_CONTACT_EMAIL="your_email@example.com"
```

### 2. Load Environment Variables

If using `direnv`:
```bash
cd orion-harvester
direnv allow
```

Or manually:
```bash
cd orion-harvester
source .envrc
```

### 3. Verify Configuration

```bash
# Check if keys are set
echo $ORION_S2_API_KEY
echo $ORION_CORE_API_KEY
```

---

## Usage Examples

### Harvest with All Sources
```bash
orion harvest --category gpu-and-cuda --max-results 50
```

### Harvest Academic Papers Only (No GitHub/StackOverflow)
```bash
orion harvest --category databases --providers papers --max-results 100
```

### Test New Sources with Dry Run
```bash
python3 orion_harvester.py harvest --category llm-serving-and-inference --dry-run --max-results 10
```

---

## Source Selection Strategy

The harvester uses a **waterfall strategy** for academic papers:
1. Try Semantic Scholar (best citation data)
2. Fall back to OpenAlex (comprehensive)
3. Fall back to arXiv (CS/physics preprints)
4. Fall back to CORE (broad coverage)
5. Fall back to DBLP (CS-focused)
6. Fall back to Crossref (DOI metadata)
7. Fall back to Zenodo (research data)
8. Fall back to HAL (European papers)
9. Fall back to PubMed (life sciences)
10. Fall back to bioRxiv (biology preprints)

**Result:** You get the best available metadata and citations for each query term.

---

## Rate Limiting & Politeness

- All providers: 5-second delay between requests
- User-Agent: Includes contact email for Crossref/OpenAlex
- Respects HTTP 429 (rate limit) responses
- Implements exponential backoff for errors

---

## Quality Metrics by Source

| Source | Citation Data | Full-Text | Freshness | Reliability |
|--------|--------------|-----------|-----------|-------------|
| Semantic Scholar | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| arXiv | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| OpenAlex | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| DBLP | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| CORE | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Crossref | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| PubMed | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| GitHub | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Official Docs | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## Troubleshooting

### "HTTP 429 Rate Limit"
- Add API keys for higher limits
- Increase `RATE_LIMIT_DELAY` in `orion_harvester.py`
- Run harvests during off-peak hours

### "No results from any source"
- Check query terms in `config/search_terms.csv`
- Verify API endpoints are accessible (`curl` test)
- Check logs: `tail -f orion-harvester/logs/harvest.log`

### "API key not working"
- Verify key is exported: `echo $ORION_S2_API_KEY`
- Check key validity on provider's website
- Ensure no extra quotes or spaces in `.envrc`

---

**Last Updated:** 2025-01-22  
**Total Sources:** 14 (10 no-auth + 4 optional keys)  
**New Sources Added:** DBLP, HAL, PubMed, bioRxiv
