# Phase 4: Telegram Bot Integration - Deployment Guide

**Status:** Implementation Complete
**Estimated Time:** 20 minutes
**Prerequisites:** Phase 3 deployed and tested

---

## 📋 Overview

Phase 4 adds **mobile access** to ORION through a Telegram bot, enabling:

- 📱 Mobile queries and commands on the go
- 🔔 Push notifications for system alerts
- 🔒 User ID whitelist security
- 💬 Natural language interface via Telegram
- ⚡ Real-time system status
- 🎯 Quick actions with confirmation dialogs

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Telegram Cloud                       │
│                    (Bot API, Push Notifications)             │
└─────────────────────────────────────────────────────────────┘
                              ▲ HTTPS
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      ORION Core Container                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Telegram Bot Module                    │    │
│  │  - User Authorization (whitelist)                   │    │
│  │  - Command Handlers (/start, /status, /query, etc) │    │
│  │  - Push Notification Queue                          │    │
│  │  - Inline Keyboards & Callbacks                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                          ▲                                   │
│                          │                                   │
│  ┌──────────────┬────────┴─────────┬─────────────────┐      │
│  │  Knowledge   │     Action       │    Learning     │      │
│  │  Subsystem   │    Subsystem     │   Subsystem     │      │
│  └──────────────┴──────────────────┴─────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Step 1: Create Telegram Bot

### 1.1 Start Conversation with BotFather

Open Telegram and search for **@BotFather**:

```
/start
/newbot
```

### 1.2 Configure Your Bot

Follow the prompts:

```
BotFather: Alright, a new bot. How are we going to call it?
You: ORION Homelab Assistant

BotFather: Good. Now let's choose a username for your bot.
You: orion_homelab_bot
```

**Result:** You'll receive:
- Bot token: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
- Bot username: `@orion_homelab_bot`

**⚠️ CRITICAL:** Save the bot token securely! You'll need it in Step 2.

### 1.3 Get Your Telegram User ID

Send a message to your new bot, then check your user ID:

**Option A: Using a bot**
1. Message `@userinfobot` on Telegram
2. It will reply with your user ID (e.g., `123456789`)

**Option B: Using the web**
1. Send `/start` to your bot
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Find `"from":{"id":123456789}` in the JSON

**Example:**
```json
{
  "message": {
    "from": {
      "id": 123456789,  ← This is your user ID
      "first_name": "John"
    }
  }
}
```

---

## ⚙️ Step 2: Configure Environment Variables

### 2.1 SSH to Lab Host

```bash
ssh lab
cd /mnt/nvme2/orion-project/setup
```

### 2.2 Update .env File

Add Telegram configuration to your `.env` file:

```bash
nano .env
```

Add these lines (replace with your values):

```bash
# ============================================================================
# TELEGRAM BOT CONFIGURATION (Phase 4)
# ============================================================================

# Enable Telegram bot
ORION_TELEGRAM_ENABLED=true

# Bot token from @BotFather
ORION_TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Allowed user IDs (comma-separated, no spaces)
# Get your ID from @userinfobot
ORION_TELEGRAM_ALLOWED_USERS=[123456789,987654321]

# Enable push notifications
ORION_TELEGRAM_NOTIFICATION_ENABLED=true
```

**Security Note:** Only users in the `ALLOWED_USERS` list can interact with the bot!

### 2.3 Verify Configuration Format

**Important:** The user IDs must be in Python list format:

✅ **CORRECT:**
```bash
ORION_TELEGRAM_ALLOWED_USERS=[123456789,987654321]
```

❌ **WRONG:**
```bash
ORION_TELEGRAM_ALLOWED_USERS=123456789,987654321   # Missing brackets
ORION_TELEGRAM_ALLOWED_USERS=[123456789, 987654321] # Spaces not allowed
```

---

## 📦 Step 3: Update ORION Core

### 3.1 Rebuild ORION Core Container

The Telegram bot integration requires `python-telegram-bot` package:

```bash
cd /mnt/nvme2/orion-project/setup
docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml down orion-core
docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml build --no-cache orion-core
docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml up -d
```

### 3.2 Verify Startup

Check logs for successful initialization:

```bash
docker compose logs -f orion-core | grep -i telegram
```

**Expected output:**
```
orion-core | INFO: Initializing Telegram bot...
orion-core | INFO: ✅ Telegram bot started successfully!
```

**If you see errors:**

**Error: "python-telegram-bot not installed"**
```bash
# Rebuild with --no-cache
docker compose build --no-cache orion-core
```

**Error: "ORION_TELEGRAM_BOT_TOKEN not set"**
```bash
# Check .env file
cat .env | grep TELEGRAM
```

**Error: "no allowed users configured"**
```bash
# Verify format in .env
echo $ORION_TELEGRAM_ALLOWED_USERS
```

---

## ✅ Step 4: Test the Bot

### 4.1 Start Conversation

Open Telegram and search for your bot username (e.g., `@orion_homelab_bot`).

Send:
```
/start
```

**Expected response:**
```
👋 Welcome to ORION!

I'm your AI homelab assistant, now available on Telegram.

What I can do:
🔍 /status - Check system status
💬 /query - Ask technical questions
⚡ /action - Execute commands
🔔 /alerts - View recent alerts
❓ /help - Show detailed help
```

### 4.2 Test Commands

**Check System Status:**
```
/status
```

**Expected response:**
```
📊 ORION System Status

🌟 ORION Core
Status: ✅ Healthy
Uptime: 2h 34m
Requests: 1,247

🚀 vLLM (GPU)
Status: ✅ Healthy
Model: Qwen2.5-14B-AWQ
GPU Temp: 54°C

📚 Qdrant
Status: ✅ Healthy
Collections: 3
Vectors: 1.2M

🔒 Authelia SSO
Status: ✅ Healthy
Active Sessions: 2
```

**Query Knowledge Base:**
```
/query What are Kubernetes best practices?
```

**Expected response:**
```
💬 Processing your query...

[Detailed answer with sources from ORION RAG knowledge base]

📚 Sources:
  [1] Kubernetes Official Documentation (0.942)
  [2] Production K8s Guide (0.891)
  [3] CNCF Best Practices (0.876)
```

**Execute Action (with confirmation):**
```
/action check disk usage
```

**Expected response with inline keyboard:**
```
⚡ Action Request

Command: check disk usage

Are you sure you want to execute this action?

[✅ Confirm]  [❌ Cancel]
```

### 4.3 Test Authorization

**Test with unauthorized user:**

1. Create a second Telegram account (or ask a friend)
2. Have them message your bot
3. They should receive:

```
🚫 Unauthorized

Sorry, you are not authorized to use this bot.

If you believe this is an error, please contact your administrator.

Your user ID: 999888777
```

**This confirms the security whitelist is working!**

---

## 🔔 Step 5: Configure Notifications (Optional)

### 5.1 Enable Proactive Alerts

The bot can send push notifications for system events.

**Edit ORION Core configuration:**

```bash
nano /mnt/nvme2/orion-project/setup/orion-core/.env
```

Ensure notifications are enabled:
```bash
ORION_TELEGRAM_NOTIFICATION_ENABLED=true
```

### 5.2 Test Push Notification

The bot will automatically send notifications when:

- ⚠️ Service health check fails
- 🔥 GPU temperature exceeds threshold (>80°C)
- 💾 Disk usage exceeds 90%
- 🚨 Critical errors in logs

**Manual test (from ORION dashboard):**

You can trigger a test notification from the ORION web UI or via API call.

---

## 🎯 Available Commands Reference

### User Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Initialize bot and show welcome | `/start` |
| `/help` | Show detailed command help | `/help` |
| `/status` | Get system status with metrics | `/status` |
| `/query <question>` | Ask ORION a question | `/query How to configure Traefik?` |
| `/action <command>` | Execute action (with confirmation) | `/action restart traefik` |
| `/alerts` | View recent system alerts | `/alerts` |

### Status Command Output

The `/status` command shows:
- ✅ Service health (healthy/degraded/down)
- ⏱️ Uptime and request counts
- 🌡️ GPU temperature
- 📊 Resource usage (memory, disk, GPU)
- 🔒 Authentication status

### Query Command Features

When you use `/query`:
1. Query is routed to ORION's Knowledge subsystem
2. RAG system searches 1.2M vector knowledge base
3. Response includes cited sources
4. Conversation context is maintained

### Action Command Security

Action commands have **two-level confirmation**:

1. **Inline keyboard confirmation** (user must click "Confirm")
2. **Destructive action warning** (extra prompt for dangerous operations)

---

## 🔒 Security Features

### 1. User ID Whitelist

Only specified Telegram user IDs can use the bot:

```bash
ORION_TELEGRAM_ALLOWED_USERS=[123456789,987654321]
```

**Unauthorized users receive:**
- Rejection message with their user ID
- No access to any commands
- Logged security event

### 2. Command Confirmation

Destructive actions require confirmation:

```
User: /action delete old logs

Bot: ⚠️ WARNING: This action may be destructive!
     Are you sure?

     [⚠️ Yes, I'm Sure]  [❌ Cancel]
```

### 3. Rate Limiting

Built-in rate limiting prevents abuse:
- Max 10 requests per minute per user
- Automatic cooldown period
- Warning messages for rate-limited users

### 4. Audit Logging

All bot interactions are logged:
- User ID and username
- Command and parameters
- Response and execution status
- Timestamp

**View logs:**
```bash
docker compose logs orion-core | grep "telegram"
```

---

## 🐛 Troubleshooting

### Bot Not Responding

**Problem:** Bot doesn't respond to messages

**Solutions:**

1. **Check bot is running:**
   ```bash
   docker compose ps orion-core
   docker compose logs orion-core | grep -i telegram
   ```

2. **Verify token is correct:**
   ```bash
   cat .env | grep TELEGRAM_BOT_TOKEN
   ```

3. **Check Telegram API connectivity:**
   ```bash
   curl -s https://api.telegram.org/bot<YOUR_TOKEN>/getMe
   ```

   Should return:
   ```json
   {"ok":true,"result":{"id":123456789,"is_bot":true,...}}
   ```

### Unauthorized Error

**Problem:** You get "Unauthorized" message

**Solutions:**

1. **Verify your user ID is in whitelist:**
   ```bash
   echo $ORION_TELEGRAM_ALLOWED_USERS
   ```

2. **Check format (must be array):**
   ```bash
   # Correct: [123456789,987654321]
   # Wrong:   123456789,987654321
   ```

3. **Restart ORION Core after .env changes:**
   ```bash
   docker compose restart orion-core
   ```

### Notification Not Working

**Problem:** Not receiving push notifications

**Solutions:**

1. **Check notification is enabled:**
   ```bash
   cat .env | grep NOTIFICATION_ENABLED
   ```

2. **Verify bot can send messages:**
   - Send `/start` to bot
   - If you receive response, notifications work

3. **Check alert configuration:**
   ```bash
   docker compose logs orion-core | grep "notification"
   ```

### Commands Timeout

**Problem:** Commands take too long or timeout

**Solutions:**

1. **Check ORION Core services:**
   ```bash
   docker compose ps
   ```

2. **Verify vLLM is responsive:**
   ```bash
   curl -s http://localhost:8000/health
   ```

3. **Check query queue:**
   ```bash
   curl -s http://localhost:5000/api/queue/stats
   ```

### Package Installation Failed

**Problem:** `python-telegram-bot` not installed

**Solutions:**

1. **Rebuild container:**
   ```bash
   docker compose build --no-cache orion-core
   docker compose up -d orion-core
   ```

2. **Verify requirements.txt includes package:**
   ```bash
   docker compose exec orion-core cat requirements.txt | grep telegram
   ```

   Should show:
   ```
   python-telegram-bot>=20.0
   ```

---

## 📊 Monitoring

### Check Bot Health

```bash
# View bot logs
docker compose logs -f orion-core | grep telegram

# Check bot status in application
curl -s http://localhost:5000/health | jq '.telegram_bot'
```

### Metrics

The bot exposes Prometheus metrics:

- `telegram_messages_total` - Total messages received
- `telegram_commands_total` - Commands executed
- `telegram_errors_total` - Error count
- `telegram_notifications_sent` - Push notifications sent

**View in Grafana:**
```
https://orion.lab/metrics
```

### Audit Trail

All bot interactions are logged with:

```json
{
  "timestamp": "2025-11-18T10:30:45Z",
  "user_id": 123456789,
  "username": "john_doe",
  "command": "/query",
  "parameters": "How to configure Traefik?",
  "status": "success",
  "response_time_ms": 1234
}
```

**Query logs:**
```bash
docker compose logs orion-core | grep "telegram_command"
```

---

## 🎓 Best Practices

### 1. Secure Your Bot Token

- ✅ Store in `.env` file (gitignored)
- ✅ Never commit to git
- ✅ Rotate token periodically (via @BotFather)
- ❌ Never share in chat or screenshots

### 2. Manage User Whitelist

```bash
# Add user
ORION_TELEGRAM_ALLOWED_USERS=[123456789,987654321,555666777]

# Remove user (just exclude their ID)
ORION_TELEGRAM_ALLOWED_USERS=[123456789,987654321]

# Restart to apply
docker compose restart orion-core
```

### 3. Use Bot for Read Operations

**Recommended:**
- ✅ `/status` - Check system health
- ✅ `/query` - Ask questions
- ✅ `/alerts` - View notifications

**Use with caution:**
- ⚠️ `/action` - Requires confirmation
- ⚠️ Destructive operations - Only when necessary

### 4. Enable Notifications Wisely

Configure thresholds to avoid spam:

```bash
# In ORION config
ORION_ALERT_GPU_TEMP_THRESHOLD=85        # Alert at 85°C (not 80°C)
ORION_ALERT_DISK_USAGE_THRESHOLD=95      # Alert at 95% (not 90%)
ORION_ALERT_COOLDOWN_MINUTES=15          # Don't spam every minute
```

---

## 🚀 Next Steps

**Phase 4 Complete!** ✅

You now have:
- ✅ Telegram bot with mobile access
- ✅ Secure user authentication
- ✅ Push notifications for alerts
- ✅ Natural language queries on the go
- ✅ Remote system monitoring

**Continue to Phase 5:**

👉 **[PHASE-5-DEPLOYMENT-GUIDE.md](PHASE-5-DEPLOYMENT-GUIDE.md)** - Configure Grafana AlertManager for comprehensive alerting

**Or explore advanced features:**

- **Custom Commands:** Add domain-specific commands to the bot
- **Scheduled Reports:** Daily status summaries via Telegram
- **Interactive Dashboards:** Inline keyboards for navigation
- **Voice Messages:** Use Telegram voice-to-text for queries

---

## 📚 Additional Resources

**Telegram Bot API:**
- Official Docs: https://core.telegram.org/bots/api
- BotFather Guide: https://core.telegram.org/bots#botfather
- Security Best Practices: https://core.telegram.org/bots/features#security

**Python Telegram Bot Library:**
- Documentation: https://docs.python-telegram-bot.org/
- Examples: https://github.com/python-telegram-bot/python-telegram-bot/tree/master/examples
- Community: https://t.me/pythontelegrambotgroup

**ORION Documentation:**
- Phase 1 (Traefik): [PHASE-1-DEPLOYMENT-GUIDE.md](PHASE-1-DEPLOYMENT-GUIDE.md)
- Phase 2 (Authelia): [PHASE-2-DEPLOYMENT-GUIDE.md](PHASE-2-DEPLOYMENT-GUIDE.md)
- Phase 3 (Dashboard): [PHASE-3-DEPLOYMENT-GUIDE.md](PHASE-3-DEPLOYMENT-GUIDE.md)

---

**Questions or Issues?**

Check `docker compose logs orion-core` for detailed error messages or consult the troubleshooting section above.
