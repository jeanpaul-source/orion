# Project Summary

> Last updated: 2026-03-14 by AI

## Status

Active branch: `main`. All layers operational.

HAL runs in Docker container (`orion`) on the-lab (192.168.5.10),
using a pre-built image from `ghcr.io/jeanpaul-source/orion:latest`.
HTTP server + Telegram bot via supervisord inside container.
Harvest + watchdog run on host venv (need direct host access).

Three defense layers: Judge (software) → hal-svc SSH service account
(OS permissions) → container boundary (isolation).

## Architecture (condensed)

Query → IntentClassifier (embedding similarity, threshold 0.65) →

- `conversational` → single LLM call, no tools, no KB
- everything else → `run_agent()` — 8-iteration tool loop, KB + Prometheus pre-seeded

Chat: VLLMClient → vLLM (Qwen2.5-32B-Instruct-AWQ, port 8000).
Embeddings: OllamaClient → Ollama (nomic-embed-text, port 11434, CPU-only).
Judge gates every action (tier 0–3). KB: pgvector, harvested nightly.
Interfaces: REPL, HTTP `/chat`, Web UI, Telegram bot.

## Tools

8 core: `search_kb`, `get_metrics`, `get_trend`, `run_command`, `read_file`,
`list_dir`, `write_file`, `run_code`.
Optional: `web_search` (requires `TAVILY_API_KEY`).
Multi-host: `run_command`, `read_file`, `list_dir`, `write_file` accept
`target_host` — `ExecutorRegistry` resolves via `EXTRA_HOSTS` env var.
`run_code` runs Python in sandboxed Docker container (no network, read-only,
stdlib only); Judge tier 2.

## Observability

- Structured JSON logging with session/trace correlation
- OTel tracing → Grafana Tempo (OTLP HTTP port 4318)
- Prometheus Pushgateway metrics → Grafana dashboard
- Audit log at `~/.orion/audit.log`

## Memory

SQLite sessions at `~/.orion/memory.db` with poison-turn filter and
30-day pruning (TURN_WINDOW=40). `/remember` facts stored in pgvector.

## Recent changes

- 2026-03-14: Session 5 — dependency consistency & polish (PR #38)
  - CI + Makefile use pip-sync with lock files (F-10, F-19)
  - Dependabot auto-merge workflow for patch/minor updates (F-11)
  - Shared .vscode/settings.json tracked in git (F-20)
  - Lock file constraint added (-c) to prevent cross-file version conflicts
- 2026-03-14: Image-based deploys via GHCR (PRs #33, #34) — build workflow + deploy switch
- 2026-03-13: AI context restructure — slimmed instruction files, created memory/SUMMARY.md
- 2026-03-11: Instruction audit completed (notes/2026-03-11-instruction-audit.md)
- 2026-03-08: CD workflow added — auto-deploy to lab on main merge

## Known issues

- Production code audit findings (P0-P2) tracked in notes/audit-findings.md — not yet fixed
- System prompt contains hardcoded hardware specs (ROADMAP.md Path C item 1)
- Judge patterns are Python literals, not externalized (ROADMAP.md Path C item 2)
- F-21, F-08, F-09 resolved by image-based deploys (PR #34)

## Active decisions

- Risk-proportional proposal mode under consideration (audit finding C6) —
  formal proposals for high-risk changes, simple explain-and-proceed for low-risk
- See notes/README.md for full decision history

## What's next

- Automation guardrails plan complete (all 5 sessions merged)
- Fix P0 audit findings (sandbox security, SSRF TOCTOU)
- Fix P1 audit findings (silent error swallowing, trust Evolution edge cases)
- Path C architectural backlog (template system prompt, externalize Judge patterns)
