# Phase 5: Grafana AlertManager - Deployment Guide

**Status:** Implementation Complete
**Estimated Time:** 30 minutes
**Prerequisites:** Phase 4 deployed (Telegram bot recommended for notifications)

---

## 📋 Overview

Phase 5 adds **comprehensive alerting and monitoring** with Grafana AlertManager, providing:

- 🚨 **Multi-channel alerts** (Telegram, Email, Webhooks)
- 📊 **25+ alert rules** for all ORION services
- 🎯 **Smart routing** by severity and service
- 🔕 **Silencing and inhibition** to prevent alert fatigue
- 📈 **System metrics** (CPU, memory, disk, GPU, containers)
- 🎨 **Rich formatting** with custom templates

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Prometheus                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Alert Rules (25+ rules):                         │    │
│  │  • ORION Core (down, errors, slow, queue)        │    │
│  │  • vLLM (down, GPU temp, memory, model load)     │    │
│  │  • Qdrant (down, empty, slow searches)           │    │
│  │  • Authelia (down, auth failures, Redis)         │    │
│  │  • System (disk, memory, CPU)                    │    │
│  │  • Docker (restarts, OOM kills)                  │    │
│  │  • Traefik (down, errors, SSL expiry)            │    │
│  └────────────────────────────────────────────────────┘    │
│                          ▼                                  │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Metrics Collection:                               │    │
│  │  • Node Exporter (system metrics)                 │    │
│  │  • cAdvisor (container metrics)                   │    │
│  │  • NVIDIA Exporter (GPU metrics)                  │    │
│  │  • Service metrics (ORION, vLLM, Qdrant, etc.)   │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 Grafana AlertManager                        │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Routing Logic:                                    │    │
│  │  • Critical → Telegram + Email + Webhook          │    │
│  │  • Warning → Telegram only                        │    │
│  │  • Info → Log only (no notification)              │    │
│  │  • Service-specific routing                       │    │
│  └────────────────────────────────────────────────────┘    │
│                          ▼                                  │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Inhibition Rules:                                 │    │
│  │  • Suppress warnings if critical firing           │    │
│  │  • Suppress info if warning firing                │    │
│  │  • Suppress resource alerts if service down       │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Notification Channels                          │
│                                                             │
│  📱 Telegram       ✉️ Email        🌐 Webhook               │
│  (via Phase 4)    (SMTP)         (ORION API)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Step 1: Configure Telegram for Alerts

### 1.1 Option A: Use Existing ORION Bot (Recommended)

If you deployed Phase 4, you can reuse the same Telegram bot:

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup

# Get your bot token from .env (already configured in Phase 4)
grep TELEGRAM_BOT_TOKEN .env

# Get your chat ID (already configured in Phase 4)
grep TELEGRAM_ALLOWED_USERS .env
```

**Use these values in Step 1.3 below.**

### 1.2 Option B: Create Dedicated Alert Bot (Advanced)

If you want separate bots for chat and alerts:

```bash
# On Telegram:
# 1. Message @BotFather
# 2. Send /newbot
# 3. Name: ORION Alerts
# 4. Username: orion_alerts_bot
# 5. Save the token
```

### 1.3 Add Alert Configuration to .env

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup
nano .env
```

Add these lines:

```bash
# ============================================================================
# GRAFANA ALERTMANAGER (Phase 5)
# ============================================================================

# Telegram alerts (use same bot as Phase 4 or create new one)
GRAFANA_TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
GRAFANA_TELEGRAM_CHAT_ID=123456789

# Email alerts (optional - for critical alerts)
ALERT_EMAIL_TO=admin@example.com
ALERT_EMAIL_FROM=alerts@orion.lab

# SMTP configuration (optional - Gmail example)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

**Note:** For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833), not your regular password.

---

## 📦 Step 2: Deploy Monitoring Stack

### 2.1 Stop Current Services

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup

# Stop services
docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml down
```

### 2.2 Deploy with Alert Monitoring

```bash
# Start all services with alerting overlay
docker compose \
  -f docker-compose.traefik.yml \
  -f docker-compose.authelia.yml \
  -f docker-compose.alerting.yml \
  up -d

# This adds:
# - node-exporter (system metrics)
# - cadvisor (container metrics)
# - nvidia-gpu-exporter (GPU metrics)
# - Updated Prometheus (with alert rules)
# - Updated Grafana (with AlertManager)
```

### 2.3 Verify Deployment

```bash
# Check all services are running
docker compose ps

# Expected new services:
# - orion-node-exporter (running)
# - orion-cadvisor (running)
# - orion-nvidia-exporter (running)

# Verify Prometheus loaded alert rules
docker compose logs prometheus | grep "Loading configuration file"
docker compose logs prometheus | grep "alert_rules"

# Expected output:
# "Loaded 1 rule files with 25 rules"
```

---

## ✅ Step 3: Verify Prometheus Configuration

### 3.1 Access Prometheus Web UI

```bash
# Open browser to Prometheus
https://orion.lab/prometheus

# Or direct access (from lab host only)
http://localhost:9090
```

### 3.2 Check Alert Rules

1. Navigate to **Status → Rules**
2. Verify all rule groups loaded:
   - `orion_core_alerts` (4 rules)
   - `vllm_alerts` (5 rules)
   - `qdrant_alerts` (3 rules)
   - `authelia_alerts` (3 rules)
   - `system_resource_alerts` (4 rules)
   - `docker_alerts` (2 rules)
   - `traefik_alerts` (3 rules)

**Total: 24 alert rules**

### 3.3 Check Targets

Navigate to **Status → Targets**

Verify all targets are **UP:**
- ✅ prometheus (localhost:9090)
- ✅ traefik (traefik:8080)
- ✅ orion-core (orion-core:5000)
- ✅ vllm (vllm:8000)
- ✅ qdrant (qdrant:6333)
- ✅ authelia (authelia:9959)
- ✅ redis (redis:6379)
- ✅ node-exporter (node-exporter:9100)
- ✅ cadvisor (cadvisor:8080)
- ✅ nvidia-gpu (nvidia-gpu-exporter:9835)

**If any target is down**, check logs:
```bash
docker compose logs <service-name>
```

---

## 📊 Step 4: Configure Grafana Dashboards

### 4.1 Access Grafana

```bash
# Open browser
https://orion.lab/metrics

# Login:
# Username: admin
# Password: (from Phase 3 setup)
```

### 4.2 Import System Dashboards

**Node Exporter Dashboard:**

1. Navigate to **Dashboards → Import**
2. Enter dashboard ID: **1860**
3. Click **Load**
4. Select Prometheus data source
5. Click **Import**

**Docker/Container Dashboard:**

1. **Dashboards → Import**
2. Enter dashboard ID: **193**
3. Select Prometheus
4. **Import**

**NVIDIA GPU Dashboard:**

1. **Dashboards → Import**
2. Enter dashboard ID: **14574**
3. Select Prometheus
4. **Import**

### 4.3 Create ORION Alert Dashboard

1. **Dashboards → New → New Dashboard**
2. Click **Add visualization**
3. Select **Prometheus** data source
4. Add panels:

**Panel 1: Active Alerts**
```promql
ALERTS{alertstate="firing"}
```

**Panel 2: Alert Rate by Severity**
```promql
sum by(severity) (rate(ALERTS{alertstate="firing"}[5m]))
```

**Panel 3: Service Health**
```promql
up{job=~"orion-core|vllm|qdrant|authelia"}
```

5. Save dashboard as "ORION Alert Overview"

---

## 🔔 Step 5: Test Alerts

### 5.1 Test Telegram Notifications

**Trigger a test alert manually:**

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup

# Stop a service to trigger "Down" alert
docker compose stop qdrant

# Wait 2 minutes for alert to fire
# You should receive Telegram notification:
# "🚨 CRITICAL ALERT: QdrantDown"
```

**Check Telegram:**

You should receive a message like:

```
🚨 CRITICAL ALERT 🚨

QdrantDown
🔥 Severity: CRITICAL
📦 Service: qdrant

⚠️ Qdrant vector database is down

Qdrant has been unreachable for 2+ minutes. RAG queries will fail.

📖 Runbook: https://orion.lab/docs/runbooks/qdrant-down

⏰ Started: 14:32:45 EST

🔗 View in Grafana

⚡ IMMEDIATE ACTION REQUIRED
```

**Resolve the alert:**

```bash
# Restart the service
docker compose start qdrant

# Wait ~1 minute
# You should receive resolution notification:
# "✅ RESOLVED: QdrantDown"
```

### 5.2 Test GPU Temperature Alert

**Simulate high GPU temperature (for testing only!):**

This alert fires automatically when GPU temp >80°C. You can monitor it without triggering:

```bash
# Check current GPU temperature
nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader

# If temp is below 80°C, alert won't fire (this is good!)
# Under normal load (vLLM running), temp should be 50-70°C
```

**To test the alert** (only if needed):

Run a GPU stress test:
```bash
# Install stress tool
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 \
  bash -c "apt update && apt install -y mesa-utils && while true; do glxgears; done"

# Monitor temperature
watch -n 1 nvidia-smi

# Stop when temp reaches 80°C (before it gets critical!)
# You should receive warning alert
```

### 5.3 Test Disk Space Alert

```bash
# Check current disk usage
df -h /mnt/nvme2

# Disk space alerts trigger at:
# - Warning: 90% full
# - Critical: 95% full

# If you're below 90%, alert won't fire (good!)
```

---

## 🔕 Step 6: Configure Silences (Optional)

### 6.1 Silence During Maintenance

If you're performing maintenance and don't want alerts:

1. Open Grafana: `https://orion.lab/metrics`
2. Navigate to **Alerting → Silences**
3. Click **New Silence**
4. Configure:
   - **Matchers:** `service=qdrant` (or leave empty for all)
   - **Start:** Now
   - **Duration:** 1 hour
   - **Comment:** "Planned maintenance"
5. Click **Submit**

### 6.2 Pre-configured Maintenance Window

The AlertManager is configured with a maintenance window:

- **Time:** Sunday 2:00 AM - 4:00 AM
- **Effect:** All alerts are silenced during this time

**To modify:**

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup
nano grafana/provisioning/alerting/alertmanager.yml

# Find the 'maintenance' time interval
# Modify times/days as needed
```

---

## 📈 Step 7: Monitor Alert Performance

### 7.1 View Alert History

**In Grafana:**

1. Navigate to **Alerting → Alert groups**
2. View all active and resolved alerts
3. Click on alert to see details and timeline

**In Prometheus:**

1. Go to **Alerts** tab
2. See all configured rules and their status
3. Filter by state (firing, pending, inactive)

### 7.2 Alert Metrics

**Query Prometheus for alert metrics:**

```promql
# Total alerts by severity
count by(severity) (ALERTS{alertstate="firing"})

# Alert duration
time() - ALERTS_FOR_STATE{alertstate="firing"}

# Alert frequency (alerts per hour)
rate(ALERTS{alertstate="firing"}[1h])
```

### 7.3 Notification Delivery

**Check notification logs:**

```bash
# Grafana logs (shows alert delivery)
docker compose logs grafana | grep -i "alert"

# Look for:
# "Alert sent successfully to telegram"
# "Alert sent successfully to email"
```

---

## 🐛 Troubleshooting

### Alerts Not Firing

**Problem:** Expected alert didn't trigger

**Solutions:**

1. **Check Prometheus rules:**
   ```bash
   # Verify rules loaded
   docker compose exec prometheus promtool check rules /etc/prometheus/alert_rules.yml

   # Check for errors
   docker compose logs prometheus | grep -i error
   ```

2. **Check alert state:**
   - Go to Prometheus UI → Alerts
   - Look for your alert rule
   - Check if it's in "Pending" state (waiting for `for` duration)
   - Verify the expression is evaluating correctly

3. **Test the PromQL query:**
   - Go to Prometheus UI → Graph
   - Paste the alert expression
   - Execute and verify it returns data

**Example:**
```promql
# This should return 0 if service is up, 1 if down
up{job="orion-core"} == 0
```

### Telegram Notifications Not Received

**Problem:** Alerts fire but no Telegram message

**Solutions:**

1. **Verify bot token:**
   ```bash
   cat .env | grep GRAFANA_TELEGRAM_BOT_TOKEN
   curl "https://api.telegram.org/bot<TOKEN>/getMe"
   ```

   Should return bot info.

2. **Verify chat ID:**
   ```bash
   cat .env | grep GRAFANA_TELEGRAM_CHAT_ID

   # Test sending message
   curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
     -d "chat_id=<CHAT_ID>" \
     -d "text=Test from AlertManager"
   ```

3. **Check Grafana logs:**
   ```bash
   docker compose logs grafana | grep -i telegram
   ```

   Look for errors like:
   - "Unauthorized" → Wrong bot token
   - "Chat not found" → Wrong chat ID
   - "Bad Request" → Malformed message

4. **Check AlertManager config:**
   ```bash
   # Verify config loaded
   docker compose logs grafana | grep -i "alertmanager"
   ```

### Email Notifications Not Received

**Problem:** Email alerts not delivered

**Solutions:**

1. **Check SMTP credentials:**
   ```bash
   cat .env | grep SMTP
   ```

2. **Test SMTP connection:**
   ```bash
   # From lab host
   telnet smtp.gmail.com 587

   # Should connect to SMTP server
   ```

3. **For Gmail - Check App Password:**
   - Regular Gmail password won't work
   - Must create App Password: https://myaccount.google.com/apppasswords
   - Use that password in SMTP_PASSWORD

4. **Check spam folder** in your email

5. **Check Grafana logs:**
   ```bash
   docker compose logs grafana | grep -i "email\|smtp"
   ```

### GPU Metrics Missing

**Problem:** GPU temperature/usage not showing in alerts

**Solutions:**

1. **Check nvidia-gpu-exporter is running:**
   ```bash
   docker compose ps nvidia-gpu-exporter
   ```

2. **Verify GPU is accessible:**
   ```bash
   docker compose exec nvidia-gpu-exporter nvidia-smi
   ```

3. **Check Prometheus target:**
   - Go to Prometheus UI → Targets
   - Find nvidia-gpu target
   - Should be UP, not DOWN

4. **Query GPU metrics:**
   ```promql
   nvidia_gpu_temperature_celsius
   ```

   Should return current GPU temperature.

### High Alert Volume (Alert Fatigue)

**Problem:** Too many alerts, becoming overwhelming

**Solutions:**

1. **Adjust thresholds:**
   - Edit `prometheus/alert_rules.yml`
   - Increase thresholds (e.g., disk 90% → 95%)
   - Increase `for` duration (e.g., 2m → 5m)

2. **Use inhibition rules:**
   - Already configured to suppress warnings if critical firing
   - Add custom inhibition in `alertmanager.yml`

3. **Adjust notification frequency:**
   - In `alertmanager.yml`, increase `repeat_interval`
   - Default: 3h for warnings, 30m for critical

4. **Use silences:**
   - Temporary silence known issues
   - Silence during maintenance

---

## 🎓 Best Practices

### 1. Alert Tuning

**Start conservative, then refine:**

```yaml
# Week 1: Default thresholds
- alert: HighCPU
  expr: cpu_usage > 90
  for: 10m

# Week 2: After observing baseline
- alert: HighCPU
  expr: cpu_usage > 95  # Adjusted based on normal patterns
  for: 5m  # Reduced delay for faster response
```

### 2. Alert Hierarchy

**Critical → Immediate action required**
- Service completely down
- Data loss risk
- Security breach

**Warning → Investigate soon**
- High resource usage
- Degraded performance
- Potential issues

**Info → For awareness only**
- Routine events
- Non-urgent notifications
- Status changes

### 3. Runbook Links

**Always include runbook URLs in alerts:**

```yaml
annotations:
  runbook_url: "https://orion.lab/docs/runbooks/service-down"
```

**Create simple runbooks:**

```markdown
# Qdrant Down Runbook

## Symptoms
- Qdrant service unreachable
- RAG queries failing

## Investigation
1. Check service status: `docker compose ps qdrant`
2. Check logs: `docker compose logs qdrant --tail 100`
3. Check disk space: `df -h /mnt/nvme1`

## Resolution
1. Restart service: `docker compose restart qdrant`
2. If fails, check data corruption
3. Restore from backup if needed
```

### 4. Alert Documentation

**Document each alert:**

```yaml
- alert: GPUTemperatureHigh
  # WHY: High temps can damage GPU and reduce performance
  # WHEN: Sustained temp >80°C for 2+ minutes
  # ACTION: Check cooling, reduce load, monitor
  expr: nvidia_gpu_temperature_celsius > 80
  for: 2m
```

---

## 📊 Alert Rules Reference

### ORION Core Alerts (4 rules)

| Alert | Severity | Threshold | Duration | Description |
|-------|----------|-----------|----------|-------------|
| ORIONCoreDown | Critical | Service unreachable | 1m | ORION API is down |
| ORIONHighErrorRate | Warning | >10 errors/sec | 2m | High error rate in requests |
| ORIONSlowResponses | Warning | 95th %ile >10s | 5m | Response time degraded |
| ORIONQueueBacklog | Warning | >50 requests queued | 3m | Request queue growing |

### vLLM Alerts (5 rules)

| Alert | Severity | Threshold | Duration | Description |
|-------|----------|-----------|----------|-------------|
| vLLMDown | Critical | Service unreachable | 2m | GPU inference unavailable |
| GPUTemperatureHigh | Warning | >80°C | 2m | GPU temp above threshold |
| GPUTemperatureCritical | Critical | >85°C | 1m | GPU temp critically high |
| GPUMemoryHigh | Warning | >90% used | 5m | GPU memory nearly full |
| vLLMModelLoadFailed | Critical | Load errors | Immediate | Model failed to load |

### Qdrant Alerts (3 rules)

| Alert | Severity | Threshold | Duration | Description |
|-------|----------|-----------|----------|-------------|
| QdrantDown | Critical | Service unreachable | 2m | Vector DB is down |
| QdrantCollectionEmpty | Critical | 0 vectors | 5m | Knowledge base empty |
| QdrantSlowSearches | Warning | 95th %ile >2s | 5m | Search performance degraded |

### System Resource Alerts (4 rules)

| Alert | Severity | Threshold | Duration | Description |
|-------|----------|-----------|----------|-------------|
| DiskSpaceLow | Warning | <10% free | 5m | Disk space running low |
| DiskSpaceCritical | Critical | <5% free | 2m | Critically low disk space |
| HighMemoryUsage | Warning | <10% available | 5m | System memory low |
| HighCPUUsage | Warning | >90% used | 10m | Sustained high CPU |

---

## 🚀 Next Steps

**Phase 5 Complete!** ✅

You now have:
- ✅ Comprehensive monitoring (system, containers, GPU)
- ✅ 24+ alert rules covering all services
- ✅ Multi-channel notifications (Telegram, email)
- ✅ Smart routing and inhibition
- ✅ Rich alert templates

**Continue to Phase 6:**

👉 **[PHASE-6-DEPLOYMENT-GUIDE.md](PHASE-6-DEPLOYMENT-GUIDE.md)** - Centralized audit logging with searchable dashboard

**Or enhance alerting:**

- Create custom alert rules for your workloads
- Add Slack/Discord notification channels
- Build custom Grafana dashboards
- Set up alert escalation policies

---

## 📚 Additional Resources

**Grafana Alerting:**
- Official Docs: https://grafana.com/docs/grafana/latest/alerting/
- Best Practices: https://grafana.com/docs/grafana/latest/alerting/fundamentals/
- Template Guide: https://grafana.com/docs/grafana/latest/alerting/manage-notifications/template-notifications/

**Prometheus Alerting:**
- Alert Rules: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- Best Practices: https://prometheus.io/docs/practices/alerting/
- PromQL: https://prometheus.io/docs/prometheus/latest/querying/basics/

**Telegram Bot API:**
- Formatting: https://core.telegram.org/bots/api#formatting-options
- HTML Mode: https://core.telegram.org/bots/api#html-style

---

**Questions or Issues?**

Check `docker compose logs grafana` and `docker compose logs prometheus` for detailed error messages.
