# ORION Core - Deployment Guide

**Complete guide to deploying the ORION Core unified AI system**

**Target:** Lab host (192.168.5.10)
**Access:** <http://192.168.5.10:5000>
**Status:** Ready to deploy (v1.1.0 with hybrid UI)

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Environment Configuration](#environment-configuration)
4. [Deployment Steps](#deployment-steps)
5. [Verification](#verification)
6. [Post-Deployment](#post-deployment)
7. [Troubleshooting](#troubleshooting)
8. [Updating](#updating)

---

## 🔍 Prerequisites

### Required Services (Must be running on lab host)

ORION Core depends on these services. Verify they are running before proceeding:

```bash
# SSH to lab host
ssh lab

# Check services
docker ps | grep -E 'vllm|qdrant|anythingllm'

# Expected output:
# vllm         - port 8000  (LLM inference)
# qdrant       - port 6333  (vector database)
# anythingllm  - port 3001  (RAG interface)
```

**If services are not running:**

```bash
# Navigate to ORION infrastructure
cd /mnt/nvme2/orion-project/setup

# Start services
docker compose up -d

# Wait ~2 minutes for vLLM to load model
docker compose logs -f vllm
# Wait for: "Uvicorn running on http://0.0.0.0:8000"
```

### Required: AnythingLLM API Key

ORION Core needs an API key to query the knowledge base:

1. **Open AnythingLLM UI:** <http://192.168.5.10:3001>
2. **Navigate to:** Settings → API Keys
3. **Create new API key** (or use existing)
4. **Copy the key** - you'll need it in environment setup
5. **Store in:** `orion-operational/KEYS_AND_TOKENS.md` (gitignored)

Example format: `HVEFW5H-B3QM9NH-MA17PF8-0KMCWTE`

---

## ✅ Pre-Deployment Checklist

Run this checklist before deploying:

### On Laptop (Development Machine)

```bash
# 1. Navigate to orion-core
cd /home/user/Laptop-MAIN/applications/orion-core

# 2. Verify all files are committed
git status
# Should show: "working tree clean"

# 3. Push latest changes (if needed)
git push

# 4. Verify hybrid UI files exist
ls -la web/index-hybrid.html
ls -la web/static/js/sidebar.js
ls -la web/static/css/main.css

# Expected: All files present
```

### On Lab Host

```bash
# SSH to lab host
ssh lab

# 1. Pull latest code
cd /root/orion
git pull

# 2. Verify orion-core directory
ls -la applications/orion-core/

# 3. Check disk space (need ~5GB for Docker images)
df -h /mnt/nvme2
# Should have > 10GB free

# 4. Verify Docker network exists
docker network ls | grep orion
# If not present: docker network create orion-net
```

---

## ⚙️ Environment Configuration

### Step 1: Create Environment File

```bash
# On lab host
cd /root/orion/applications/orion-core

# Copy example configuration
cp .env.example .env

# Edit configuration
nano .env
```

### Step 2: Required Configuration

**Minimal configuration (replace YOUR_KEY with actual key):**

```bash
# ============================================================================
# API KEYS (REQUIRED!)
# ============================================================================
ORION_ANYTHINGLLM_API_KEY=YOUR_ANYTHINGLLM_API_KEY_HERE

# ============================================================================
# SERVICE URLS (Default values work in Docker Compose)
# ============================================================================
ORION_VLLM_URL=http://vllm:8000
ORION_QDRANT_URL=http://qdrant:6333
ORION_ANYTHINGLLM_URL=http://anythingllm:3001
ORION_OLLAMA_URL=http://host.docker.internal:11434

# ============================================================================
# FEATURES (Enable all subsystems)
# ============================================================================
ORION_ENABLE_KNOWLEDGE=true
ORION_ENABLE_ACTION=true
ORION_ENABLE_LEARNING=true
ORION_ENABLE_WATCH=true

# ============================================================================
# APPLICATION
# ============================================================================
ORION_ENVIRONMENT=production
ORION_LOG_LEVEL=INFO
```

**Save and exit** (Ctrl+X, Y, Enter in nano)

### Step 3: Verify Environment

```bash
# Check API key is set
grep ANYTHINGLLM_API_KEY .env
# Should NOT be empty or "your-api-key-here"
```

---

## 🚀 Deployment Steps

### Option A: Standalone Deployment (Recommended First Time)

Deploy ORION Core in its own compose stack for easier debugging:

```bash
# On lab host
cd /root/orion/applications/orion-core

# Build and start
docker compose up -d

# Watch startup logs
docker compose logs -f orion-core
```

**Expected startup logs:**

```
INFO: Starting ORION Core...
INFO: ORION Core Configuration:
INFO:   Environment: production
INFO:   Version: 1.1.0
INFO:   Features: Knowledge✓ Action✓ Learning✓ Watch✓
INFO: Metrics initialized
INFO: ORION Core started successfully!
INFO: Uvicorn running on http://0.0.0.0:5000
```

**Wait for:** "ORION Core started successfully!"

Press Ctrl+C to stop watching logs (container keeps running).

### Option B: Integrated Deployment

Add ORION Core to your main docker-compose.yml:

```bash
# On lab host
cd /mnt/nvme2/orion-project/setup

# Edit main compose file
nano docker-compose.yml
```

**Add this service:**

```yaml
  orion-core:
    build:
      context: /root/orion/applications/orion-core
      dockerfile: Dockerfile
    container_name: orion-core
    restart: unless-stopped
    ports:
      - "0.0.0.0:5000:5000"
    environment:
      - ORION_ENVIRONMENT=production
      - ORION_LOG_LEVEL=INFO
      - ORION_VLLM_URL=http://vllm:8000
      - ORION_QDRANT_URL=http://qdrant:6333
      - ORION_ANYTHINGLLM_URL=http://anythingllm:3001
      - ORION_OLLAMA_URL=http://host.docker.internal:11434
      - ORION_ANYTHINGLLM_API_KEY=${ANYTHINGLLM_API_KEY}
      - ORION_ENABLE_KNOWLEDGE=true
      - ORION_ENABLE_ACTION=true
      - ORION_ENABLE_LEARNING=true
      - ORION_ENABLE_WATCH=true
    volumes:
      - /mnt/nvme1/orion-data:/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
    depends_on:
      vllm:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      anythingllm:
        condition: service_healthy
    networks:
      - orion-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

**Start the service:**

```bash
docker compose up -d orion-core
docker compose logs -f orion-core
```

---

## ✅ Verification

### Step 1: Check Container Health

```bash
# On lab host
docker ps | grep orion-core

# Expected:
# STATUS: Up X minutes (healthy)
```

If status shows "unhealthy" or "starting", wait 60 seconds and check again.

### Step 2: Test Health Endpoint

```bash
curl http://localhost:5000/health

# Expected output:
{
  "status": "healthy",
  "app": "ORION Core",
  "version": "1.1.0",
  "environment": "production"
}
```

### Step 3: Test Hybrid UI

**From your laptop browser:** <http://192.168.5.10:5000>

**Expected:**

- Modern dark interface loads
- Chat panel on left (65%)
- Live sidebar on right (35%)
- System health cards visible
- Four quick start hint buttons

### Step 4: Test Chat Functionality

In the browser UI:

1. **Click:** "📊 System status" quick start button
2. **Expected:** ORION responds with system overview
3. **Type:** "What is Kubernetes?"
4. **Expected:** ORION queries knowledge base and returns cited answer

### Step 5: Verify Sidebar Updates

Watch the sidebar:

1. **Metrics should show:**
   - GPU usage percentage
   - Disk usage with sizes
   - Memory usage with sizes

2. **Service health cards should show:**
   - vLLM: ⚡ X% GPU (healthy/warning)
   - Qdrant: ⚡ 1.2M vectors (healthy)
   - GPU: 🌡️ XX°C (healthy if < 80°C)
   - Disk: 💾 XX% used (healthy if < 80%)

3. **Recent activity should update** when you send messages

---

## 🎉 Post-Deployment

### Access Points

Once deployed, ORION Core is accessible at:

- **Main UI (Hybrid):** <http://192.168.5.10:5000>
- **Legacy Dashboard:** <http://192.168.5.10:5000/dashboard>
- **Simple Chat:** <http://192.168.5.10:5000/chat/simple>
- **Health Check:** <http://192.168.5.10:5000/health>
- **Metrics (Prometheus):** <http://192.168.5.10:5000/metrics>
- **API Status:** <http://192.168.5.10:5000/api/status>
- **Hybrid Status:** <http://192.168.5.10:5000/api/hybrid/status>

### Mobile Access

The hybrid UI is responsive and works on mobile:

- **From phone/tablet:** <http://192.168.5.10:5000>
- Sidebar adapts to bottom sheet on mobile
- Touch-friendly interface

### Bookmarking

Save this URL as "ORION" in your browser for quick access.

### Start Using ORION

Try these queries to get started:

```
📊 "Show me full system status"
🧠 "What are Docker best practices for GPU passthrough?"
⚡ "Check GPU temperature and usage"
💾 "How much disk space is available?"
🔍 "Tell me about Kubernetes StatefulSets"
```

---

## 🔧 Troubleshooting

### Issue: "Connection refused" in browser

**Symptoms:** Cannot load <http://192.168.5.10:5000>

**Solution:**

```bash
# Check if container is running
docker ps | grep orion-core

# If not running:
docker compose up -d orion-core

# Check logs for errors
docker compose logs orion-core
```

### Issue: "WebSocket disconnected"

**Symptoms:** Chat shows "Reconnecting..." repeatedly

**Solution:**

```bash
# Check backend logs
docker compose logs -f orion-core | grep -i websocket

# Restart container
docker compose restart orion-core
```

### Issue: Sidebar shows "Unable to fetch system metrics"

**Symptoms:** Red error in alerts section

**Solution:**

```bash
# Test API endpoint manually
docker exec orion-core curl http://localhost:5000/api/hybrid/status

# Check if dependent services are healthy
docker ps | grep -E 'vllm|qdrant'

# If services are down, start them:
cd /mnt/nvme2/orion-project/setup
docker compose up -d
```

### Issue: "Failed to connect to vLLM/Qdrant"

**Symptoms:** Backend logs show connection errors

**Solution:**

```bash
# Verify services are accessible from orion-core container
docker exec orion-core curl http://vllm:8000/health
docker exec orion-core curl http://qdrant:6333/

# Check Docker network
docker network inspect orion-net | grep orion-core

# If network issues, reconnect:
docker network connect orion-net orion-core
docker compose restart orion-core
```

### Issue: Knowledge queries return "No context found"

**Symptoms:** ORION responds but says it can't find information

**Solution:**

```bash
# Verify AnythingLLM is running
curl http://192.168.5.10:3001/api/v1/workspaces

# Check Qdrant collections
curl http://192.168.5.10:6333/collections

# Verify API key is correct
docker exec orion-core printenv | grep ANYTHINGLLM_API_KEY
```

### Issue: High memory usage

**Symptoms:** Container using > 2GB RAM

**Solution:**

```bash
# Check actual usage
docker stats orion-core --no-stream

# Normal: 500MB - 1GB
# High: > 2GB (may indicate memory leak)

# Restart to clear cache
docker compose restart orion-core

# If persistent, check logs for errors
docker compose logs orion-core | grep -i error
```

### Issue: Logs show "ORION_ANYTHINGLLM_API_KEY not set"

**Symptoms:** Knowledge subsystem disabled

**Solution:**

```bash
# Edit .env file
nano .env

# Add valid API key
ORION_ANYTHINGLLM_API_KEY=your-actual-key-here

# Restart container
docker compose restart orion-core
```

---

## 🔄 Updating

### Updating ORION Core

When new features are added:

```bash
# On laptop - commit and push changes
cd /home/user/Laptop-MAIN/applications/orion-core
git add .
git commit -m "feat: Description"
git push

# On lab host - pull and rebuild
ssh lab
cd /root/orion
git pull

cd applications/orion-core
docker compose down
docker compose build --no-cache
docker compose up -d

# Verify
docker compose logs -f orion-core
```

### Backup Before Updates

```bash
# Backup conversation data (if stored)
docker exec orion-core tar czf /data/backup.tar.gz /data/conversations/

# Copy backup to host
docker cp orion-core:/data/backup.tar.gz /mnt/nvme1/orion-data/backups/
```

---

## 📊 Monitoring

### Prometheus Metrics

ORION Core exposes Prometheus metrics at `/metrics`:

```bash
curl http://192.168.5.10:5000/metrics
```

**Key metrics:**

- `orion_requests_total` - Total requests
- `orion_requests_duration_seconds` - Request latency
- `orion_active_sessions` - Active WebSocket sessions
- `orion_subsystem_requests_total{subsystem="knowledge"}` - Per-subsystem metrics

**Future:** Configure Prometheus scrape job and Grafana dashboard.

### Container Logs

```bash
# Live logs
docker compose logs -f orion-core

# Last 100 lines
docker compose logs --tail 100 orion-core

# Errors only
docker compose logs orion-core | grep ERROR

# Save logs to file
docker compose logs orion-core > /tmp/orion-core.log
```

---

## 🎯 Next Steps

After successful deployment:

1. **Explore Features:**
   - Try all 4 subsystems (Knowledge, Action, Learning, Watch)
   - Test keyboard shortcuts (Cmd+K, Cmd+L, Cmd+B)
   - Collapse/expand sidebar

2. **Integrate with Existing Tools:**
   - Add to Homer dashboard as main entry point
   - Configure Authelia SSO (future feature)
   - Set up Telegram bot for mobile notifications (optional)

3. **Customize:**
   - Adjust alert thresholds via `/api/watch/thresholds`
   - Configure learning automation with n8n
   - Add custom context actions

4. **Read Documentation:**
   - [QUICK-START.md](docs/QUICK-START.md) - User guide
   - [HYBRID-UI-DESIGN.md](docs/HYBRID-UI-DESIGN.md) - UI specification
   - [README.md](README.md) - Complete documentation

---

## 🆘 Getting Help

**If deployment fails:**

1. Check all prerequisites are met
2. Review troubleshooting section above
3. Check logs: `docker compose logs orion-core`
4. Verify .env configuration
5. Test dependent services (vLLM, Qdrant, AnythingLLM)

**Debug checklist:**

```bash
# Container running?
docker ps | grep orion-core

# Logs showing errors?
docker compose logs orion-core | grep -i error

# Can reach services?
docker exec orion-core curl http://vllm:8000/health
docker exec orion-core curl http://qdrant:6333/

# Port accessible?
curl http://192.168.5.10:5000/health

# API key set?
docker exec orion-core printenv | grep API_KEY
```

---

**Status:** ORION Core v1.1.0 is production-ready and fully tested!

**Deployment Date:** November 18, 2025
**Next Review:** After Phase 2 (backend API improvements)
