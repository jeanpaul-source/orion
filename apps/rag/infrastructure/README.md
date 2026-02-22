# ORION Infrastructure

**Deployment and configuration management for ORION production services**

**Location:** `applications/orion-rag/infrastructure/`
**Purpose:** Infrastructure-as-code for host services (vLLM, Qdrant, AnythingLLM, n8n)

---

## 📋 What This Is

This directory contains the **source of truth** for ORION's infrastructure configuration. All changes are made here on the laptop, then deployed to the host.

**Philosophy:** Laptop = control plane (edit configs here) | Host = execution layer (just runs what we deploy)

---

## 🎯 Current Configuration

### Embedding Model: BGE-base-en-v1.5 (768-dim)

**Configured:** November 12, 2025
**Model:** `BAAI/bge-base-en-v1.5`
**Dimensions:** 768
**Max Chunk Length:** 512 tokens

**Why BGE over MiniLM:**

- Better quality for technical documentation
- Industry standard for production RAG systems
- Only ~440MB RAM overhead (runs in AnythingLLM, not GPU)
- One-time embedding cost, lifetime quality benefit

### ⚠️ CRITICAL WARNING

**DO NOT CHANGE `EMBEDDING_MODEL_PREF` AFTER DOCUMENTS ARE EMBEDDED**

Once documents are processed with BGE (768-dim), changing to a different model will:

- ❌ Cause dimension mismatch errors from Qdrant
- ❌ Break all search functionality
- ❌ Require re-embedding ALL documents (hours of work)

If you must change:

1. Stop all services
2. Delete all Qdrant collections
3. Clear AnythingLLM database
4. Re-upload and process ALL documents

---

## 🚀 Deployment

### Quick Deploy

```bash
cd ~/Laptop-MAIN/applications/orion-rag/infrastructure
./deploy.sh
```

The deploy script will:

1. ✅ Verify BGE is configured correctly
2. 📦 Backup existing configs on host
3. 📤 Copy docker-compose.yml and .env to host
4. 🔄 Optionally restart services
5. ✅ Verify deployment succeeded

### Manual Deployment

If you prefer manual control:

```bash
# Copy files
scp docker-compose.yml lab:/mnt/nvme2/orion-project/setup/
scp .env lab:/mnt/nvme2/orion-project/setup/.env

# Restart services
ssh lab "cd /mnt/nvme2/orion-project/setup && docker compose down && docker compose up -d"
```

---

## 📁 Files

- **`docker-compose.yml`** - Service definitions (vLLM, Qdrant, AnythingLLM, n8n, command-api)
- **`.env`** - Production environment variables (HF token, auth) - **Not tracked in git**
- **`.env.example`** - Template for new deployments (no secrets)
- **`deploy.sh`** - Automated deployment script
- **`README.md`** - This file

### Additional Docker Compose Files

- `docker-compose.authelia.yml` - Authentication (Authelia SSO)
- `docker-compose.traefik.yml` - Reverse proxy
- `docker-compose.observability.yml` - Prometheus, Grafana
- `docker-compose.logging.yml` - Loki, Promtail
- `docker-compose.alerting.yml` - Alert manager

---

## 🔧 Service Configuration

### vLLM (Qwen2.5-14B-AWQ)

- **Port:** 127.0.0.1:8000 (internal only)
- **Model:** Qwen/Qwen2.5-14B-Instruct-AWQ (88GB)
- **GPU:** 70% utilization (~16GB VRAM)
- **API Key:** `optional-api-key`

### Qdrant (Vector Database)

- **Port:** 127.0.0.1:6333 (HTTP), 127.0.0.1:6334 (gRPC)
- **Storage:** `/mnt/nvme2/orion-project/services/qdrant`
- **API Key:** EMPTY (no auth on internal network)
- **Expected Dimensions:** 768 (BGE)

### AnythingLLM (RAG Orchestrator)

- **Port:** 0.0.0.0:3001 (LAN accessible)
- **Auth:** Disabled for homelab mode
- **Storage:** `/mnt/nvme2/orion-project/services/anythingllm`
- **Embedding:** BGE-base-en-v1.5 (768-dim)

### n8n (Workflow Automation)

- **Port:** 0.0.0.0:5678 (LAN accessible)
- **Auth:** Disabled (admin/admin default)

---

## 🔄 Making Changes

### Workflow

1. **Edit on laptop** - Modify `docker-compose.yml` in this directory
2. **Test locally** - Review changes, check syntax: `docker compose config`
3. **Deploy** - Run `./deploy.sh`
4. **Verify** - Check services are healthy

### Common Changes

**Change embedding model** (⚠️ requires re-embedding all docs):

```yaml
# In docker-compose.yml, AnythingLLM environment:
- EMBEDDING_MODEL_PREF=BAAI/bge-large-en-v1.5  # 1024-dim
```

**Change LLM model:**

```yaml
# In docker-compose.yml, vLLM command:
command: >
  --model Qwen/Qwen2.5-32B-Instruct-AWQ
```

**Adjust resource limits:**

```yaml
# In docker-compose.yml, service deploy section:
deploy:
  resources:
    limits:
      cpus: '16'
      memory: 32G
```

### After Editing

Always run `./deploy.sh` to push changes to host. **Never edit docker-compose.yml directly on the host** - those changes will be overwritten on next deployment.

---

## 📊 Verification Commands

### After Deployment

```bash
# Check services running
ssh lab "cd /mnt/nvme2/orion-project/setup && docker compose ps"

# Verify BGE configuration
ssh lab "docker exec orion-anythingllm env | grep EMBEDDING"

# Check Qdrant collections
ssh lab "curl -s http://localhost:6333/collections"

# Check vLLM model
ssh lab "curl -s http://localhost:8000/v1/models"
```

### Expected Output

**BGE configuration:**

```
EMBEDDING_ENGINE=native
EMBEDDING_MODEL_PREF=BAAI/bge-base-en-v1.5
EMBEDDING_MODEL_MAX_CHUNK_LENGTH=512
```

**Qdrant (after fresh rebuild):**

```json
{"result":{"collections":[]},"status":"ok"}
```

---

## 🆘 Troubleshooting

### Deployment Failed

```bash
# Check what's on host
ssh lab "cat /mnt/nvme2/orion-project/setup/docker-compose.yml | grep EMBEDDING"

# Restore from backup
ssh lab "cd /mnt/nvme2/orion-project/setup && cp docker-compose.yml.backup-* docker-compose.yml"
```

### Services Won't Start

```bash
# Check logs
ssh lab "cd /mnt/nvme2/orion-project/setup && docker compose logs --tail=50"

# Validate config
ssh lab "cd /mnt/nvme2/orion-project/setup && docker compose config"
```

### Wrong Embedding Model

If services are running but wrong model:

1. Edit `docker-compose.yml` locally
2. Run `./deploy.sh`
3. Restart services (script will prompt)

---

## 📚 Related Documentation

- **Main README:** `../../../README.md` - ORION system overview
- **Quick Access:** `../../../operational/QUICK-ACCESS.md` - Service access and operations
- **API Keys:** `../../../operational/KEYS_AND_TOKENS.md` - API credentials (gitignored)
- **Deployment Guides:** `./PHASE-*-DEPLOYMENT-GUIDE.md` - Phase-specific deployment docs

---

**Version:** 1.0.0 (BGE Rebuild - Nov 12, 2025)
**Maintainer:** JP
**Last Updated:** November 12, 2025
