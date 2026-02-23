# Orion — Copilot Instructions

## Architecture

HAL is a thin coordinator. Every query passes through `hal/intent.py` (embedding classifier,
threshold 0.65) **before** the LLM sees it. Three routes:

```
health  → run_health()  — Prometheus query only, no tool loop
fact    → run_fact()    — pgvector KB search only, no tool loop
agentic → run_agent()   — full VLLMClient tool loop, Judge-gated
```

Key data flow: `hal/main.py` → `IntentClassifier` → one of three handlers in `hal/agent.py`
→ `VLLMClient` (chat) + `OllamaClient` (embeddings only) → `Judge` gates every tool call.

## LLM Backend Split (Critical)

- **Chat (`VLLMClient`):** vLLM OpenAI-compatible API at `VLLM_URL` (default `http://localhost:8000`),
  model `Qwen/Qwen2.5-32B-Instruct-AWQ`. Uses `/v1/chat/completions`.
- **Embeddings (`OllamaClient`):** Ollama at `OLLAMA_HOST`, model `nomic-embed-text:latest`.
  Ollama is **embeddings-only** — never used for chat.

**vLLM status (Feb 2026): RUNNING** as a user systemd service (`vllm.service`, enabled).
Venv: `~/vllm-env/`. Two required env vars in the unit file:
- `VLLM_USE_FLASHINFER_SAMPLER=0` — fixes CUDA device-side assert on RTX 3090 Ti
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` — prevents KV cache OOM under load

`Restart=always` + `RestartSec=10`. Flags: `--enforce-eager --tool-call-parser hermes --max-model-len 8192 --gpu-memory-utilization 0.95`.
Manage: `systemctl --user [start|stop|status] vllm.service`. Logs: `journalctl --user -u vllm`.

**Ollama GPU:** `OLLAMA_NUM_GPU=0` is set in `/etc/systemd/system/ollama.service.d/override.conf` — Ollama runs on CPU. This is required: Ollama was consuming ~800 MB VRAM, causing vLLM to OOM during inference. Do not remove this flag.

## Developer Workflow

```bash
# Run tests (requires Ollama reachable — embeddings-based intent tests)
OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v

# Deploy to server
git push origin main          # laptop only — server never pushes
ssh jp@192.168.5.10
cd ~/orion && git pull        # alias: orion-update

# Run HAL on server
cd ~/orion && .venv/bin/python -m hal    # alias: hal

# Re-harvest lab state into pgvector
python -m harvest

# Watchdog (user systemd on server)
systemctl --user status watchdog.timer
systemctl --user restart watchdog.service
```

`.env` layout: laptop uses `192.168.5.10` IPs + `USE_SSH_TUNNEL=true`; server uses `localhost`.
Copy `.env.example` and fill `PGVECTOR_DSN` password (from `/run/homelab-secrets/pgvector-kb.env`).

## Tiered Action Approval (Judge)

All tool calls pass through `hal/judge.py`. Tiers:
- **0** — read-only → auto-approved
- **1** — restart service → prompt user, then execute
- **2** — config change → explain plan, wait for approval
- **3** — destructive → explicit confirmation required

`run_command` in `hal/workers.py` calls `judge.approve()` before SSH execution. Never bypass Judge.

## Known Failure Modes

- **RC1 — resolved:** Ollama + `qwen2.5-coder:32b` emitted tool calls as JSON text in `content`. Fixed by switching to vLLM + `Qwen2.5-32B-Instruct-AWQ`. Eval baseline: `no_raw_json=100%`.
- **RC2 — resolved:** Model identity override. Fixed by vLLM instruct model + stronger system prompt. Eval baseline: `hal_identity=100%`.
- **RC3 — open:** Broken turns accumulate in SQLite and compound future sessions. No pruning. Use `hal --new` to start fresh.
- **RC4/5 — open:** Casual input (greetings) falls to `agentic`, seeds irrelevant KB context. A `conversational` intent category would fix this cleanly.
- **SQLite init race:** If HAL crashes between opening `~/.orion/memory.db` and completing `_init()`, the file is left as an empty schema-0 database. Next start fails with `sqlite3.OperationalError: disk I/O error`. Fix: `rm ~/.orion/memory.db` — HAL recreates it on next launch.

## Evaluation

Run on server after changes:
```bash
python -m eval.run_eval                              # 24 queries → eval/responses.jsonl
python -m eval.evaluate --skip-llm-eval              # score → eval/results/eval_out.json
```
Baseline (Feb 23 2026): `hal_identity=100%`, `no_raw_json=100%`, `intent_accuracy=95.8%`.

## Conventions

- **Explain before acting** (from CLAUDE.md): state root cause + proposed fix + confidence level
  before writing any code. No silent bandaid patches.
- **One change at a time.** Verify before moving on.
- **No bandaids:** if adding a flag/cap/rule to work around misbehaviour, stop and fix the root cause.
- Tests live in `tests/` and cover the intent classifier (21 tests). The agent loop has no tests.
- Band-aids already in the codebase are documented in `SESSION_FINDINGS.md` (P1–P5) — do not add more.

## Key Files

| File | Role |
|---|---|
| `hal/agent.py` | Three handlers + agentic tool loop (`MAX_ITERATIONS=8`) |
| `hal/intent.py` | Embedding classifier; adjust `THRESHOLD = 0.65` here |
| `hal/judge.py` | Policy gate; tier table + `_llm_reason()` risk eval |
| `hal/llm.py` | `VLLMClient` (chat) and `OllamaClient` (embed) |
| `hal/config.py` | All config; loaded from `.env` via `load()` |
| `hal/memory.py` | SQLite session store at `~/.orion/memory.db` |
| `hal/watchdog.py` | Standalone monitor; deployed as user systemd timer on server |
| `SESSION_FINDINGS.md` | Ground-truth audit of what actually runs and known failure modes |
