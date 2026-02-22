# ORION Core - Unified AI Homelab Assistant

**Version:** 1.1.0
**Created:** November 17, 2025
**Updated:** November 18, 2025 (Hybrid UI)
**Status:** 🚀 Production Ready

<!-- markdownlint-disable MD013 -->

---

## 🌌 What is ORION Core?

**ORION** (Orchestrated Research & Intelligence Orchestration Network) is the unified AI entity that coordinates your entire homelab through natural language.

**Think JARVIS for your homelab** - One AI you talk to, that orchestrates everything behind the scenes.

### Key Features

- **💬 Natural Language Only** - No commands to memorize, just talk naturally
- **🧠 Intelligent Routing** - Automatically routes queries to knowledge, action, or monitoring subsystems
- **📚 RAG Knowledge Base** - Live rebuild awareness
  (Qdrant reset Nov 17)
- **🛠️ Tool Execution** - Docker, SSH, Git, system operations via natural language
- **📊 Proactive Monitoring** - Real-time health checks and alerts
- **🎓 Self-Learning** - Can teach itself new topics on demand

---

## 🏗️ Architecture

### Hybrid Interface Design

```
┌─────────────────────────────────────────────────────────────────┐
│  🌌 ORION Core - Hybrid Interface                              │
│  http://192.168.5.10:5000                                       │
├────────────────────────────────┬────────────────────────────────┤
│                                │  📊 LIVE STATUS SIDEBAR        │
│  💬 CHAT PANEL (65%)           │  (35%, collapsible)            │
│  ───────────────────────────   │  ───────────────────────────   │
│                                │  🟢 System Health              │
│  Quick Start Hints             │  • vLLM: 78% GPU               │
│  (when empty)                  │  • Qdrant: rebuild pending     │
│                                │  • GPU: 68°C                   │
│  ┌──────────────────────────┐ │  • Disk: 45% used              │
│  │ 👤 User messages         │ │                                │
│  │ 🌌 ORION responses       │ │  📈 Live Metrics               │
│  │   (markdown, tables,     │ │  • GPU usage (sparkline)       │
│  │    charts, code blocks)  │ │  • Disk usage (bar)            │
│  └──────────────────────────┘ │  • Memory usage (bar)          │
│                                │                                │
│  📝 Input Bar:                 │  🔔 Alerts                     │
│  [Ask ORION anything...] [📤] │  • All systems nominal         │
│                                │                                │
│  💡 Suggestions (contextual)   │  📜 Recent Activity            │
│                                │  • 2m ago - User query         │
│                                │  • 5m ago - Health check       │
│                                │                                │
│                                │  🎯 Context Panel (adaptive)   │
│                                │  Changes based on              │
│                                │  conversation topic!           │
│                                │  • Quick actions               │
│                                │  • Related metrics             │
└────────────────────────────────┴────────────────────────────────┘
```

### Backend Architecture

```
┌─────────────────────────────────────────┐
│         ORION Core (Lab Host)           │
│  ┌───────────────────────────────────┐  │
│  │  Hybrid UI (FastAPI + Static)     │  │
│  │  • Chat Panel (WebSocket)         │  │
│  │  • Sidebar (REST API)             │  │
│  └────────────┬──────────────────────┘  │
│               │                          │
│  ┌────────────┼──────────────────────┐  │
│  │  Intelligence Router              │  │
│  │  • Intent Classification (vLLM)   │  │
│  │  • Context Management             │  │
│  │  • Context Detection (keywords)   │  │
│  └────────────┬──────────────────────┘  │
│               │                          │
│  ┌────────────┼──────────────────────┐  │
│  │  Subsystems                        │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐      │  │
│  │  │Know- │ │Action│ │Watch │      │  │
│  │  │ledge │ │      │ │(NEW!)│      │  │
│  │  └──────┘ └──────┘ └──────┘      │  │
│  └────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**All processing happens on lab host GPU:**

- vLLM (Qwen2.5-14B) - LLM inference
- Qdrant - Vector search
- AnythingLLM - RAG pipeline

**Access from anywhere:**

- Laptop browser: `http://192.168.5.10:5000`
- Phone browser: `http://192.168.5.10:5000`
- Tablet browser: `http://192.168.5.10:5000`

**Responsive design:** Automatically adapts to screen size!

---

## 🚀 Quick Start

**👉 See [DEPLOYMENT.md](DEPLOYMENT.md) for complete deployment instructions!**

### Prerequisites

Running on lab host (`192.168.5.10`):

- ✅ Docker & Docker Compose
- ✅ vLLM (GPU inference)
- ✅ Qdrant (vector database)
- ✅ AnythingLLM (RAG service)

### Quick Deploy

```bash
# On lab host
ssh lab
cd /root/orion/applications/orion-core

# Configure environment
cp .env.example .env
nano .env  # Set ORION_ANYTHINGLLM_API_KEY

# Build and run
docker compose up -d

# Verify
docker compose logs -f orion-core
# Wait for: "ORION Core started successfully!"
```

### Access

Open browser on laptop or phone:

```
http://192.168.5.10:5000
```

**📚 Documentation:**

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete deployment guide with troubleshooting
- **[QUICK-START.md](docs/QUICK-START.md)** - User guide for the hybrid UI
- **[HYBRID-UI-DESIGN.md](docs/HYBRID-UI-DESIGN.md)** - Technical UI specification

---

## 💬 Usage Examples

### Knowledge Queries

```
User: What are Kubernetes StatefulSet best practices?

ORION: [Checks knowledge stats, prompts for rebuild steps if empty]
```

### Task Execution

```
User: Check disk usage on nvme2

ORION: [Executes: df -h /mnt/nvme2 && du -sh /mnt/nvme2/*]
       [Returns formatted results]
```

### System Monitoring

```
User: What's my system status?

ORION: 🟢 ORION System Status
       Overall: HEALTHY

       Services:
       🟢 vLLM (LLM Inference): healthy
       🟢 Qdrant (Vector DB): healthy
       🟢 AnythingLLM (RAG): healthy

       Resources:
       🔷 CPU: 23.4%
       🔷 Memory: 28.1GB / 64.0GB (43.9%)
       🔷 Disk: 842.3GB / 1.8TB (45.6%)
```

### Self-Learning

```
User: Teach yourself about PostgreSQL replication

ORION: Starting self-learning on: PostgreSQL replication

       📚 Phase 1: Harvesting academic papers...
         - Found 15 potential papers

       📖 Phase 2: Collecting technical documentation...
         - Found 8 relevant documents

       ⚙️ Phase 3: Processing and ingesting...
         - This will happen in the background

       ✅ Self-learning initiated! Ask me about this topic in a few minutes.
```

---

## 📂 Project Structure

```
orion-core/
├── Dockerfile                     # Container definition
├── docker-compose.yml             # Service configuration
├── requirements.txt               # Python dependencies
├── .env.example                   # Configuration template
├── README.md                      # This file
│
├── docs/
│   └── HYBRID-UI-DESIGN.md        # Complete UI specification (643 lines)
│
├── src/
│   ├── main.py                    # FastAPI app + WebSocket
│   ├── config.py                  # Pydantic configuration
│   ├── conversation.py            # Dialogue management
│   ├── router.py                  # Intelligence routing
│   │
│   ├── api/
│   │   ├── chat.py                # WebSocket chat handler (planned)
│   │   ├── status.py              # System status API (planned)
│   │   └── metrics.py             # Metrics collector (planned)
│   │
│   └── subsystems/
│       ├── knowledge.py           # RAG integration
│       ├── action.py              # Tool execution
│       ├── learning.py            # Self-teaching
│       └── watch.py               # Monitoring
│
├── web/
│   ├── index.html                 # Old simple chat UI
│   ├── index-hybrid.html          # NEW! Hybrid interface (2,433 lines)
│   │
│   └── static/
│       ├── css/
│       │   ├── main.css           # Layout, variables, responsive
│       │   ├── chat.css           # Chat panel styles
│       │   └── sidebar.css        # Sidebar styles
│       │
│       ├── js/
│       │   ├── app.js             # Main application coordinator
│       │   ├── websocket.js       # WebSocket client with reconnect
│       │   ├── chat.js            # Chat component
│       │   ├── sidebar.js         # Sidebar component
│       │   └── utils.js           # Helper functions
│       │
│       └── lib/
│           └── marked.min.js      # Markdown parser (CDN)
│
└── tests/
    └── (test files)
```

---

## 🔧 Configuration

### Environment Variables

See `.env.example` for all options. Key settings:

```bash
# API Keys
ORION_ANYTHINGLLM_API_KEY=your-key-here  # Required

# Service URLs (Docker network)
ORION_VLLM_URL=http://vllm:8000
ORION_QDRANT_URL=http://qdrant:6333
ORION_ANYTHINGLLM_URL=http://anythingllm:3001
ORION_OLLAMA_URL=http://host.docker.internal:11434

# Tracing
ORION_ENABLE_TRACING=true
ORION_TRACING_ENDPOINT=http://localhost:4318/v1/traces

# Features
ORION_ENABLE_KNOWLEDGE=true
ORION_ENABLE_ACTION=true
ORION_ENABLE_LEARNING=true
ORION_ENABLE_WATCH=true
```

---

## 🧪 Development

### Local Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run locally (connects to lab services)
cd src/
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

### Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-report=html
```

---

## 📊 API Endpoints

### Web UI

- `GET /` - Main chat interface

### API

- `GET /health` - Health check
- `GET /api/status` - Full system status
- `GET /api/knowledge/stats` - Knowledge base statistics
- `WS /chat` - WebSocket chat endpoint

### Development

- `GET /api/dev/routes` - List all routes

---

## 🔌 Integration with Existing Services

ORION Core integrates seamlessly with the existing ORION ecosystem:

```yaml
# Add to main docker-compose.yml
services:
  orion-core:
    build: ./applications/orion-core
    ports:
      - "0.0.0.0:5000:5000"
    environment:
      - ORION_VLLM_URL=http://vllm:8000
      - ORION_QDRANT_URL=http://qdrant:6333
      - ORION_ANYTHINGLLM_URL=http://anythingllm:3001
    depends_on:
      - vllm
      - qdrant
      - anythingllm
    networks:
      - orion-network
```

---

## 🐛 Troubleshooting

### "Connection refused" from browser

Check service is running:

```bash
docker compose ps
docker compose logs orion-core
```

### "Failed to connect to vLLM/Qdrant"

Verify services are accessible:

```bash
docker compose exec orion-core curl http://vllm:8000/health
docker compose exec orion-core curl http://qdrant:6333/
```

### Web UI not loading

Check web files are mounted:

```bash
docker compose exec orion-core ls -la /app/web/
```

---

## 🛣️ Development Roadmap

### Week 1: Foundation ✅ COMPLETE (Nov 18, 2025)

- [x] Unified hybrid HTML layout (chat + sidebar)
- [x] Responsive CSS (mobile, tablet, desktop)
- [x] WebSocket chat with auto-reconnect
- [x] Basic sidebar with mock data
- [x] Markdown rendering
- [x] Conversation persistence (localStorage)
- [x] Keyboard shortcuts (Cmd+K, Cmd+L, Cmd+B)
- [x] Quick start hints
- [x] Loading indicators

**Deliverable:** 2,433 lines of production-ready frontend code

### Week 2: Smart Sidebar 🚧 IN PROGRESS

- [ ] Real `/api/status` endpoint (GPU, disk, memory)
- [ ] Context detection (keyword-based)
- [ ] Chart.js sparklines for GPU history
- [ ] Background status monitoring
- [ ] Sidebar auto-updates (30s interval)
- [ ] Alert system

### Week 3: Rich Content 📅 PLANNED

- [ ] Inline charts in chat messages
- [ ] Tables and code blocks formatting
- [ ] Action buttons in responses
- [ ] Conversation export (markdown/JSON)
- [ ] Quick actions panel
- [ ] History management

### Week 4: Polish & Features 📅 PLANNED

- [ ] Voice input (Web Speech API)
- [ ] Voice output (TTS, optional)
- [ ] Slash commands (/status, /help, /gpu)
- [ ] Mobile optimizations
- [ ] Performance tuning
- [ ] Accessibility improvements

### Future Enhancements

- Voice-only mode (full JARVIS experience)
- Mobile app (React Native / Flutter)
- Multi-user support with Authelia SSO
- Advanced task planning
- Integration with n8n workflows
- Plugin system for custom tools

---

## 📄 License

Part of the Laptop-MAIN ORION Project
Created: November 17, 2025

---

## 🙏 Acknowledgments

Built on top of:

- **vLLM** - Fast LLM inference
- **Qdrant** - Vector database
- **AnythingLLM** - RAG pipeline
- **FastAPI** - Modern Python web framework

---

**ORION Core** - Your AI homelab assistant that actually understands you.

Talk naturally, get intelligent results. 🌌
