# Orion — Copilot Instructions

Orion is a homelab AI assistant (HAL). It runs a local LLM (vLLM), monitors
infrastructure via Prometheus, and executes operations through a tiered approval
system (the Judge). Every action is audited.

## Critical constraints

Violating any of these breaks the system. Do not change them without discussion.

- **Ollama is embeddings-only.** `OLLAMA_NUM_GPU=0` prevents VRAM OOM on the RTX 3090 Ti.
- **Prometheus is port 9091.** Port 9090 is Cockpit — a different service.
- **The Judge has no bypass.** Every tool call goes through `judge.approve()`.
- **`main` is always deployable.** The server auto-deploys from `main` on merge.

## Key commands

```bash
make check        # lint + format + typecheck + test + doc-drift — run before every push
make test         # offline tests only (no Ollama needed)
make test-full    # full suite including intent classifier (requires Ollama)
```

## Where to find things

- **AI operating contract:** CLAUDE.md — read before any code change
- **Current project state:** memory/SUMMARY.md — AI-maintained, read at session start
- **Architecture and data flow:** ARCHITECTURE.md
- **Deploy, .env, systemd, known traps:** OPERATIONS.md
- **Dev workflow, tests, git conventions:** CONTRIBUTING.md
- **Roadmap and backlog:** ROADMAP.md
- **Project history and decisions:** notes/README.md (index)
