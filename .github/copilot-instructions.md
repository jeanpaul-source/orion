# Orion — Copilot Instructions

This file is auto-injected into every AI assistant context. It is the orientation layer —
not the full reference. For depth, read the dedicated docs:

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Component map, data flow, design decisions |
| [OPERATIONS.md](../OPERATIONS.md) | Deploy, `.env` reference, systemd units, known traps |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Dev workflow, tests, linting, git workflow, eval |
| [ROADMAP.md](../ROADMAP.md) | What's done, what's next, end-state vision |
| [CLAUDE.md](../CLAUDE.md) | AI operating contract — required format before every code change |
| [SESSION_FINDINGS.md](../SESSION_FINDINGS.md) | Ground-truth audit, known failure modes (P1–P5) |

---

## Architecture

Every query passes through `hal/intent.py` (embedding classifier, threshold 0.65)
**before** the LLM sees it. Four routes:

```
conversational → run_conversational() — direct LLM reply, no tools, no KB
health         → run_health()         — Prometheus only, no tool loop
fact           → run_fact()           — pgvector KB search only, no tool loop
agentic        → run_agent()          — full VLLMClient tool loop, Judge-gated
```

Data flow: `hal/main.py` → `IntentClassifier` → one of four handlers in `hal/agent.py`
→ `VLLMClient` (chat) + `OllamaClient` (embeddings only) → `Judge` gates every tool call.

---

## LLM backend split — critical

- **Chat:** `VLLMClient` → vLLM at `VLLM_URL` (port 8000) → `Qwen/Qwen2.5-32B-Instruct-AWQ`
- **Embeddings:** `OllamaClient` → Ollama at `OLLAMA_HOST` (port 11434) → `nomic-embed-text:latest`

Ollama is **embeddings-only — never chat**. `OLLAMA_NUM_GPU=0` is set in Ollama's systemd
override. Do not remove it — Ollama was consuming ~800 MB VRAM and causing vLLM to OOM on
the RTX 3090 Ti. See [OPERATIONS.md](../OPERATIONS.md) for full vLLM unit file details.

---

## Judge — never bypass

Every tool call and shell command passes through `hal/judge.py`. There is no `force=True`.
Tiers: 0 = auto, 1 = prompt, 2 = explain + approve, 3 = confirmation phrase required.
Audit log at `~/.orion/audit.log`. See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full
tier assignment rules.

---

## Conventions

**Before every code change** (from CLAUDE.md — no exceptions):
- State root cause (not symptom), proposed change, why it's correct long-term, confidence level
- Wait for approval
- Make one change, verify it works, then move to the next

**No bandaids.** If adding a flag/cap/rule to work around misbehaviour, stop and ask
whether the component itself is wrong. Band-aids already in the codebase are documented in
`SESSION_FINDINGS.md` (P1–P5) — do not add more.

**Git workflow** (from CONTRIBUTING.md):
- Conventional Commits: `feat|fix|docs|refactor|test|chore: subject`
- One logical change per commit — tests pass + ruff passes + one thing changed
- `main` is always deployable; server runs `git pull main`
- Claude-assisted commits get `Co-Authored-By: Claude <noreply@anthropic.com>`

---

## Key commands

```bash
# Tests (offline — no Ollama needed)
.venv/bin/pytest tests/ --ignore=tests/test_intent.py -v

# Tests (full — requires Ollama reachable)
OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v

# Lint
.venv/bin/ruff check hal/ tests/ harvest/ eval/

# Eval (on server — requires vLLM + Ollama + pgvector)
python -m eval.run_eval && python -m eval.evaluate --skip-llm-eval

# Harvest
python -m harvest --dry-run   # preview
python -m harvest             # live run

# Deploy: laptop pushes → server pulls
git push origin main
ssh jp@192.168.5.10 'cd ~/orion && git pull'   # alias: orion-update
```

---

## Key files

| File | Role |
|---|---|
| `hal/main.py` | REPL entry point; `SYSTEM_PROMPT`; all slash commands |
| `hal/agent.py` | Four handlers + agentic loop (`MAX_ITERATIONS=8`) |
| `hal/intent.py` | Embedding classifier; tune `EXAMPLES` and `THRESHOLD` here |
| `hal/judge.py` | Policy gate; tier rules; audit log; `_llm_reason()` risk eval |
| `hal/llm.py` | `VLLMClient` (chat) and `OllamaClient` (embeddings only) |
| `hal/security.py` | Falco, Osquery, ntopng, Nmap workers; `_FALCO_NOISE` filter |
| `hal/memory.py` | SQLite session store at `~/.orion/memory.db` |
| `hal/prometheus.py` | PromQL client; `flush_metrics()` batch push to Pushgateway |
| `hal/server.py` | FastAPI `/chat` + `/health`; `ServerJudge` auto-denies tier 1+ |
| `hal/trust_metrics.py` | Audit log parser; `get_action_stats()` tool |
| `hal/config.py` | Dataclass + `.env` loader; all tunable values live here |
| `harvest/collect.py` | Lab state + static docs collectors |
| `harvest/ingest.py` | Chunk → embed → upsert; clears stale chunks before re-ingest |
| `tests/` | 147 tests: 35 intent (require Ollama) + 112 offline |
