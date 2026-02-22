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

| Service | Host Port | Container Port | Type | Notes |
|---|---|---|---|---|
| ollama | 11434 | — | systemd | Bare metal, all interfaces, firewalled from LAN |
| pgvector-kb | 5432 | 5432 | Docker | PostgreSQL+pgvector; DB: knowledge_base, user: kb_user |
| pgvector-kb-api | 5001 | — | systemd | Python search API wrapping pgvector; at /opt/homelab-infrastructure/pgvector-kb/api.py |
| prometheus | 9091 | 9090 | Docker | compose at /opt/homelab-infrastructure/monitoring-stack/ |
| grafana | 3001 | 3000 | Docker | same compose stack |
| node-exporter | — | 9100 | Docker | internal to monitoring network only |
| blackbox-exporter | — | 9115 | Docker | internal to monitoring network only |
| agent-zero | 50080 | 80 | Docker | AI agent UI; uses Ollama via host.docker.internal:11434 |
| cockpit | 9090 | — | systemd | Server management UI — NOT Prometheus |

**Secrets:** Managed by SOPS + `homelab-secrets.service` (tmpfs at `/run/homelab-secrets/`).
Secrets files: `monitoring-stack.env`, `agent-zero.env`, `pgvector-kb.env`.

**Config source of truth:** `/opt/homelab-infrastructure/` (git-tracked)
- `monitoring-stack/` — prometheus, grafana, blackbox, node-exporter compose + configs
- `pgvector-kb/` — pgvector compose + api.py
- `agent-zero/` — agent-zero compose + production.env
- `secrets/` — SOPS-encrypted secrets

**Runtime data:** `/docker/` (not source of truth — compose runtime mounts)

**Ollama models present:**
- `qwen2.5-coder-14b-32k:latest` — default, 14B params, 32k context
- `qwen2.5-coder:32b` — big model, available if needed
- `nomic-embed-text:latest` — 768-dim embeddings, matches pgvector index

**pgvector knowledge base:**
- 2,244 document chunks, 768-dim HNSW embeddings (cosine)
- Categories: ai-agents-and-multi-agent-systems (1,440), rag-and-knowledge-retrieval (799), misc (5)
- After harvest: also `lab-infrastructure` and `lab-state` categories
- Table: `documents` — columns: content, embedding, category, file_name, file_path, metadata

**NOT running:** vLLM, Qdrant, AnythingLLM, n8n, Traefik, Authelia

**Watch:** Swap usage was 7.3G/8G despite 49G RAM free (Feb 21 2026) — worth investigating

---

## This Repo

**Remote:** https://github.com/jeanpaul-source/orion (private)

| Path | What it is |
|---|---|
| `hal/` | HAL coordinator — REPL, LLM, knowledge, prometheus, SSH executor |
| `harvest/` | Lab infrastructure harvester — collects real state into pgvector |
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
  Server: orion-update  (alias: cd ~/orion && git pull)
  Server: hal           (alias: cd ~/orion && .venv/bin/python -m hal)
  Server: python -m harvest   (re-harvest lab state into pgvector)
```

**Rule:** Laptop pushes only. Server pulls only. Server never has push credentials.

**Server .env** uses `localhost` for all services (no tunnel needed).
**Laptop .env** uses `192.168.5.10` + auto SSH tunnel for Ollama.

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
- GitHub private repo + deploy key on server
- Built lab infrastructure harvester (`harvest/`)

**Backlog (in order):**
1. **Persistent memory** — SQLite session store + fact memory written back to pgvector
2. **Proactive monitoring** — background watchdog on server, alerts via ntfy
3. **Judge + Workers** — policy gate, audit log, multi-step action planning
