# Orion

A personal homelab AI assistant built intentionally. It knows the infrastructure, answers
questions about it, takes actions within it, monitors health, learns over time, and guards
the home network.

---

## How I (Claude) Work With the Operator

**The reason this section exists:** I drift on long projects. Each individual fix can seem
logical in isolation, but over many sessions and context resets I lose the thread of what
we're actually building and start optimising for "make the immediate problem go away" instead
of "build something genuinely reliable." The operator cannot see this drift from the outside —
each thing I do looks plausible, the code runs, the symptom disappears. The only way to
surface drift is to force me to explain my reasoning in full before every action, because when
I'm drifting the explanation will sound wrong or thin. That is the catch mechanism.

**Rules — no exceptions:**

1. **Explain before acting.** Before writing or changing any code I must state:
   - What I think the problem actually is (root cause, not symptom)
   - What I propose to do and why this approach is correct long-term
   - Whether I *know* this is right or whether I am *guessing*
   Then wait for the operator to agree before proceeding.

2. **One change at a time.** Make one change, verify it works, then move to the next.
   Multiple simultaneous changes make it impossible to know what worked or broke.

3. **No bandaids.** If I find myself adding rules, caps, flags, or prompt instructions to
   work around a misbehaving component, I must stop and ask: is the component itself wrong?
   Patching symptoms is how drift accumulates silently.

4. **Say "I'm guessing" out loud.** If I don't fully understand why something is broken,
   I say so explicitly before proposing a fix. Confident-sounding guesses are the most
   dangerous thing I do.

---

## The Vision (what we're building)

```
You → HAL (thin coordinator, LLM brain)
        ├── IntentClassifier  (routes query before LLM sees it)
        │     ├── health  → run_health()  (metrics, no tool loop)
        │     ├── fact    → run_fact()    (KB search, no tool loop)
        │     └── agentic → run_agent()  (full tool loop)
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
- `qwen2.5-coder:32b` — **default**, 32B params
- `qwen2.5-coder-14b-32k:latest` — available but not used
- `nomic-embed-text:latest` — 768-dim embeddings, used by intent classifier + pgvector

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
| `hal/main.py` | REPL entry point; intent routing; all slash commands |
| `hal/intent.py` | Embedding-based intent classifier (health / fact / agentic); threshold 0.65 |
| `hal/agent.py` | `run_health()`, `run_fact()`, `run_agent()` — the three handlers |
| `hal/judge.py` | Policy gate: tier 0-3, sensitive path blocklist, safe command allowlist, LLM risk eval, audit log |
| `hal/workers.py` | `read_file`, `write_file`, `list_dir` — all gated through Judge |
| `hal/executor.py` | SSH runner; detects localhost and runs directly (no self-SSH) |
| `hal/memory.py` | SQLite session store (`~/.orion/memory.db`); `search_sessions()` full-text search |
| `hal/facts.py` | `/remember` — embeds facts to pgvector as `category='memory'` |
| `hal/watchdog.py` | Standalone monitoring watchdog (run via systemd timer) |
| `hal/prometheus.py` | Prometheus query client; `health()` returns cpu/mem/disk/swap/load |
| `hal/llm.py` | `OllamaClient`: `chat_with_tools()`, `chat()` |
| `hal/knowledge.py` | pgvector KB search |
| `hal/config.py` | Config dataclass + `.env` loader (includes `NTFY_URL`) |
| `harvest/` | Lab infrastructure harvester — re-indexes lab state into pgvector |
| `tests/` | pytest suite for intent classifier (21 tests); requires Ollama running |
| `pytest.ini` | `pythonpath = .` so pytest can find the `hal` package |
| `requirements.txt` | Production Python deps |
| `requirements-dev.txt` | Dev-only deps (pytest) |
| `.env.example` | Config template |
| `ops/` | Systemd units (`watchdog.service`, `watchdog.timer`) — gitignored |

---

## Dev Workflow

```
Laptop (edit code)
  → run tests on server: OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v
  → git push origin main
  → github.com/jeanpaul-source/orion
       ↓
  Server: orion-update  (alias: cd ~/orion && git pull)
  Server: hal           (alias: cd ~/orion && .venv/bin/python -m hal)
  Server: python -m harvest   (re-harvest lab state into pgvector)
```

**Rule:** Laptop pushes only. Server pulls only. Server never has push credentials.

**Rule:** Run `pytest tests/` before every push. Tests require Ollama (uses real embeddings).
If tests are skipped (Ollama unreachable from laptop), SSH to the server and run them there first.

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

**Done (as of Feb 22, 2026):**

- Minimal HAL: Ollama + pgvector + Prometheus + SSH executor + REPL
- Persistent memory: SQLite session store (`/remember`, `/search_memory`, `/sessions`)
- Judge: tier 0-3, sensitive path blocklist, safe command allowlist, LLM risk eval at approval prompts
- Reason Tokens: tools declare `reason` field → logged in audit trail + shown at approval
- Proactive monitoring watchdog: queries Prometheus, ntfy alerts, 30min cooldown per metric; installed as user systemd timer on the-lab
- Harvest: lab infrastructure state re-indexed into pgvector
- Intent-based routing: embedding classifier routes health/fact/agentic before the LLM sees the query; health and fact queries never enter the tool loop
- Test suite: 21 tests for intent classifier, all passing; pytest.ini configured
- Dead code removed: JSON-in-content fallback parser (was for 14b model), tool-use rules from system prompt
- Per-turn output size cap: tool results capped at 8000 chars in run_agent
- write_file tool added to agent TOOLS list

**Watchdog deployment (server):**

- Deployed as user systemd (not system) — SELinux blocks system services from running home-dir code
- Unit files: `~/.config/systemd/user/watchdog.{service,timer}` (use `%h` for home dir, no `User=` line)
- `loginctl enable-linger jp` — user systemd instance survives without login session
- Manage with: `systemctl --user [status|start|stop] watchdog.{service,timer}`
- ops/ files updated to match user-service format (use `%h`, no `User=jp`)
- ntfy not yet configured — alerts log to `~/.orion/watchdog.log` only

**Backlog:**

- **Run harvest on server**: `python -m harvest` — clears the current `harvest_lag` watchdog alert (timestamp file not yet written on server)
- **Judge no-tools constraint**: `_llm_reason()` in `hal/judge.py` should tell the LLM "do not call tools or fetch external data" — prevents the risk evaluator from trying to use tools
- **Security module**: network guard — planned, needs design conversation before any code
