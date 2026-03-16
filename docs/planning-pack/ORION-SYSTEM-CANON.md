# ORION System Canon

Status: working canonical snapshot derived from uploaded docs/code and 2026 external guidance  
Purpose: one living document to keep architecture, runtime, and planned changes grounded

## How to use this file

This file is the canonical orientation document for Orion/HAL.
When code, runtime behavior, or operating assumptions change, update this file first or in the same change.
Other docs may explain or market the system, but this file is the current-system anchor.

Truth precedence:

1. Running system
2. Code
3. Docs

## System identity

Orion is a local-first, single-operator homelab control plane.
HAL is the reasoning layer inside Orion.

HAL is not just “a chatbot with tools.”
It is a trust-bounded infrastructure operator with:

- a tool-using agent loop
- a policy gate (Judge)
- harvested lab state in a vector-backed KB
- session memory in SQLite
- live metrics via Prometheus
- recovery/watchdog behaviors
- multiple user surfaces (REPL, HTTP/Web UI, Telegram)

## Core architecture

### Layer 1: Interfaces

- REPL / slash commands
- HTTP API and Web UI
- Telegram bot

### Layer 2: Routing

Current routing behavior is simple:

- conversational → fast one-call response path
- everything else → `run_agent()`

This is important: older docs may describe more separate paths, but the current bootstrap path has effectively collapsed health/fact/agentic into the full capable path.

### Layer 3: Agent loop

The current agent loop:

- pre-seeds KB context when strong semantic matches exist
- pre-seeds a live Prometheus snapshot
- limits iterations
- limits unique tool calls
- deduplicates repeated tool invocations
- forces a plain-text finish if the model loops
- writes only final clean turns to history

### Layer 4: Policy gate

Judge is the safety center of gravity.

It classifies:
- shell commands
- file reads/writes
- web fetches
- sandbox execution
- recovery actions

It enforces:
- safe read-only allowlists
- sensitive-path escalation
- git write blocking on the server
- shell evasion detection
- destructive-action confirmation
- trust evolution based on recorded outcomes

### Layer 5: Execution and runtime

Execution is split:

- vLLM → chat / reasoning / tool calling
- Ollama → embeddings only
- pgvector / PostgreSQL → semantic KB storage
- Prometheus → live metrics
- Dockerized Orion runtime + host access through constrained mounts / service account

### Layer 6: State and memory

- SQLite stores sessions and turns
- pgvector stores harvested + reference + memory docs
- poison responses are filtered before persistence
- old turns are pruned
- session windows are bounded

## Runtime contract

### Current deployment reality

The current runtime is Docker-first for Orion itself.

Observed deployment shape in compose:

- image: `ghcr.io/jeanpaul-source/orion:latest`
- container name: `orion`
- port 8087 exposed
- only writable mount is Orion state under `/home/jp/.orion`
- `.env`, infra configs, reference docs, Falco logs, `/etc`, and SSH key are mounted read-only
- `LAB_HOST=host.docker.internal`
- `LAB_USER=hal-svc`

This means the real operator boundary is:

Judge → hal-svc → container/runtime isolation

### LLM backend split

Current design intentionally separates:

- vLLM for chat
- Ollama for embeddings

This should remain load-bearing unless there is a measured reason to collapse it.

### Knowledge pipeline

The harvest pipeline currently collects:

- ground truth docs
- Docker containers
- live system state
- hardware summary
- config files
- selected systemd units
- static docs (including text/HTML/PDF-derived content)

Ingest currently:

- chunks at about 800 characters with overlap
- always clears/rebuilds live-state + ground-truth tiers
- incrementally updates reference docs via content hashes
- performs orphan cleanup for removed reference docs
- stores `doc_tier`

## Current invariants

These should stay true unless intentionally redesigned.

1. All meaningful actions go through Judge.
2. HTTP mode cannot execute tier 1+ actions because there is no interactive approval path.
3. HAL may not write to its own repo on the server.
4. Agent history should only persist final, sanitized assistant turns.
5. KB should remain tiered: ground-truth, reference, live-state, memory.
6. Sandbox execution must remain isolated and non-networked.
7. Tool execution must remain bounded by iteration and/or call caps.
8. Running-system truth outranks stale docs.
9. Any trust evolution logic must be explainable through the audit log.
10. System prompt text must not silently drift away from runtime reality.

## Known current drift

### Drift 1: deployment story
The codebase and runtime indicate Dockerized Orion deployment, but some prompt/document text still talks like `server.service` / `telegram.service` are the live primary deployment contract.

### Drift 2: routing story
Current bootstrap behavior effectively routes only conversational queries away from `run_agent()`.
Older descriptions that imply multiple rich handler paths are stale.

### Drift 3: trust evolution status
Trust evolution exists in the current code and roadmap.
Any doc that still frames it as “not built” is stale.

### Drift 4: prompt hardcoding
The system prompt still contains lab-specific literals that Path C explicitly says should be externalized.

## High-risk seams already identified

These are not speculative.

1. Sandbox hardening gaps
   - missing container hardening flags
   - cleanup path bypasses Judge
   - host temp-file permissions need tightening

2. Web fetch protections
   - TOCTOU DNS rebinding gap in `fetch_url()`
   - IPv6 private-address sanitization gap in web search query cleaning

3. Audit / outcome integrity
   - direct `/run` usage does not fully contribute to trust data
   - trust loading degrades silently on audit-log read failure

4. Observability blind spots
   - some failures degrade silently or too quietly
   - health/watchdog paths need stronger diagnostics

## Architectural direction

The right next direction is not “add more agent magic.”

It is:

1. close P0/P1 safety and correctness gaps
2. reconcile runtime truth with prompt/docs
3. externalize site-specific hardcoding
4. improve observability and eval quality
5. make work resumable across constrained contexts and long-running changes

## Living-document maintenance rule

When reality changes:

- update this file in place
- do not append session logs
- note what changed in current-state sections
- keep a short “known drift” section only for unresolved mismatches

Recommended companion files:
- `ORION-2026-BEST-PRACTICES-GAP-ANALYSIS.md`
- `ORION-IMPROVEMENT-BLUEPRINT.md`
- `ORION-VSCODE-COPILOT-FRAMEWORK.md`
