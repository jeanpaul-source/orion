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

```text
You → HAL (thin coordinator, LLM brain)
        ├── IntentClassifier  (routes query before LLM sees it)
        │     ├── health  → run_health()  (metrics, no tool loop)
        │     ├── fact    → run_fact()    (KB search, no tool loop)
        │     └── agentic → run_agent()  (full tool loop)
        ├── pgvector  (knows the lab — 2,293 doc chunks indexed)
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

**What's actually running (verified Feb 22, 2026):**

| Service | Host Port | Container Port | Type | Notes |
|---|---|---|---|---|
| ollama | 11434 | — | systemd | Bare metal, all interfaces, firewalled from LAN |
| pgvector-kb | 5432 | 5432 | Docker | PostgreSQL+pgvector; DB: knowledge_base, user: kb_user |
| pgvector-kb-api | 5001 | — | systemd | Python search API wrapping pgvector; at /opt/homelab-infrastructure/pgvector-kb/api.py |
| prometheus | 9091 | 9090 | Docker | compose at /opt/homelab-infrastructure/monitoring-stack/ |
| grafana | 3001 | 3000 | Docker | same compose stack |
| node-exporter | — | 9100 | Docker | internal to monitoring network only |
| blackbox-exporter | — | 9115 | Docker | internal to monitoring network only |
| cockpit | 9090 | — | systemd | Server management UI — NOT Prometheus |
| vLLM | 8000 | — | user systemd | `~/vllm-env/bin/vllm`; `VLLM_USE_FLASHINFER_SAMPLER=0` workaround for RTX 3090 Ti CUDA issue; `--enforce-eager --tool-call-parser hermes` |

**NOT running (but planned):**
- agent-zero — container is absent (not just stopped); decomissioned or never deployed on this host

**Secrets:** Managed by SOPS + `homelab-secrets.service` (tmpfs at `/run/homelab-secrets/`).
Secrets files: `monitoring-stack.env`, `agent-zero.env`, `pgvector-kb.env`.

**Config source of truth:** `/opt/homelab-infrastructure/` (git-tracked)
- `monitoring-stack/` — prometheus, grafana, blackbox, node-exporter compose + configs
- `pgvector-kb/` — pgvector compose + api.py
- `agent-zero/` — agent-zero compose + production.env
- `secrets/` — SOPS-encrypted secrets

**Runtime data:** `/docker/` (not source of truth — compose runtime mounts)

**Ollama models present (verified Feb 22, 2026):**
- `qwen2.5-coder:32b` — primary fallback; 32B params
- `qwen2.5-coder-32b-16k:latest` — 32B, 16k context variant
- `qwen2.5-coder:14b` — 14B params
- `qwen2.5-coder-14b-32k:latest` — 14B, 32k context variant
- `nomic-embed-text:latest` — 768-dim embeddings, used by intent classifier + pgvector

**Chat LLM:** HAL uses vLLM (OpenAI-compatible API at port 8000) as its primary chat backend. Ollama is used only for embeddings. Model: `Qwen/Qwen2.5-Coder-32B-Instruct-AWQ` (19GB AWQ-quantised).

**pgvector knowledge base (verified Feb 22, 2026):**
- 2,293 document chunks, 768-dim HNSW embeddings (cosine)
- Categories: ai-agents-and-multi-agent-systems (1,440), rag-and-knowledge-retrieval (799), lab-infrastructure (35), lab-state (14), ghs-genome (4), ghs-rejections (1)
- Harvest HAS been run; `harvest_last_run` timestamp file not yet written → watchdog incorrectly reports harvest_lag
- `ghs-genome` and `ghs-rejections` (5 rows) are foreign data — don't belong, low harm, should be cleaned
- Table: `documents` — columns: content, embedding, category, file_name, file_path, metadata

**NOT running:** Qdrant, AnythingLLM, n8n, Traefik, Authelia

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
| `hal/llm.py` | `OllamaClient` (embeddings), `VLLMClient` (chat via OpenAI-compatible API) |
| `hal/tracing.py` | OTel setup; `setup_tracing()` + `get_tracer()`; no-op fallback if collector absent |
| `hal/tunnel.py` | SSH tunnel for laptop-side use (auto-tunnel when vLLM/Ollama not directly reachable) |
| `hal/knowledge.py` | pgvector KB search |
| `hal/config.py` | Config dataclass + `.env` loader (includes `NTFY_URL`, `VLLM_URL`) |
| `harvest/` | Lab infrastructure harvester — re-indexes lab state into pgvector |
| `eval/queries.jsonl` | 24 test queries covering B1–B6 failure cases from SESSION_FINDINGS |
| `eval/run_eval.py` | Eval runner — drives HAL handlers, writes `eval/responses.jsonl` |
| `eval/evaluate.py` | Scores responses: no_raw_json, hal_identity, intent_accuracy, relevance, coherence |
| `tests/` | pytest suite for intent classifier (21 tests); requires Ollama running |
| `pytest.ini` | `pythonpath = .` so pytest can find the `hal` package |
| `requirements.txt` | Production Python deps (includes opentelemetry-*) |
| `requirements-dev.txt` | Dev-only deps (pytest, azure-ai-evaluation) |
| `.env.example` | Config template |
| `ops/` | Systemd units (`watchdog.service`, `watchdog.timer`) — gitignored |

---

## Dev Workflow

```text
Laptop (edit code)
  → run tests on server: OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v
  → run eval on server:  python -m eval.run_eval && python -m eval.evaluate --skip-llm-eval
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
- Switched LLM backend from Ollama chat → vLLM OpenAI-compatible API (`VLLMClient`); Ollama now embeddings-only
- OTel tracing: `hal/tracing.py`; spans on every turn, intent classify, LLM call, tool call; collector at localhost:4318
- Evaluation framework: `eval/` — 24 queries targeting B1–B6, runner + 5 evaluators (azure-ai-evaluation)

**Done (as of Feb 23, 2026):**

- **vLLM fully operational**: service running, model loaded, inference verified end-to-end from laptop
  - `Restart=always` + `RestartSec=10` added to `vllm.service` (was `Restart=no`)
  - `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` added — fixes KV cache fragmentation OOM on RTX 3090 Ti
  - `OLLAMA_NUM_GPU=0` added to `/etc/systemd/system/ollama.service.d/override.conf` — forces Ollama onto CPU, gives vLLM full 24 GB VRAM
- **System prompt rewritten** (`hal/main.py:SYSTEM_PROMPT`): five explicit roles (know/answer/act/monitor/guard), stronger identity assertion, tool-use decision rule (tools for live state, KB for documented answers)
- **Evaluation baseline established**: `eval/run_eval.py` fixed to import real `SYSTEM_PROMPT` from `hal.main`; full 24-query run completed; results in `eval/responses.jsonl` + `eval/results/eval_out.json`
  - `hal_identity`: 100% — never identifies as Qwen (RC2 resolved with instruct model + prompt)
  - `no_raw_json`: 100% — no raw JSON tool calls in responses (RC1 resolved by vLLM)
  - `intent_accuracy`: 95.8% (23/24) — 1 misroute remaining
  - Run eval: `python -m eval.run_eval && python -m eval.evaluate --skip-llm-eval`
- **SQLite memory.db fragility documented**: if HAL crashes mid-init, DB is left as empty schema-0 file causing `sqlite3.OperationalError: disk I/O error` on next start. Fix: `rm ~/.orion/memory.db` — HAL recreates it cleanly on next launch

**Watchdog deployment (server):**

- Deployed as user systemd (not system) — SELinux blocks system services from running home-dir code
- Unit files: `~/.config/systemd/user/watchdog.{service,timer}` (use `%h` for home dir, no `User=` line)
- `loginctl enable-linger jp` — user systemd instance survives without login session
- Manage with: `systemctl --user [status|start|stop] watchdog.{service,timer}`
- ops/ files updated to match user-service format (use `%h`, no `User=jp`)
- ntfy not yet configured — alerts log to `~/.orion/watchdog.log` only

**Backlog:**

- **Fix harvest_lag watchdog alert**: Harvest already ran and the data is in pgvector. Just write the timestamp: `touch ~/.orion/harvest_last_run`. Or re-run `python -m harvest` to refresh data and write it properly.
- **Clean foreign KB data**: `ghs-genome` (4 rows) and `ghs-rejections` (1 row) don't belong. Delete with: `DELETE FROM documents WHERE category IN ('ghs-genome', 'ghs-rejections');`
- **Judge no-tools constraint**: `_llm_reason()` in `hal/judge.py` should tell the LLM "do not call tools or fetch external data" — prevents the risk evaluator from trying to use tools
- **Security module**: network guard — planned, needs design conversation before any code
- **RC3 — session history pruning**: Bad turns (Qwen identity, JSON dumps) accumulate in SQLite and compound future failures. Need a pruning strategy or quality filter on what gets saved.
