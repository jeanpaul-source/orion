# Phase 4: Telegram Bot - Quick Start ⚡

**Time:** 10 minutes | **Difficulty:** Easy | **Prerequisites:** Phase 3 deployed

---

## 📱 Quick Deploy

### Step 1: Create Bot (3 minutes)

```bash
# On your phone/computer:
# 1. Open Telegram
# 2. Search for @BotFather
# 3. Send /newbot
# 4. Follow prompts:
#    - Name: ORION Homelab Assistant
#    - Username: orion_homelab_bot
# 5. Save the bot token!

# Get your user ID:
# Message @userinfobot and save your ID
```

### Step 2: Configure (2 minutes)

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup

# Add to .env
cat >> .env << 'EOF'

# ===== TELEGRAM BOT (Phase 4) =====
ORION_TELEGRAM_ENABLED=true
ORION_TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
ORION_TELEGRAM_ALLOWED_USERS=[YOUR_USER_ID]
ORION_TELEGRAM_NOTIFICATION_ENABLED=true
EOF

# Edit with your actual values
nano .env
```

### Step 3: Deploy (5 minutes)

```bash
# Rebuild and restart
docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml \
  down orion-core

docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml \
  build --no-cache orion-core

docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml \
  up -d

# Verify
docker compose logs -f orion-core | grep -i telegram
```

**Expected output:**
```
✅ Telegram bot started successfully!
```

### Step 4: Test (1 minute)

```bash
# On Telegram:
# 1. Search for your bot (@orion_homelab_bot)
# 2. Send: /start
# 3. Send: /status
# 4. Verify you get responses!
```

---

## 🎯 Available Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message | `/start` |
| `/status` | System status | `/status` |
| `/query` | Ask questions | `/query How to configure Traefik?` |
| `/action` | Execute commands | `/action check disk space` |
| `/alerts` | View alerts | `/alerts` |
| `/help` | Command help | `/help` |

---

## 🔒 Security Verification

### Test Authorization

Have a friend message your bot. They should see:

```
🚫 Unauthorized

Sorry, you are not authorized to use this bot.
Your user ID: 123456789
```

This confirms security is working! ✅

### Add Another User

```bash
# Update .env
ORION_TELEGRAM_ALLOWED_USERS=[123456789,987654321]

# Restart
docker compose restart orion-core
```

---

## 🐛 Quick Troubleshooting

### Bot not responding?

```bash
# Check logs
docker compose logs orion-core | grep telegram

# Verify token
cat .env | grep TELEGRAM_BOT_TOKEN

# Test API
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

### Unauthorized error for yourself?

```bash
# Verify user ID in .env
cat .env | grep ALLOWED_USERS

# Format must be: [123456789,987654321]
# No spaces!

# Restart after changes
docker compose restart orion-core
```

---

## ✅ Success Criteria

- ✅ Bot responds to `/start`
- ✅ `/status` shows system metrics
- ✅ `/query` returns RAG answers
- ✅ Unauthorized users are blocked
- ✅ No errors in logs

---

**Phase 4 Complete!** 🎉

**Next:** [Phase 5: Grafana AlertManager](PHASE-5-DEPLOYMENT-GUIDE.md)

**Full Guide:** [PHASE-4-DEPLOYMENT-GUIDE.md](PHASE-4-DEPLOYMENT-GUIDE.md)
