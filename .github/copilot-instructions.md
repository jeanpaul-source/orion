# Orion — Copilot Instructions

This file is auto-injected into every AI assistant context. It is the orientation layer —
not the full reference. For depth, read the dedicated docs.

## Communication contract

This project is maintained by someone actively learning to code. Every AI interaction
is both a work session and a learning opportunity. In addition to global instructions:

1. **Show your work before every code change.** State what you think the problem is
   (root cause, not symptom), what you plan to change, and why this approach is correct
   long-term. This is a reliability mechanism — it forces you to reason through the
   change before making it. If you're guessing, say "I'm guessing because..." explicitly.
2. **One change at a time.** Make one change, verify it works (tests, lint), then
   move to the next. Multiple simultaneous changes make it impossible to know what
   helped or broke.
3. **No band-aids.** If you're adding a flag, rule, or workaround to suppress a symptom,
   stop and ask whether the underlying component is actually wrong.

These rules exist because AI assistants drift on long projects — each fix looks
plausible in isolation, but over many sessions the system degrades. Forcing
explanation-before-action is the catch mechanism.

---

## Reference docs

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Component map, data flow, design decisions |
| [OPERATIONS.md](../OPERATIONS.md) | Deploy, `.env` reference, systemd units, known traps |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Dev workflow, tests, linting, git workflow, eval |
| [ROADMAP.md](../ROADMAP.md) | What's done, what's next, end-state vision |
| [CLAUDE.md](../CLAUDE.md) | AI operating contract — required format before every code change |

---

## Architecture

Every query passes through `hal/intent.py` (embedding classifier, threshold 0.65)
**before** the LLM sees it. Two routes:

```text
conversational → _handle_conversational() — single LLM call, tools=[], no KB, no Prometheus
everything else → run_agent()             — full VLLMClient tool loop, Judge-gated
```

health/fact intents map to `run_agent()` — KB context (≥0.75 score) and a live Prometheus
snapshot are pre-seeded at iteration 0, so simple queries resolve without a tool call.

Data flow: `hal/main.py` → `IntentClassifier` → `dispatch_intent()` in `hal/bootstrap.py`
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

# Deploy: push from server (VS Code Remote SSH), CD runner auto-deploys on merge
git push origin <feature-branch>              # open PR → CI → merge → auto-deploy
ssh jp@192.168.5.10 'cd ~/orion && git pull'  # manual fallback after merge
```

---

## Key files

| File | Role |
|---|---|
| `hal/main.py` | REPL entry point; `SYSTEM_PROMPT`; all slash commands |
| `hal/agent.py` | Four handlers + agentic loop (`MAX_ITERATIONS=8`) |
| `hal/intent.py` | Embedding classifier; tune `EXAMPLES` and `THRESHOLD` here |
| `hal/judge.py` | Policy gate; tier 0-3; command normalization; evasion detection; git write blocking; path canonicalization; self-edit governance; default-deny; JSON audit with session/trace |
| `hal/llm.py` | `VLLMClient` (chat) and `OllamaClient` (embeddings only) |
| `hal/falco_noise.py` | Falco noise rules (`NOISE_RULES` tuples + `is_falco_noise()`); zero `hal.*` deps |
| `hal/sanitize.py` | Response sanitiser — strips tool-call artefacts (`TOOL_CALL_FENCE_RE`) + CJK leaks; used by `agent.py`, `memory.py`, `server.py` |
| `hal/security.py` | Falco, Osquery, ntopng, Nmap workers; noise-filtered via `hal/falco_noise.py` |
| `hal/web.py` | `web_search()` via Tavily; `fetch_url()` with SSRF protection + DNS rebinding defence; `sanitize_query()` privacy guard |
| `hal/memory.py` | SQLite session store at `~/.orion/memory.db` |
| `hal/prometheus.py` | PromQL client; `flush_metrics()` batch push to Pushgateway |
| `hal/server.py` | FastAPI `/chat` + `/health` + Web UI at `GET /`; `ServerJudge` auto-denies tier 1+ |
| `hal/telegram.py` | Telegram bot; polls API, POSTs to `/chat`; auth by `TELEGRAM_ALLOWED_USER_ID` |
| `hal/trust_metrics.py` | Audit log parser; `get_action_stats()` tool |
| `hal/config.py` | Dataclass + `.env` loader; all tunable values live here |
| `harvest/collect.py` | Lab state + static docs collectors |
| `harvest/ingest.py` | Chunk → embed → upsert; clears stale chunks before re-ingest |
| `tests/` | 1176 offline tests passing; intent tests require reachable Ollama |
