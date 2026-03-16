# ORION Improvement Blueprint

Purpose: prioritized, implementation-ready roadmap derived from current code/docs plus 2026 guidance.

## Priority model

- P0: security / correctness / invariant protection
- P1: reliability / observability / control-plane hygiene
- P2: architectural cleanup / externalization / retrieval quality
- P3: workflow, docs, and developer-experience improvements

---

## P0.1 Harden sandbox execution

### Root cause
The sandbox concept is good, but several implementation details lag least-privilege container practice and Orion’s own “everything meaningful goes through Judge” invariant.

### Target files
- `sandbox.py`
- `tools.py`
- any related tests

### Actions
1. Add container hardening flags:
   - `--user sandbox:sandbox`
   - `--cap-drop ALL`
   - `--security-opt no-new-privileges`
2. Review whether seccomp behavior should be explicitly documented or pinned.
3. Tighten temp-file permissions for host-side code file creation.
4. Route cleanup through the same audit/governance path if feasible, or explicitly document the exception if not.

### Acceptance criteria
- sandbox still runs valid code successfully
- sandbox cannot run as root inside the container
- cleanup remains reliable
- audit trail no longer has silent governance bypasses

### Commit shape
One logical change set:
- sandbox hardening
Second logical change set:
- cleanup / temp-file integrity

---

## P0.2 Fix web safety edge cases

### Root cause
Web access is safer than average, but not complete.

### Target files
- `web.py`
- tests for web safety

### Actions
1. Extend search-query sanitization to IPv6 private/link-local/loopback ranges.
2. Remove TOCTOU DNS-validation gap by pinning resolved IPs for actual fetch requests.
3. Ensure remote page content is treated as untrusted input in downstream flows.

### Acceptance criteria
- IPv4 and IPv6 private-address leakage tests pass
- fetches to rebind/private targets are blocked
- allowed public fetches still work

### Commit shape
Single focused change.

---

## P0.3 Complete outcome tracking for trust evolution

### Root cause
Trust evolution is architecturally important, but direct command paths do not fully feed it.

### Target files
- `tools.py`
- `main.py`
- `judge.py`
- trust-related tests

### Actions
1. Record `run_command` outcomes in direct tool/REPL paths.
2. Log warnings when trust override loading falls back because audit reading failed.
3. Plan short-term scaling fix for audit-log reread behavior.

### Acceptance criteria
- direct `/run` and tool-based command execution contribute to trust stats
- degraded audit-log loading is visible
- no duplicate logging regressions

### Commit shape
One commit for outcome tracking.
One commit for trust-load diagnostics / scaling.

---

## P1.1 Remove unnecessary double intent classification

### Root cause
HTTP chat currently classifies intent twice.

### Target files
- `server.py`
- `bootstrap.py`
- tests

### Actions
1. Pass already-computed intent/confidence into dispatch logic.
2. Remove second embedding call.
3. Keep response metadata unchanged.

### Acceptance criteria
- HTTP response still includes intent metadata
- only one classify call is made per HTTP request
- existing routing behavior is preserved

---

## P1.2 Sanitize conversational responses before persistence

### Root cause
Conversational fast path currently does not sanitize tool-call artifacts before saving.

### Target files
- `bootstrap.py`
- tests around poison/tool-call artifact persistence

### Actions
1. Apply artifact stripping before persistence in conversational path.
2. Keep history contract consistent with `run_agent()` and server sanitization.

### Acceptance criteria
- conversational hallucinated tool-call JSON is not persisted
- clean conversational replies still persist normally

---

## P1.3 Improve degraded-path diagnostics

### Root cause
Several components degrade quietly or too quietly.

### Target files
- `prometheus.py`
- `watchdog.py`
- `tracing.py`
- `config.py`
- possibly `healthcheck.py`

### Actions
1. Add warning logs where failures are currently swallowed.
2. Make malformed config entries visible.
3. Ensure watchdog component-health failures emit diagnostics.
4. Differentiate “optional package absent” from “configured but broken”.

### Acceptance criteria
- operator can identify Prometheus / tracing / watchdog issues from logs
- silent-failure paths are materially reduced

---

## P1.4 Tighten HTTP surface defaults

### Root cause
The HTTP surface is safety-conscious in Judge terms, but browser/CORS defaults are broader than they need to be.

### Target files
- `server.py`
- `config.py`

### Actions
1. Add configurable allowed-origins support.
2. Default to same-origin / explicit LAN origins instead of wildcard where practical.
3. Document auth + CORS contract in canon and ops docs.

### Acceptance criteria
- bearer-token flow still works
- same-origin web UI still works
- wildcard CORS is no longer the only production path

---

## P2.1 Reconcile system prompt with runtime truth

### Root cause
The system prompt still carries deployment and lab literals that drift away from reality.

### Target files
- `bootstrap.py`
- `config.py`
- tests
- docs

### Actions
1. Externalize more site-specific prompt values into config/lab profile inputs.
2. Remove prompt claims that no longer match deployment reality.
3. Decide what belongs in config vs KB vs inferred runtime metadata.
4. Keep the prompt strong, concise, and behaviorally effective.

### Acceptance criteria
- prompt no longer misstates current deployment
- key runtime values derive from config where appropriate
- tests updated accordingly

### Notes
This is Path C work already acknowledged by the roadmap.

---

## P2.2 Externalize site-specific Judge rules without weakening security

### Root cause
Judge contains both universal policy and site-specific literals in the same source structures.

### Target files
- `judge.py`
- `config.py`
- tests
- docs

### Actions
1. Separate universal rules from site-specific extensions.
2. Keep evasion detection, git-write blocking, and core destructive patterns in source.
3. Move only site-specific sensitive paths / allowlists where justified.
4. Fail loud on missing/malformed external policy config.

### Acceptance criteria
- no silent weakening of policy
- site-specific entries can move without editing core policy code
- tests clearly cover base policy vs local extensions

---

## P2.3 Audit and improve retrieval quality deliberately

### Root cause
Knowledge ingestion is solid, but retrieval/index strategy is not yet proven against 2026 scaling guidance from the uploaded subset.

### Target files
- `knowledge.py`
- `ingest.py`
- DB/index setup
- retrieval tests/evals

### Actions
1. Verify current pgvector index and query strategy before changing anything.
2. Benchmark exact vs approximate retrieval if scale justifies it.
3. Confirm metadata filter indexing.
4. Consider configurable chunk/window settings only after measurement.
5. Evaluate whether hybrid lexical+semantic retrieval or reranking would materially help.

### Acceptance criteria
- retrieval changes are benchmark-backed
- no blind algorithm swaps
- any new index strategy is documented in canon/ops

---

## P2.4 Strengthen telemetry for GenAI workloads

### Root cause
Orion already uses OTel, but 2026 guidance now expects more deliberate GenAI trace design.

### Target files
- tracing-related code
- logging/tracing config
- dashboards/docs

### Actions
1. Align spans more clearly with GenAI/agent operations.
2. Avoid storing excessive raw content in traces when references would do.
3. Make tool execution and agent iterations easier to inspect at workflow level.

### Acceptance criteria
- trace data is more useful operationally
- sensitive or huge payloads are handled more carefully
- agent workflows are easier to debug

---

## P2.5 Expand evaluation from component correctness to workflow correctness

### Root cause
Current eval posture is respectable, but workflow-level agent regressions need stronger direct coverage.

### Target files
- eval harness
- tests / fixtures / traces
- docs

### Actions
1. Add workflow eval sets:
   - routing
   - tool selection
   - loop completion
   - recovery recommendations
   - web safety behavior
2. Introduce trace grading / workflow-level inspection.
3. Gate risky changes with these evals.

### Acceptance criteria
- regressions in agent workflows become visible before release
- eval corpus covers real failure modes, not only happy-path prompts

---

## P3.1 Establish the living canonical system doc as policy

### Root cause
Docs drift because no single file is explicitly treated as the current-state anchor.

### Target files
- canonical doc
- docs index
- contributing guidance if needed

### Actions
1. Adopt the canon doc as the architecture ground truth.
2. Require updates when runtime or invariants change.
3. Track known drift explicitly until resolved.
4. Link planning/execution prompts back to the canon.

### Acceptance criteria
- future work has a stable grounding document
- contradictions are surfaced, not hidden

---

## P3.2 Make long-running work resumable by design

### Root cause
VS Code / chat contexts are limited, and Orion work will span many bounded sessions.

### Target files
- prompt packs
- project docs
- maybe templates under `docs/` or `notes/`

### Actions
1. Require bounded work packets.
2. Require end-of-packet handoff summaries.
3. Use phase/category prompt packs instead of giant omnibus threads.
4. Keep one implementation packet per logical change boundary.

### Acceptance criteria
- Copilot sessions can stop/restart without rediscovering everything
- implementation remains reviewable and commit-friendly

---

## Recommended execution order

1. P0.1 sandbox hardening
2. P0.2 web safety fixes
3. P0.3 trust/accounting fixes
4. P1.1 double classification removal
5. P1.2 conversational sanitization
6. P1.3 degraded-path diagnostics
7. P1.4 HTTP surface tightening
8. P2.1 prompt/runtime reconciliation
9. P2.2 Judge policy externalization
10. P2.3 retrieval audit + measured improvement
11. P2.4 telemetry refinement
12. P2.5 workflow eval expansion
13. P3.1 canon adoption
14. P3.2 resumable work system

## Stop conditions

Pause implementation and return to planning if:
- runtime reality diverges materially from this blueprint
- tests reveal hidden invariants not captured here
- retrieval or policy changes would alter safety boundaries more than expected
