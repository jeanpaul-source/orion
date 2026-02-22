# ORION Core - Quick Start Guide

**Get started with the ORION Hybrid UI in 5 minutes!**

---

## 🚀 First Time Setup

### Step 1: Access ORION

Open your web browser and navigate to:

```
http://192.168.5.10:5000
```

**Works on:**
- 💻 Laptop browser
- 📱 Phone browser
- 📱 Tablet browser

---

## 🎯 Understanding the Interface

When you first load ORION, you'll see:

```
┌──────────────────────────────────────────────────────────┐
│  🌌 ORION              [🎤] [🔄] [⚙️] [⬅️]              │
├─────────────────────────────────┬────────────────────────┤
│  💡 Quick Start                 │  📊 System Health      │
│                                 │  🟢 All systems up     │
│  [📊 System status]             │                        │
│  [⚡ GPU usage]                  │  📈 Live Metrics       │
│  [📝 Recent logs]                │  GPU: 78%             │
│  [🧠 RAG stats]                  │  Disk: 45%            │
│                                 │  Memory: 44%           │
│  Or try: /status, /help        │                        │
│                                 │  🔔 Alerts             │
│                                 │  All nominal           │
├─────────────────────────────────┴────────────────────────┤
│  💬 Ask ORION anything...              [Send ►]         │
└──────────────────────────────────────────────────────────┘
```

**Two main areas:**
1. **Left (Chat Panel)** - Your conversation with ORION
2. **Right (Live Sidebar)** - Real-time system monitoring

---

## 💬 Your First Queries

### Try the Quick Start Hints

Click any of the 4 hint buttons to try:
- **📊 System status** - Get complete system overview
- **⚡ GPU usage** - Check GPU utilization
- **📝 Recent logs** - View recent activity
- **🧠 RAG stats** - Knowledge base statistics

### Or Type Naturally

Just type what you want in plain English:

**Examples:**
```
What's my disk usage?
Show me GPU temperature
Check if all services are running
Tell me about Kubernetes best practices
```

ORION understands natural language - no commands to memorize!

---

## 🎨 Using the Sidebar

### Sidebar Features

The right sidebar shows:
- **🟢 System Health** - 4 key services at a glance
- **📈 Live Metrics** - GPU, disk, memory usage bars
- **🔔 Alerts** - Important notifications
- **📜 Recent Activity** - What happened recently
- **🎯 Quick Actions** - Context-aware shortcuts

### Collapsing the Sidebar

Click the **⬅️** button in the header to cycle through:
1. **Expanded** (default) - Full sidebar visible
2. **Mini** - Icon-only view
3. **Hidden** - Full-screen chat

**Keyboard shortcut:** `Cmd+B` (or `Ctrl+B` on Windows)

---

## ⌨️ Keyboard Shortcuts

Master these for faster workflow:

| Shortcut | Action |
|----------|--------|
| `Cmd+K` / `Ctrl+K` | Focus input (type from anywhere) |
| `Cmd+L` / `Ctrl+L` | Clear chat history |
| `Cmd+B` / `Ctrl+B` | Toggle sidebar |
| `Enter` | Send message |
| `Escape` | Clear input |

---

## 💡 Tips & Tricks

### 1. Quick Start Hints

When the chat is empty, click any hint button for instant queries.

### 2. Slash Commands

Type special commands for shortcuts:
- `/status` - Full system status
- `/help` - Show help
- `/gpu` - GPU details
- `/logs` - Recent logs
- `/rag stats` - Knowledge base stats

### 3. Suggestions

After ORION responds, you'll see suggested follow-up questions below the input.

### 4. Conversation History

Your conversation is saved automatically. Refresh the page and it persists!

### 5. Markdown Support

ORION responses support:
- **Bold** text
- *Italic* text
- `code blocks`
- Tables
- Links

### 6. Auto-Scroll

Messages auto-scroll to bottom. ORION keeps the latest message visible.

---

## 📱 Mobile Usage

### On Mobile Devices

The UI adapts automatically:
- Sidebar moves to bottom (swipe up to expand)
- Chat takes full width
- Touch-friendly buttons

### Tips for Mobile:
- Tap sidebar header to expand/collapse
- Rotate to landscape for split view
- Use quick start hints for faster input

---

## 🔄 Real-Time Updates

### Live Sidebar

The sidebar updates every **30 seconds** automatically:
- Service health checks
- GPU/disk/memory metrics
- Recent activity log

### Manual Refresh

Click the **🔄** button in the header to refresh instantly.

---

## 🆘 Troubleshooting

### Chat Not Working?

**Check connection status:**
- Look for "Connected" at bottom of page
- If "Reconnecting...", wait a moment
- If persistent, refresh the page

### Sidebar Not Updating?

**Check refresh button:**
- Click 🔄 in header to force update
- Check browser console for errors (F12)

### Can't See Sidebar?

**Check sidebar state:**
- Click ⬅️ button to cycle visibility
- Try `Cmd+B` keyboard shortcut
- Check if you're on mobile (sidebar at bottom)

### Messages Not Sending?

**Verify:**
- Input has text (send button should be blue)
- WebSocket connected (check bottom status)
- No "waiting for response" indicator

---

## 🎓 Next Steps

### Learn More

- **[Full ORION Core README](../README.md)** - Complete documentation
- **[Hybrid UI Design Doc](HYBRID-UI-DESIGN.md)** - Technical specification
- **[Week 2 Features](../README.md#roadmap)** - What's coming next

### Advanced Features (Coming Soon)

- 🎤 Voice input/output
- 📊 Inline charts in responses
- 🔔 Proactive alerts
- 📱 Mobile app

### Get Help

If you have questions:
1. Ask ORION: "How do I...?"
2. Check the README
3. Review the Hybrid UI Design Doc

---

## 🌟 Pro Tips

1. **Keep Sidebar Open** - Glance at metrics while chatting
2. **Use Keyboard Shortcuts** - Faster than clicking
3. **Try Natural Language** - Don't overthink queries
4. **Watch Context Panel** - It adapts to what you discuss!
5. **Export Conversations** - (Feature coming in Week 3)

---

**Enjoy using ORION!** 🌌

Your homelab's AI assistant is ready to help.
