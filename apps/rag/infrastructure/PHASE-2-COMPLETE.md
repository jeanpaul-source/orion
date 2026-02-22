# Phase 2: Single Sign-On with Authelia - COMPLETE ✅

**Completion Date:** November 18, 2025
**Status:** Ready for deployment
**Time to Deploy:** 4-6 hours
**Prerequisites:** Phase 1 deployed and stable

---

## 🎉 What Was Built

Phase 2 adds enterprise-grade authentication and authorization to your ORION infrastructure using Authelia SSO with multi-factor authentication.

### **Before Phase 2:**
```
Each service has separate login:
- Grafana: admin/password
- n8n: admin/password
- Traefik: admin/password
No MFA, no centralized auth
```

### **After Phase 2:**
```
Single Sign-On (SSO):
1. Login once at https://orion.lab/auth
2. Enter username + password + MFA code
3. Access ALL services automatically
4. Session persists 24 hours (or 7 days with "remember me")
```

---

## 📁 Files Created

### **Configuration Files:**

```
applications/orion-rag/infrastructure/
├── authelia/
│   ├── configuration.yml               # Main Authelia config (350 lines)
│   │   ├── Authentication backend (file-based, argon2id hashing)
│   │   ├── Access control rules (admins, users, viewers)
│   │   ├── Session management (Redis, 24h expiry)
│   │   ├── TOTP/MFA configuration
│   │   ├── Brute-force protection
│   │   └── Metrics endpoint
│   │
│   ├── users_database.yml              # User accounts (template)
│   │   └── Username, password hash, email, groups
│   │
│   ├── generate-secrets.sh             # Generate JWT/session/encryption secrets
│   └── add-user.sh                     # Add/update users easily
│
├── docker-compose.authelia.yml         # Authelia + Redis services (180 lines)
│   ├── authelia service (port 9091, 9959 metrics)
│   ├── redis service (session storage)
│   └── Updated labels for all services (SSO integration)
│
├── traefik/dynamic/
│   └── middlewares.yml                 # UPDATED: Added Authelia middleware
│       ├── authelia (two-factor)
│       └── authelia-basic (one-factor)
│
├── prometheus/
│   └── prometheus.yml                  # UPDATED: Added Authelia + Redis scraping
│
├── PHASE-2-DEPLOYMENT-GUIDE.md         # Step-by-step deployment (650 lines)
└── PHASE-2-COMPLETE.md                 # This file
```

### **File Sizes:**
- `authelia/configuration.yml`: ~12 KB (fully commented)
- `authelia/users_database.yml`: ~1.5 KB (template)
- `authelia/add-user.sh`: ~4.5 KB (user management script)
- `docker-compose.authelia.yml`: ~6.5 KB (Authelia stack)
- `PHASE-2-DEPLOYMENT-GUIDE.md`: ~28 KB (comprehensive guide)

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────┐
│            Browser / User                   │
└───────────────┬────────────────────────────┘
                │
                ▼
          [Traefik Proxy]
                │
          [SSL/TLS Layer]
                │
     ┌──────────┴──────────┐
     │                     │
     ▼                     ▼
[Public Routes]      [Protected Routes]
(bypass)             (authelia middleware)
     │                     │
     │                     ▼
     │             ┌──────────────┐
     │             │  Authelia    │
     │             │  (Port 9091) │
     │             └──────┬───────┘
     │                    │
     │              ┌─────┴──────┐
     │              │   Redis    │
     │              │ (Sessions) │
     │              └────────────┘
     │                    │
     │              [Session Valid?]
     │                    │
     │              ┌─────┴─────┐
     │         YES  │           │ NO
     │              ▼           ▼
     │        [Allow Access] [Redirect to /auth]
     │              │           │
     ▼              ▼           ▼
[ORION Core]  [Backend     [Login Page]
              Services]         │
                  │             │
         ┌────────┼─────────────┘
         │        │        │
         ▼        ▼        ▼
    [Grafana] [n8n] [AnythingLLM]
```

---

## 🔐 Security Features Implemented

### **Authentication:**
✅ **File-based user database** - Simple for homelab (no LDAP needed)
✅ **Argon2id password hashing** - Most secure algorithm (3 iterations, 64MB memory)
✅ **Password complexity** - Enforced by add-user.sh script
✅ **Brute-force protection** - 5 attempts → 10 minute ban

### **Multi-Factor Authentication (MFA):**
✅ **TOTP (Time-based One-Time Password)** - Google Authenticator, Authy, 1Password
✅ **Backup codes** - Generated during MFA setup
✅ **QR code enrollment** - Easy mobile setup
✅ **6-digit codes** - SHA1, 30-second period

### **Authorization (Access Control):**
✅ **Role-based access** - Groups: admins, users, viewers
✅ **Path-based rules** - Different policies per service/route
✅ **Network-based rules** - LAN-only routes (Traefik dashboard, Prometheus)
✅ **Granular policies** - bypass, one_factor, two_factor

### **Session Management:**
✅ **Redis backend** - Persistent sessions across restarts
✅ **24-hour expiry** - Maximum session lifetime
✅ **4-hour inactivity** - Auto-logout after inactivity
✅ **7-day "remember me"** - Optional extended sessions
✅ **Secure cookies** - HttpOnly, SameSite=lax

### **Audit & Monitoring:**
✅ **Prometheus metrics** - Login attempts, failures, latency
✅ **Structured logging** - JSON logs to `/var/log/authelia/`
✅ **Failed auth tracking** - Monitor brute-force attempts
✅ **Session analytics** - Active users, session duration

---

## 🚦 Access Control Rules

### **Public Routes (No Auth):**

| Path | Policy | Notes |
|------|--------|-------|
| `/` | bypass | ORION Core main interface |
| `/health` | bypass | Health checks |
| `/static/*` | bypass | Static assets |
| `/ws` | bypass | WebSocket (for ORION chat) |

### **One-Factor Routes (Password Only):**

| Path | Policy | Groups | Notes |
|------|--------|--------|-------|
| `/api/*` | one_factor | all | ORION API endpoints |
| `/metrics/*` | one_factor | all | Grafana dashboards |
| `/workflows/*` | one_factor | all | n8n automation |
| `/knowledge/*` | one_factor | all | AnythingLLM RAG |

### **Two-Factor Routes (Password + MFA):**

| Path | Policy | Groups | Notes |
|------|--------|--------|-------|
| `/dashboard/*` | two_factor | admins | Traefik admin panel |
| `/prometheus/*` | two_factor | admins | Raw metrics (LAN-only) |

**Customizable!** Edit `authelia/configuration.yml` → `access_control` section.

---

## 🔄 Service Integration

### **Services Updated with SSO:**

| Service | Middleware | Before | After |
|---------|-----------|--------|-------|
| **Grafana** | authelia-basic | User/pass per login | SSO (one login) |
| **n8n** | authelia-basic | Basic auth each time | SSO (one login) |
| **AnythingLLM** | authelia-basic | API key prompt | SSO (one login) |
| **Traefik** | authelia | Basic auth | SSO + MFA required |
| **Prometheus** | authelia | No auth (LAN-only) | SSO + MFA required |
| **ORION Core** | bypass | No auth | No auth (public) |

### **How SSO Works:**

```
1. User visits https://orion.lab/metrics (Grafana)
   ↓
2. Traefik checks middleware: authelia-basic
   ↓
3. Traefik sends request to Authelia: "Is this user authenticated?"
   ↓
4. Authelia checks session cookie in browser
   ↓
5a. IF SESSION VALID:
    → Authelia returns: "Yes, user is 'admin' in groups ['admins','users']"
    → Traefik forwards request to Grafana
    → User sees Grafana (no login prompt)

5b. IF NO SESSION:
    → Authelia returns: "No session, redirect to login"
    → Traefik redirects to: https://orion.lab/auth/?rd=https://orion.lab/metrics
    → User logs in (password + MFA)
    → Authelia creates session cookie
    → Redirects back to Grafana
    → User sees Grafana
```

**Subsequent service access:**
- User visits `https://orion.lab/workflows` (n8n)
- Session cookie already exists
- **Instant access** (no login prompt)

---

## 🧪 Testing Scenarios

### **Scenario 1: First Login**

```bash
# Browser: Open https://orion.lab/metrics
# Expected: Redirect to /auth login page

# Action: Enter username + password
# Expected: Prompt to set up MFA (first time only)

# Action: Scan QR code with authenticator app
# Expected: Prompt for 6-digit code

# Action: Enter TOTP code
# Expected: Redirect back to /metrics, logged into Grafana
```

### **Scenario 2: SSO Test**

```bash
# Browser: Already logged in from Scenario 1
# Action: Open new tab, visit https://orion.lab/workflows

# Expected: Instant access to n8n (no login prompt)
# Reason: Session cookie valid
```

### **Scenario 3: MFA Enforcement**

```bash
# Browser: Try logging in without MFA

# Expected: Cannot proceed past login
# Reason: TOTP required (totp.disable: false in config)
```

### **Scenario 4: Access Control**

```bash
# Browser: Login as regular user (not in 'admins' group)
# Action: Try accessing https://orion.lab/dashboard

# Expected: 403 Forbidden or "Access Denied"
# Reason: Only 'admins' group allowed (access_control rules)
```

### **Scenario 5: Session Expiry**

```bash
# Browser: Login without "Remember me"
# Action: Wait 4 hours without activity
# Action: Visit https://orion.lab/metrics

# Expected: Redirect to login (session expired)
# Reason: inactivity: 4h in session config
```

### **Scenario 6: Brute Force Protection**

```bash
# Browser: Enter wrong password 5 times

# Expected: Account locked for 10 minutes
# Log message: "Max retries exceeded"
# Reason: max_retries: 5, ban_time: 10m in regulation config
```

---

## 📊 Metrics & Monitoring

### **Authelia Metrics (Prometheus):**

Available at: `https://orion.lab/prometheus/graph`

**Key Metrics:**
```promql
# Total login attempts
authelia_authentication_first_factor_total

# Successful logins
authelia_authentication_first_factor_success_total

# Failed logins (potential attacks)
authelia_authentication_first_factor_failure_total

# MFA attempts
authelia_authentication_second_factor_total

# Request latency (should be <100ms)
authelia_request_duration_seconds_bucket

# Active sessions (via Redis)
redis_connected_clients
```

### **Grafana Dashboard Queries (Phase 3):**

```promql
# Login success rate
rate(authelia_authentication_first_factor_success_total[5m])
/ rate(authelia_authentication_first_factor_total[5m]) * 100

# Failed login attempts (security alert)
increase(authelia_authentication_first_factor_failure_total[1h]) > 10

# MFA usage percentage
rate(authelia_authentication_second_factor_total[1h])
/ rate(authelia_authentication_first_factor_total[1h]) * 100
```

---

## 🛠️ User Management

### **Add User:**

```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/authelia/

./add-user.sh username password email@example.com "Display Name" groups
```

**Example:**
```bash
# Admin user
./add-user.sh alice SecurePass123 alice@orion.lab "Alice Admin" admins,users

# Regular user
./add-user.sh bob BobPass456 bob@orion.lab "Bob User" users

# Viewer (read-only)
./add-user.sh charlie ViewPass789 charlie@orion.lab "Charlie Viewer" viewers
```

### **Update Password:**

```bash
# Run add-user.sh with same username (it overwrites)
./add-user.sh alice NewSecurePass456 alice@orion.lab "Alice Admin" admins,users
```

### **Remove User:**

```bash
# Manually edit users_database.yml
nano users_database.yml

# Delete user entry, then:
rsync -avz users_database.yml lab:/mnt/nvme2/orion-project/setup/authelia/
ssh lab "docker restart orion-authelia"
```

### **Reset MFA:**

```bash
# User lost phone/authenticator app

# Method 1: Use backup codes (saved during MFA setup)

# Method 2: Admin reset (requires host access)
ssh lab
cd /mnt/nvme2/orion-project/setup/authelia/
sqlite3 db.sqlite3 "DELETE FROM totp_configurations WHERE username='alice';"
docker restart orion-authelia

# User must re-enroll MFA on next login
```

---

## 🎯 Deployment Comparison

### **Phase 1 vs Phase 2:**

| Aspect | Phase 1 | Phase 2 |
|--------|---------|---------|
| **Entry Point** | https://orion.lab | https://orion.lab |
| **Authentication** | Per-service (separate logins) | Single sign-on (one login) |
| **MFA** | None | TOTP (Google Authenticator) |
| **Session** | Per-service | Centralized (Redis) |
| **Access Control** | IP whitelist only | Role-based + IP whitelist |
| **User Management** | Manual (per service) | Centralized (users_database.yml) |
| **Security** | Basic (SSL + headers) | Enterprise-grade (SSO + MFA) |
| **Services** | 8 (Traefik, vLLM, Qdrant, AnythingLLM, n8n, Grafana, Prometheus, ORION) | 10 (+ Authelia, Redis) |
| **Resource Usage** | ~900MB RAM | ~1.2GB RAM (+300MB for Authelia+Redis) |

---

## 🔄 Rollback Plan

If Phase 2 causes issues:

### **Option 1: Rollback to Phase 1 (Full):**

```bash
# On host
cd /mnt/nvme2/orion-project/setup/

# Stop Phase 2 services
docker compose \
  -f docker-compose.traefik.yml \
  -f docker-compose.authelia.yml \
  down authelia redis

# Start only Phase 1 services
docker compose -f docker-compose.traefik.yml up -d

# Services back to Phase 1 state (no SSO)
```

**No data loss** - All volumes preserved.

### **Option 2: Disable Authelia for Specific Service:**

```bash
# Edit docker-compose.authelia.yml
# Remove authelia middleware from service labels

# Example: Remove SSO from Grafana
# Change:
- "traefik.http.routers.grafana.middlewares=authelia-basic,security-headers,compression"
# To:
- "traefik.http.routers.grafana.middlewares=security-headers,compression"

# Restart
docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml up -d
```

---

## 🎓 What You Learned

### **Skills Acquired:**
✅ Single Sign-On (SSO) architecture
✅ Multi-factor authentication (TOTP)
✅ Forward authentication pattern (Traefik → Authelia)
✅ Session management (Redis)
✅ Access control (RBAC - role-based)
✅ User management workflows
✅ Security hardening (brute-force protection)

### **Industry Patterns:**
- Authelia pattern = Forward auth (used by Traefik, nginx)
- Same concepts as: Keycloak, Auth0, Okta
- Transferable to: Enterprise SSO, SAML, OAuth2/OIDC

### **Tools Mastered:**
- Authelia (open-source SSO)
- Redis (session storage)
- Argon2id (password hashing)
- TOTP (MFA protocol)
- Docker Compose overlays (-f flag multiple times)

---

## 🚀 Next Steps (Phase 3)

### **Phase 3: Unified Dashboard Portal**

**What you'll build:**
- React or HTML/CSS/JS single-page app
- Landing page at `https://orion.lab/`
- Status cards (real-time service health)
- Quick actions (restart services, check logs)
- Tabbed interface:
  - Dashboard (default)
  - Metrics (Grafana iframe)
  - Workflows (n8n iframe)
  - Knowledge (AnythingLLM iframe)
  - Chat (ORION Core iframe)

**Features:**
- WebSocket for real-time updates
- GPU usage, disk space, service status
- Dark mode toggle
- Mobile responsive
- Integrated with Authelia (shows logged-in user)

**Timeline:** 1 week (8-12 hours)

---

## 📚 Resources

### **Authelia Documentation:**
- [Official Docs](https://www.authelia.com/docs/)
- [Access Control](https://www.authelia.com/configuration/security/access-control/)
- [Session Management](https://www.authelia.com/configuration/session/introduction/)
- [TOTP Configuration](https://www.authelia.com/configuration/second-factor/time-based-one-time-password/)

### **Community:**
- [GitHub](https://github.com/authelia/authelia)
- [Discord](https://discord.authelia.com)
- [Reddit](https://reddit.com/r/authelia)

### **Troubleshooting:**
- Logs: `docker logs orion-authelia -f`
- Debug: Set `log.level: debug` in configuration.yml
- Test: `https://orion.lab/auth/api/health`

---

## 🏆 Success Criteria

Phase 2 is **deployment-ready** when:

- [x] Authelia configuration created and validated
- [x] User database template ready
- [x] Scripts created (generate-secrets.sh, add-user.sh)
- [x] Docker Compose overlay configured
- [x] Traefik middlewares updated
- [x] Prometheus scraping configured
- [x] Documentation complete
- [ ] **Deployed to production** ← Your next step!
- [ ] **SSO working for all services**
- [ ] **MFA enforced and tested**
- [ ] **Access control verified**
- [ ] **Running stable for 48 hours**

---

## 💬 Common Questions

**Q: Do I need to keep n8n basic auth if I have Authelia?**
A: Optional. You can disable it (N8N_BASIC_AUTH_ACTIVE=false) to rely only on Authelia. Keeping both is more secure (defense in depth).

**Q: Can I use LDAP or Active Directory instead of file-based users?**
A: Yes! Authelia supports LDAP. Update `authentication_backend` section in configuration.yml. More complex but scales better for large teams.

**Q: What if I lose my MFA device?**
A: Use backup codes saved during MFA setup. If lost, admin can reset via SQLite: `DELETE FROM totp_configurations WHERE username='user';`

**Q: Can I integrate with Google/GitHub login?**
A: Not directly with file backend. Would require Authelia as OIDC provider + separate identity provider. Complex for homelab.

**Q: How many users can this handle?**
A: File backend: ~100 users comfortably. Beyond that, consider LDAP or database backend (PostgreSQL).

**Q: Is this secure enough for remote access?**
A: Yes! With MFA enabled, this is enterprise-grade security. Use with VPN or Cloudflare Tunnel for additional protection.

---

**Phase 2 Implementation: COMPLETE** ✅

**Ready to deploy?** → See `PHASE-2-DEPLOYMENT-GUIDE.md`

**Questions or issues?** → Check Authelia logs: `docker logs orion-authelia -f`

**Ready for Phase 3?** → Let me know and I'll create the unified dashboard portal!

---

**Built with:** ❤️ for the ORION ecosystem
**Date:** November 18, 2025
**Phase:** 2/7 (SSO & Authentication)
