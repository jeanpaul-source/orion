# Project Summary

> Last updated: 2026-03-17 by AI (Pass 4 — SUMMARY audit against code)

## Status

Default branch: `main`. All tests passing (`make test` for current count). All layers operational.

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

Chat: VLLMClient → vLLM (model set by `CHAT_MODEL` in `hal/config.py`, default Qwen2.5-32B-Instruct-AWQ).
Embeddings: OllamaClient → Ollama (model set by `EMBED_MODEL`, default nomic-embed-text, CPU-only).
Judge gates every action (tier 0–3). KB: pgvector (thousands of chunks), harvested nightly.
Interfaces: REPL, HTTP `/chat`, Web UI, Telegram bot.

## Tools

See `TOOL_REGISTRY` in `hal/tools.py` for the canonical list.
Always-on tools cover KB search, Prometheus metrics/trends, file I/O,
command execution, URL fetching, security events, LAN scanning, and
health/recovery actions.
Optional: `web_search` (requires `TAVILY_API_KEY`), `run_code` (requires `sandbox_enabled`).
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

Planning pack at `docs/planning-pack/`.
Living findings file: `docs/planning-pack/audit-findings.md` (see file for current counts).

**Workflow note:** Original delegated-chat workflow abandoned after 1E caught
confabulating. All findings verified by coordinator chat reading source files
directly with tool-call evidence. No UNVERIFIED findings remain.

### Audit progress

| Sub | Scope | Status |
| --- | --- | --- |
| 1A | Safety & Security | VERIFIED |
| 1B | Control-plane & Routing | VERIFIED |
| 1C | Knowledge & Retrieval | VERIFIED |
| 1D | Runtime & Deployment | VERIFIED |
| 1E | Observability & Trust | VERIFIED |
| 1F | Docs & Prompt Drift | VERIFIED |

### Findings summary

See `docs/planning-pack/audit-findings.md` for current counts, severity
breakdown, and full details with line citations.
Dropped: F-21, F-32, F-39, F-49 (confabulated), F-70, F-78. F-74 merged into F-47.

## Recent changes

- 2026-03-17: Pass 4 — SUMMARY.md audited against code. Fixed stale tool count,
  findings count, test count. Replaced brittle hardcoded values with pointers
  to source-of-truth files. Model names now reference config vars.
- 2026-03-17: Docs audit pass 1–3 (PRs #46–#52): docs-auditor agent created,
  ARCHITECTURE.md aligned with code and made drift-resistant, instruction files
  modernized, OPERATIONS.md audited, README.md drift fixed.
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

- Phase 1 findings — see `docs/planning-pack/audit-findings.md` for open count and severity
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
