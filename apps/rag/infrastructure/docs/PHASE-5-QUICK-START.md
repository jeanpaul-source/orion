# Phase 5: Grafana AlertManager - Quick Start ⚡

**Time:** 15 minutes | **Difficulty:** Medium | **Prerequisites:** Phase 4 deployed

---

## 🚀 Quick Deploy

### Step 1: Configure Alerts (5 minutes)

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup

# Add to .env
cat >> .env << 'EOF'

# ===== GRAFANA ALERTMANAGER (Phase 5) =====
# Use same Telegram bot as Phase 4
GRAFANA_TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_FROM_PHASE_4
GRAFANA_TELEGRAM_CHAT_ID=YOUR_USER_ID_FROM_PHASE_4

# Email alerts (optional)
ALERT_EMAIL_TO=admin@example.com
ALERT_EMAIL_FROM=alerts@orion.lab
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EOF

# Edit with real values
nano .env
```

### Step 2: Deploy Monitoring (5 minutes)

```bash
# Stop services
docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml down

# Start with alerting
docker compose \
  -f docker-compose.traefik.yml \
  -f docker-compose.authelia.yml \
  -f docker-compose.alerting.yml \
  up -d

# Verify
docker compose ps | grep -E "node-exporter|cadvisor|nvidia"
```

**Expected:** 3 new services running (node-exporter, cadvisor, nvidia-gpu-exporter)

### Step 3: Verify (3 minutes)

```bash
# Check Prometheus loaded rules
docker compose logs prometheus | grep "Loaded.*rules"

# Expected: "Loaded 1 rule files with 24 rules"

# Access Prometheus
https://orion.lab/prometheus
# Go to Status → Rules
# Verify all 7 rule groups loaded

# Access Grafana
https://orion.lab/metrics
# Go to Alerting → Alert groups
# Verify rules are active
```

### Step 4: Test (2 minutes)

```bash
# Trigger test alert
docker compose stop qdrant

# Wait 2 minutes
# Check Telegram - you should receive:
# "🚨 CRITICAL ALERT: QdrantDown"

# Resolve
docker compose start qdrant

# Wait 1 minute
# Check Telegram - you should receive:
# "✅ RESOLVED: QdrantDown"
```

---

## 📊 What You Get

**24+ Alert Rules:**
- ✅ ORION Core (down, errors, slow, queue)
- ✅ vLLM (down, GPU temp, memory)
- ✅ Qdrant (down, empty, slow)
- ✅ Authelia (down, auth failures)
- ✅ System (disk, memory, CPU)
- ✅ Docker (restarts, OOM)
- ✅ Traefik (down, errors, SSL)

**Monitoring:**
- ✅ System metrics (node-exporter)
- ✅ Container metrics (cAdvisor)
- ✅ GPU metrics (nvidia-exporter)

**Notifications:**
- ✅ Telegram (instant mobile alerts)
- ✅ Email (critical alerts)
- ✅ Webhook (ORION API)

---

## 🎯 Alert Routing

| Severity | Channels | Example |
|----------|----------|---------|
| **Critical** | Telegram + Email + Webhook | Service down, GPU critical temp |
| **Warning** | Telegram only | High resource usage, slow responses |
| **Info** | Log only | Routine events, status changes |

---

## 🐛 Quick Troubleshooting

### No alerts received?

```bash
# Check logs
docker compose logs grafana | grep -i alert
docker compose logs prometheus | grep -i alert

# Verify bot token
curl "https://api.telegram.org/bot<TOKEN>/getMe"
```

### Alerts not firing?

```bash
# Test PromQL query in Prometheus UI
up{job="orion-core"} == 0

# Check if service is actually down
docker compose ps orion-core
```

### GPU metrics missing?

```bash
# Verify exporter running
docker compose ps nvidia-gpu-exporter

# Test GPU access
docker compose exec nvidia-gpu-exporter nvidia-smi
```

---

## ✅ Success Criteria

- ✅ 3 new exporters running
- ✅ Prometheus shows 24 rules loaded
- ✅ Test alert received on Telegram
- ✅ Resolution alert received
- ✅ All targets UP in Prometheus

---

**Phase 5 Complete!** 🎉

**Next:** [Phase 6: Centralized Audit Logging](PHASE-6-DEPLOYMENT-GUIDE.md)

**Full Guide:** [PHASE-5-DEPLOYMENT-GUIDE.md](PHASE-5-DEPLOYMENT-GUIDE.md)
