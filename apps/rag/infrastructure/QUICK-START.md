# ORION Phase 1 - Quick Start Guide

## 🚀 Deploy in 10 Commands

**Estimated Time:** 30-45 minutes (plus vLLM model loading ~5 min)

### **On Laptop:**

```bash
# 1. Navigate to infrastructure directory
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/

# 2. Generate SSL certificates
cd traefik && ./generate-certs.sh orion.lab && cd ..

# 3. Add to /etc/hosts
echo "192.168.5.10  orion.lab" | sudo tee -a /etc/hosts

# 4. Sync to host
rsync -avz --progress traefik/ prometheus/ grafana/ docker-compose.traefik.yml \
  lab:/mnt/nvme2/orion-project/setup/
```

### **On Host (via SSH):**

```bash
# 5. SSH to host
ssh lab

# 6. Navigate to setup directory
cd /mnt/nvme2/orion-project/setup/

# 7. Create/update .env file
nano .env  # Add missing variables (see PHASE-1-DEPLOYMENT-GUIDE.md Step 4)

# 8. Stop old services (if running)
docker compose -f docker-compose.yml down

# 9. Start Traefik + Infrastructure
docker compose -f docker-compose.traefik.yml up -d traefik qdrant vllm

# 10. Wait for vLLM, then start remaining services
# Wait ~3-5 min for model loading
docker logs -f orion-vllm  # Press Ctrl+C when ready

docker compose -f docker-compose.traefik.yml up -d anythingllm n8n prometheus grafana orion-core
```

### **Verify:**

```bash
# Check all services running
docker compose -f docker-compose.traefik.yml ps

# Test access (from laptop)
curl -k https://orion.lab/health
```

### **Access:**

Open browser → **https://orion.lab/**

---

## 🔑 Default Credentials

**Change these immediately after first login!**

- **Traefik Dashboard:** admin / admin
- **n8n:** admin / (from .env N8N_ADMIN_PASSWORD)
- **Grafana:** admin / (from .env GRAFANA_ADMIN_PASSWORD)

---

## 📚 Full Documentation

- **Step-by-step deployment:** `PHASE-1-DEPLOYMENT-GUIDE.md`
- **Architecture & overview:** `PHASE-1-COMPLETE.md`
- **Troubleshooting:** See deployment guide Section 9

---

## 🆘 Quick Troubleshooting

**Problem:** Connection refused
```bash
# Check DNS
ping orion.lab  # Should resolve to 192.168.5.10

# Check Traefik running
ssh lab "docker ps | grep traefik"
```

**Problem:** 503 Service Unavailable
```bash
# Check backend service health
ssh lab "docker compose -f docker-compose.traefik.yml ps"

# Check specific service
ssh lab "docker logs orion-vllm --tail 50"
```

**Problem:** Certificate error
- Expected with self-signed certs
- Click "Advanced" → "Accept Risk" in browser
- OR: Trust certificate (see deployment guide Step 8)

---

## ⏭️ Next: Phase 2 (SSO)

Once Phase 1 is stable (48 hours), move to Phase 2:
- Single sign-on (Authelia)
- Multi-factor authentication
- Centralized user management

---

**Questions?** Check `PHASE-1-DEPLOYMENT-GUIDE.md` for detailed steps.
