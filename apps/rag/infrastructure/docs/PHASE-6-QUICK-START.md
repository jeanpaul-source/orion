# Phase 6: Centralized Audit Logging - Quick Start ⚡

**Time:** 10 minutes | **Difficulty:** Easy | **Prerequisites:** Phase 5 deployed

---

## 🚀 Quick Deploy

### Step 1: Deploy Logging Stack (5 minutes)

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup

# Stop services
docker compose \
  -f docker-compose.traefik.yml \
  -f docker-compose.authelia.yml \
  -f docker-compose.alerting.yml \
  down

# Start with logging
docker compose \
  -f docker-compose.traefik.yml \
  -f docker-compose.authelia.yml \
  -f docker-compose.alerting.yml \
  -f docker-compose.logging.yml \
  up -d

# Verify
docker compose ps | grep -E "loki|promtail"
```

**Expected:** 2 new services running (loki, promtail)

### Step 2: Verify (3 minutes)

```bash
# Check Loki is ready
curl -s http://localhost:3100/ready

# Check Promtail is collecting logs
docker compose logs promtail | grep "client.*connected"

# Access Grafana
https://orion.lab/metrics
```

### Step 3: Explore Logs (2 minutes)

In Grafana:

1. Click **Explore** (compass icon)
2. Select **Loki** datasource
3. Try these queries:

```logql
# All ORION Core logs
{service="orion-core"}

# Errors only
{service="orion-core"} |= "error"

# Authentication events
{service="authelia"} |~ "authentication"

# Telegram bot activity
{component="telegram-bot"}

# Last hour of errors
{level="error"} | json
```

---

## 📊 What You Get

**Log Collection:**
- ✅ All Docker container logs
- ✅ System logs (journald)
- ✅ ORION audit logs (structured)
- ✅ Traefik access logs
- ✅ Authelia auth events
- ✅ Telegram bot activity

**Features:**
- ✅ 30-day log retention
- ✅ Full-text search
- ✅ Label-based filtering
- ✅ Real-time streaming
- ✅ Log-based alerts

**Queries:**
- ✅ Filter by service, level, container
- ✅ Regex pattern matching
- ✅ JSON log parsing
- ✅ Time range selection
- ✅ Rate calculations

---

## 🔍 Useful Queries

### Find Errors

```logql
# All errors in last hour
{level="error"} |~ "."

# Critical errors only
{level="critical"}

# Errors by service
sum by(service) (count_over_time({level="error"}[1h]))
```

### Authentication Audit

```logql
# All auth events
{service="authelia"}

# Failed logins
{service="authelia"} |~ "authentication.*failed"

# Successful logins with username
{service="authelia"} | json | username != ""
```

### Performance Analysis

```logql
# Slow requests (>5s)
{service="orion-core"} | json | duration > 5000

# Request rate
rate({service="orion-core"}[5m])

# Error rate by endpoint
sum by(path) (rate({service="orion-core",level="error"}[5m]))
```

### Security Monitoring

```logql
# Unauthorized access attempts
{service="traefik"} |~ "401|403"

# Suspicious patterns
{service=~".*"} |~ "(?i)sql injection|script|xss|attack"

# Rate of security events
rate({service="authelia"} |~ "blocked|denied|unauthorized"[10m])
```

---

## 🐛 Quick Troubleshooting

### No logs appearing?

```bash
# Check Promtail is running
docker compose ps promtail

# Check Promtail logs
docker compose logs promtail --tail 50

# Verify Docker socket mounted
docker compose exec promtail ls -l /var/run/docker.sock
```

### Loki not starting?

```bash
# Check logs
docker compose logs loki --tail 100

# Verify storage directory
ls -la /mnt/nvme2/orion-project/services/loki

# Check config syntax
docker compose exec loki loki -config.file=/etc/loki/loki-config.yml -verify-config
```

### Logs not searchable?

```bash
# Wait 30 seconds for ingestion
sleep 30

# Check if Loki has logs
curl -s "http://localhost:3100/loki/api/v1/label/service/values" | jq
```

---

## ✅ Success Criteria

- ✅ Loki and Promtail running
- ✅ Logs visible in Grafana Explore
- ✅ Can filter by service
- ✅ Can search for errors
- ✅ Real-time log streaming works

---

**Phase 6 Complete!** 🎉

**Next:** [Phase 7: Security Hardening & Polish](PHASE-7-DEPLOYMENT-GUIDE.md)

**Full Guide:** [PHASE-6-DEPLOYMENT-GUIDE.md](PHASE-6-DEPLOYMENT-GUIDE.md)
