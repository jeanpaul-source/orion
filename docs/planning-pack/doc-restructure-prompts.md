# Documentation Restructure — Execution Prompts

> Created: 2026-03-15
> Status: Ready for execution
> Context: Produced by planning chat after full repo audit. Each prompt
> is self-contained — give it to a fresh Copilot chat in agent mode.
> Delete this file after all 3 PRs are merged.

## Execution order

1. **Prompt 1** — Fix contradictions + rollback labels (no structural changes)
2. **Prompt 2** — Restructure docs, create canon, archive noise, add trust contract
3. **Prompt 3** — Expand CI doc-drift checks (code change, independent of 1 & 2)

Prompts 1 and 2 must be done in order (2 assumes 1's changes are on main).
Prompt 3 is independent — can run in parallel with either.

---

## Prompt 1: Fix contradictions and mark rollback units

Branch: `docs/fix-contradictions-and-rollback-labels`

```text
You are working on the Orion repo (jeanpaul-source/orion). Read CLAUDE.md
and memory/SUMMARY.md before making any changes.

Your task: fix documented contradictions and mark rollback-only systemd
units. This is a docs-only change — no code changes. One branch, one PR.

Branch name: docs/fix-contradictions-and-rollback-labels

IMPORTANT CONTEXT: The repo currently has conflicting KB chunk counts in
multiple docs. The actual count is not known at runtime — use qualified
wording ("thousands of chunks, harvested nightly") instead of picking a
number. Also: the system prompt in bootstrap.py hardcodes "~19,900 doc
chunks" — that is a code fix tracked as finding F-89 in
docs/planning-pack/audit-findings.md and is OUT OF SCOPE for this PR.

--- COMMIT 1: Fix contradictory KB chunk counts ---

Files to edit:
- README.md
- ROADMAP.md
- memory/SUMMARY.md

In each file, find every hardcoded KB chunk count (~19,900 or ~17,250)
and replace with qualified wording. The goal is that no doc states a
specific number that might be wrong.

README.md currently has TWO different numbers:
  - Line ~25 (intro): "~19,900 chunks" → change to "thousands of chunks"
  - Line ~53 (status table): "~17,250 chunks, 18 categories" → change to
    "thousands of chunks harvested nightly across 18 categories"

ROADMAP.md line ~12: "~19,900 chunks" → "thousands of chunks"

memory/SUMMARY.md line ~26: "~17,250 chunks" → "thousands of chunks"

After editing, verify with:
  grep -rn '19.900\|17.250\|19900\|17250' README.md ROADMAP.md memory/SUMMARY.md

The grep should return zero matches in those files. (bootstrap.py will
still match — that is F-89, out of scope.)

Commit message: docs: replace hardcoded KB chunk counts with qualified wording

--- COMMIT 2: Mark systemd units as rollback-only ---

Files to edit:
- ops/server.service
- ops/telegram.service

In each file, add a comment block at the very top (BEFORE the [Unit]
section) explaining that the file is retained for rollback only:

For ops/server.service, prepend:
# ROLLBACK ONLY — not the primary deployment path.
# Orion runs inside Docker via docker-compose.yml (supervisord manages
# the HTTP server and Telegram bot inside the container).
# This unit file is retained for emergency rollback to host-venv mode.
# See OPERATIONS.md for the current deployment procedure.

For ops/telegram.service, prepend:
# ROLLBACK ONLY — not the primary deployment path.
# The Telegram bot runs inside the Docker container alongside the HTTP
# server, managed by supervisord.
# This unit file is retained for emergency rollback to host-venv mode.
# See OPERATIONS.md for the current deployment procedure.

Commit message: ops: mark legacy systemd units as rollback-only

--- FINAL STEP ---

Run: make check
Everything must pass. Then push the branch and open a PR.
PR title: docs: fix KB count contradictions and mark rollback units
PR body: Fixes contradictory KB chunk counts across README, ROADMAP, and
SUMMARY.md by replacing hardcoded numbers with qualified wording. Marks
ops/server.service and ops/telegram.service as rollback-only with header
comments explaining the current Docker-first deployment.
```

---

## Prompt 2: Restructure docs — canon, archive, trust contract

Branch: `docs/restructure-canon-and-archive`

`````text
You are working on the Orion repo (jeanpaul-source/orion). Read CLAUDE.md
and memory/SUMMARY.md before making any changes.

Your task: restructure the documentation to establish a single canonical
source of truth, archive completed planning docs, and add an AI-assistance
trust contract. One branch, one PR, multiple commits.

Branch name: docs/restructure-canon-and-archive

IMPORTANT CONTEXT:
- The repo currently has 5 ChatGPT-generated planning docs in
  docs/planning-pack/ that overlap with each other and with the
  verified audit-findings.md.
- The actual verified work queue is docs/planning-pack/audit-findings.md
  (72 findings with line citations).
- docs/automation-guardrails-plan.md is a completed work artifact (all 5
  sessions done, PRs #33-#38 merged).
- docs/ideal-system-plan.md is an unvalidated draft vision doc.

--- COMMIT 1: Create docs/canon/ with verified system canon ---

Create directory: docs/canon/
Create file: docs/canon/ORION-SYSTEM-CANON.md

This is the AUTHORITATIVE source of truth for Orion's runtime contracts,
invariants, and known drift. Keep it SHORT (~100 lines). Every factual
claim must be verifiable against the codebase. Do NOT duplicate
architecture explanation (that's ARCHITECTURE.md's job). Do NOT include
roadmap items (that's ROADMAP.md's job).

Write the file with these sections:

1. Header with purpose statement and truth-precedence rule:
   Running system > Code > Docs

2. "System identity" — 3-4 sentences. Orion is a local-first homelab
   control plane. HAL is the reasoning layer. Not a chatbot wrapper.

3. "Runtime contracts" — bullet list of what MUST be true:
   - All meaningful actions go through Judge (hal/judge.py)
   - HTTP mode auto-denies tier 1+ (ServerJudge in hal/server.py)
   - HAL may not write to its own repo on the server
     (git write blocking in judge.py _GIT_WRITE_SUBCOMMANDS)
   - Agent history persists only final sanitized assistant turns
   - KB is tiered: ground-truth, reference, live-state, memory
   - Sandbox execution is isolated and non-networked
     (hal/sandbox.py: --network none, --read-only)
   - Tool execution bounded by MAX_ITERATIONS=8
   - Trust evolution must be explainable through the audit log
   - Ollama is embeddings-only (OLLAMA_NUM_GPU=0 prevents VRAM OOM)
   - Prometheus is port 9091 (9090 is Cockpit)
   - System prompt text must not silently drift from runtime reality

4. "Current deployment" — 5-6 lines. Docker-first via docker-compose.yml.
   Image from ghcr.io/jeanpaul-source/orion:latest. supervisord runs
   HTTP server + Telegram bot inside container. Harvest + watchdog run
   on host venv. ops/*.service files are rollback-only.

5. "Known drift" — bullet list of currently-known mismatches:
   - System prompt hardcodes "~19,900 doc chunks" (F-89)
   - System prompt hardcodes hardware specs (ROADMAP.md Path C item 1)
   - Judge patterns are Python literals, not externalized (Path C item 2)
   Cite the finding ID or ROADMAP.md reference for each.

6. "Document authority" — which doc owns what:
   - System contracts and invariants → this file
   - Architecture and design rationale → ARCHITECTURE.md
   - Operational procedures → OPERATIONS.md
   - Dev workflow → CONTRIBUTING.md
   - Roadmap → ROADMAP.md
   - AI assistant behavior → CLAUDE.md
   - Current project state (AI session start) → memory/SUMMARY.md
   - Verified findings backlog → docs/planning-pack/audit-findings.md

7. "Maintenance rule" — update in place when reality changes. Do not
   append session logs. Git history is the changelog.

Commit message: docs: create verified system canon in docs/canon/

--- COMMIT 2: Archive completed and superseded planning docs ---

Create directory: docs/archive/

Move these files to docs/archive/ (use git mv):
- docs/automation-guardrails-plan.md → docs/archive/
- docs/ideal-system-plan.md → docs/archive/
- docs/planning-pack/ORION-2026-BEST-PRACTICES-GAP-ANALYSIS.md → docs/archive/
- docs/planning-pack/ORION-VSCODE-COPILOT-FRAMEWORK.md → docs/archive/

Delete these files (git rm):
- docs/planning-pack/ORION-SYSTEM-CANON.md
  (replaced by docs/canon/ORION-SYSTEM-CANON.md)
- docs/planning-pack/ORION-IMPROVEMENT-BLUEPRINT.md
  (superseded by audit-findings.md; contains factually wrong P1.1 claim)
- docs/planning-pack/ORION-PLANNING-PACK-INDEX.md
  (stale index, will be replaced by README)
- docs/planning-pack/orion-phase1-planning-doc.md
  (planning artifact, purpose served)

Create file: docs/archive/README.md with content:
```
# Archive

Completed or superseded planning documents. Kept for historical reference.
These are NOT authoritative — see docs/canon/ORION-SYSTEM-CANON.md for
current system truth.

| File | Why archived |
|---|---|
| automation-guardrails-plan.md | All 5 sessions complete (PRs #33-#38) |
| ideal-system-plan.md | Draft vision, never validated against code |
| ORION-2026-BEST-PRACTICES-GAP-ANALYSIS.md | Reference material, findings absorbed into audit-findings.md |
| ORION-VSCODE-COPILOT-FRAMEWORK.md | Audit framework, work complete |
```

Create file: docs/planning-pack/README.md with content:
```
# Planning Pack

Active planning and tracking documents.

| File | Role |
|---|---|
| audit-findings.md | Verified findings backlog (72 findings, prioritized) |

For completed plans, see docs/archive/.
For system truth, see docs/canon/ORION-SYSTEM-CANON.md.
```

Commit message: docs: archive completed plans, delete superseded files

--- COMMIT 3: Update cross-references ---

Files to edit:
- README.md — update the Documentation table to include the canon and
  remove the session-findings-archive link (check if it's still there;
  it may have been fixed). Add a row for the canon:
  | [docs/canon/ORION-SYSTEM-CANON.md](docs/canon/ORION-SYSTEM-CANON.md) | System contracts, invariants, deployment truth |
- CLAUDE.md — in the "Documentation" section, add a line:
  "System canon: docs/canon/ORION-SYSTEM-CANON.md (contracts and invariants)"
- memory/SUMMARY.md — add a line in the Architecture section:
  "System canon: docs/canon/ORION-SYSTEM-CANON.md"

Verify no broken references remain:
  grep -rn 'ORION-IMPROVEMENT-BLUEPRINT\|ORION-PLANNING-PACK-INDEX\|ORION-SYSTEM-CANON' --include='*.md' . | grep -v docs/archive | grep -v docs/canon

That grep should return zero matches (only archive and canon dirs should
reference those names).

Commit message: docs: update cross-references for new doc structure

--- COMMIT 4: Add AI-assistance trust contract to CLAUDE.md ---

In CLAUDE.md, add a new section AFTER the "How the AI Assistant Works With
the Developer" section and BEFORE the "Documentation" section. Title it:

## Trust and Verification

Add this content:

```
## Trust and Verification

**Why this section exists:** AI assistants sound confident even when wrong.
In a system where documentation drives code changes, a confidently wrong
claim causes wrong fixes. These rules make uncertainty visible.

**Claim labeling — use when stating facts about the system:**

When making a factual claim about how the system works, label it:
- **[CONFIRMED]** — verified by reading the actual code or runtime output
- **[INFERRED]** — reasonable conclusion from evidence, but not directly
  verified (e.g., "this function probably does X based on its name")
- **[STALE]** — from documentation that may not reflect current code
- **[UNKNOWN]** — no evidence either way

If you cannot confidently label a claim as CONFIRMED, say so. Do not
flatten contradiction into certainty.

**Planning docs are not runtime truth.** Files in docs/planning-pack/ and
docs/archive/ reflect plans and historical analysis. They may contain
claims that were true when written but have since been fixed, superseded,
or invalidated. Always verify against code before acting on a planning
doc claim.

**The canon is the truth anchor.** docs/canon/ORION-SYSTEM-CANON.md
defines current contracts and invariants. If a planning doc contradicts
the canon, the canon wins. If the canon contradicts the code, the code
wins — and the canon needs updating.
```

Commit message: docs: add AI-assistance trust contract to CLAUDE.md

--- FINAL STEP ---

Run: make check
Everything must pass. Then push the branch and open a PR.
PR title: docs: restructure documentation — canon, archive, trust contract
PR body:
Establishes a layered documentation structure:
- docs/canon/ORION-SYSTEM-CANON.md — single source of truth for contracts
  and invariants (~100 lines, every claim code-verifiable)
- docs/archive/ — completed and superseded planning docs
- docs/planning-pack/ — slimmed to active work only (audit-findings.md)
- CLAUDE.md gains a Trust and Verification section with claim labeling
  rules ([CONFIRMED], [INFERRED], [STALE], [UNKNOWN])

Archives: automation-guardrails-plan, ideal-system-plan, gap analysis,
copilot framework. Deletes: old canon, blueprint (wrong P1.1), index,
phase1 planning doc.
`````

---

## Prompt 3: Expand CI doc-drift checks

Branch: `chore/expand-doc-drift-checks`

```text
You are working on the Orion repo (jeanpaul-source/orion). Read CLAUDE.md
and memory/SUMMARY.md before making any changes.

Your task: expand scripts/check_doc_drift.py with new verifiable checks
that prevent the documentation contradictions that led to the recent
restructure. One branch, one PR.

Branch name: chore/expand-doc-drift-checks

IMPORTANT CONTEXT:
- check_doc_drift.py already has 7 checks (file existence, module drift,
  port consistency, test count sanity, required env vars, optional env
  vars, key-file table paths). Read it fully before adding anything.
- The script runs as part of `make check` — it must stay fast and offline.
- The canon file is at docs/canon/ORION-SYSTEM-CANON.md (may or may not
  exist yet depending on whether Prompt 2 has landed).
- The system is a homelab AI assistant called Orion/HAL.

--- CHECK 7: No hardcoded KB chunk counts in docs ---

Add a check that scans these files for patterns matching a specific KB
chunk count (a number followed by "chunks"):
  README.md, ROADMAP.md, memory/SUMMARY.md, ARCHITECTURE.md

The pattern to flag: a line containing a number like "17,250" or "19,900"
or any 4-5 digit number immediately followed by "chunks" (with optional
comma thousands separators).

Regex: r'\b[\d,]{4,6}\s+chunks\b'

If any match is found, report:
  "{file} line {n} contains a hardcoded chunk count — use qualified
   wording like 'thousands of chunks' instead"

Exceptions: docs/planning-pack/audit-findings.md is allowed to reference
specific counts (it's a findings log). docs/archive/* is allowed (historical).

--- CHECK 8: No "not yet built" for things that exist ---

Add a check that looks for these patterns in README.md:
  "Not yet built" or "not yet implemented" or "not built"

For each match, extract the feature name from the same table row. Then
check if known indicators exist:
  - "Web UI" → hal/static/index.html must exist (it does)
  - "Autonomous remediation" → hal/healthcheck.py and hal/playbooks.py
    must exist (they do)
  - "Trust evolution" → hal/trust_metrics.py must exist (it does)

If a row says "Not yet built" but the corresponding code exists, report:
  "README.md claims '{feature}' is not yet built, but {evidence_file}
   exists — update the status"

Implementation approach: define a list of (feature_substring, evidence_path)
tuples and scan the README status table for contradictions.

Currently README.md has these "Not yet built" entries:
  - "Autonomous remediation" — BUT hal/healthcheck.py exists
  - "Voice interfaces" — this one is legitimately not built
  - "Trust evolution" — BUT hal/trust_metrics.py exists

So this check should currently flag 2 issues. The developer should then
fix README.md to resolve them (that fix is a separate commit, possibly in
this same PR).

--- CHECK 9: Canon invariants match code ---

Add a check that verifies a few key invariants from the canon:
(Only run this if docs/canon/ORION-SYSTEM-CANON.md exists — skip with
a warning if it doesn't.)

9a. Verify that hal/judge.py contains "_GIT_WRITE_SUBCOMMANDS" (the
    git-write blocking invariant). If missing, report:
    "Canon invariant violated: judge.py must contain git-write blocking
     via _GIT_WRITE_SUBCOMMANDS"

9b. Verify that hal/sandbox.py contains "--network none" (the sandbox
    isolation invariant). If missing, report:
    "Canon invariant violated: sandbox.py must contain --network none"

9c. Verify that hal/server.py imports or defines "ServerJudge" (the HTTP
    tier-gating invariant). If missing, report:
    "Canon invariant violated: server.py must use ServerJudge for HTTP
     tier gating"

Keep this check list short and focused on safety invariants only. Each
check is one grep against one file — fast and offline.

--- CHECK 10: No orphaned doc cross-references ---

Add a check that scans all *.md files in the repo root and docs/ for
markdown links to .md files, and verifies the target exists.

Regex for markdown links: r'\[([^\]]+)\]\(([^)]+\.md)\)'
For each match, resolve the path relative to the file containing the
link. If the target doesn't exist, report:
  "{source_file} links to {target} but file does not exist"

Skip external URLs (http://, https://).
Skip anchor-only links (#section).

--- COMMIT PLAN ---

Commit 1: Add the new checks to check_doc_drift.py
  - Add all 4 new check functions
  - Register them in main()
  Commit message: chore: expand doc-drift checks with chunk counts,
    status table, canon invariants, and link validation

Commit 2: Fix any issues the new checks surface
  - If README.md has "Not yet built" contradictions, fix them
  - If any cross-references are broken, fix them
  Commit message: docs: fix issues surfaced by expanded drift checks

--- FINAL STEP ---

Run: make check
Everything must pass (including the new checks). Then push the branch
and open a PR.
PR title: chore: expand doc-drift checks — chunk counts, status table,
  canon invariants, link validation
PR body:
Adds 4 new automated checks to scripts/check_doc_drift.py:
- No hardcoded KB chunk counts in key docs (prevents count contradictions)
- No "not yet built" claims for features that exist in the source tree
- Canon safety invariants verified against code (judge git-blocking,
  sandbox network isolation, server tier gating)
- No broken markdown cross-references between docs

Also fixes README.md status table entries that contradict the codebase.
```
