# Orion — Copilot Instructions

Orientation layer for AI assistants. For depth, read the dedicated docs.

## Rules

1. **Explain before acting.** State root cause (not symptom), proposed change,
   why it's correct long-term, and whether you KNOW or are GUESSING. Wait for approval.
2. **One change at a time.** Make one change, verify it works (`make check`), then
   move to the next.
3. **No band-aids.** If adding a flag or workaround, stop and ask whether the
   underlying component is actually wrong.
4. **Feature branches.** Never push directly to `main`. Create a branch, open a PR,
   let CI pass, then merge.

## Reference docs

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Component map, data flow, design decisions |
| [OPERATIONS.md](../OPERATIONS.md) | Deploy, `.env` reference, systemd units, known traps |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Dev workflow, tests, linting, git workflow, eval |
| [ROADMAP.md](../ROADMAP.md) | What's done, what's next, end-state vision |
| [CLAUDE.md](../CLAUDE.md) | AI operating contract — required format before every code change |

## Key commands

```bash
make check      # runs ALL quality gates (lint, format, typecheck, test, doc-drift)
make test       # offline tests only (no Ollama needed)
make lint       # ruff check
make format     # ruff format
make typecheck  # mypy hal/
```

## Key files

| File | Role |
|---|---|
| `hal/agent.py` | Agentic loop (`MAX_ITERATIONS=8`), handlers |
| `hal/bootstrap.py` | `dispatch_intent()`, system prompt |
| `hal/config.py` | Dataclass + `.env` loader |
| `hal/intent.py` | Embedding classifier; tune `EXAMPLES` and `THRESHOLD` here |
| `hal/judge.py` | Policy gate; tier 0-3; never bypass |
| `hal/llm.py` | `VLLMClient` (chat) and `OllamaClient` (embeddings only) |
| `hal/server.py` | FastAPI `/chat` + `/health` + Web UI |
| `hal/sanitize.py` | Response sanitiser — strips tool-call artefacts + CJK leaks |
| `hal/security.py` | Falco, Osquery, ntopng, Nmap workers |
| `hal/web.py` | `web_search()`, `fetch_url()` with SSRF protection |
| `harvest/` | KB pipeline: collect → chunk → embed → upsert to pgvector |
| `tests/` | 1176+ offline tests; intent tests require reachable Ollama |
