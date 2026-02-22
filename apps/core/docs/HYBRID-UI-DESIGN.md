# ORION Core - Hybrid UI Design Document

**Version:** 1.0.0
**Created:** November 18, 2025
**Status:** 🚧 In Development
**Target:** Production Ready (4 weeks)

---

## 🎯 Vision

**ORION Hybrid Interface** - A conversational AI chat interface with live monitoring sidebar that adapts to context.

### Design Principles

1. **Conversation-First** - Primary interaction is natural language chat
2. **Context-Aware** - Sidebar adapts based on what you're discussing
3. **Glanceable Status** - At-a-glance system health without interrupting flow
4. **Single-User Optimized** - No auth complexity, personal tool
5. **Responsive & Fast** - Works on desktop and mobile, instant updates

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🌌 ORION                              [🎤 Voice] [🔄] [⚙️] [⬅️ Collapse]│
├────────────────────────────────────┬────────────────────────────────────┤
│                                    │  📊 LIVE STATUS                    │
│  💬 CONVERSATION (65%)             │  ────────────────────────────────  │
│  ──────────────────────────────    │  🟢 All Systems Healthy            │
│                                    │                                    │
│  Quick Start Hints (when empty)    │  vLLM    ⚡ 78%  🌡️ 68°C         │
│  Message History (scrollable)      │  Qdrant  ⚡ 1.2M vectors           │
│  Rich Content (tables, charts)     │  GPU     ⚡ 18.7/24 GB             │
│  Action Buttons                    │  Disk    ⚡ 842/1800 GB            │
│  Suggestions                       │                                    │
│                                    │  📈 Live Metrics (sparklines)      │
│  Input Bar with Voice              │  🔔 Alerts                         │
│                                    │  📜 Recent Activity                │
│                                    │  🎯 Context Panel (adaptive)       │
│                                    │                                    │
├────────────────────────────────────┴────────────────────────────────────┤
│  💬 Ask ORION anything... (or try /status, /help)        [Send ►] [🎤] │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Breakdown

| Component | Width | Purpose | Update Frequency |
|-----------|-------|---------|------------------|
| **Chat Panel** | 65% (flexible) | Primary interaction | Real-time (WebSocket) |
| **Sidebar** | 35% (collapsible) | Live status + context | 30s auto-refresh |
| **Header** | Full width | Branding + actions | Static |
| **Input Bar** | Full width | Message input | Static |

### Sidebar States

1. **Expanded (default)** - 35% width, full content visible
2. **Mini** - 60px width, icon-only view
3. **Hidden** - 0px width, full-screen chat

---

## 🎨 User Experience Flow

### First Visit

1. User opens `http://192.168.5.10:5000`
2. Quick start hints appear with common queries
3. Sidebar shows current system status
4. User clicks hint or types query
5. ORION responds with rich content
6. Sidebar adapts to conversation context

### Daily Usage

1. **Glance Mode** - Open page → see sidebar status → close if all green
2. **Quick Query** - Type `/status` → get instant system overview
3. **Deep Dive** - Ask "What's using disk space?" → conversation with charts
4. **Monitoring** - Leave tab open → sidebar updates every 30s

### Troubleshooting

1. User asks: "Why is GPU at 90%?"
2. ORION responds with analysis
3. Sidebar switches to **GPU context** automatically
4. Context panel shows: "View logs", "Temperature history", "Open Grafana"
5. User clicks "View logs" → inline log display in chat
6. Problem identified and fixed

---

## 🧩 Component Specifications

### 1. Chat Panel (Left/Center - 65%)

**Sections:**

#### A. Quick Start (visible when no messages)
```
💡 Quick Start
─────────────────────────────
[📊 System status] [⚡ GPU usage]
[📝 Recent logs]   [🧠 RAG stats]

Or try: /status, /help, /gpu
```

#### B. Message History
- Scrollable container
- User messages (right-aligned, blue)
- ORION messages (left-aligned, gray)
- Timestamps on hover
- Rich content support:
  - **Markdown** - Bold, italic, links
  - **Code blocks** - Syntax highlighted
  - **Tables** - Formatted data
  - **Charts** - Inline Chart.js graphs
  - **Action buttons** - Quick actions in messages

#### C. Input Area
- Text input with placeholder
- Send button (enabled when text entered)
- Voice button (Web Speech API)
- Slash command support (`/status`, `/help`, etc.)
- Suggested actions (contextual, below input)

**Features:**
- Conversation persistence (localStorage)
- Auto-scroll to bottom on new message
- Loading indicator while waiting
- Error handling (connection lost, etc.)

---

### 2. Live Status Sidebar (Right - 35%)

**Sections (top to bottom):**

#### A. System Health (always visible)
```
🟢 System Health
─────────────────────
Service      Status
vLLM         🟢 Up (78% GPU)
Qdrant       🟢 Up (1.2M vectors)
GPU          🟢 Ok (68°C)
Disk         🟢 Ok (45% used)
```

#### B. Live Metrics
```
📈 Live Metrics
─────────────────────
GPU Usage:  78%
[Mini sparkline chart - last 60 data points]
[Progress bar]

Disk (nvme2): 842 GB / 1.8 TB
[Progress bar]

Memory: 28.1 GB / 64 GB
[Progress bar]
```

#### C. Alerts
```
🔔 Alerts
─────────────────────
🟡 High GPU temp (72°C) - 5m ago
🟢 All clear now
```

Or when no alerts:
```
🔔 Alerts
─────────────────────
All systems nominal
```

#### D. Recent Activity
```
📜 Recent Activity
─────────────────────
• 2m ago - User query: GPU status
• 5m ago - System health check
• 12m ago - Harvester completed
```

#### E. Context Panel (adaptive) ⭐
**Default (no context):**
```
🎯 Quick Actions
─────────────────────
→ Full system status
→ Check recent logs
→ Knowledge base stats
→ Run harvester
```

**GPU Context:**
```
⚡ GPU Performance
─────────────────────
Current topic: GPU monitoring

Quick actions:
→ View full GPU history
→ Check vLLM logs
→ Temperature trends
→ [Open Grafana GPU dashboard →]
```

**Qdrant Context:**
```
🗄️ Vector Database
─────────────────────
Current topic: Qdrant

Collections:
• orion_homelab: 1.2M vectors
• technical-docs: 1.4M vectors

Quick actions:
→ Collection stats
→ Recent queries
→ Memory usage
```

---

## 🤖 Smart Context Detection

### Algorithm

```javascript
// Analyze user message for keywords
const message = "What's my GPU usage?"
const keywords = ['gpu', 'usage']

// Match to context definitions
contexts = {
  gpu: ['gpu', 'vllm', 'temperature', 'vram', 'cuda'],
  qdrant: ['qdrant', 'vectors', 'collection'],
  disk: ['disk', 'nvme', 'storage', 'space'],
  // ...
}

// Score each context
scores = { gpu: 2, qdrant: 0, disk: 0 }

// Highest score wins → GPU context
sidebar.updateContext('gpu')
```

### Context Definitions

| Context | Keywords | Icon | Quick Actions |
|---------|----------|------|---------------|
| **GPU** | gpu, vllm, temperature, vram, nvidia, cuda | ⚡ | GPU history, vLLM logs, temp trends, Grafana |
| **Qdrant** | qdrant, vectors, collection, embeddings, search | 🗄️ | Collection stats, queries, memory, UI |
| **Disk** | disk, nvme, storage, space, filesystem | 💾 | Usage breakdown, large files, mounts |
| **Knowledge** | knowledge, rag, papers, documents, harvester | 🧠 | RAG stats, harvests, run harvester, AnythingLLM |
| **Docker** | docker, container, compose, service, restart | 🐳 | Service status, logs, restart |

---

## 🎨 Visual Design

### Color Scheme (Dark Theme)

```css
--bg-primary: #0f172a      /* Main background */
--bg-secondary: #1e293b    /* Sidebar, header */
--bg-tertiary: #334155     /* Hover states */
--text-primary: #f1f5f9    /* Main text */
--text-secondary: #cbd5e1  /* Secondary text */
--text-muted: #94a3b8      /* Timestamps, hints */

--accent-primary: #3b82f6  /* Blue - primary actions */
--accent-success: #10b981  /* Green - healthy states */
--accent-warning: #f59e0b  /* Orange - warnings */
--accent-error: #ef4444    /* Red - errors */
```

### Typography

```css
--font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif
--font-mono: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', monospace

--text-xs: 0.75rem    /* Timestamps */
--text-sm: 0.875rem   /* Metadata */
--text-base: 1rem     /* Body text */
--text-lg: 1.125rem   /* Headings */
--text-xl: 1.5rem     /* Logo */
```

### Spacing

```css
--spacing-xs: 0.25rem   /* 4px */
--spacing-sm: 0.5rem    /* 8px */
--spacing-md: 1rem      /* 16px */
--spacing-lg: 1.5rem    /* 24px */
--spacing-xl: 2rem      /* 32px */
```

---

## 🔧 Technical Stack

### Frontend

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Framework** | Vanilla JavaScript | No build step, fast, simple |
| **WebSocket** | Native WebSocket API | Real-time chat, no polling |
| **Charts** | Chart.js v4 | Lightweight, sparklines for sidebar |
| **Markdown** | Marked.js | Parse ORION responses |
| **Syntax Highlighting** | Highlight.js | Code blocks in messages |
| **Icons** | Emoji + SVG | No icon library needed |
| **State** | Plain JS + localStorage | Single user, no Redux needed |

### Backend

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Framework** | FastAPI | Already using, async, fast |
| **WebSocket** | FastAPI WebSocket | Native support, easy |
| **Background Tasks** | FastAPI BackgroundTasks | Status monitoring |
| **Validation** | Pydantic | Type safety |
| **Logging** | Python logging | Structured logs |

### External Dependencies

```json
{
  "frontend": {
    "chart.js": "^4.4.0",
    "marked": "^9.0.0",
    "highlight.js": "^11.9.0"
  },
  "backend": {
    "fastapi": "^0.104.0",
    "uvicorn": "^0.24.0",
    "pydantic": "^2.5.0",
    "psutil": "^5.9.0",
    "httpx": "^0.25.0"
  }
}
```

---

## 📋 Implementation Roadmap

### Week 1: Foundation (15 hours)

**Goal:** Basic hybrid layout with working WebSocket chat

**Deliverables:**
- ✅ Unified HTML layout (chat + sidebar)
- ✅ CSS styling (responsive, dark theme)
- ✅ WebSocket connection + chat
- ✅ Basic sidebar with static data
- ✅ Markdown rendering in messages
- ✅ FastAPI backend with /chat WebSocket

**Files Created:**
```
web/
├── index.html              # Main UI
├── static/
│   ├── css/
│   │   ├── main.css        # Layout, vars, reset
│   │   ├── chat.css        # Chat panel styles
│   │   └── sidebar.css     # Sidebar styles
│   └── js/
│       ├── app.js          # Main entry point
│       ├── websocket.js    # WebSocket handler
│       ├── chat.js         # Chat component
│       └── utils.js        # Helpers

src/
├── main.py                 # Add WebSocket endpoint
└── api/
    └── chat.py             # WebSocket handler logic
```

---

### Week 2: Smart Sidebar (20 hours)

**Goal:** Live metrics, context detection, auto-updates

**Deliverables:**
- ✅ Real metrics API (/api/status)
- ✅ Context detector (keyword-based)
- ✅ Sidebar adapts to conversation
- ✅ Background status monitor
- ✅ Auto-refresh every 30s
- ✅ Sidebar collapse states

**Files Created:**
```
static/js/
├── sidebar.js              # Sidebar component
└── context-detector.js     # Context detection

src/api/
├── status.py              # Status API
└── metrics.py             # Metrics collector

src/services/
└── status_monitor.py      # Background monitoring
```

---

### Week 3: Rich Content (20 hours)

**Goal:** Inline charts, tables, action buttons, history

**Deliverables:**
- ✅ Chart.js integration
- ✅ Rich message types (tables, code, charts)
- ✅ Action buttons in messages
- ✅ Conversation persistence (localStorage)
- ✅ Export conversation as markdown
- ✅ Quick start hints

**Files Updated:**
```
static/js/
└── chat.js                # Add rich rendering

web/static/lib/
├── chart.min.js           # Chart.js CDN
├── marked.min.js          # Markdown parser
└── highlight.min.js       # Syntax highlighting
```

---

### Week 4: Polish & Features (20 hours)

**Goal:** Voice I/O, slash commands, mobile, performance

**Deliverables:**
- ✅ Voice input (Web Speech API)
- ✅ Voice output (TTS, optional)
- ✅ Slash commands (/status, /help, etc.)
- ✅ Mobile responsive layout
- ✅ Performance optimizations
- ✅ Keyboard shortcuts (Cmd+K, etc.)

**Files Updated:**
```
static/js/
├── app.js                 # Add keyboard shortcuts
├── chat.js                # Add voice I/O
└── utils.js               # Add helpers

static/css/
├── main.css               # Add mobile queries
└── chat.css               # Add voice button styles
```

---

## 🎯 Success Criteria

### Functional Requirements

- [x] Chat interface with WebSocket communication
- [x] Real-time system status in sidebar
- [x] Context-aware sidebar (adapts to conversation)
- [x] Rich message formatting (markdown, code, tables)
- [x] Conversation persistence
- [x] Mobile responsive
- [x] Voice input/output

### Performance Requirements

- [ ] Initial page load < 1s
- [ ] WebSocket message latency < 100ms
- [ ] Sidebar updates without blocking chat
- [ ] Smooth animations (60fps)
- [ ] Works on mobile (iOS/Android)

### Usability Requirements

- [ ] Intuitive UI (no tutorial needed)
- [ ] Keyboard accessible
- [ ] Clear status indicators
- [ ] Helpful error messages
- [ ] Graceful degradation (if services down)

---

## 🔒 Security Considerations

### Current (Single-User)

- No authentication required
- Runs on private network (192.168.5.x)
- WebSocket connection over HTTP (not WSS)
- LocalStorage for conversation (client-side only)

### Future (Multi-User)

- Add Authelia SSO integration
- Upgrade to WSS (WebSocket Secure)
- Per-user conversation history (database)
- API key authentication for status endpoints
- Rate limiting on WebSocket

---

## 📱 Responsive Design

### Desktop (> 1024px)

```
┌────────────────────────────────┬──────────────┐
│                                │              │
│  Chat (65%)                    │  Sidebar     │
│                                │  (35%)       │
│                                │              │
└────────────────────────────────┴──────────────┘
```

### Tablet (768px - 1024px)

```
┌────────────────────────────────┬──────────┐
│                                │          │
│  Chat (70%)                    │ Sidebar  │
│                                │ (30%)    │
│                                │          │
└────────────────────────────────┴──────────┘
```

### Mobile (< 768px)

```
┌────────────────────────────────┐
│                                │
│  Chat (100%)                   │
│                                │
│                                │
├────────────────────────────────┤
│  Sidebar (drawer from bottom)  │
│  Swipe up to expand            │
└────────────────────────────────┘
```

---

## 🧪 Testing Strategy

### Manual Testing

- [ ] WebSocket connection/reconnection
- [ ] Message sending/receiving
- [ ] Markdown rendering
- [ ] Context detection accuracy
- [ ] Sidebar metric updates
- [ ] Mobile layout
- [ ] Voice input/output
- [ ] Keyboard shortcuts

### Browser Compatibility

- [ ] Chrome/Edge (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Mobile Safari (iOS 15+)
- [ ] Chrome Mobile (Android 11+)

---

## 📚 Future Enhancements

### Phase 2 (Future)

- [ ] **Multi-user support** - Authelia SSO, per-user history
- [ ] **Advanced visualizations** - D3.js for complex charts
- [ ] **File uploads** - Analyze log files, configs
- [ ] **Screen sharing** - Remote troubleshooting
- [ ] **Notifications** - Browser push for alerts
- [ ] **Mobile app** - React Native or Flutter
- [ ] **API playground** - Test ORION endpoints
- [ ] **Plugin system** - Custom tools/integrations

### Phase 3 (Experimental)

- [ ] **AI vision** - Upload screenshots, analyze
- [ ] **Voice-only mode** - Full JARVIS experience
- [ ] **Predictive alerts** - ML-based anomaly detection
- [ ] **Auto-remediation** - ORION fixes issues autonomously
- [ ] **Natural language queries to Grafana** - "Show me GPU usage last week"
- [ ] **Integration with external services** - Slack, Discord, Telegram

---

## 📖 References

### Design Inspiration

- ChatGPT interface (conversational simplicity)
- Vercel Dashboard (clean metrics visualization)
- Linear.app (keyboard shortcuts, speed)
- GitHub Copilot Chat (IDE integration, context)

### Technical Documentation

- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Chart.js Documentation](https://www.chartjs.org/docs/)
- [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [CSS Custom Properties](https://developer.mozilla.org/en-US/docs/Web/CSS/Using_CSS_custom_properties)

---

## 👥 Contributors

**Design & Implementation:** ORION Project
**Created:** November 18, 2025
**Status:** 🚧 Week 1 in progress

---

## 📄 License

Part of ORION Core v1.0.0
Private homelab infrastructure - Not licensed for public use

---

**Next:** Begin Week 1 implementation → `web/index.html`
