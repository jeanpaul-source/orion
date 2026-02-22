# API Key Setup Guide for ORION Harvester

Quick reference for obtaining free API keys to increase rate limits for data providers.

---

## Required Keys (For Production Use)

### 1. Semantic Scholar API Key

**Why:** Increases rate limit from 100 req/5min → 5000 req/5min  
**Cost:** Free  
**Time to obtain:** ~1 minute  

**Steps:**
1. Visit: https://www.semanticscholar.org/product/api#api-key-form
2. Fill out form with name and email
3. Check email for API key
4. Export key:
   ```bash
   export ORION_S2_API_KEY="your_key_here"
   ```

---

### 2. CORE API Key

**Why:** Enables access to 240M papers (required)  
**Cost:** Free (Standard plan)  
**Time to obtain:** ~2 minutes  

**Steps:**
1. Visit: https://core.ac.uk/services/api/
2. Click "Register" and create account
3. Navigate to API dashboard
4. Copy API key from dashboard
5. Export key:
   ```bash
   export ORION_CORE_API_KEY="your_key_here"
   ```

---

## Optional Keys (For Higher Rate Limits)

### 3. GitHub Personal Access Token

**Why:** Increases rate limit from 60 req/hr → 5000 req/hr  
**Cost:** Free  
**Time to obtain:** ~1 minute  

**Steps:**
1. Visit: https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Name: "ORION Harvester"
4. Scopes: Select only `public_repo` (read-only access to public repos)
5. Expiration: "No expiration" or 1 year
6. Click "Generate token" and copy immediately
7. Export token:
   ```bash
   export ORION_GITHUB_TOKEN="ghp_xxxxxxxxxxxxx"
   ```

**Security Note:** This token only needs read-only public access. Never commit it to Git.

---

### 4. Stack Overflow API Key

**Why:** Increases rate limit from 300 req/day → 10,000 req/day  
**Cost:** Free  
**Time to obtain:** ~3 minutes  

**Steps:**
1. Visit: https://stackapps.com/apps/oauth/register
2. Log in with Stack Overflow account (or create one)
3. Fill out form:
   - **Name:** ORION Harvester
   - **Description:** Academic paper and Q&A harvesting
   - **OAuth Domain:** (leave blank)
   - **Application Website:** (optional)
4. Click "Register Your Application"
5. Copy the **Key** (not the Secret)
6. Export key:
   ```bash
   export ORION_SO_API_KEY="your_key_here"
   ```

---

## Configuration

### Method 1: Environment Variables (Temporary)

```bash
export ORION_S2_API_KEY="your_semantic_scholar_key"
export ORION_CORE_API_KEY="your_core_api_key"
export ORION_GITHUB_TOKEN="your_github_token"
export ORION_SO_API_KEY="your_stackoverflow_key"
export ORION_CONTACT_EMAIL="your_email@example.com"  # For Crossref/Unpaywall
```

**Lasts:** Until terminal session ends

---

### Method 2: .envrc File (Persistent)

Create `orion-harvester/.envrc`:

```bash
# Required for production
export ORION_S2_API_KEY="your_semantic_scholar_key"
export ORION_CORE_API_KEY="your_core_api_key"

# Optional for higher limits
export ORION_GITHUB_TOKEN="your_github_token"
export ORION_SO_API_KEY="your_stackoverflow_key"

# Recommended for better Crossref results
export ORION_CONTACT_EMAIL="your_email@example.com"
```

**Load with direnv:**
```bash
cd orion-harvester
direnv allow
```

**Or manually:**
```bash
cd orion-harvester
source .envrc
```

**Lasts:** Permanently (reload on each `cd orion-harvester`)

---

### Method 3: Shell Profile (Global)

Add to `~/.bashrc` or `~/.zshrc`:

```bash
export ORION_S2_API_KEY="your_semantic_scholar_key"
export ORION_CORE_API_KEY="your_core_api_key"
export ORION_GITHUB_TOKEN="your_github_token"
export ORION_SO_API_KEY="your_stackoverflow_key"
export ORION_CONTACT_EMAIL="your_email@example.com"
```

Then reload:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

**Lasts:** All terminal sessions

---

## Verification

Check if keys are set:
```bash
echo $ORION_S2_API_KEY        # Should print your key
echo $ORION_CORE_API_KEY      # Should print your key
echo $ORION_GITHUB_TOKEN      # Should print your token
echo $ORION_SO_API_KEY        # Should print your key
echo $ORION_CONTACT_EMAIL     # Should print your email
```

---

## Security Best Practices

### ✅ DO:
- Store keys in `.envrc` (Git-ignored)
- Use `direnv` for automatic loading
- Rotate keys periodically
- Use minimal scopes (GitHub: only `public_repo`)
- Keep keys out of shell history (use `.envrc` instead of typing)

### ❌ DON'T:
- Commit keys to Git (check `.gitignore` includes `.envrc`)
- Share keys publicly (Discord, Slack, GitHub issues)
- Use keys with write permissions (GitHub)
- Hardcode keys in Python scripts

---

## Troubleshooting

### "API key not working"
1. Verify key is exported: `echo $ORION_S2_API_KEY`
2. Check for extra quotes/spaces: should be alphanumeric only
3. Re-generate key on provider's website
4. Test with `curl`:
   ```bash
   curl -H "x-api-key: $ORION_S2_API_KEY" \
     "https://api.semanticscholar.org/graph/v1/paper/search?query=vllm&limit=1"
   ```

### "Rate limit still low"
1. Confirm key is loaded: `echo $ORION_S2_API_KEY` (should not be empty)
2. Restart terminal or `source .envrc`
3. Check provider dashboard for key status

### "Key revoked"
- Regenerate key on provider's website
- Update `.envrc` with new key
- Reload: `source .envrc`

---

## Rate Limits Summary

| Provider | No Key | With Key | Key Required? |
|----------|--------|----------|---------------|
| Semantic Scholar | 100 req/5min | 5000 req/5min | No, but highly recommended |
| CORE | N/A | 10 req/sec | **Yes** (free) |
| GitHub | 60 req/hr | 5000 req/hr | No, but recommended |
| Stack Overflow | 300 req/day | 10,000 req/day | No, but recommended |
| arXiv | 3 req/sec | N/A | No |
| OpenAlex | Polite | N/A | No (email in User-Agent) |
| Crossref | 50 req/sec | N/A | No (email in User-Agent) |
| PubMed | 3 req/sec | 10 req/sec | No, but key increases limit |
| All others | Varies | N/A | No |

---

## Quick Start (Recommended Minimum)

For production use, obtain at minimum:

1. **Semantic Scholar key** - Essential for quality citation data
2. **CORE key** - Required for accessing 240M papers

**Time investment:** ~3 minutes total  
**Benefit:** 50x rate limit increase for primary sources

---

**Last Updated:** 2025-01-22  
**Related:** [Data Sources Guide](../guides/DATA_SOURCES.md)
