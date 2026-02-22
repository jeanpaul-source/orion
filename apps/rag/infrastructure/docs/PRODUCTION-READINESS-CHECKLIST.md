# ORION Production Readiness Checklist ✅

**Last Updated:** November 18, 2025
**Infrastructure Version:** Production-Lite v1.0

Use this checklist before deploying ORION to production or exposing it to the internet.

---

## 🔒 Security (Critical)

### Authentication & Authorization

- [ ] **Authelia SSO configured** with strong passwords
- [ ] **MFA/TOTP enabled** for all admin users
- [ ] **Session secrets generated** (JWT, session, encryption)
- [ ] **Default passwords changed** (Grafana, n8n, AnythingLLM)
- [ ] **API keys rotated** from defaults
- [ ] **Telegram bot whitelist** configured (user IDs only)
- [ ] **User database backed up** (`users_database.yml`)

**Verify:**
```bash
# Check Authelia secrets are set
cat .env | grep -E "AUTHELIA_(JWT|SESSION|ENCRYPTION)_SECRET"

# Verify MFA is enabled in Authelia config
grep "disable: false" grafana/authelia/configuration.yml

# Check no default passwords
docker compose logs grafana | grep "default admin password"
```

### SSL/TLS

- [ ] **Self-signed certificates** generated (or Let's Encrypt configured)
- [ ] **HTTPS redirect** enabled (HTTP → HTTPS)
- [ ] **HSTS enabled** (31536000 seconds, includeSubDomains, preload)
- [ ] **TLS 1.2+ only** (no TLS 1.0/1.1)
- [ ] **Strong cipher suites** configured
- [ ] **Certificate expiry monitoring** enabled (Prometheus alert)

**Verify:**
```bash
# Check SSL redirect works
curl -I http://orion.lab

# Check HSTS header
curl -I https://orion.lab | grep -i strict

# Test TLS version
openssl s_client -connect orion.lab:443 -tls1_1  # Should fail
openssl s_client -connect orion.lab:443 -tls1_2  # Should succeed
```

### Network Security

- [ ] **Firewall configured** (only ports 80/443/22 exposed)
- [ ] **Internal services** not exposed to internet (Qdrant, Redis, Prometheus)
- [ ] **LAN-only access** for sensitive endpoints
- [ ] **Rate limiting** enabled on all public endpoints
- [ ] **IP whitelist** configured (if needed)
- [ ] **DDoS protection** enabled (Traefik middlewares)

**Verify:**
```bash
# Check open ports
sudo netstat -tulpn | grep LISTEN

# Verify internal services not exposed
curl -I https://orion.lab/qdrant  # Should require auth or fail
curl -I https://orion.lab/redis    # Should fail
```

### Security Headers

- [ ] **Content Security Policy** (CSP) configured
- [ ] **X-Frame-Options** set to SAMEORIGIN
- [ ] **X-Content-Type-Options** set to nosniff
- [ ] **X-XSS-Protection** enabled
- [ ] **Referrer-Policy** set
- [ ] **Permissions-Policy** configured

**Verify:**
```bash
# Check security headers
curl -I https://orion.lab | grep -E "Content-Security-Policy|X-Frame-Options|X-Content-Type"
```

---

## 📊 Monitoring & Alerting (Important)

### Metrics & Dashboards

- [ ] **Prometheus scraping** all services
- [ ] **24 alert rules** loaded and active
- [ ] **Grafana dashboards** imported (Node Exporter, Docker, GPU, ORION)
- [ ] **Service health checks** passing
- [ ] **GPU metrics** collecting (temperature, usage, memory)
- [ ] **System metrics** collecting (CPU, memory, disk)

**Verify:**
```bash
# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job, health}'

# Check alert rules loaded
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[].name'
```

### Alerting

- [ ] **Telegram bot** configured for alerts
- [ ] **Email alerts** configured (for critical)
- [ ] **Alert routing** tested (critical → Telegram+Email)
- [ ] **Test alert** triggered and received
- [ ] **Inhibition rules** working (no alert spam)
- [ ] **Silence schedules** configured (maintenance windows)

**Verify:**
```bash
# Trigger test alert
docker compose stop qdrant
# Wait 2 minutes, check Telegram

# Verify alert routing
docker compose logs grafana | grep -i "alert.*sent"
```

### Logging

- [ ] **Loki collecting logs** from all containers
- [ ] **Promtail running** and connected
- [ ] **30-day retention** configured
- [ ] **Log queries working** in Grafana
- [ ] **Audit logs** collecting (auth events, API requests)
- [ ] **Log-based alerts** active (errors, auth failures)

**Verify:**
```bash
# Check Loki ingestion
curl -s "http://localhost:3100/loki/api/v1/label/service/values" | jq

# Query logs
curl -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={service="orion-core"}' | jq
```

---

## 🔧 System Configuration (Important)

### Storage & Backups

- [ ] **Disk usage < 80%** on all volumes
- [ ] **Log rotation** configured (30-day retention)
- [ ] **Prometheus retention** set (30 days)
- [ ] **Loki retention** set (30 days)
- [ ] **Backup strategy** defined for:
  - [ ] Authelia users database
  - [ ] Grafana dashboards
  - [ ] n8n workflows
  - [ ] AnythingLLM workspaces
  - [ ] Qdrant collections

**Verify:**
```bash
# Check disk usage
df -h /mnt/nvme2

# Verify retention settings
docker compose exec prometheus cat /etc/prometheus/prometheus.yml | grep retention
docker compose exec loki cat /etc/loki/loki-config.yml | grep retention
```

### Performance

- [ ] **GPU temperature** < 80°C under load
- [ ] **Memory usage** < 90%
- [ ] **CPU usage** < 80% sustained
- [ ] **Network latency** < 100ms to services
- [ ] **Query response time** < 2s (95th percentile)
- [ ] **No memory leaks** (monitor over 24h)

**Verify:**
```bash
# GPU stats
nvidia-smi

# System stats
htop

# Query performance
curl -w "@curl-format.txt" -o /dev/null -s https://orion.lab/health
```

### Dependencies

- [ ] **Docker version** >= 24.0
- [ ] **Docker Compose version** >= 2.20
- [ ] **NVIDIA drivers** installed and working
- [ ] **CUDA** compatible with vLLM
- [ ] **Sufficient disk space** (min 100GB free)
- [ ] **Sufficient RAM** (min 16GB free)

**Verify:**
```bash
docker --version
docker compose version
nvidia-smi
df -h
free -h
```

---

## 📱 Services (Required)

### Core Services

- [ ] **ORION Core** running (port 5000)
- [ ] **vLLM** running with model loaded
- [ ] **Qdrant** running with collections
- [ ] **Traefik** routing all services
- [ ] **Authelia** authenticating users
- [ ] **Redis** storing sessions

**Verify:**
```bash
# All services up
docker compose ps

# Health checks passing
curl -s https://orion.lab/health | jq
curl -s http://localhost:8000/health | jq  # vLLM
curl -s http://localhost:6333/            # Qdrant
```

### Monitoring Services

- [ ] **Prometheus** scraping metrics
- [ ] **Grafana** displaying dashboards
- [ ] **Loki** collecting logs
- [ ] **Promtail** shipping logs
- [ ] **Node Exporter** exposing system metrics
- [ ] **cAdvisor** exposing container metrics
- [ ] **NVIDIA GPU Exporter** exposing GPU metrics

**Verify:**
```bash
# Check monitoring stack
curl -s http://localhost:9090/-/ready    # Prometheus
curl -s http://localhost:3000/api/health # Grafana
curl -s http://localhost:3100/ready      # Loki
```

### Optional Services

- [ ] **n8n** for workflow automation
- [ ] **AnythingLLM** for knowledge base UI
- [ ] **Telegram bot** for mobile access

---

## 🧪 Testing (Before Production)

### Functional Testing

- [ ] **Login works** (Authelia SSO)
- [ ] **MFA works** (TOTP code required)
- [ ] **Dashboard loads** (all tabs functional)
- [ ] **Chat works** (WebSocket connection)
- [ ] **RAG queries return results** (with sources)
- [ ] **Metrics visible** in Grafana
- [ ] **Logs searchable** in Loki
- [ ] **Alerts trigger** on test conditions

**Test Scenarios:**
```bash
# 1. Authentication
# - Try login with wrong password (should fail)
# - Try login with correct password (should require MFA)
# - Complete MFA (should grant access)

# 2. Chat Functionality
# - Send message in chat
# - Verify response received
# - Check conversation history

# 3. RAG Query
# - Ask technical question
# - Verify sources cited
# - Check response quality

# 4. Alerting
# - Stop a service
# - Verify alert received (Telegram + Email)
# - Start service
# - Verify resolution alert received
```

### Load Testing (Optional)

- [ ] **Concurrent users** tested (10+ simultaneous)
- [ ] **Query throughput** measured (requests/second)
- [ ] **WebSocket stability** under load
- [ ] **Memory usage** stable over time
- [ ] **No connection leaks** (WebSocket, HTTP)

**Tools:**
```bash
# HTTP load test
ab -n 1000 -c 10 https://orion.lab/health

# WebSocket test
# Use wscat or custom script
```

### Security Testing

- [ ] **SQL injection** tested (if applicable)
- [ ] **XSS** tested (sanitization works)
- [ ] **CSRF** protection verified
- [ ] **Rate limiting** works (429 on exceed)
- [ ] **Auth bypass** attempted (fails)
- [ ] **Unauthorized API access** fails

**Test:**
```bash
# Rate limit test
for i in {1..200}; do curl https://orion.lab/health; done
# Should see 429 errors

# Unauthorized access
curl -I https://orion.lab/metrics  # Should redirect to auth
```

---

## 📚 Documentation (Recommended)

### Runbooks

- [ ] **Service restart procedures** documented
- [ ] **Disaster recovery plan** created
- [ ] **Backup/restore procedures** tested
- [ ] **Incident response playbook** defined
- [ ] **Escalation contacts** listed

### Knowledge Base

- [ ] **Architecture diagram** created
- [ ] **Service dependencies** mapped
- [ ] **Port mappings** documented
- [ ] **Environment variables** documented
- [ ] **Troubleshooting guide** complete

### Operations

- [ ] **Deployment steps** automated or documented
- [ ] **Rollback procedure** defined
- [ ] **Health check procedures** documented
- [ ] **Log analysis tips** documented
- [ ] **Common issues** with solutions

---

## 🚀 Deployment (Production)

### Pre-Deployment

- [ ] **All checklist items** above completed
- [ ] **Staging environment** tested successfully
- [ ] **Rollback plan** prepared
- [ ] **Downtime window** scheduled (if needed)
- [ ] **Stakeholders notified**

### During Deployment

- [ ] **Services stopped** gracefully
- [ ] **Configuration validated** before start
- [ ] **Services started** in correct order
- [ ] **Health checks** passing
- [ ] **Smoke tests** run successfully
- [ ] **Monitoring** shows green

### Post-Deployment

- [ ] **All services operational**
- [ ] **No errors in logs**
- [ ] **Metrics collecting**
- [ ] **Alerts functioning**
- [ ] **Users can access**
- [ ] **24-hour observation** period

---

## 🔄 Maintenance (Ongoing)

### Daily

- [ ] Check dashboard for service health
- [ ] Review critical alerts (if any)
- [ ] Monitor disk usage trends

### Weekly

- [ ] Review alert history
- [ ] Check for failed health checks
- [ ] Review error logs
- [ ] Verify backups completed

### Monthly

- [ ] Review security logs (auth failures)
- [ ] Update dependencies (security patches)
- [ ] Review and optimize alert thresholds
- [ ] Test disaster recovery procedures
- [ ] Review and update documentation

### Quarterly

- [ ] Rotate secrets and API keys
- [ ] Review access control lists
- [ ] Audit user permissions
- [ ] Performance optimization review
- [ ] Capacity planning review

---

## ✅ Sign-Off

**Deployed by:** ___________________  
**Date:** ___________________  
**Environment:** [ ] Development [ ] Staging [ ] Production  
**Version:** ___________________  

**Checklist Completion:**
- [ ] All Critical items complete
- [ ] All Important items complete
- [ ] All Recommended items reviewed
- [ ] Production deployment approved

**Notes:**
_________________________________
_________________________________
_________________________________

---

**Questions or Issues?**

Refer to:
- [PHASE-1-DEPLOYMENT-GUIDE.md](PHASE-1-DEPLOYMENT-GUIDE.md) - Traefik & SSL
- [PHASE-2-DEPLOYMENT-GUIDE.md](PHASE-2-DEPLOYMENT-GUIDE.md) - Authelia SSO
- [PHASE-3-DEPLOYMENT-GUIDE.md](PHASE-3-DEPLOYMENT-GUIDE.md) - Dashboard
- [PHASE-4-DEPLOYMENT-GUIDE.md](PHASE-4-DEPLOYMENT-GUIDE.md) - Telegram Bot
- [PHASE-5-DEPLOYMENT-GUIDE.md](PHASE-5-DEPLOYMENT-GUIDE.md) - AlertManager
- [PHASE-6-QUICK-START.md](PHASE-6-QUICK-START.md) - Logging
