# Phase 2: Single Sign-On with Authelia - Deployment Guide

**Status:** Ready for deployment
**Duration:** 4-6 hours
**Complexity:** Medium
**Prerequisites:** Phase 1 (Traefik + SSL) deployed and stable

---

## 🎯 What This Phase Delivers

After completing Phase 2, you will have:

✅ **Single Sign-On (SSO):** Log in once, access all services
✅ **Multi-Factor Authentication (MFA):** TOTP (Google Authenticator, Authy, 1Password)
✅ **Centralized User Management:** File-based user database
✅ **Session Management:** 24-hour sessions, 7-day "remember me"
✅ **Granular Access Control:** Role-based access (admins, users, viewers)
✅ **Security Hardening:** Brute-force protection, rate limiting

---

## 📋 Prerequisites

### **Phase 1 Must Be Running:**

```bash
# Verify Phase 1 services are healthy
ssh lab "docker compose -f /mnt/nvme2/orion-project/setup/docker-compose.traefik.yml ps"

# Should show: traefik, qdrant, vllm, anythingllm, n8n, grafana, prometheus all "healthy"
```

### **Test Phase 1 Access:**

```bash
# From laptop
curl -k https://orion.lab/health
# Should return: {"status":"healthy"}
```

If Phase 1 isn't working, fix it first before proceeding.

---

## 🚀 Deployment Steps

### **Step 1: Generate Authelia Secrets**

On laptop:

```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/authelia/

# Make scripts executable
chmod +x generate-secrets.sh add-user.sh

# Generate secrets
./generate-secrets.sh
```

**Expected Output:**
```
Generating Authelia Secrets

✓ Secrets generated successfully

Add these to your .env file:

# Authelia Secrets (generated 2025-11-18)
AUTHELIA_JWT_SECRET=a1b2c3d4... (128 characters)
AUTHELIA_SESSION_SECRET=e5f6g7h8... (128 characters)
AUTHELIA_STORAGE_ENCRYPTION_KEY=i9j0k1l2... (128 characters)
```

**COPY these three lines** - you'll need them in Step 3.

⚠️ **CRITICAL:** Never change `AUTHELIA_STORAGE_ENCRYPTION_KEY` after first use!

---

### **Step 2: Create Your First User**

On laptop:

```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/authelia/

# Create admin user (replace with your details)
./add-user.sh admin YourSecurePassword123 admin@orion.lab "Admin User" admins,users
```

**Expected Output:**
```
Generating password hash (this may take a few seconds)...
Password hash generated successfully
Backed up existing users file

✓ User added successfully!

User Details:
  Username:    admin
  Email:       admin@orion.lab
  Display:     Admin User
  Groups:      admins,users
```

**Verify user was added:**
```bash
cat users_database.yml
# Should show your user entry with password hash
```

**Add more users (optional):**
```bash
# Regular user
./add-user.sh john SecurePass456 john@orion.lab "John Doe" users

# Viewer (read-only)
./add-user.sh viewer ViewerPass789 viewer@orion.lab "Dashboard Viewer" viewers
```

---

### **Step 3: Update Environment Variables**

On laptop, prepare the updated .env content:

```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/

# Create a file with new variables
cat > authelia-env.txt << 'EOF'
# Authelia Secrets (add to .env on host)
AUTHELIA_JWT_SECRET=YOUR_GENERATED_SECRET_FROM_STEP_1
AUTHELIA_SESSION_SECRET=YOUR_GENERATED_SECRET_FROM_STEP_1
AUTHELIA_STORAGE_ENCRYPTION_KEY=YOUR_GENERATED_SECRET_FROM_STEP_1
EOF

# Edit and paste your actual secrets
nano authelia-env.txt
```

On host (ssh lab):

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup/

# Backup current .env
cp .env .env.backup.$(date +%Y%m%d)

# Add Authelia secrets to .env
cat >> .env << 'ENV_EOF'

# ===== Phase 2: Authelia SSO =====
# CRITICAL: Never change AUTHELIA_STORAGE_ENCRYPTION_KEY after first use!
AUTHELIA_JWT_SECRET=paste_your_jwt_secret_here
AUTHELIA_SESSION_SECRET=paste_your_session_secret_here
AUTHELIA_STORAGE_ENCRYPTION_KEY=paste_your_storage_key_here
ENV_EOF

# Edit .env and replace placeholders with real secrets
nano .env
```

**Verify .env has all required variables:**
```bash
grep AUTHELIA .env
# Should show 3 AUTHELIA_* variables
```

---

### **Step 4: Sync Authelia Configuration to Host**

On laptop:

```bash
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/

# Sync Authelia files
rsync -avz --progress authelia/ lab:/mnt/nvme2/orion-project/setup/authelia/

# Sync updated middlewares
rsync -avz --progress traefik/dynamic/middlewares.yml lab:/mnt/nvme2/orion-project/setup/traefik/dynamic/

# Sync updated Prometheus config
rsync -avz --progress prometheus/prometheus.yml lab:/mnt/nvme2/orion-project/setup/prometheus/

# Sync docker-compose.authelia.yml
rsync -avz --progress docker-compose.authelia.yml lab:/mnt/nvme2/orion-project/setup/
```

**Verify on host:**
```bash
ssh lab "ls -la /mnt/nvme2/orion-project/setup/authelia/"
# Should show: configuration.yml, users_database.yml, add-user.sh, generate-secrets.sh

ssh lab "ls -la /mnt/nvme2/orion-project/setup/docker-compose.authelia.yml"
# Should exist
```

---

### **Step 5: Deploy Authelia**

On host:

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup/

# Deploy with both compose files
docker compose \
  -f docker-compose.traefik.yml \
  -f docker-compose.authelia.yml \
  up -d
```

**What happens:**
1. Pulls Authelia and Redis images (if not cached)
2. Creates Redis container for session storage
3. Creates Authelia container
4. Updates existing service labels (applies SSO to all services)
5. Traefik detects changes and reloads routing

**Monitor deployment:**
```bash
# Watch all services come up
docker compose \
  -f docker-compose.traefik.yml \
  -f docker-compose.authelia.yml \
  ps

# Check Authelia logs
docker logs orion-authelia -f
# Press Ctrl+C when you see: "Authelia is listening"

# Check Redis
docker logs orion-redis --tail 20
# Should see: "Ready to accept connections"
```

**Verify services are healthy:**
```bash
docker ps | grep -E "(authelia|redis)"
# Both should show status "healthy"
```

---

### **Step 6: Test SSO Login**

#### **A. Test Authelia Web UI:**

From laptop browser:
1. Open: `https://orion.lab/auth/`
2. You should see **Authelia login page**
3. Enter credentials:
   - Username: `admin`
   - Password: `YourSecurePassword123` (from Step 2)
4. Click **Sign in**

**Expected: First-time login prompts for MFA setup**

#### **B. Set Up MFA (TOTP):**

1. **Install authenticator app** (if not already):
   - Google Authenticator (mobile)
   - Authy (mobile/desktop)
   - 1Password (if you use it)

2. **Scan QR code** shown on screen

3. **Enter 6-digit code** from authenticator app

4. **Save backup codes** (download or write down)

5. Click **Done**

**Expected: You're now logged in to Authelia**

#### **C. Test Protected Service (Grafana):**

1. Open: `https://orion.lab/metrics`
2. **Should redirect to Authelia login** (if not already logged in)
3. Enter credentials + MFA code
4. **Should redirect back to Grafana** automatically

**Expected: You're logged into Grafana without entering Grafana credentials!**

#### **D. Test SSO (Single Sign-On):**

1. Open new tab: `https://orion.lab/workflows` (n8n)
2. **Should NOT ask for login** (already authenticated)
3. You're automatically logged in!

4. Open another tab: `https://orion.lab/knowledge` (AnythingLLM)
5. Again, **automatic login** via SSO

**This is SSO working!** One login, access to all services.

---

### **Step 7: Test Access Control**

#### **Admin Access (Traefik Dashboard):**

1. Open: `https://orion.lab/dashboard`
2. Login with admin account (if prompted)
3. **Should see Traefik dashboard**

Expected: Only `admins` group can access (configured in configuration.yml)

#### **Regular User Access:**

If you created a regular user (not in admins group):

1. Logout: Open `https://orion.lab/auth/logout`
2. Login with regular user account
3. Try accessing: `https://orion.lab/dashboard`

**Expected: "Access Denied" or 403 error** (not in admins group)

#### **Services Regular Users CAN Access:**

With regular user account:
- ✅ `https://orion.lab/metrics` (Grafana)
- ✅ `https://orion.lab/workflows` (n8n)
- ✅ `https://orion.lab/knowledge` (AnythingLLM)
- ✅ `https://orion.lab/` (ORION Core - public)
- ❌ `https://orion.lab/dashboard` (Traefik - admins only)
- ❌ `https://orion.lab/prometheus` (Prometheus - admins only)

This confirms **role-based access control** is working!

---

### **Step 8: Test Session Persistence**

#### **Test "Remember Me":**

1. Logout: `https://orion.lab/auth/logout`
2. Login again
3. **Check "Remember me"** checkbox
4. Login with credentials + MFA

5. Close browser completely
6. Reopen browser
7. Visit: `https://orion.lab/metrics`

**Expected: Still logged in** (session persists for 7 days with "remember me")

#### **Test Session Expiry:**

Without "remember me":
- Session expires after **4 hours of inactivity**
- Session expires after **24 hours maximum**

To test:
1. Login without "remember me"
2. Wait 4+ hours without activity
3. Try accessing protected service

**Expected: Redirected to login page**

---

### **Step 9: Configure Service-Specific Settings (Optional)**

#### **Grafana: Add OIDC (Advanced):**

Authelia can act as an OAuth2/OIDC provider for Grafana.

**Skip this for now** (works fine with forward auth). Document available if needed.

#### **n8n: Adjust Authentication:**

n8n has its own auth. With Authelia, you have **double authentication**:
1. Authelia (SSO)
2. n8n basic auth

**Options:**
- Keep both (more secure)
- Disable n8n basic auth (rely only on Authelia)

To disable n8n auth:
```yaml
# In docker-compose.traefik.yml, update n8n environment:
- N8N_BASIC_AUTH_ACTIVE=false
```

**Recommended:** Keep both for now.

---

## ✅ Verification Checklist

### **Functionality Tests:**

- [ ] Authelia login page accessible at `https://orion.lab/auth/`
- [ ] Can login with username + password + MFA
- [ ] MFA setup works (QR code scan)
- [ ] Accessing Grafana redirects to Authelia login
- [ ] After login, automatically redirected back to Grafana
- [ ] Accessing n8n does NOT ask for login again (SSO works)
- [ ] AnythingLLM also uses SSO (no re-login)
- [ ] Traefik dashboard requires admin group
- [ ] Regular users cannot access Traefik dashboard
- [ ] Logout works: `https://orion.lab/auth/logout`
- [ ] "Remember me" persists across browser restarts
- [ ] Session expires after 4 hours inactivity (if not "remember me")

### **Security Tests:**

- [ ] Cannot access protected services without login
- [ ] MFA is enforced (cannot login without TOTP code)
- [ ] Brute force protection works (5 failed attempts = 10 min ban)
- [ ] LAN-only routes still restricted (Prometheus requires LAN IP)
- [ ] Access control rules enforced (admins vs users vs viewers)

### **Performance Tests:**

- [ ] Login completes in <3 seconds
- [ ] Service redirects are fast (<1 second)
- [ ] No noticeable latency vs Phase 1

### **Monitoring:**

- [ ] Authelia metrics visible in Prometheus: `https://orion.lab/prometheus/targets`
- [ ] Redis metrics visible in Prometheus
- [ ] Authelia logs clean (no errors): `docker logs orion-authelia`

---

## 🔧 Troubleshooting

### **Problem: "502 Bad Gateway" on /auth**

**Possible Causes:**
1. Authelia not running
2. Redis not running
3. Configuration error

**Solution:**
```bash
# Check Authelia status
ssh lab "docker logs orion-authelia --tail 50"

# Check Redis
ssh lab "docker logs orion-redis --tail 20"

# Restart both
ssh lab "docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml restart authelia redis"
```

---

### **Problem: "Invalid credentials" (but password is correct)**

**Possible Causes:**
1. Password hash mismatch
2. Wrong username
3. users_database.yml not synced

**Solution:**
```bash
# Verify user exists
ssh lab "cat /mnt/nvme2/orion-project/setup/authelia/users_database.yml"

# Re-generate password hash
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/authelia/
./add-user.sh admin NewPassword email@example.com "Admin" admins,users

# Re-sync and restart
rsync -avz users_database.yml lab:/mnt/nvme2/orion-project/setup/authelia/
ssh lab "docker restart orion-authelia"
```

---

### **Problem: Redirect loop (keeps redirecting to /auth)**

**Possible Causes:**
1. Traefik middleware misconfigured
2. Authelia can't reach Redis
3. Session cookie not being set

**Solution:**
```bash
# Check Traefik logs
ssh lab "docker logs orion-traefik --tail 100 | grep authelia"

# Check Authelia can reach Redis
ssh lab "docker exec orion-authelia ping -c 2 redis"

# Check browser cookies
# Open browser dev tools → Application → Cookies → https://orion.lab
# Should see: authelia_session cookie
```

---

### **Problem: MFA QR code not showing**

**Possible Causes:**
1. TOTP disabled in configuration
2. Browser blocking image

**Solution:**
```bash
# Verify TOTP enabled
ssh lab "grep 'totp:' /mnt/nvme2/orion-project/setup/authelia/configuration.yml -A 5"
# Should show: disable: false

# Try different browser
# Or use manual entry (secret key shown below QR code)
```

---

### **Problem: "Access Denied" for all services**

**Possible Causes:**
1. Access control rules too strict
2. User not in correct group

**Solution:**
```bash
# Check user groups
ssh lab "cat /mnt/nvme2/orion-project/setup/authelia/users_database.yml | grep -A 5 'your-username'"

# Verify access control rules
ssh lab "cat /mnt/nvme2/orion-project/setup/authelia/configuration.yml | grep 'access_control' -A 50"

# Temporarily set default_policy to one_factor for testing
# Edit configuration.yml: default_policy: one_factor
# Restart: docker restart orion-authelia
```

---

### **Problem: Session not persisting (keeps asking for login)**

**Possible Causes:**
1. Redis not running
2. Session cookie not being saved
3. Browser blocking cookies

**Solution:**
```bash
# Check Redis
ssh lab "docker exec orion-redis redis-cli ping"
# Should return: PONG

# Check browser cookie settings
# Ensure cookies enabled for orion.lab

# Check Authelia session config
ssh lab "grep 'session:' /mnt/nvme2/orion-project/setup/authelia/configuration.yml -A 15"
```

---

## 🔐 Security Best Practices

### **Passwords:**

✅ **Do:**
- Use strong passwords (16+ characters)
- Use unique passwords per user
- Store securely (password manager)

❌ **Don't:**
- Use dictionary words
- Reuse passwords
- Share passwords

### **MFA:**

✅ **Do:**
- Enable MFA for all users
- Save backup codes securely
- Use hardware keys if available (YubiKey - requires WebAuthn config)

❌ **Don't:**
- Skip MFA setup
- Lose backup codes
- Share TOTP secrets

### **Secrets:**

✅ **Do:**
- Generate strong random secrets (./generate-secrets.sh)
- Keep .env file secure (chmod 600)
- Never commit secrets to git

❌ **Don't:**
- Use weak secrets
- Change AUTHELIA_STORAGE_ENCRYPTION_KEY after first use
- Share secrets via email/chat

### **Access Control:**

✅ **Do:**
- Follow principle of least privilege
- Use groups (admins, users, viewers)
- Review access regularly

❌ **Don't:**
- Give everyone admin access
- Use default_policy: bypass (unless specific service)
- Skip access control review

---

## 📊 Monitoring

### **Authelia Metrics (Prometheus):**

Available at: `https://orion.lab/prometheus/targets`

**Key Metrics:**
- `authelia_authentication_first_factor_total` - Login attempts
- `authelia_authentication_second_factor_total` - MFA attempts
- `authelia_authentication_first_factor_success_total` - Successful logins
- `authelia_authentication_first_factor_failure_total` - Failed logins
- `authelia_request_duration_seconds` - Response times

### **Redis Metrics:**

- `redis_connected_clients` - Active sessions
- `redis_memory_used_bytes` - Memory usage
- `redis_commands_processed_total` - Operations

### **Useful Queries:**

```promql
# Failed login attempts (brute force detection)
rate(authelia_authentication_first_factor_failure_total[5m])

# MFA usage
rate(authelia_authentication_second_factor_total[1h])

# Active sessions
redis_connected_clients{service="redis"}
```

**Add to Grafana dashboard in Phase 3!**

---

## 🎯 Next Steps (Phase 3)

Once Phase 2 is stable (48 hours):

### **Phase 3: Unified Dashboard Portal**

**What you'll build:**
- React or HTML/CSS/JS dashboard
- Status cards (service health, GPU usage, disk space)
- Quick actions (restart services, check logs)
- Tabbed interface (Grafana, n8n, AnythingLLM embedded)

**Timeline:** 1 week (8-12 hours work)

---

## 📚 Resources

**Authelia Documentation:**
- [Access Control](https://www.authelia.com/configuration/security/access-control/)
- [Session Management](https://www.authelia.com/configuration/session/introduction/)
- [TOTP (MFA)](https://www.authelia.com/configuration/second-factor/time-based-one-time-password/)

**Troubleshooting:**
- Authelia logs: `docker logs orion-authelia -f`
- Redis logs: `docker logs orion-redis -f`
- Traefik logs: `docker logs orion-traefik -f | grep authelia`

---

## 🏆 Success Criteria

Phase 2 is **complete** when:

- [x] Authelia configuration created
- [x] Users database configured
- [x] Secrets generated
- [x] Docker compose updated
- [x] Traefik middlewares configured
- [x] Prometheus scraping Authelia
- [ ] **Deployed to production** (your next step!)
- [ ] **SSO working for all services**
- [ ] **MFA enforced**
- [ ] **Access control rules working**
- [ ] **Running stable for 48 hours**

---

## 💬 Common Questions

**Q: Can I disable MFA for certain users?**
A: Yes. In `configuration.yml`, change policy from `two_factor` to `one_factor` for specific resources.

**Q: Can I use this remotely (outside home network)?**
A: Yes! Authelia is designed for this. Access via VPN or Cloudflare Tunnel.

**Q: What if I lose my phone (TOTP app)?**
A: Use backup codes saved during MFA setup. If lost, manually edit `users_database.yml` and remove user's TOTP secret (forces re-enrollment).

**Q: Can I integrate with external auth (Google, GitHub)?**
A: Not directly with Authelia file backend. Would require LDAP/OIDC backend (complex for homelab).

**Q: How do I add more users?**
A: Use `./add-user.sh` script, sync to host, restart Authelia.

---

**Phase 2 Deployment: Ready** ✅

**Ready to deploy?** → Follow steps 1-9 above

**Need help?** → Check troubleshooting section or Authelia logs

**Ready for Phase 3?** → Let me know and I'll create the dashboard portal!

---

**Built with:** ❤️ for the ORION ecosystem
**Date:** November 18, 2025
**Phase:** 2/7 (SSO & Authentication)
