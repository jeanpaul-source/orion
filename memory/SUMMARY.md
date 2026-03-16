# Project Summary

> Last updated: 2026-03-15 by AI (1E audit re-verified)

## Status

Active branch: `main` (1176 tests passing). All layers operational.

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
Judge gates every action (tier 0–3). KB: pgvector (thousands of chunks), harvested nightly.
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

## Phase 1 Structured Audit — VERIFIED

Planning pack at `docs/planning-pack/` (5 files).
Living findings file: `docs/planning-pack/audit-findings.md` (72 findings, all verified).

**Workflow note:** Original delegated-chat workflow abandoned after 1E caught
confabulating. All findings verified by coordinator chat reading source files
directly with tool-call evidence. No UNVERIFIED findings remain.

### Audit progress

| Sub | Scope | Status |
| --- | --- | --- |
| 1A | Safety & Security | 12 findings — VERIFIED |
| 1B | Control-plane & Routing | 11 findings — VERIFIED |
| 1C | Knowledge & Retrieval | 12 findings — VERIFIED |
| 1D | Runtime & Deployment | 20 findings — VERIFIED (6 new from code read) |
| 1E | Observability & Trust | 15 findings — VERIFIED (10 new from full 8-file audit) |
| 1F | Docs & Prompt Drift | 2 findings — VERIFIED (1 new from direct audit) |

### Findings summary

72 active findings: 7 HIGH, 26 MED, 39 LOW.
Dropped: F-21, F-32, F-39, F-49 (confabulated), F-70, F-78. F-74 merged into F-47.
Resolved: F-71 (watchdog interval corrected in SUMMARY.md).

HIGH (7):

- F-14: Missing `--cap-drop ALL` in sandbox Docker flags
- F-15: Missing `--user` runtime flag in sandbox
- F-56: Non-atomic clear-then-insert in harvest (data loss window)
- F-65: Partial harvest clears all lab-state rows
- F-85: `HAL_WEB_TOKEN` defaults to "" — auth silently disabled on LAN
- F-102: Watchdog metric alerts mark cooldown even when ntfy fails — silent alert loss
- F-103: Watchdog simple alerts have same silent-loss bug as F-102

Full details with line citations: `docs/planning-pack/audit-findings.md`.

## Recent changes

- 2026-03-15: 1E audit re-verified — 10 new findings (F-102–F-111), 3 existing
  findings line-corrected. Two HIGH findings: watchdog silently loses alerts when
  ntfy is unreachable (F-102/F-103). Total now 72 findings (7 HIGH, 26 MED, 39 LOW).
- 2026-03-15: Phase 1 audit — 62 findings verified with line citations.
  1B re-verified (F-39 dropped, F-90–F-93 added).
  1C re-verified (F-59 restored, F-94–F-95 added).
  1D re-verified — 8 line-number corrections, 6 new findings (F-96–F-101).
  Key 1D additions: Dockerfile uses requirements.txt not lock file (F-100),
  supervisor unpinned (F-101), 17 undocumented env vars (F-73 expanded).
  4 new findings from direct 1E/1F audits (F-86–F-89).
  Delegated chat workflow abandoned after 1E caught confabulating.
  All verification now done by coordinator chat with direct code reads.
- 2026-03-14: Session 5 — dependency consistency & polish (PR #38)
  - CI + Makefile use pip-sync with lock files
  - Dependabot auto-merge workflow for patch/minor updates
  - Shared .vscode/settings.json tracked in git
- 2026-03-14: Image-based deploys via GHCR (PRs #33, #34)
- 2026-03-13: AI context restructure — slimmed instruction files, created memory/SUMMARY.md
- 2026-03-08: CD workflow added — auto-deploy to lab on main merge

## Known issues

- Phase 1 findings (59 open) — see `docs/planning-pack/audit-findings.md`
- System prompt hardcodes "~19,900 doc chunks" (F-89) and hardware specs (ROADMAP.md Path C item 1)
- Judge patterns are Python literals, not externalized (ROADMAP.md Path C item 2)

## Active decisions

- Delegated `@workspace` audit chats ABANDONED — unreliable for judgment tasks
- All audit work done directly by coordinator chat with tool-call evidence
- See notes/README.md for full decision history

## What's next

1. Transition to Phase 2 (planning) — prioritize and group findings into fix PRs
2. Fix HIGH findings first (sandbox hardening, harvest atomicity, auth default)
3. Address MED findings in logical batches
