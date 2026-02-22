# Orion

A personal homelab AI assistant built intentionally. It knows the infrastructure, answers
questions about it, takes actions within it, monitors health, learns over time, and guards
the home network.

**This is the real start.** Everything in this repo before the first real commit is from the
experimental phase — reference material and raw parts, not settled architecture.
Nothing here is sacred.

---

## The Vision (what we're building)

```
You → HAL (thin coordinator, LLM brain)
        ├── pgvector  (knows the lab — 2,244 doc chunks already indexed)
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

Security/network guard is a first-class subsystem from day one, not bolted on later.

---

## Lab Host: the-lab (192.168.5.10)

**Hardware:**
- CPU: Intel Core Ultra 7 265K (20 cores)
- RAM: 62GB DDR5
- GPU: RTX 3090 Ti (24GB VRAM — usually idle)
- Storage: Samsung 990 PRO 2TB (boot/root), 2x WD SN850X 2TB (/docker, /data/projects)
- Tailscale: 100.82.66.91

**What's actually running (verified Feb 21, 2026):**

| Service | Port | Notes |
|---|---|---|
| prometheus | 9091 | Scraping node-exporter, blackbox (9090 = Cockpit) |
| grafana | 3000 | Dashboards, healthy |
| node-exporter | 9100 | Host metrics |
| blackbox-exporter | 9115 | Endpoint probing |
| pgvector-kb | 5432 | PostgreSQL + pgvector; DB: knowledge_base, user: kb_user |

**Ollama:** Running bare metal (`/usr/local/bin/ollama serve`), port 11434, firewalled from LAN.
HAL auto-tunnels via SSH. Models present:
- `qwen2.5-coder-14b-32k:latest` (default — 14B, 32k ctx)
- `qwen2.5-coder:32b` (big model, available if needed)
- `nomic-embed-text:latest` (768-dim embeddings — matches pgvector index)

**pgvector knowledge base:**
- 2,244 document chunks, 768-dim HNSW embeddings
- Categories: ai-agents (1,440), rag (799), misc (5)
- Connect: `psql -h 192.168.5.10 -U kb_user -d knowledge_base`

**NOT running (old docs were wrong):** vLLM, Qdrant, AnythingLLM, n8n, Traefik, Authelia

---

## This Repo

| Path | What it is |
|---|---|
| `apps/core/` | Old FastAPI chat UI — reference only |
| `apps/rag/` | Old RAG + harvester — reference only |
| `infra/` | Old infra configs — reference only |
| `ops/` | Keys and tokens — gitignored, on disk only |

Old code gets wiped on first real commit. Start fresh.

---

## Architecture Docs (in ~/Downloads)

- `orion_lean_sre_core_plan.md` — HAL + Judge + Workers, tiered governance ← best plan
- `orion_homelab.md` — full homelab end-state (OPNsense, VLANs, Proxmox)
- `forclaudecode.md` — Agent Zero + Ollama setup guide for this hardware
- `ARCHITECTURE-DECISIONS.md` — 6 ADRs from experimental phase

---

## Dev Machine: Laptop (192.168.5.25)

- OS: Ubuntu desktop
- Git identity: jean-paul carrerou <jeanpaul@protostarsolutions.com>
- SSH to server: `ssh jp@192.168.5.10`
- This repo lives at: `/home/jp/orion`

---

## Where We Left Off

1. Wiped old experimental code from this repo
2. CLAUDE.md rewritten with accurate state
3. **Next: start Ollama on the server, write minimal HAL coordinator, wire to pgvector**

The smallest useful Orion:
- HAL talks to Ollama (qwen2.5-coder:14b, 32K context)
- HAL queries pgvector for homelab knowledge
- HAL can read Prometheus metrics
- HAL SSHes to server for Tier 1+ actions (with approval)
- One Python entry point, no microservices yet
