# ORION 2026 Best-Practices Gap Analysis

Purpose: compare Orion’s current architecture to 2026 guidance from primary sources and convert that into grounded decisions.

## Summary

Orion is already aligned with several 2026 recommendations:

- simple composable architecture over framework-heavy “agent stacks”
- explicit state/memory/orchestration separation
- strong human-approval boundary for sensitive actions
- observability and audit awareness
- local-first deployment and clear tool boundaries

The biggest gaps are not “needs more agents.”
They are:

- runtime/prompt/doc truth drift
- sandbox and web-edge hardening
- tool-surface scaling discipline
- workflow-level eval coverage
- better context-bridging artifacts for long-running work

## Category A: Agent architecture and orchestration

### Current position
Strong.

Orion already uses simple composable pieces:
- model backends
- tools
- memory
- orchestration
- policy gate

That is aligned with 2026 guidance to prefer simple, composable patterns over overbuilt agent frameworks.

### Keep
- do not replace the current architecture with a heavyweight agent framework just for aesthetics
- keep the clear separation between routing, agent loop, memory, and policy

### Improve
- introduce explicit “work packet” / “handoff artifact” patterns for long-running multi-session work
- make the canonical document and bounded work prompts part of the architecture, not just project management

## Category B: Tool calling and tool-surface management

### Current position
Good now, but this will become a problem as the tool surface grows.

Orion already has a relatively large active tool registry.
2026 guidance recommends:
- concise tool descriptions
- explicit tool contracts
- token-efficient tool responses
- tool subset restriction or discovery when the tool surface becomes large

### Keep
- keep clear tool descriptions and layer separation
- keep output caps and dedupe behavior in the agent loop

### Improve
- verify whether the full active tool registry is always exposed every turn
- if yes, consider dynamic tool subsets by intent / mode before adopting full tool search
- reserve tool-search-style discovery for when tool count or schema size starts hurting reliability

## Category C: Context engineering and long-running work

### Current position
Partially aligned.

Orion already limits session history and stores durable state.
But the project itself now needs explicit context-bridging strategy for long-running code work.

### Gap
2026 guidance is clear that long-running agentic work benefits from:
- initializer/architect artifacts
- resumable handoff files
- explicit progress summaries
- external artifacts instead of overloading one chat window

### Improve
- treat the canon doc as mandatory context anchor
- produce bounded VS Code prompt packs by phase/category
- require each Copilot work packet to emit a concise handoff summary before ending

## Category D: RAG / knowledge pipeline

### Current position
Solid core design.

Strengths:
- tiered knowledge
- mixed source collection
- incremental reference ingestion
- orphan cleanup
- bounded chunking

### Unknowns to verify
The uploaded files do not prove whether the current retrieval path uses:
- exact scan only
- HNSW / IVFFlat
- hybrid lexical+semantic retrieval
- reranking
- metadata filter indexes

### Improve
- do not blindly swap retrieval algorithms
- first audit current `knowledge.py` behavior and database indexes
- if exact scan is still in use at larger scale, benchmark approximate indexing plus metadata-aware tuning
- if metadata filters are heavily used, ensure normal indexes exist on filter columns
- consider whether chunk size/overlap should become configurable and benchmarked rather than fixed

## Category E: Sandbox and execution isolation

### Current position
Conceptually good, operationally behind best practice.

Strengths:
- disposable Docker container
- no network
- read-only rootfs
- memory/CPU/PID caps
- explicit timeout
- separate run_code tool

### Gaps
Container hardening should follow least privilege more strictly:
- run unprivileged
- drop capabilities
- block privilege escalation
- keep cleanup actions inside the same approval/audit model where possible

### Improve
- add `--user`
- add `--cap-drop ALL`
- add `--security-opt no-new-privileges`
- confirm seccomp profile behavior and document whether default Docker seccomp is relied on intentionally
- tighten temp-file permissions and cleanup path

## Category F: Web / remote-content safety

### Current position
Better than average, but not finished.

Strengths:
- query sanitization
- SSRF-aware URL validation
- non-HTTP scheme blocking
- private/loopback address checks
- tiered approval for fetch

### Gaps
- IPv6 private-address leakage in search-query sanitization
- TOCTOU gap in hostname validation vs actual request
- external content handling should be treated as prompt-injection exposure, not just SSRF exposure

### Improve
- pin resolved IPs for fetches
- extend sanitization to IPv6 private/link-local/loopback ranges
- treat remote content as untrusted input and sanitize/label it before agent reuse
- keep least-privilege defaults for remote fetch tools

## Category G: Observability, tracing, and evals

### Current position
Promising, but not yet at 2026 “agent operations” maturity.

Strengths:
- structured logs
- audit log
- OTel tracing
- Prometheus metrics
- health checks
- watchdog
- existing eval harness

### Gaps
2026 guidance emphasizes:
- workflow-level evals, not only unit/query evals
- trace grading for agent paths
- strong diagnostics around degraded backends
- careful handling of prompt/tool content in telemetry to avoid excessive sensitive data in traces

### Improve
- add workflow/agent eval sets with trace grading
- strengthen warning-level logging on degraded-but-not-crashing paths
- review GenAI span payloads and prefer content references over dumping full inputs/outputs into tracing backends
- define release gates for agent regressions, not just unit tests

## Category H: Memory and persistence safety

### Current position
Good foundation.

Strengths:
- SQLite durable sessions
- poison-response filtering
- pruning
- bounded turn window

### Improve
- make turn window configurable
- add explicit memory-hygiene checks during audit phase
- consider integrity/audit checks on persisted memory objects if memory types expand
- preserve the rule that not everything should be remembered just because it exists

## Category I: Docs and source-of-truth discipline

### Current position
This is the largest practical gap.

The architecture is better than the documentation state.

### Improve
- canonical living document first
- explicitly mark drift instead of letting contradictions hide
- update prompt text when deployment reality changes
- require plan/implementation prompts to prefer runtime truth over older prose docs

## Recommended stance

Do not redesign Orion around shiny 2026 abstractions.
Instead:

1. keep the simple composable architecture
2. harden the risky edges
3. improve truth-sync and work handoff
4. expand evals and observability where agent behavior is subtle
5. scale the tool surface deliberately, not accidentally
