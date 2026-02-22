# Phase 1: Reverse Proxy & SSL - Deployment Guide

**Status:** Ready for deployment
**Duration:** 2-4 hours
**Complexity:** Medium

---

## 🎯 What This Phase Delivers

After completing Phase 1, you will have:

✅ **Single Domain Access:** `https://orion.lab` (instead of multiple ports)
✅ **SSL/TLS Encryption:** HTTPS for all services
✅ **Path-Based Routing:**
- `https://orion.lab/` → ORION Core (main portal)
- `https://orion.lab/knowledge` → AnythingLLM
- `https://orion.lab/workflows` → n8n
- `https://orion.lab/metrics` → Grafana
- `https://orion.lab/dashboard` → Traefik dashboard (admin only)

✅ **Security Headers:** CSP, HSTS, XSS protection
✅ **Compression:** Gzip compression for better performance
✅ **Monitoring:** Prometheus scraping Traefik metrics

---

## 📋 Prerequisites

### **On Laptop (Development Machine)**

```bash
# Verify you're in the right directory
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/

# Check files exist
ls -la traefik/
ls -la traefik/dynamic/
ls -la prometheus/
ls -la grafana/provisioning/
```

### **On Host (192.168.5.10)**

```bash
# Verify existing services are running
docker ps | grep -E "orion-(vllm|qdrant|anythingllm|n8n)"

# Check disk space
df -h /mnt/nvme2

# Verify network exists
docker network ls | grep orion-net
```

---

## 🚀 Deployment Steps

### **Step 1: Generate SSL Certificates**

On laptop:

```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/traefik/

# Make script executable
chmod +x generate-certs.sh

# Generate self-signed certificate for orion.lab
./generate-certs.sh orion.lab
```

**Expected Output:**
```
Creating certificate directory: /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/traefik/certs
Generating private key...
Generating self-signed certificate (valid for 3650 days)...
Certificate generated successfully!

Files created:
  - certs/orion.lab.key (private key)
  - certs/orion.lab.crt (certificate)
```

**Verify certificates:**
```bash
ls -lh certs/
# Should show: orion.lab.crt, orion.lab.key
```

---

### **Step 2: Add DNS Entry**

On laptop:

```bash
# Add to /etc/hosts (requires sudo)
echo "192.168.5.10  orion.lab" | sudo tee -a /etc/hosts

# Verify
ping -c 2 orion.lab
# Should resolve to 192.168.5.10
```

On host (192.168.5.10):

```bash
# Add to /etc/hosts
echo "192.168.5.10  orion.lab" | sudo tee -a /etc/hosts
```

**Optional:** If you have a local DNS server (Pi-hole, etc.), add `orion.lab` there instead.

---

### **Step 3: Copy Files to Host**

On laptop:

```bash
# Create deployment package
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/

# Sync to host
rsync -avz --progress \
  traefik/ \
  prometheus/ \
  grafana/ \
  docker-compose.traefik.yml \
  lab:/mnt/nvme2/orion-project/setup/
```

**Verify on host:**
```bash
ssh lab "ls -la /mnt/nvme2/orion-project/setup/traefik/"
```

---

### **Step 4: Create Environment File**

On host:

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup/

# Create .env file (if not exists)
cat > .env << 'EOF'
# Existing variables (from original setup)
HF_TOKEN=your_huggingface_token
VLLM_API_KEY=your_vllm_api_key
QDRANT_API_KEY=your_qdrant_api_key
ANYTHINGLLM_API_KEY=your_anythingllm_api_key
ANYTHINGLLM_AUTH_TOKEN=your_auth_token
N8N_ADMIN_USER=admin
N8N_ADMIN_PASSWORD=changeme_secure_password
N8N_WEBHOOK_URL=https://orion.lab/workflows
N8N_OWNER_EMAIL=admin@orion.lab

# New variables for Grafana
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=changeme_secure_password
EOF

# Secure the file
chmod 600 .env

# Verify
cat .env
```

**⚠️ IMPORTANT:** Replace all `changeme_*` passwords with strong passwords!

---

### **Step 5: Stop Existing Services**

On host:

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup/

# Stop current services (if running)
docker compose -f docker-compose.yml down

# Verify all stopped
docker ps | grep orion
# Should show nothing (empty)
```

**⚠️ Note:** This will cause downtime. Services will be unavailable during migration.

---

### **Step 6: Deploy with Traefik**

On host:

```bash
cd /mnt/nvme2/orion-project/setup/

# Start Traefik first
docker compose -f docker-compose.traefik.yml up -d traefik

# Wait 10 seconds
sleep 10

# Check Traefik health
docker logs orion-traefik --tail 50

# Should see:
# "Configuration loaded from file"
# "Server configuration reloaded"
```

**Start backend services:**

```bash
# Start infrastructure services
docker compose -f docker-compose.traefik.yml up -d qdrant vllm

# Wait for vLLM to load model (3-5 minutes)
docker logs -f orion-vllm
# Press Ctrl+C when you see: "Application startup complete"

# Start AnythingLLM
docker compose -f docker-compose.traefik.yml up -d anythingllm

# Start remaining services
docker compose -f docker-compose.traefik.yml up -d n8n prometheus grafana

# Start ORION Core (build first if needed)
cd /home/user/Laptop-MAIN/applications/orion-core/
docker build -t orion-core:latest .

# Then on host:
docker compose -f docker-compose.traefik.yml up -d orion-core
```

**Verify all services running:**

```bash
docker compose -f docker-compose.traefik.yml ps

# Should show all services as "running" and "healthy"
```

---

### **Step 7: Verify Routing**

On laptop (or any machine with orion.lab in /etc/hosts):

#### **Test HTTP → HTTPS Redirect:**
```bash
curl -I http://orion.lab
# Should see: HTTP/1.1 308 Permanent Redirect
# Location: https://orion.lab/
```

#### **Test HTTPS (ignore cert warning for now):**
```bash
curl -k https://orion.lab/health
# Should return: {"status": "healthy"}
```

#### **Test Service Routes:**
```bash
# ORION Core
curl -k https://orion.lab/ | grep "ORION"

# AnythingLLM
curl -k https://orion.lab/knowledge/api/v1/system/ping

# n8n
curl -k -u admin:your_password https://orion.lab/workflows/healthz

# Grafana
curl -k https://orion.lab/metrics/api/health

# Prometheus (LAN only)
curl -k https://orion.lab/prometheus/-/healthy
```

---

### **Step 8: Trust SSL Certificate (Optional)**

To remove browser warnings about self-signed certificates:

#### **On Linux (laptop):**
```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/traefik/

sudo cp certs/orion.lab.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates
```

#### **On macOS:**
```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  certs/orion.lab.crt
```

#### **On Windows:**
1. Open `certs/orion.lab.crt`
2. Click "Install Certificate"
3. Choose "Local Machine"
4. Place in "Trusted Root Certification Authorities"

#### **On Browser (Firefox):**
1. Visit `https://orion.lab`
2. Click "Advanced" → "Accept the Risk and Continue"
3. Firefox will remember this exception

---

### **Step 9: Access Services**

Open browser and navigate to:

| Service | URL | Notes |
|---------|-----|-------|
| **ORION Core** | https://orion.lab/ | Main portal |
| **AnythingLLM** | https://orion.lab/knowledge | RAG UI |
| **n8n** | https://orion.lab/workflows | Workflows (requires auth) |
| **Grafana** | https://orion.lab/metrics | Dashboards (admin/password) |
| **Prometheus** | https://orion.lab/prometheus | Metrics (LAN only) |
| **Traefik Dashboard** | https://orion.lab/dashboard | Proxy admin (admin/changeme) |

**⚠️ CRITICAL:** Change the Traefik dashboard password immediately!

Generate new password:
```bash
# On host
sudo apt install apache2-utils
echo $(htpasswd -nB admin) | sed -e s/\\$/\\$\\$/g
# Copy output to traefik/dynamic/middlewares.yml → dashboard-auth
```

---

## ✅ Verification Checklist

### **Functionality Tests:**

- [ ] All services accessible via `https://orion.lab/*`
- [ ] HTTP redirects to HTTPS
- [ ] SSL certificate valid (or warning acknowledged)
- [ ] ORION Core web interface loads
- [ ] AnythingLLM responds to queries
- [ ] n8n workflow editor accessible
- [ ] Grafana shows Prometheus datasource
- [ ] Traefik dashboard shows all routers

### **Performance Tests:**

- [ ] Page load times < 2 seconds
- [ ] No console errors in browser
- [ ] WebSocket connections work (ORION chat)
- [ ] Gzip compression active (check Network tab)

### **Security Tests:**

- [ ] Security headers present (check browser dev tools)
- [ ] CSP policy enforced
- [ ] Rate limiting works (try 100 rapid requests)
- [ ] LAN-only routes blocked from outside network

---

## 🔧 Troubleshooting

### **Problem: "Connection refused" to https://orion.lab**

**Possible Causes:**
1. DNS not configured
2. Traefik not running
3. Firewall blocking port 443

**Solution:**
```bash
# Check DNS
ping orion.lab

# Check Traefik
ssh lab "docker ps | grep traefik"

# Check firewall (host)
ssh lab "sudo iptables -L -n | grep 443"

# Check Traefik logs
ssh lab "docker logs orion-traefik --tail 100"
```

---

### **Problem: "503 Service Unavailable"**

**Possible Causes:**
1. Backend service not running
2. Health check failing
3. Wrong service port in labels

**Solution:**
```bash
# Check service status
ssh lab "docker compose -f docker-compose.traefik.yml ps"

# Check specific service health
ssh lab "docker inspect orion-vllm | grep Health -A 10"

# Check Traefik routing
# Visit: https://orion.lab/dashboard → HTTP → Routers
```

---

### **Problem: "Certificate not trusted"**

**This is expected with self-signed certificates.**

**Solutions:**
1. Trust the certificate (Step 8)
2. Use browser exception (Firefox)
3. Switch to Let's Encrypt (requires public domain)

---

### **Problem: Traefik dashboard shows "No routers"**

**Possible Causes:**
1. Docker labels not applied
2. Services not on orion-net network
3. Traefik can't reach Docker socket

**Solution:**
```bash
# Check labels
ssh lab "docker inspect orion-core | grep traefik"

# Check network
ssh lab "docker network inspect orion-net"

# Check Docker socket
ssh lab "docker exec orion-traefik ls -la /var/run/docker.sock"
```

---

## 🎯 Next Steps (Phase 2)

Once Phase 1 is stable:

1. **Monitor for 48 hours** - Ensure no issues
2. **Collect feedback** - Note any pain points
3. **Prepare for Phase 2** - Authelia SSO deployment

**Phase 2 Preview:**
- Single sign-on (log in once)
- Multi-factor authentication
- Centralized user management
- Session management

---

## 📚 Resources

**Traefik Documentation:**
- [Quick Start](https://doc.traefik.io/traefik/getting-started/quick-start/)
- [Docker Provider](https://doc.traefik.io/traefik/providers/docker/)
- [Let's Encrypt](https://doc.traefik.io/traefik/https/acme/)

**Troubleshooting:**
- Traefik logs: `docker logs orion-traefik -f`
- Service logs: `docker logs <service-name> -f`
- Traefik dashboard: `https://orion.lab/dashboard`

---

## 🔐 Security Notes

**What's Protected:**
✅ All traffic encrypted (TLS 1.2+)
✅ Security headers (XSS, HSTS, CSP)
✅ LAN-only routes (Qdrant, vLLM, Prometheus)
✅ Rate limiting (100 req/s)

**What's NOT Protected (Yet):**
⚠️ No SSO (separate logins per service) → Phase 2
⚠️ No MFA (multi-factor auth) → Phase 2
⚠️ No audit logging → Phase 6
⚠️ Self-signed cert (not trusted by default)

---

**Deployment completed?** Mark as done and proceed to Phase 2 when ready! 🚀
