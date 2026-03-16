# HAL — Ideal System Plan

> Created: 2026-03-14
> Status: Draft — not yet validated
> Branch: `docs/ideal-system-plan`

A living implementation plan for closing the gap between HAL's current state and
the Ideal System vision. Each phase is self-contained, sequenced by dependency,
and written so an AI-assisted coding session can pick up any section and work on
it with full context.

**How to use this document:** Read the vision summary to understand the target.
Read the current-state assessment to understand where we are. Work through phases
in order — each phase lists its prerequisites, deliverables, and acceptance
criteria. Update the status checkboxes as work lands on `main`.

**How to update this document:** Edit in place. Do not append session logs or
changelogs — git history tracks that. When a deliverable ships, check the box
and update the status line at the top. When a phase completes, mark it done and
note the date.

---

## Table of Contents

- [Vision Summary](#vision-summary)
- [Current-State Assessment](#current-state-assessment)
- [Phase 0 — Foundation Fixes](#phase-0--foundation-fixes)
- [Phase 1 — Unified Session Model](#phase-1--unified-session-model)
- [Phase 2 — VS Code Integration](#phase-2--vs-code-integration)
- [Phase 3 — Repo and Project Awareness](#phase-3--repo-and-project-awareness)
- [Phase 4 — Structured Memory](#phase-4--structured-memory)
- [Phase 5 — Async Delegation](#phase-5--async-delegation)
- [Phase 6 — Proactive Awareness](#phase-6--proactive-awareness)
- [Principles for Implementation](#principles-for-implementation)
- [Open Questions](#open-questions)

---

## Vision Summary

HAL is a persistent, local-first intelligence that becomes part of personal
infrastructure. Seven properties define the Ideal System:

1. **One identity.** One system, accessible from multiple surfaces (terminal,
   browser, VS Code, Telegram). The interface changes; HAL does not. Same
   memory, same awareness, same continuity everywhere.

2. **Local-first.** Identity, memory, and core reasoning live on local hardware.
   External services are capability extensions, not dependencies.

3. **Fits existing workflow.** HAL lives alongside VS Code, Git, terminals, and
   remote development. No mode-switching, no re-orientation.

4. **Knows your world.** Genuine awareness of repos, systems, projects, and
   patterns — built from real observation, not simulated. Updates automatically.
   Surfaces relevant context without being asked.

5. **Growing capabilities.** Starts as observer/advisor. Earns executor
   privileges through trust. Eventually acts within defined boundaries without
   explicit prompting. The identity stays the same; capability grows around it.

6. **Durable over time.** Buildable and maintainable by someone using
   AI-assisted tools — not by a full-time engineer. Every layer pulls its
   weight. Complexity stays honest.

7. **Ambient presence.** When working, HAL is just there — context is ready,
   questions are already answered, delegation comes back done. Not a tool you
   use; a part of your environment that thinks.

---

## Current-State Assessment

Honest ratings based on a full codebase review against the Ideal System vision.
Each rating references the specific capabilities that exist and the specific
gaps that remain.

### One identity (~60%)

**What exists:**

- Strong identity in system prompt (`hal/bootstrap.py`)
- All interfaces (REPL, HTTP, Telegram, Web UI) converge on `dispatch_intent()`
- Session memory persists in SQLite at `~/.orion/memory.db`

**Gaps:**

- No cross-interface session continuity — Web UI uses `localStorage`, REPL uses
  SQLite, Telegram creates its own sessions. These are parallel HALs.
- The `/resume` command in the REPL only knows about REPL sessions.
- No unified concept of "my ongoing conversation with HAL" that spans surfaces.

### Local-first (~90%)

**What exists:**

- Everything runs on the-lab — vLLM, Ollama, pgvector, the full stack
- No cloud dependencies for core function (Tavily is optional)
- All data stays local (`~/.orion/`, pgvector on localhost)

**Gaps:**

- No degraded-mode operation when the lab is unreachable from elsewhere
- SSH tunnel system (`hal/tunnel.py`) helps but still requires connectivity

**Verdict:** Essentially delivered.

### Fits existing workflow (~35%)

**What exists:**

- Terminal REPL, Web UI, Telegram — three working surfaces
- HTTP API enables arbitrary integrations

**Gaps:**

- No VS Code presence at all — no extension, no MCP server, no sidebar
- No project awareness — HAL knows infrastructure, not development work
- No "pick up where you left off" for coding context

**Verdict:** Biggest gap. HAL is absent from the primary workspace.

### Knows your world (~45%)

**What exists:**

- Deep infrastructure awareness via nightly harvest into pgvector (~17,250+
  chunks, 18 categories)
- Live system state via Prometheus queries
- Security posture via Falco, Osquery, ntopng
- `knowledge/LAB_ENVIRONMENT.md` ground-truth document

**Gaps:**

- No repo awareness — no indexing of Git repos, commit histories, branches,
  open issues, or recent changes
- No project tracking — no concept of "what JP is working on"
- No pattern detection beyond threshold alerting — no "disk growing 2%/week,
  you'll hit 85% in 3 weeks"
- No cross-system event correlation
- Memory is thin — chat turns only (SQLite, 40-turn window, 30-day prune).
  `/remember` stores facts in pgvector but there is no structured memory of
  decisions, outcomes, or project context

### Growing capabilities (~55%)

**What exists:**

- Trust model works: tiers 0–3, auto-promote/demote via outcome tracking
- Recovery playbooks with circuit breakers (7 playbooks, watchdog-triggered)
- Sandboxed code execution in disposable Docker containers
- Multi-host execution via `ExecutorRegistry`

**Gaps:**

- Earned autonomy applies only to infrastructure ops — no trust model for
  "HAL can push commits" or "HAL can respond to this alert type without asking"
- No background initiative — watchdog checks thresholds, but HAL does not
  *think* in the background
- No async delegation — every interaction is synchronous request-response
  (agentic loop runs up to 8 iterations, then must respond)

### Durability (~70%)

**What exists:**

- Clean architecture with documented data flow (`ARCHITECTURE.md`)
- Docker Compose deployment with image-based deploys via GHCR
- `make check` runs lint + format + typecheck + test + doc-drift
- ~1176 offline tests, eval baselines, 87% coverage floor

**Gaps:**

- System prompt in `get_system_prompt()` is a large f-string with hardcoded
  hardware specs — ROADMAP.md Path C item 1
- Judge patterns are Python literals — ROADMAP.md Path C item 2
- Codebase is tightly coupled to one specific lab topology
- Dependent on Qwen2.5-32B-AWQ behavior (known identity override issues)

### Ambient presence (~25%)

**What exists:**

- Multiple access surfaces exist and are functional

**Gaps:**

- HAL is a separate destination, not an ambient presence in your workspace
- No awareness of what file you have open, what project you are in, or
  what your current Git state looks like
- Context must be manually provided or explicitly queried

**Verdict:** Furthest from delivery. This is the experiential goal that
everything else builds toward.

---

## Phase 0 — Foundation Fixes

> **Vision alignment:** Durability, Growing capabilities
> **Prerequisites:** None
> **Estimated scope:** Small — focused fixes to existing code

Before building new capabilities, fix the known issues that would undermine
them. These are tracked in existing documents but not yet resolved.

### Deliverables

- [ ] **P0: Sandbox security fixes** — findings from `notes/audit-findings.md`
- [ ] **P0: SSRF TOCTOU fix** — race condition in URL validation
- [ ] **P1: Silent error swallowing** — audit findings on lost exceptions
- [ ] **P1: Trust evolution edge cases** — audit findings on promotion/demotion
- [ ] **Path C item 1: Template the system prompt** — externalize hardcoded
      hardware specs from `hal/bootstrap.py:get_system_prompt()`
- [ ] **Path C item 2: Externalize Judge patterns** — move site-specific
      entries (e.g., `_SENSITIVE_PATHS`) to config

### Acceptance criteria

- All P0 and P1 findings from `notes/audit-findings.md` are resolved
- System prompt reads lab-specific values from config or KB, not literals
- At least `_SENSITIVE_PATHS` site-specific entries come from `.env`
- `make check` passes after each change
- No new test regressions

### Key files

- `hal/sandbox.py` — sandbox security
- `hal/web.py` — SSRF/URL validation
- `hal/bootstrap.py` — system prompt templating
- `hal/judge.py` — pattern externalization
- `notes/audit-findings.md` — full finding list

---

## Phase 1 — Unified Session Model

> **Vision alignment:** One identity
> **Prerequisites:** None (can run in parallel with Phase 0)
> **Estimated scope:** Medium — touches memory, server, Web UI, Telegram

The goal is that a conversation with HAL is a conversation with HAL, regardless
of which surface you started it from. You can start in the Web UI, continue in
the terminal, and pick up later from Telegram — and HAL remembers all of it.

### Current state

- `hal/memory.py` — `MemoryStore` uses SQLite, keyed by `session_id`
- REPL sessions: `session_id` is `session-{timestamp}` — stored in SQLite
- Web UI sessions: `session_id` is `web-{timestamp}` — stored in browser
  `localStorage`, sent to `/chat` endpoint per request
- Telegram sessions: `session_id` is `tg-{chat_id}` — created per chat

These are disconnected. No surface can see another surface's history.

### Deliverables

- [ ] **Server-side session storage for all surfaces** — Web UI and Telegram
      should use the same SQLite-backed `MemoryStore` that the REPL uses. Remove
      `localStorage` as the source of truth for Web UI sessions.
- [ ] **Session listing API** — `GET /sessions` endpoint that returns all
      sessions with metadata (surface, last active, turn count). Web UI sidebar
      reads from this instead of `localStorage`.
- [ ] **Session resume across surfaces** — any surface can resume any session
      by ID. The REPL's `/resume` command and the Web UI's sidebar both query
      the same session store.
- [ ] **"Current session" concept** — a default session that all surfaces
      contribute to unless a specific session is selected. This is the "one HAL"
      experience — you do not need to manage sessions explicitly.

### Acceptance criteria

- Start a conversation in the Web UI. Switch to the REPL. Run `/resume` and see
  the Web UI turns in context. Continue the conversation. Switch back to the
  Web UI and see the REPL turns.
- Telegram turns appear in the same session store and are visible from other
  surfaces.
- Web UI no longer stores conversation data in `localStorage` (session IDs may
  still be cached for quick access, but the source of truth is server-side).
- Existing REPL and Telegram functionality is not degraded.

### Key files

- `hal/memory.py` — `MemoryStore` (needs session listing, cross-surface resume)
- `hal/server.py` — new `/sessions` endpoint, session routing changes
- `hal/static/app.js` — replace `localStorage` session management with API calls
- `hal/telegram.py` — adapt to use shared session model
- `hal/main.py` — REPL `/resume` to query unified session store

### Open questions

- Should "current session" be a named singleton (e.g., `default`) or the
  most-recently-active session?
- Should sessions have explicit "close" semantics, or just age out?
- How to handle the Web UI being offline (no server) — graceful degradation vs.
  hard requirement on server connectivity?

---

## Phase 2 — VS Code Integration

> **Vision alignment:** Fits existing workflow, Ambient presence
> **Prerequisites:** Phase 1 (unified sessions, so VS Code shares the same
> memory as other surfaces)
> **Estimated scope:** Medium-large — new component, new protocol

This is the single highest-leverage item. VS Code is where the work happens.
HAL needs to be present there.

### Approach options

Two viable options exist. They are not mutually exclusive but should be
sequenced:

1. **MCP server** — HAL exposes an MCP (Model Context Protocol) server that
   VS Code AI features (Copilot, Copilot Chat) can use as a context provider.
   This gives HAL a presence inside the AI assistant you already use. Lower
   effort, leverages existing infrastructure.

2. **VS Code extension / chat participant** — A custom extension that provides
   a HAL sidebar, chat participant, or command palette integration. Richer UX,
   more control, higher effort.

### Deliverables — MCP server (recommended first step)

- [ ] **MCP server module** — new `hal/mcp.py` (or standalone entrypoint) that
      speaks the MCP protocol over stdio or SSE, backed by HAL's existing
      `/chat` endpoint and tools
- [ ] **Resource providers** — expose KB search results, session memory, and
      system health as MCP resources that VS Code can reference
- [ ] **Tool exposure** — expose HAL's tools (search_kb, get_metrics, run_command,
      etc.) as MCP tools callable from VS Code chat
- [ ] **Session integration** — MCP interactions use the unified session model
      from Phase 1, so VS Code conversations are visible from other surfaces

### Deliverables — VS Code extension (later)

- [ ] **Chat participant** — `@hal` participant in VS Code Chat that routes
      queries to the HAL backend
- [ ] **Context awareness** — extension reads the current file, Git state, and
      project structure and injects it into the HAL query automatically
- [ ] **Status bar** — shows HAL connectivity and last system health status

### Acceptance criteria (MCP server)

- VS Code Copilot Chat can use HAL as a context source via MCP
- `@hal what's the CPU at?` in VS Code Chat returns a live metric answer
- `@hal search_kb docker compose` returns relevant KB results
- MCP session appears in the unified session store

### Key references

- [MCP specification](https://modelcontextprotocol.io/specification)
- `hal/server.py` — existing HTTP API to build on
- `hal/tools.py` — tool definitions that need MCP schema wrappers

### Open questions

- MCP transport: stdio (simpler, needs process management) vs. SSE (can reuse
  the existing HTTP server)?
- Does the MCP server run inside the Docker container alongside the HTTP
  server, or as a separate process?
- Authentication model for MCP — reuse `HAL_WEB_TOKEN` or separate?

---

## Phase 3 — Repo and Project Awareness

> **Vision alignment:** Knows your world
> **Prerequisites:** Phase 0 (Path C — so the system prompt can reference
> repo context dynamically)
> **Estimated scope:** Medium — extends harvest pipeline, adds new collectors

HAL should know your repos the way it knows your infrastructure. Which repos
exist, what is in them, what changed recently, what is in progress, what
patterns repeat.

### Deliverables

- [ ] **Git repo collector** — new harvest collector that indexes Git
      repositories. For each configured repo, collect: README, recent commits
      (last N days), current branches, open PR titles (if GitHub API available),
      file tree structure. Ingest into pgvector under a `repos` category.
- [ ] **Commit activity summarizer** — a tool or harvest step that produces a
      natural-language summary of recent activity per repo ("3 commits this week:
      added MCP server, fixed sandbox security, updated docs").
- [ ] **Project state model** — a lightweight structure (JSON file or DB table)
      that tracks: which repos are active, what the current focus is, what is
      blocked, what was last touched when. Could be seeded manually via
      `/project` commands and enriched automatically from Git activity.
- [ ] **`get_repo_activity` tool** — HAL tool that returns recent Git activity
      for a named repo, Judge-gated at tier 0 (read-only).
- [ ] **Cross-repo awareness in system prompt** — the system prompt (or KB
      pre-seed) includes a summary of active projects and recent changes, so
      HAL can reference them without being asked.

### Acceptance criteria

- Ask HAL "what changed in orion this week?" and get an accurate answer from
  indexed Git data, not a generic "I don't know."
- Ask HAL "what am I working on?" and get a response based on recent commit
  activity and project state.
- Harvest includes repo data in its nightly run.
- New data appears in `search_kb` results when querying repo-related topics.

### Key files

- `harvest/collect.py` — add new collector functions
- `harvest/ingest.py` — handle new `repos` category
- `hal/tools.py` — register `get_repo_activity` tool
- `hal/bootstrap.py` — inject project context into system prompt or pre-seed

### Open questions

- Which repos to index? All repos under a configured directory, or an explicit
  list in `.env`?
- How deep to go — index actual source code, or just metadata (commits,
  branches, READMEs)?
- GitHub API integration — use the existing `GITHUB_TOKEN` for PR/issue data,
  or keep it Git-local only?
- How often to re-index — nightly with harvest, or more frequently?

---

## Phase 4 — Structured Memory

> **Vision alignment:** Knows your world, One identity
> **Prerequisites:** Phase 1 (unified session model)
> **Estimated scope:** Medium — new memory layer alongside existing SQLite/pgvector

Current memory is chat turns (SQLite, 40-turn window, 30-day prune) plus
`/remember` facts in pgvector. The Ideal System needs richer memory: decisions,
outcomes, incident timelines, project context, and patterns that persist
across sessions and grow over time.

### Deliverables

- [ ] **Decision log** — structured records of significant decisions: what was
      decided, why, when, what the alternatives were. Queryable by topic.
      Could be a pgvector collection with structured metadata, or a dedicated
      SQLite table. Populated via explicit `/decide` command or automatically
      when HAL detects a decision in conversation.
- [ ] **Incident timeline** — when something goes wrong and gets resolved,
      store a structured record: what happened, when, what was tried, what
      worked. The `/postmortem` command already generates this — the missing
      piece is persisting the output in a queryable store.
- [ ] **Session summaries** — at session end (or on request), HAL generates a
      brief summary of what was discussed and stores it. Future sessions can
      load the summary instead of the full turn history, allowing long-term
      context without unbounded token growth.
- [ ] **Automatic context surfacing** — when a new query arrives, HAL checks
      the structured memory for relevant decisions, incidents, and project
      context, and injects them alongside KB results. This is the "HAL already
      knows" experience.

### Acceptance criteria

- Come back after two weeks and ask "what did we decide about the Judge
  externalization?" — HAL retrieves the decision record and answers accurately.
- After an incident, ask "what happened last time vLLM crashed?" — HAL retrieves
  the incident timeline.
- Session summaries are generated and stored automatically (or on `/summarize`).
- Relevant memory is surfaced without explicit queries — it shows up in context
  when it is relevant.

### Key files

- `hal/memory.py` — extend with decision/incident/summary stores
- `hal/bootstrap.py` — inject structured memory into pre-seed context
- `hal/postmortem.py` — persist output to structured memory
- `hal/main.py` — `/decide`, `/summarize` commands

### Open questions

- Storage backend for structured memory — extend SQLite? Separate pgvector
  collection? Both?
- How to detect "a decision was made" automatically vs. requiring explicit
  commands?
- Memory deduplication — how to avoid storing the same decision multiple times
  across sessions?
- Retention policy — decisions persist forever? Incidents age out? What about
  session summaries?

---

## Phase 5 — Async Delegation

> **Vision alignment:** Growing capabilities
> **Prerequisites:** Phase 1 (unified sessions — so async results can be
> delivered to any surface), Phase 3 (repo awareness — so there is meaningful
> work to delegate)
> **Estimated scope:** Large — new architectural component (task queue)

Today every interaction is synchronous: you ask, HAL thinks (up to 8 agentic
iterations), HAL responds. The Ideal System supports handing HAL a task and
getting notified when it is done, without waiting.

### Deliverables

- [ ] **Task queue** — a persistent queue (SQLite table or similar) where tasks
      can be submitted, tracked, and completed. Each task has: description,
      status (queued / running / done / failed), result, submitted_at,
      completed_at, session_id.
- [ ] **Background worker** — a process or thread that picks tasks off the queue
      and runs them through the existing agentic loop. Reuses `run_agent()` —
      the difference is that results go to the queue instead of stdout.
- [ ] **Notification on completion** — when a background task finishes, notify
      the user via their preferred channel (ntfy, Telegram, or queued for next
      session). Reuse `hal/notify.py` or the existing ntfy integration in
      `hal/watchdog.py`.
- [ ] **`/delegate` command** — submit a task to the background queue from any
      surface. Example: `/delegate summarize what changed in orion this week`.
- [ ] **Task status and results** — `/tasks` command (and API endpoint) to list
      pending/completed tasks and retrieve results.

### Acceptance criteria

- `/delegate summarize this repo` returns immediately with a task ID.
- The task runs in the background using the agentic loop.
- On completion, a notification is sent (ntfy or Telegram).
- `/tasks` shows the task as completed with the summary result.
- The result is associated with the session and visible from any surface.

### Key files (new and existing)

- New: `hal/tasks.py` — task queue model and worker
- `hal/agent.py` — `run_agent()` needs to support outputting to a queue
- `hal/main.py` — `/delegate`, `/tasks` commands
- `hal/server.py` — `POST /tasks`, `GET /tasks` endpoints
- `hal/watchdog.py` — reference for existing background notification patterns

### Open questions

- Concurrency model — separate process, thread, or asyncio task?
- Resource limits — how many background tasks can run concurrently? (LLM is
  single-GPU, so probably 1 at a time.)
- Should delegated tasks have their own Judge tier, or reuse the surface's
  tier? (e.g., a task delegated from Telegram should probably not auto-approve
  tier 1 actions.)
- How to handle tasks that need human approval mid-execution (a delegated task
  hits a tier 2 action) — queue the approval request? Skip and report? Fail?

---

## Phase 6 — Proactive Awareness

> **Vision alignment:** Ambient presence, Knows your world
> **Prerequisites:** Phase 3 (repo awareness), Phase 4 (structured memory),
> Phase 5 (async delegation — so HAL can act on insights without blocking)
> **Estimated scope:** Large — this is the most architecturally ambitious phase

This is the endgame: HAL notices things you need to know and surfaces them
without being asked. Not just threshold alerts (which the watchdog already
does), but synthesized insights from across systems, repos, and history.

### Deliverables

- [ ] **Background analysis loop** — a periodic process (like the watchdog but
      for higher-level thinking) that reviews recent changes across all data
      sources and generates insights. Examples: "disk usage trending up on
      /docker — projecting 85% in 3 weeks," "you haven't committed to project X
      in 2 weeks," "the same Falco alert has fired 4 times this month."
- [ ] **Cross-system correlation** — connect events across data sources into
      coherent narratives. "Grafana restarted at 2am → monitoring compose
      updated at 1:55am → harvest re-indexed at 3am" becomes one story, not
      three unrelated log entries.
- [ ] **Insight delivery** — insights are delivered proactively via the user's
      preferred channel (morning digest via Telegram, or surfaced in the next
      interactive session). Not interrupts — batched, prioritized, and
      dismissable.
- [ ] **Pattern learning** — over time, HAL learns which insights the user
      finds valuable (acted on, asked about) vs. noise (dismissed, ignored) and
      adjusts what it surfaces. This closes the feedback loop on proactive
      awareness.

### Acceptance criteria

- HAL sends a weekly digest of notable changes across infrastructure and repos
  without being asked.
- If a metric trend is concerning, HAL surfaces a projection ("at this rate, X
  will happen in Y days") — not just "threshold exceeded."
- Insights reference correlated events, not just individual data points.
- Insight quality improves over time (fewer dismissed, more acted on).

### Key files

- `hal/watchdog.py` — existing periodic check framework to extend
- `hal/prometheus.py` — trend data for projections
- `hal/postmortem.py` — reference for cross-source synthesis
- New: `hal/insights.py` — background analysis and insight generation

### Open questions

- How to distinguish "insight" from "alert"? Alerts are urgent and threshold-
  based. Insights are informational and pattern-based. Different delivery
  channels? Different urgency levels?
- How much LLM inference budget for background analysis? Each analysis cycle
  costs GPU time that competes with interactive use.
- How to avoid insight fatigue — too many low-value observations make the user
  ignore all of them.

---

## Principles for Implementation

These are not aspirational — they are constraints that apply to every phase.
They come from the project's existing operating contract (CLAUDE.md,
CONTRIBUTING.md) and from the Ideal System vision itself.

### One change at a time

Each deliverable is one commit (or a small series of commits). Each commit
passes `make check`. No stacking unverified changes. This is the existing
CLAUDE.md rule and it does not change.

### Test before trust

Every new capability gets tests before it is considered delivered. The project
has ~1176 offline tests and an 87% coverage floor. New code maintains or
increases that floor. If a phase does not have clear testable boundaries, break
it down further.

### Explain before acting

Before implementing any deliverable, state: what the problem is, what the
proposed change is, why it is correct long-term, and whether the approach is
known-good or a guess. This is the CLAUDE.md rule. It applies to AI-assisted
implementation sessions.

### The Judge has no bypass

All new tools and capabilities go through `judge.approve()`. There is no
`force=True`. If a new feature needs a new tier classification, add it to the
Judge explicitly. This is a load-bearing constraint.

### Local-first is not negotiable

New features must not introduce cloud dependencies for core function. External
services (GitHub API, web search) are optional enhancements. Core identity,
memory, and reasoning stay local. If a feature requires a cloud service to
function at all, it must have a useful degraded mode without it.

### Complexity must earn its place

Before adding a new component, ask: does this pull its weight? Could the
existing architecture handle this with a smaller change? The Ideal System
vision explicitly warns against complexity that requires specialist maintenance.
Every new module, service, or dependency needs justification.

---

## Open Questions

Cross-cutting questions that do not belong to a single phase. These should be
resolved before or during the relevant work.

1. **Model dependency.** HAL currently runs on Qwen2.5-32B-AWQ with known
   behavioral issues (identity override, RLHF fighting system prompt). Should
   the plan account for model upgrades or multi-model support? Does that change
   any architectural assumptions?

2. **Multi-machine future.** The Ideal System mentions HAL growing to cover
   "the entire home." Path C already flags tight coupling to one lab topology.
   How far should early phases go toward multi-machine support?

3. **Privacy boundaries for repo indexing.** If HAL indexes Git repos, it has
   access to code, commit messages, and potentially secrets in history. Should
   repo indexing go through the Judge? What are the privacy/sensitivity rules?

4. **LLM inference budget.** Background tasks (Phase 5), proactive analysis
   (Phase 6), and interactive use all compete for the single RTX 3090 Ti.
   How to prioritize? Is there a scheduling model, or is it first-come?

5. **Evaluation harness.** The existing eval harness tests 40 queries with 4
   code metrics. As HAL gains new capabilities (repo awareness, project
   tracking, proactive insights), the eval needs to grow. When and how?

6. **Second user.** The Ideal System describes a personal assistant. If a
   second person ever uses the lab, how does identity and memory isolation
   work? Is this out of scope entirely?
