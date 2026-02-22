# Phase 2: SSO with Authelia - Quick Start

## 🚀 Deploy in 8 Commands

**Prerequisites:** Phase 1 deployed and stable
**Estimated Time:** 30-45 minutes

### **On Laptop:**

```bash
# 1. Navigate to authelia directory
cd /home/user/Laptop-MAIN/applications/orion-rag/infrastructure/authelia/

# 2. Generate secrets
./generate-secrets.sh
# SAVE THE OUTPUT - you need these secrets!

# 3. Create your admin user
./add-user.sh admin YourSecurePassword123 admin@orion.lab "Admin User" admins,users

# 4. Sync to host
cd ..
rsync -avz --progress \
  authelia/ \
  docker-compose.authelia.yml \
  traefik/dynamic/middlewares.yml \
  prometheus/prometheus.yml \
  lab:/mnt/nvme2/orion-project/setup/
```

### **On Host (via SSH):**

```bash
# 5. SSH to host
ssh lab

# 6. Add secrets to .env
cd /mnt/nvme2/orion-project/setup/
nano .env
# Add the three AUTHELIA_* secrets from step 2

# 7. Deploy Authelia
docker compose \
  -f docker-compose.traefik.yml \
  -f docker-compose.authelia.yml \
  up -d

# 8. Verify
docker ps | grep -E "(authelia|redis)"
# Both should show "healthy"
```

### **Test SSO:**

1. Open: **https://orion.lab/auth/**
2. Login: `admin` / `YourSecurePassword123`
3. Set up MFA: Scan QR code with Google Authenticator
4. Access service: **https://orion.lab/metrics**
5. Result: **Automatically logged in** (SSO works!)

---

## 🔑 First Login Flow

```
1. Visit https://orion.lab/metrics (Grafana)
   ↓
2. Redirected to: https://orion.lab/auth/
   ↓
3. Enter username + password
   ↓
4. First time: Set up MFA (scan QR code)
   ↓
5. Enter 6-digit code from authenticator app
   ↓
6. Redirected back to Grafana
   ↓
7. You're logged in!
```

**Subsequent logins:**
- Already have MFA set up
- Just enter: username + password + MFA code
- Instant access!

---

## 📱 MFA Apps

Choose one:
- **Google Authenticator** (mobile)
- **Authy** (mobile + desktop)
- **1Password** (if you use it)
- **Microsoft Authenticator** (mobile)

All work with Authelia TOTP!

---

## 🆘 Quick Troubleshooting

**Problem:** 502 Bad Gateway on /auth
```bash
ssh lab "docker logs orion-authelia --tail 50"
ssh lab "docker restart orion-authelia"
```

**Problem:** Invalid credentials
```bash
# Re-generate password hash and re-add user
cd authelia && ./add-user.sh admin NewPass email "Name" admins
rsync -avz users_database.yml lab:/mnt/nvme2/orion-project/setup/authelia/
ssh lab "docker restart orion-authelia"
```

**Problem:** Redirect loop
```bash
# Check session cookie in browser (Dev Tools → Application → Cookies)
# Should see: authelia_session cookie for orion.lab
# If not, check Redis: ssh lab "docker exec orion-redis redis-cli ping"
```

---

## 📚 Full Documentation

- **Step-by-step guide:** `PHASE-2-DEPLOYMENT-GUIDE.md`
- **Architecture & details:** `PHASE-2-COMPLETE.md`
- **Authelia config:** `authelia/configuration.yml`

---

## 🎯 Success Check

✅ Authelia accessible: `https://orion.lab/auth/`
✅ Can login with username + password + MFA
✅ Grafana uses SSO (no separate login)
✅ n8n uses SSO (no separate login)
✅ Traefik dashboard requires admin + MFA
✅ Session persists across browser tabs

---

## ⏭️ Next: Phase 3 (Dashboard)

Once Phase 2 is stable, move to Phase 3:
- Unified dashboard portal
- Real-time status cards
- Quick actions (restart, logs)
- Embedded services (tabs)

**Ready?** Let me know!
