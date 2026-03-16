# ORION VS Code Copilot Framework

Purpose: make implementation survivable inside constrained VS Code chat contexts.

This framework is deliberately split into three top-level phases.

- Phase 1: Audit / Flag only
- Phase 2: Plan only
- Phase 3: Implement only

Do not collapse phases unless you enjoy re-discovering the same problem six times.

## Global operating rules

1. Prefer runtime truth over stale docs.
2. Keep one bounded domain packet per Copilot chat.
3. Before editing, confirm assumptions from code/runtime where the prompt says to verify.
4. Never let one chat carry more than one subcategory unless the prompt explicitly says so.
5. End every bounded chat with:
   - findings or changes made
   - files touched
   - tests/checks run
   - unresolved questions
   - next recommended packet
6. One logical change per commit.
7. Run the smallest relevant verification after each change, and `make check` after each grouped change set.

---

# Phase 1 — AUDIT / FLAG ONLY

Goal: inspect the whole codebase and related docs/runtime surfaces, identify issues, and report findings.

Rules:
- no implementation
- no planning
- no editing
- no refactors
- no speculative fixes beyond explicitly stating likely root cause

Expected output per packet:
- findings only
- severity / confidence
- evidence
- unknowns to verify later

## 1A. Safety and security audit

### Scope
- `judge.py`
- `sandbox.py`
- `web.py`
- `tools.py`
- related tests/docs

### Prompt
Use this exact starter prompt in VS Code:

> Audit Orion safety/security behavior only. Do not plan changes and do not edit code.
> Inspect `judge.py`, `sandbox.py`, `web.py`, `tools.py`, and any directly related tests/docs.
> Flag:
> - Judge invariant violations
> - shell-evasion gaps
> - repo self-edit bypass paths
> - sandbox hardening gaps
> - temp-file / cleanup risks
> - SSRF / fetch / web-search privacy issues
> - tool-exposure mismatches
> Report findings grouped by severity with file references and concise root-cause notes.
> End with “No planning performed. No code edited.”

## 1B. Control-plane and routing audit

### Scope
- `bootstrap.py`
- `agent.py`
- `intent.py`
- `server.py`
- `main.py`
- `memory.py`

### Prompt
> Audit Orion control-plane behavior only. Do not plan changes and do not edit code.
> Inspect routing, conversational fast path, `run_agent()` loop controls, duplicate work, persistence contracts, and HTTP/CLI behavioral differences.
> Flag:
> - routing drift vs docs
> - duplicate classification or redundant calls
> - loop-control edge cases
> - inconsistent sanitization/persistence
> - context-window risks
> - session continuity seams
> Return findings only, grouped by severity and confidence.
> End with “No planning performed. No code edited.”

## 1C. Knowledge and retrieval audit

### Scope
- `collect.py`
- `ingest.py`
- `knowledge.py`
- KB-related docs/tests

### Prompt
> Audit Orion knowledge/retrieval behavior only. Do not plan changes and do not edit code.
> Inspect collectors, chunking, ingest semantics, tiering, reference-doc incrementality, orphan cleanup, and retrieval/index behavior.
> Verify what is known vs unknown from code.
> Flag:
> - stale-doc risk
> - retrieval/index blind spots
> - metadata/indexing issues
> - chunking/config rigidity
> - collector fragility
> Report findings only, with explicit “verified” vs “needs runtime verification.”
> End with “No planning performed. No code edited.”

## 1D. Runtime and deployment audit

### Scope
- `docker-compose.yml`
- service/unit files
- `config.py`
- ops docs
- startup/retry code in `server.py` / `bootstrap.py`

### Prompt
> Audit Orion runtime/deployment truth only. Do not plan changes and do not edit code.
> Compare compose/unit/config/startup code and relevant docs.
> Flag:
> - Docker vs systemd drift
> - config contract ambiguities
> - unsafe defaults
> - startup/retry inconsistencies
> - mount/permission boundary concerns
> Mark each finding as runtime-verified, code-verified, doc-only, or needs verification.
> End with “No planning performed. No code edited.”

## 1E. Observability and trust audit

### Scope
- Prometheus client
- tracing
- watchdog
- trust metrics
- audit-log behavior

### Prompt
> Audit Orion observability/trust behavior only. Do not plan changes and do not edit code.
> Inspect Prometheus error handling, tracing degradation paths, watchdog diagnostics, audit-log scaling, trust-evolution integrity, and health/recovery visibility.
> Report findings only, with root cause and impact.
> End with “No planning performed. No code edited.”

## 1F. Docs and prompt drift audit

### Scope
- `README.md`
- `ARCHITECTURE.md`
- `OPERATIONS.md`
- `ROADMAP.md`
- `CLAUDE.md`
- prompt text in `bootstrap.py`
- canon doc

### Prompt
> Audit Orion documentation/prompt drift only. Do not plan changes and do not edit code.
> Compare docs and prompt text against current code/runtime contracts.
> Flag contradictions, stale statements, missing invariants, and places where docs describe an older architecture.
> Produce a drift inventory only.
> End with “No planning performed. No code edited.”

---

# Phase 2 — PLANNING ONLY

Goal: turn Phase 1 findings into bounded execution plans and prompt packs.

Rules:
- no code editing
- no repo modification
- use Phase 1 findings as inputs
- define sequencing, dependencies, validation, and commit boundaries

Expected output per packet:
- subcategory plan
- acceptance criteria
- verification steps
- proposed commit grouping
- implementation prompt(s) for Phase 3

## 2A. Safety remediation planning

### Prompt
> Use the completed Phase 1 safety/security findings to produce a bounded implementation plan only.
> Do not edit code.
> Convert findings into:
> - prioritized tasks
> - target files
> - dependencies
> - acceptance criteria
> - minimal verification steps
> - grouped commit boundaries
> - one or more implementation prompts for Copilot Phase 3
> Keep each task small enough for one bounded VS Code chat.

## 2B. Control-plane planning

### Prompt
> Use the completed Phase 1 control-plane findings to produce a bounded implementation plan only.
> Do not edit code.
> Create small implementation packets for routing, loop control, sanitization, persistence, and session-behavior fixes.
> Include acceptance criteria, tests/checks, and commit boundaries.

## 2C. Knowledge/retrieval planning

### Prompt
> Use the completed Phase 1 knowledge/retrieval findings to produce a bounded implementation plan only.
> Do not edit code.
> Separate:
> - pure correctness fixes
> - config/externalization work
> - benchmark-required retrieval changes
> Mark any item that must not be implemented before measurement/runtime verification.

## 2D. Runtime/deployment planning

### Prompt
> Use the completed Phase 1 runtime/deployment findings to produce a bounded implementation plan only.
> Do not edit code.
> Separate:
> - safety/correctness changes
> - config contract changes
> - doc/runtime reconciliation changes
> Keep packets small and commit-friendly.

## 2E. Observability/trust planning

### Prompt
> Use the completed Phase 1 observability/trust findings to produce a bounded implementation plan only.
> Do not edit code.
> Create implementation packets for diagnostics, audit-log scaling, trust integrity, and health/recovery visibility.
> Include validation steps and rollback risk notes.

## 2F. Docs and canon planning

### Prompt
> Use the completed Phase 1 docs/prompt drift findings to produce a bounded documentation reconciliation plan only.
> Do not edit code.
> Define:
> - canon updates
> - prompt/runtime truth-sync updates
> - secondary doc updates
> - ordering rules so docs follow verified reality
> Include grouped commit strategy.

---

# Phase 3 — IMPLEMENTATION ONLY

Goal: execute the approved Phase 2 plan in bounded code-change packets.

Rules:
- implement only one planned packet at a time
- no fresh architecture redesign unless blocked
- verify after each packet
- use grouped commits
- update canon/docs when the packet changes reality or removes drift

Expected output per packet:
- concise change summary
- files changed
- tests/checks run
- commit message proposal
- residual risks
- next packet suggestion

## 3A. Safety implementation packet template

### Prompt
> Implement the approved safety packet only.
> Do not broaden scope.
> Before editing, re-check the targeted files for drift from the plan.
> Then:
> - make the smallest correct change
> - update/add tests
> - run the smallest relevant checks
> - propose one logical commit message
> - summarize residual risk and next packet
> If reality differs from the plan in a material way, stop and report instead of improvising.

## 3B. Control-plane implementation packet template

### Prompt
> Implement the approved control-plane packet only.
> Do not broaden scope.
> Verify current code shape first, then apply the smallest correct change.
> Update tests/checks.
> Propose one logical commit message.
> End with:
> - files changed
> - checks run
> - what changed in behavior
> - whether the canon doc also needs an update

## 3C. Knowledge/retrieval implementation packet template

### Prompt
> Implement the approved knowledge/retrieval packet only.
> Do not broaden scope.
> If the packet depends on benchmarks or runtime verification, stop unless those results are already present.
> Otherwise apply the smallest correct change, update tests, and summarize any retrieval-quality risk.

## 3D. Runtime/deployment implementation packet template

### Prompt
> Implement the approved runtime/deployment packet only.
> Do not broaden scope.
> Keep config and ops changes tightly scoped.
> If the packet alters the runtime contract, also draft the matching canon/doc update in the same packet summary.

## 3E. Observability/trust implementation packet template

### Prompt
> Implement the approved observability/trust packet only.
> Do not broaden scope.
> Preserve existing safety behavior while improving diagnostics/integrity.
> Update tests where possible and note any runtime-only verification still needed.

## 3F. Docs/canon implementation packet template

### Prompt
> Implement the approved documentation/canon packet only.
> Do not edit unrelated code.
> Update the canon doc first, then reconcile secondary docs as instructed by the plan.
> Explicitly list which prior drift items were resolved.

---

# Recommended subcategory order

1. 1A → 2A → 3A
2. 1B → 2B → 3B
3. 1E → 2E → 3E
4. 1D → 2D → 3D
5. 1C → 2C → 3C
6. 1F → 2F → 3F

This keeps safety and control-plane issues ahead of retrieval polish and doc cleanup.

# Commit / merge policy

- one logical fix per commit
- one small related cluster per push/PR
- never mix safety, retrieval, and docs in one commit unless the doc update is required to describe the exact same change
- after each grouped batch, update the canon if runtime truth changed

# Minimal packet size rule

If a prompt would require Copilot to:
- inspect more than ~6–8 files deeply
- hold more than one domain in memory
- both discover and implement architecture
then it is too large.
Split it.

# Handoff template for every bounded chat

Use this exact ending structure:

- Packet completed:
- Scope:
- Files inspected:
- Files changed:
- Checks run:
- Findings or changes:
- Open questions:
- Canon/doc update needed:
- Suggested next packet:
