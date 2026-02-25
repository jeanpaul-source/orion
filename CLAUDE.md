# Orion

A personal homelab AI assistant built intentionally. It knows the infrastructure, answers
questions about it, takes actions within it, monitors health, learns over time, and guards
the home network.

---

## ⛔ REQUIRED FORMAT — Before Every Code Change

**This applies to every single change, no exceptions. Violations are drift.**

For each proposed change I must output exactly this block and then **STOP and wait**:

```
### Item N — <short title>

**Root cause (not symptom):** <what is actually wrong and why>

**What I propose:** <exact files and lines I will touch, and what I will do>

**Why this is correct long-term:** <not just "it fixes the symptom">

**Confidence:** I KNOW this is right / I am GUESSING because <reason>
```

I do **not** write or change any code until the operator replies with approval.
After the operator approves, I make **exactly one change**, verify it, commit it,
then present the **next** item in the same format and stop again.

If I skip this format, the operator should say **"format"** and I will stop, restate
the plan correctly, and wait.

---

## How I (Claude) Work With the Operator

Observability aid: I will also emit structured logs with session_id and trace correlation for each approved change when running code paths, and I will update README and SESSION_FINDINGS as I go to prevent documentation drift. These logs are JSON by default and can be toggled with HAL_LOG_JSON.

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
        │     ├── conversational → run_conversational()  (direct reply, no tools)
        │     ├── health  → run_health()  (metrics, no tool loop)
        │     ├── fact    → run_fact()    (KB search, no tool loop)
        │     └── agentic → run_agent()  (full tool loop)
        ├── pgvector  (knows the lab — ~19,900 doc chunks indexed)
        ├── Judge     (policy gate — "is this safe to do?", approval tiers)
        └── Workers   (do things)
              ├── SSH executor   (run commands on the server)
              ├── Prometheus     (health queries)
              └── Security       (Falco · Osquery · ntopng · Nmap)
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
| --- | --- | --- | --- | --- |
| ollama | 11434 | — | systemd | Bare metal, all interfaces, firewalled from LAN |
| pgvector-kb | 5432 | 5432 | Docker | PostgreSQL+pgvector; DB: knowledge_base, user: kb_user |
| pgvector-kb-api | 5001 | — | systemd | Python search API wrapping pgvector; at /opt/homelab-infrastructure/pgvector-kb/api.py |
| prometheus | 9091 | 9090 | Docker | compose at /opt/homelab-infrastructure/monitoring-stack/ |
| grafana | 3001 | 3000 | Docker | same compose stack |
| node-exporter | — | 9100 | Docker | internal to monitoring network only |
| blackbox-exporter | — | 9115 | Docker | internal to monitoring network only |
| cockpit | 9090 | — | systemd | Server management UI — NOT Prometheus |
| vLLM | 8000 | — | user systemd | `~/vllm-env/bin/vllm`; `VLLM_USE_FLASHINFER_SAMPLER=0` workaround for RTX 3090 Ti CUDA issue; `--enable-auto-tool-choice --tool-call-parser hermes --enforce-eager --max-model-len 8192 --gpu-memory-utilization 0.95`; model `Qwen/Qwen2.5-32B-Instruct-AWQ` |
| ntopng | 3000 | 3000 | Docker | `~/ntopng/docker-compose.yml`; Redis on same stack; interface `enp130s0`; login disabled; Community API at `/lua/rest/v2/` |
| Falco | — | — | system systemd | `falco-modern-bpf.service`; JSON events at `/var/log/falco/events.json`; group `falco-readers` (jp is member) |
| Osquery | — | — | bare metal | 5.21.0; `/etc/sudoers.d/osquery-hal` scopes `jp` to `osqueryi` only (no password) |

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

**Chat LLM:** HAL uses vLLM (OpenAI-compatible API at port 8000) as its primary chat backend. Ollama is used only for embeddings. Model: `Qwen/Qwen2.5-32B-Instruct-AWQ` (19GB AWQ-quantised). The Coder variant (`Qwen2.5-Coder-32B-Instruct-AWQ`) is also on disk but is NOT used — it emits tool calls in `<tools>` tag format that `--tool-call-parser hermes` does not handle.

**pgvector knowledge base (verified Feb 23, 2026 — session 4):**

- ~19,900 document chunks, 768-dim HNSW embeddings (cosine)
- 18 categories: github (7,197), virtualization (1,980), ai-agents-and-multi-agent-systems (1,771), databases (1,183), llm-serving-and-inference (1,145), homelab-networking-security (1,092), homelab-infrastructure (1,054), rag-and-knowledge-retrieval (1,048), readthedocs (960), gpu-passthrough-and-vgpu (669), vector-databases (511), self-healing-and-remediation (432), container-platforms (399), observability-and-alerting (316), workflow-automation-n8n (79), lab-infrastructure (35), lab-state (18), vendor_pdf (7)
- Static docs ingested from `/data/orion/orion-data/documents/raw` — 727 documents, 17,657 chunks (Feb 23 2026)
- Nightly harvest timer (`harvest.timer`) deployed on server — clears and re-ingests at 3am daily
- `search_kb` threshold 0.45, top_k 8 (raised from 0.3/5 to reduce low-quality results with larger KB)
- Table: `documents` — columns: content, embedding, category, file_name, file_path, metadata

**NOT running:** Qdrant, AnythingLLM, n8n, Traefik, Authelia

**Watch:** Swap usage was 7.3G/8G despite 49G RAM free (Feb 21 2026) — worth investigating

**Observability (as of Feb 24, 2026):**
- JSON logs with trace_id/span_id when tracing is on; session_id context per turn
- Tracing via OTLP HTTP (default http://localhost:4318), no-op if deps/endpoint missing
- Metrics via Pushgateway at `http://localhost:9092` (deployed); `hal_requests_total`, `hal_request_latency_seconds`, `hal_tool_calls_total`
- Grafana dashboard provisioned at `/opt/homelab-infrastructure/monitoring-stack/grafana/provisioning/dashboards/hal.json`

---

## This Repo

**Remote:** <https://github.com/jeanpaul-source/orion> (private)

| Path | What it is |
| --- | --- |
| `hal/main.py` | REPL entry point; intent routing; all slash commands |
| `hal/intent.py` | Embedding-based intent classifier (conversational / health / fact / agentic); threshold 0.65 |
| `hal/agent.py` | `run_conversational()`, `run_health()`, `run_fact()`, `run_agent()` — the four handlers |
| `hal/judge.py` | Policy gate: tier 0-3, sensitive path blocklist, safe command allowlist, LLM risk eval, audit log |
| `hal/workers.py` | `read_file`, `write_file`, `list_dir` — all gated through Judge |
| `hal/executor.py` | SSH runner; detects localhost and runs directly (no self-SSH) |
| `hal/memory.py` | SQLite session store (`~/.orion/memory.db`); `search_sessions()` full-text search |
| `hal/facts.py` | `/remember` — embeds facts to pgvector as `category='memory'` |
| `hal/watchdog.py` | Standalone monitoring watchdog (run via systemd timer) |
| `hal/prometheus.py` | Prometheus query client; `health()` returns cpu/mem/disk/swap/load; optional Counter/Histogram helpers (push via PROM_PUSHGATEWAY) |
| `hal/server.py` | FastAPI HTTP server — `/health` liveness probe, `/POST chat` endpoint; `ServerJudge` auto-denies tier 1+ (no TTY) |
| `hal/agents.py` | `PlannerAgent` + `CriticAgent` sub-agents — tool-less LLM wrappers with structured output prompts |
| `hal/trust_metrics.py` | Parses `~/.orion/audit.log` into `AuditEvent` objects; `get_action_stats()` exposed as a HAL tool |
| `hal/logging_utils.py` | Structured logging utilities (JSON), contextvars for session correlation |
| `hal/llm.py` | `OllamaClient` (embeddings), `VLLMClient` (chat via OpenAI-compatible API) |
| `hal/tracing.py` | OTel setup; `setup_tracing()` + `get_tracer()`; no-op fallback if collector absent |
| `hal/tunnel.py` | SSH tunnel for laptop-side use (auto-tunnel when vLLM/Ollama not directly reachable) |
| `hal/knowledge.py` | pgvector KB search |
| `hal/security.py` | Security workers: `get_security_events` (Falco), `get_host_connections` (Osquery), `get_traffic_summary` (ntopng), `scan_lan` (Nmap) — all Judge-gated, tiers 0/1 |
| `hal/config.py` | Config dataclass + `.env` loader (includes `NTFY_URL`, `VLLM_URL`, `NTOPNG_URL`) |
| `~/ntopng/docker-compose.yml` | ntopng + Redis compose; host network; interface `enp130s0`; not in this repo |
| `harvest/` | Lab infrastructure harvester — re-indexes lab state into pgvector |
| `eval/queries.jsonl` | 24 test queries covering B1–B6 failure cases from SESSION_FINDINGS |
| `eval/run_eval.py` | Eval runner — drives HAL handlers, writes `eval/responses.jsonl` |
| `eval/evaluate.py` | Scores responses: no_raw_json, hal_identity, intent_accuracy, relevance, coherence |
| `tests/` | pytest suite: 35 intent classifier tests (require Ollama) + 112 offline tests (Judge, MemoryStore, agent loop, trust_metrics, agents) = 147 total |
| `pytest.ini` | `pythonpath = .` so pytest can find the `hal` package |
| `requirements.txt` | Production Python deps (includes opentelemetry-*) |
| `requirements-dev.txt` | Dev-only deps (pytest, azure-ai-evaluation) |
| `.env.example` | Config template |
| `ops/` | Systemd units: `vllm.service`, `watchdog.service`, `watchdog.timer`, `harvest.service`, `harvest.timer`; `KEYS_AND_TOKENS.md` |

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

**Rule:** Run `pytest tests/` before every push. Agent loop and unit tests (Judge, MemoryStore) run anywhere with no dependencies. Intent classifier tests require Ollama — if skipped on laptop, SSH to server and run there first.

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

**Done (as of Feb 23, 2026 — session 3):**

- **KB foreign data deleted**: `DELETE FROM documents WHERE category IN ('ghs-genome', 'ghs-rejections')` — 5 rows removed
- **OllamaClient model param removed**: `model: str` arg was unused (embeddings use `embed_model`; chat is VLLMClient). Removed from `__init__`, call site in `main.py`, and `tests/conftest.py`
- **Security stack installed on the-lab**:
  - Falco (eBPF modern-bpf): `falco-modern-bpf.service`, JSON events at `/var/log/falco/events.json`, `falco-readers` group, logrotate
  - Osquery 5.21.0: `/etc/sudoers.d/osquery-hal` — scoped to `osqueryi` only
  - ntopng + Redis: Docker Compose at `~/ntopng/`, port 3000, login disabled, interface `enp130s0`; Community API confirmed working
  - Nmap 7.92: bare metal, XML output (`-oX -`)
- **`hal/security.py`**: four workers — `get_security_events`, `get_host_connections`, `get_traffic_summary`, `scan_lan`; registered in `agent.py` TOOLS + `_dispatch`; tiers in `judge.py`; `ntopng_url` added to `config.py`
- **Security intent examples**: 15 agentic examples added to `hal/intent.py` covering Falco/port/traffic/LAN queries
- **System prompt updated**: Role 5 (GUARD) rewritten with four concrete tool names and trigger phrases; security stack listed in services section
- **`VLLMClient.ping()` hardened**: now uses `/health` endpoint (only returns 200 when model is fully loaded) instead of `/v1/models` (returns 200 immediately on API server start — before weights are in VRAM)
- **vLLM 404 guard**: `chat_with_tools` and `chat` catch HTTP 404 and raise `RuntimeError` with readable "still loading" message instead of traceback
- **Model name fix**: server `.env` had `Qwen2.5-32B-Instruct-AWQ` but vLLM service was set to Coder variant; fixed `ops/vllm.service` and `.env` back to `Qwen/Qwen2.5-32B-Instruct-AWQ`; Instruct model uses Hermes tool-call format natively
- **`_extract_tool_calls_from_content()`**: fallback parser in `llm.py` for `<tools>`/`<tool_call>` wrappers; active while Coder model was loaded, retained as defensive code
- **End-to-end verified**: `get_security_events` fires as structured tool call, Falco events returned, HAL answers correctly

**Known noise (Falco):** `systemd-userwork` accessing `/etc/shadow` — benign, not yet in noise filter. Add to `_FALCO_NOISE` in `hal/security.py`.

**Done (as of Feb 23, 2026 — session 2):**

- **Poison-turn filter**: `is_poison_response()` in `memory.py` + guard in `save_turn()` — raw tool-call JSON dumps from pre-vLLM era are no longer persisted to SQLite (RC3 mitigation)
- **Session history pruning**: `MemoryStore.prune_old_turns(days=30)` — deletes turns older than 30 days and orphaned sessions on every startup; called from `main.py` (RC3 structural fix)
- **Agentic KB seeding threshold raised**: `run_agent()` threshold `0.6 → 0.75` — only strong semantic matches seed the first message; prevents low-confidence KB docs biasing the LLM on casual queries (RC5)
- **Unit tests for Judge and MemoryStore**: 96 new tests in `tests/test_judge.py` and `tests/test_memory.py`; run without Ollama; `conftest.py` `require_ollama` fixture changed from `autouse=True` to explicit opt-in so unit tests are never skipped
- **harvest_last_run written on server**: `touch ~/.orion/harvest_last_run` — silences false watchdog harvest_lag alarm (harvest had already run; timestamp file was missing)
- **CLAUDE.md required-format block added**: strict plan-before-code format enforced at top of file to prevent drift

**Done (as of Feb 23, 2026 — session 4):**

- **Static docs ingested into pgvector**: 727 documents, 17,657 chunks from `/data/orion/orion-data/documents/raw` — subdirectory names used as categories
- **`collect_static_docs()` added** to `harvest/collect.py` — reads raw docs directory without moving or modifying files; registered in `collect_all()`
- **`clear_static_docs()` added** to `harvest/ingest.py` — deletes all rows under the static docs path before re-harvest to prevent orphan chunks from deleted files
- **`harvest/main.py` bug fixed**: `OllamaClient` was called with 3 args (`ollama_host, ollama_model, embed_model`) but the constructor only takes 2 (`base_url, embed_model`); `ollama_model` doesn't exist on `Config`. This caused every harvest run to crash at the ingest step.
- **KB search quality raised**: `search_kb` threshold raised `0.3 → 0.45`, `top_k 5 → 8` in `hal/agent.py` — with 17k+ chunks, 0.3 was too permissive and returned irrelevant results
- **Nightly harvest timer deployed**: `ops/harvest.service` + `ops/harvest.timer` created and deployed to server (`~/.config/systemd/user/`); fires at 3:00am daily; `Persistent=true` so missed runs catch up on next boot

**Done (as of Feb 23, 2026 — trust hardening):**

- **NTFY_URL set on server**: `NTFY_URL=https://ntfy.sh/hal-lab-alerts-2158c448` appended to server `.env`; watchdog alerts will now be delivered. Subscribe to that topic in the ntfy app.
- **RC3 confirmed resolved**: `prune_old_turns(days=30)` already called at startup + `TURN_WINDOW=40` caps context load; README updated to mark RC3 resolved.
- **RC4/RC5 fix**: `conversational` example set expanded from 15 → 30 entries (added: `okay`, `yep`, `nope`, `sure`, `alright`, `perfect`, `roger that`, `understood`, `noted`, `good to know`, `thanks got it`, `that makes sense`, `awesome`, `fair enough`, `will do`).
- **Intent test suite expanded**: added `CONVERSATIONAL_QUERIES` list (14 queries) + `test_conversational_queries` parametrized test; updated `test_low_confidence_falls_back_to_agentic` to use a genuinely ambiguous phrase instead of "hello" (which is now correctly classified as `conversational`); total intent tests 21 → 35.
- **P4 confirmed resolved**: both `tool_call_id` paths in the loop already correct; `SESSION_FINDINGS.md` updated to mark P4 resolved.
- **Agent loop integration tests**: 10 new tests in `tests/test_agent_loop.py` — all mocked, no external services; cover: direct text response, single tool call + `tool_call_id` propagation, dedup loop-breaker, max-iterations guard, output truncation, KB search no-results, unknown tool graceful error, Prometheus unavailable fallback, KB injection threshold (≥0.75 injected, <0.75 discarded). Test count: 117 → 141.

**Done (as of Feb 24, 2026):**

- **Agent Inspector cleanup**: removed `HalAgent` class and `agentdev` dead code from `hal/server.py` (~80 lines); removed `debugpy`, `agent-dev-cli`, `agent-framework-core` from `requirements-dev.txt`; replaced Agent Inspector VS Code tasks with plain `Run HAL HTTP Server` and `Debug HAL HTTP Server` tasks; deleted stray `=0.115` file
- **New files from previous session committed**: `hal/server.py` (FastAPI HTTP server, `/chat` + `/health`), `hal/agents.py` (`PlannerAgent` / `CriticAgent` sub-agents), `hal/trust_metrics.py` (audit log stats + `get_action_stats` tool), `hal/logging_utils.py`, `tests/test_agent_loop.py`, `tests/test_agents.py`, `tests/test_trust_metrics.py`, `pyproject.toml` (ruff config), `.github/workflows/test.yml`, `.vscode/` config
- **Prometheus Pushgateway deployed** on server at port 9092 (`prom/pushgateway:v1.10.0`); added to monitoring-stack `docker-compose.yml`; scrape job added to `prometheus.yml` with `honor_labels: true`; `--web.enable-lifecycle` added to Prometheus so config can be reloaded without restart
- **Metrics accumulator fix** in `hal/prometheus.py`: replaced per-call `_push_metric()` (clobbered Pushgateway on every call) with in-memory `_counters`/`_gauges` accumulators + thread-safe `flush_metrics()` that batches all metrics in a single POST at turn end; `Counter.inc()` now truly accumulates (was always-1); `run_conversational` now tracked
- **HAL Grafana dashboard** provisioned at `/opt/homelab-infrastructure/monitoring-stack/grafana/provisioning/dashboards/hal.json` — 6 panels: requests/sec, latency, tool calls/sec, totals stat, requests by intent bar
- **`PROM_PUSHGATEWAY`** added to laptop and server `.env` (ports 9092)
- **Ruff linter baseline**: fixed import ordering and unused import issues in `hal/trust_metrics.py`, `tests/test_trust_metrics.py`; added `per-file-ignores` for `hal/server.py` in `pyproject.toml` (intentional sys.path manipulation)

**Backlog:**

See [ROADMAP.md](ROADMAP.md) for the full backlog and end-state roadmap. Summary:

- **Falco noise filter**: add `systemd-userwork` + `/etc/shadow` to `_FALCO_NOISE` in `hal/security.py` (same pattern as existing `unix_chkpwd` entry)
- **Swap investigation**: 7.3G/8G swap used despite 49G RAM free (Feb 21 2026) — root cause unknown
- **Eval re-run**: baseline predates security tools, prompt rewrite, and KB expansion; run `python -m eval.run_eval && python -m eval.evaluate --skip-llm-eval` on server to capture new baseline
- **Tempo / OTel traces**: `hal/tracing.py` is wired and emitting spans; deploy Grafana Tempo container to receive them (separate item, pending investigation)
