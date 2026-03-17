# Orion — Copilot Instructions

Orion is a homelab AI assistant (HAL). Local LLM (vLLM/Qwen) with RAG
(pgvector + Ollama embeddings), Prometheus monitoring, and a tiered Judge
approval system. Every action is audited to `~/.orion/audit.log`.

## How to work on this codebase

1. **Root cause first.** Before changing anything, state what is actually wrong
   and why. If the explanation sounds thin, dig deeper.
2. **One logical change per commit.** One finding, one fix, or one feature —
   not one line. Makes diffs reviewable and reverts safe.
3. **State confidence.** Say whether you *know* this is correct or are *guessing*.
   Confident-sounding guesses are the most dangerous failure mode.
4. **No bandaids.** If a fix requires adding rules, caps, or flags to work around
   a misbehaving component — stop. Fix the component.
5. **Verify after each change.** Run `make check` (or the relevant subset).
   Don't stack unverified changes.

## Critical constraints

Violating any of these breaks the system. Do not change them without discussion.

- **Ollama is embeddings-only.** `OLLAMA_NUM_GPU=0` — vLLM owns the GPU exclusively.
- **Prometheus is port 9091.** Port 9090 is Cockpit — never use 9090 for Prometheus.
- **The Judge has no bypass.** Every tool call flows through `judge.approve()`.
- **`main` is always deployable.** CI builds a Docker image and auto-deploys on merge.
- **Config lives in `hal/config.py`.** Never hardcode IPs, ports, paths, or model names.

## Key commands

```bash
make check        # lint + format + typecheck + test + doc-drift — run before every push
make test         # offline tests only (no Ollama needed)
make test-full    # full suite including intent classifier (requires Ollama)
make dev-setup    # one-command fresh-clone setup (venv, deps, hooks)
```

## Architecture (verified from code)

Three execution modes:

| Mode | Entry point | Judge behavior |
|------|-------------|----------------|
| REPL | `python -m hal` → `hal/main.py` | Interactive (tier 1+ prompts user) |
| HTTP | `hal/server.py --port 8087` | Auto-deny tier 1+ (no TTY) |
| Harvest | `python -m harvest` | N/A — data ingestion only |

Core flow: Query → IntentClassifier (embedding-based, no LLM) → route to
agent / health / fact / conversational → Agent loop (max 8 iterations,
5 tool calls per turn) → Judge gates every tool → result.

Key modules:

- `hal/agent.py` — agentic tool-calling loop
- `hal/judge.py` — 4-tier approval (0=auto, 1=prompt, 2=explain, 3=confirm)
- `hal/intent.py` — embedding classifier (threshold 0.65, 4 categories)
- `hal/knowledge.py` — pgvector RAG with tier-based score boosting
- `hal/executor.py` — multi-host SSH (localhost→subprocess, remote→SSH)
- `hal/bootstrap.py` — initializes backends, builds dynamic system prompt
- `hal/tools.py` — tool definitions and dispatch
- `hal/memory.py` — SQLite session store with poison detection (CJK leaks)
- `hal/sanitize.py` — strips LLM hallucinations from responses

## Testing

- All tests offline — mock Ollama, vLLM, pgvector. Exception: `test_intent.py`.
- Test doubles in `tests/conftest.py`: `ScriptedLLM`, `ScriptedExecutor`,
  `FakeClassifier`, `StubKB`, `StubProm`. Check before creating new mocks.
- Property-based testing via Hypothesis (see `test_judge_properties.py`).
- Coverage ratchet: threshold auto-uplifts via `make ratchet`, never decreases.

## Commit conventions

Conventional Commits enforced by commitlint: `feat:`, `fix:`, `docs:`,
`refactor:`, `test:`, `chore:`, `ci:`, `perf:`, `build:`, `revert:`.
Subject: max 72 chars, lowercase start, no trailing period.
AI-assisted commits require a `Co-Authored-By:` trailer.

## Where to find things

> **Assume docs may be stale.** Verify claims against code when in doubt.

- **Current project state:** memory/SUMMARY.md — AI-maintained, read at session start
- **Architecture claims:** ARCHITECTURE.md (verify against code)
- **Deploy, .env, systemd, known traps:** OPERATIONS.md
- **Dev workflow, tests, git conventions:** CONTRIBUTING.md
- **Audit findings (72 verified):** docs/planning-pack/audit-findings.md
- **Project history and decisions:** notes/README.md (index)
