# Orion

A personal homelab AI assistant built intentionally. It knows the infrastructure, answers
questions about it, takes actions within it, monitors health, learns over time, and guards
the home network.

---

## The Vision (what we're building)

```
You → HAL (thin coordinator, LLM brain)
        ├── pgvector  (knows the lab — 2,244 doc chunks indexed)
        ├── Judge     (policy gate — "is this safe to do?", approval tiers)
        └── Workers   (do things)
              ├── SSH executor   (run commands on the server)
              ├── Prometheus     (health queries)
              └── Security       (network guard — planned)
```

**Tiered action approval:**
- Tier 0: read-only (free, no approval)
- Tier 1: restart a service (ask, then do)
- Tier 2: config change (explain plan, wait for approval, apply, verify)
- Tier 3: destructive (explicit confirmation required)

---

## Lab Host: the-lab (192.168.5.10)

**OS:** Fedora Linux 43 (Server Edition)

**Hardware:**
- CPU: Intel Core Ultra 7 265K (20 cores)
- RAM: 62GB DDR5
- GPU: RTX 3090 Ti (24GB VRAM — usually idle)
- Storage: Samsung 990 PRO 2TB (boot/root), 2x WD SN850X 2TB (/docker, /data/projects)
- Tailscale: 100.82.66.91

**What's actually running (verified Feb 21, 2026):**

| Service | Port | Notes |
|---|---|---|
| ollama | 11434 | Bare metal (`/usr/local/bin/ollama serve`), firewalled from LAN |
| prometheus | 9091 | Docker; 9090 = Cockpit (don't confuse them) |
| grafana | 3000 | Docker |
| node-exporter | 9100 | Docker |
| blackbox-exporter | 9115 | Docker |
| pgvector-kb | 5432 | Docker; DB: knowledge_base, user: kb_user |
| cockpit | 9090 | Server management UI (HTTPS redirect) |

**Ollama models present:**
- `qwen2.5-coder-14b-32k:latest` — default, 14B params, 32k context
- `qwen2.5-coder:32b` — big model, available if needed
- `nomic-embed-text:latest` — 768-dim embeddings, matches pgvector index

**pgvector knowledge base:**
- 2,244 document chunks, 768-dim HNSW embeddings (cosine)
- Categories: ai-agents-and-multi-agent-systems (1,440), rag-and-knowledge-retrieval (799), misc (5)
- Table: `documents` — columns: content, embedding, category, file_name, file_path, metadata

**NOT running:** vLLM, Qdrant, AnythingLLM, n8n, Traefik, Authelia

---

## This Repo

**Remote:** https://github.com/jeanpaul-source/orion (private)

| Path | What it is |
|---|---|
| `hal/` | HAL coordinator — the real thing |
| `hal/main.py` | REPL entry point |
| `hal/llm.py` | Ollama client (embed + streaming chat) |
| `hal/knowledge.py` | pgvector semantic search |
| `hal/prometheus.py` | Prometheus metrics queries |
| `hal/executor.py` | SSH executor, tiered approval |
| `hal/tunnel.py` | SSH tunnel helper (used from laptop only) |
| `hal/config.py` | Load settings from .env |
| `requirements.txt` | Python deps |
| `.env.example` | Config template |
| `ops/` | Keys and tokens — gitignored, on disk only |

---

## Dev Workflow

```
Laptop (edit code)
  → git push origin main
  → github.com/jeanpaul-source/orion
       ↓
  Server: orion-update  (alias for: cd ~/orion && git pull)
  Server: hal           (alias for: cd ~/orion && .venv/bin/python -m hal)
```

**Rule:** Laptop pushes only. Server pulls only. Server never has push credentials.

**On the server, after pulling:**
- HAL runs from `~/orion` with `.venv/bin/python -m hal`
- `.env` on the server uses `localhost` for all services (no tunnel needed)
- `.env` on the laptop uses `192.168.5.10` + auto SSH tunnel for Ollama

**Server deploy key:** `~/.ssh/orion_deploy` (read-only, registered on GitHub)

---

## Dev Machine: Laptop (192.168.5.25)

- OS: Ubuntu desktop
- Git identity: jean-paul carrerou <jeanpaul@protostarsolutions.com>
- SSH to server: `ssh jp@192.168.5.10`
- Repo: `/home/jp/orion`
- GitHub CLI: authenticated as `jeanpaul-source`

---

## Where We Left Off

**Done (Feb 21, 2026):**
- Wiped experimental code (apps/, infra/)
- Built minimal HAL: Ollama + pgvector + Prometheus + SSH executor + REPL
- HAL lives on the server, runs via SSH (`hal` alias)
- GitHub private repo set up, deploy key on server
- Discovered: Ollama is bare metal not Docker, Prometheus on 9091 not 9090

**Backlog (in order):**
1. **KB harvester** — harvest actual lab state (docker configs, running services) into pgvector. Current KB is all academic papers, not infrastructure knowledge.
2. **Persistent memory** — SQLite session store + fact memory written back to pgvector
3. **Proactive monitoring** — background watchdog on server, alerts via ntfy when thresholds crossed
4. **Judge + Workers** — policy gate, audit log, multi-step action planning
