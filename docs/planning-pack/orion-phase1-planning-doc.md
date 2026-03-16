# Orion Phase 1 Planning Doc

## Title
Documentation Trust Hardening for Canon + Generated Architecture Map

## Status
Proposed

## Last updated
2026-03-15

## Owner
TBD

## Scope
Phase 1 establishes trustworthy documentation boundaries so Orion can support a two-layer model:

1. **Canon layer** for design invariants, rationale, trust semantics, operational traps, and AI-assistance guarantees.
2. **Generated architecture map layer** for machine-verifiable inventories such as routes, tools, judge rules, env vars, services, and workflows.

This phase does **not** build the full generator. It removes the highest-risk trust defects and prepares the repo for generator work.

---

## Problem statement
The source tree is structured well enough to support generated architecture snapshots, but the documentation set still has several high-impact trust defects:

- contradictory KB chunk counts across docs
- one incorrect remediation claim in `ORION-IMPROVEMENT-BLUEPRINT.md`
- stale findings in `automation-guardrails-plan.md`
- planning-pack docs without validation dates or freshness signals
- rollback-only systemd units that are not visibly marked as disabled deployment paths
- canon guidance without sufficient file-and-line provenance
- insufficiently explicit user-facing guarantees for AI assistance honesty, verification, and uncertainty handling

These issues do not block development, but they **do** block reliable use by humans and AI assistants. Left alone, they create false work, wrong fixes, and loss of confidence in the docs.

---

## Goals

### G1. Restore documentation trust
Remove or neutralize the highest-risk contradictions and stale claims so assistants and operators can safely use the docs.

### G2. Establish explicit documentation boundaries
Make it clear which documents are authoritative for:

- system invariants
- operational procedures
- roadmap and future direction
- generated architecture inventories
- user-facing AI-assistance guarantees

### G3. Make AI-assistance trust rules explicit
Document clear expectations that Orion must be honest with the user, verify what it can, distinguish confirmed facts from inference, and never hide uncertainty behind confident wording.

### G4. Prepare for generator implementation
Create a clean starting point for a later phase that auto-generates architecture inventories and validates them in CI.

---

## Non-goals
This phase will **not**:

- build the complete architecture generator
- add runtime DB inspection tooling unless already desired for separate reasons
- redesign the deployment model
- rewrite all docs into a new format
- resolve runtime-only unknowns such as ANN index presence or self-hosted runner health
- change system behavior in code unless needed to support doc accuracy labels or comments

---

## Deliverables

1. KB-count contradiction removed or explicitly qualified.
2. Incorrect Blueprint routing item corrected.
3. Planning-pack docs carry freshness metadata.
4. Resolved findings in `automation-guardrails-plan.md` are visibly marked.
5. Rollback-only unit files are visibly labeled.
6. Canon structure decision documented.
7. AI-assistance trust guarantees documented explicitly.
8. Phase 2 entry criteria documented.

---

## Guiding decisions

### D1. Canon and generated inventories must remain separate
Narrative architecture explanation and design rationale should not be mixed with generated inventories in the same maintainability boundary.

### D2. Mutable runtime numbers do not belong in unqualified canonical prose
Counts like KB chunks should either:

- come from a runtime snapshot with date, or
- be described qualitatively until runtime verification exists.

### D3. Planning docs require explicit freshness markers
Every planning or audit-derived doc should declare:

- status
- last validated date
- validation basis
- authoritative scope
- non-authoritative scope
- supersession status where applicable

### D4. Rollback paths must self-identify
Files that still work but are not primary deployment paths must say so inside the file, not only in separate docs.

### D5. AI assistance must optimize for user trust, not surface-level confidence
User-facing AI behavior must be documented as a contract, not treated as an informal style preference.

Orion should be explicit that it must:

- tell the truth even when the truth is uncertainty
- verify claims against code, config, or runtime where possible
- label facts as confirmed, inferred, or unknown
- refuse to invent missing evidence
- preserve provenance so users can audit important claims
- prefer “I do not know yet” over confident fabrication

---

## AI-assistance operating contract
This section should be added to the canon or adjacent AI-guidance docs as a first-class rule set.

### Principles

#### 1. Honesty over fluency
The assistant must not present guesses, assumptions, or stale planning claims as established fact.

#### 2. Verification before certainty
When a claim can be checked against source code, config, tests, or runtime state, the assistant should verify it before speaking with high confidence.

#### 3. Provenance for important claims
Material architectural, operational, and security claims should be traceable to source files, runtime evidence, or clearly labeled human judgment.

#### 4. Explicit uncertainty
When evidence is incomplete, contradictory, or runtime-only, the assistant should say so plainly and name what remains unknown.

#### 5. No fake resolution
The assistant must not imply a bug is fixed, a finding is current, or a deployment fact is confirmed unless the evidence actually supports that statement.

#### 6. User trust is the product
For Orion, trustworthiness is not decorative. A helpful answer that is unverified or misleading is a failure mode, not a success.

### Required language pattern for architecture and ops claims
Where appropriate, docs and assistants should classify claims using one of these labels:

- **[CONFIRMED]** directly supported by code, config, tests, or runtime evidence
- **[INFERRED]** best interpretation from partial evidence
- **[UNKNOWN]** cannot be established from current evidence
- **[STALE]** once true or previously reported, but no longer reliable without re-checking

### Required assistant behaviors
- Do not flatten contradiction into certainty.
- Do not cite planning docs as runtime truth unless explicitly validated.
- Do not hide missing evidence behind summary language.
- Do not prescribe fixes from disproven premises.
- Do surface the precise blocking unknown when one exists.

### Documentation implication
Any future canon or architecture-map generation should preserve these labels or an equivalent provenance system so the user can tell what is known, what is inferred, and what still requires inspection.

---

## Acceptance criteria

Phase 1 is complete when all of the following are true:

### A. KB count trust defect is resolved
One of these outcomes is implemented consistently across all relevant docs:

- exact runtime-verified count with verification date, or
- all conflicting hard counts removed and replaced with qualified wording

Affected docs are updated so no contradictory values remain.

### B. Blueprint P1.1 is corrected
`ORION-IMPROVEMENT-BLUEPRINT.md` no longer claims that HTTP chat performs intent classification twice or that a second embedding call must be removed. It instead states the routing issue accurately.

### C. Planning-pack docs are freshness-labeled
At minimum, the following docs include a standardized metadata block:

- `ORION-SYSTEM-CANON.md`
- `ORION-IMPROVEMENT-BLUEPRINT.md`
- `ideal-system-plan.md`
- `automation-guardrails-plan.md`
- any other active planning/audit doc retained as current

### D. Stale findings are explicitly resolved or superseded
`automation-guardrails-plan.md` clearly distinguishes:

- open findings
- resolved findings
- superseded findings
- invalidated findings

### E. Rollback systemd units are visibly marked
`ops/server.service` and `ops/telegram.service` include a clear header comment indicating that they are disabled rollback-only units and not the current primary deployment path.

### F. Canon ownership boundary is documented
A single short section exists in the canon or architecture docs that states which information belongs in:

- Canon
- `ARCHITECTURE.md`
- generated architecture map / appendix

### G. AI-assistance trust contract is published
A canon or AI-guidance doc explicitly states that Orion must be honest with users, verify claims when possible, label uncertainty, and preserve provenance for material claims.

### H. Phase 2 is unblocked
A short implementation note exists defining the source inputs for the generator and the first validations to add to `check_doc_drift.py`.

---

## Proposed workstreams

## Workstream 1: Neutralize contradictory factual claims

### Tasks
- Resolve KB chunk count contradictions across all docs.
- Replace unverified runtime counts with qualified wording if runtime SQL verification is not available.
- Sweep for repeated references in planning docs and summaries.

### Notes
This is the highest-value documentation cleanup because it directly affects assistant correctness.

---

## Workstream 2: Correct planning guidance that would cause wrong engineering work

### Tasks
- Update Blueprint P1.1 to describe the real routing issue.
- Add a note tying the correction to the relevant audit finding.
- Review any other planning-pack statements that prescribe actions from stale assumptions.

### Notes
This prevents wasted debugging effort and accidental regression-inducing edits.

---

## Workstream 3: Add freshness and authority metadata to planning docs

### Tasks
- Add a standard header block to planning and canon docs.
- Record status, last validated date, and validation basis.
- Add “authoritative for / not authoritative for” to reduce misuse.

### Standard metadata block
```md
Status: Draft | Active | Partially stale | Superseded | Archived
Last validated: YYYY-MM-DD
Validation basis: source audit | runtime check | mixed
Authoritative for: <scope>
Not authoritative for: <scope>
Superseded by: <doc or none>
```

### Notes
This is low-risk, high-leverage governance work.

---

## Workstream 4: Make deployment-path status visible in the files themselves

### Tasks
- Add header comments to rollback unit files.
- Ensure wording is unambiguous and consistent with `OPERATIONS.md`.

### Suggested header text
```ini
# DISABLED - rollback only.
# Not part of the current primary deployment path.
# Current production path is Docker + supervisord; see OPERATIONS.md.
```

### Notes
This protects future operators and assistants who open the unit file directly.

---

## Workstream 5: Make AI-assistance trust rules explicit

### Tasks
- Add an “AI-assistance operating contract” section to the canon or AI-guidance docs.
- Require claim labels such as Confirmed, Inferred, Unknown, and Stale for material architectural and operational claims.
- State clearly that Orion must be honest with the user, verify where possible, and expose uncertainty instead of smoothing it away.
- Add a brief note on how planning docs should be treated by assistants: useful for direction, not automatic proof.

### Notes
This is not cosmetic language. It is a product-level trust requirement.

---

## Workstream 6: Define the documentation model for Phase 2

### Tasks
- Record the agreed split between canon, narrative architecture, and generated inventories.
- Capture the minimum generator input set.
- Capture the first drift checks to implement.

### Phase 2 starter scope
Generated map should begin with:

- FastAPI route table from `server.py`
- tool registry from `tools.py`
- judge tiers/rules from `judge.py`
- env var matrix from `config.py`
- Docker service summary from `docker-compose.yml`
- systemd/timer summary from `ops/*`
- CI workflow summary from `.github/workflows/*`

---

## File-by-file edit list

## P0 edits

### `README.md`
- Remove one of the conflicting KB chunk counts or replace both with qualified wording.
- Ensure the status table and any intro/system summary agree.

### `ROADMAP.md`
- Replace stale hard KB count if present.
- Keep “Done” and “End state” intact if still valid.

### `SUMMARY.md`
- Replace hard KB count unless runtime-verified.
- Align with whichever wording is chosen for `README.md`.

### `ORION-IMPROVEMENT-BLUEPRINT.md`
- Rewrite P1.1 to reflect the actual issue:
  - classifier metadata exists
  - classifier result is not wired into HTTP routing behavior
- Remove any reference to a second embedding call unless source-backed.
- Add metadata block at top.
- Add or link to AI-assistance trust expectations if this doc directs assistant-facing work.

## P1 edits

### `ORION-SYSTEM-CANON.md`
- Add metadata block.
- Add citations or at least explicit source references for major claims.
- Add a short “AI-assistance operating contract” section or a clear pointer to the doc that owns it.
- Remove or downgrade any uncited “observed deployment shape” claims until sourced.
- Keep it short and principle-focused.

### `CLAUDE.md`
- Optionally strengthen the contract language so it explicitly requires honest uncertainty, evidence-backed claims, and no false confidence.
- Keep behavioral guidance aligned with the canon so the two docs do not diverge.

### `copilot-instructions.md`
- Optionally add a line clarifying that planning docs are not runtime truth unless validated.

### `ideal-system-plan.md`
- Add metadata block.
- Mark it clearly as draft and pre-audit where applicable.
- Add note on relationship to the newer audit-driven blueprint.

### `automation-guardrails-plan.md`
- Add metadata block.
- Add status per finding: Open / Resolved / Superseded / Invalidated.
- Mark at least the known stale items as resolved or superseded.
- Add a short note explaining that the document is historical unless findings remain open.

### `ops/server.service`
- Add rollback-only header comment.

### `ops/telegram.service`
- Add rollback-only header comment.

## P2 edits

### `ARCHITECTURE.md`
- Add or refine a short section explaining where generated inventories will live.
- Keep design rationale here, not in generated output.
- Optionally add a short note that generated inventories should preserve provenance labels when practical.

### `OPERATIONS.md`
- Optionally add a pointer that rollback unit files are retained only for rollback and are annotated as such.

### `CONTRIBUTING.md`
- Optionally tighten “~1200 tests” to a less brittle phrase such as “over 1,100 offline tests” unless you want to keep exact counts maintained.

---

## Commit grouping plan

## Commit 1: Resolve factual contradictions
**Purpose:** remove the most dangerous conflicting claims.

Files:
- `README.md`
- `ROADMAP.md`
- `SUMMARY.md`

Message:
```text
docs: remove contradictory KB chunk counts
```

## Commit 2: Correct incorrect remediation guidance
**Purpose:** stop future wrong fixes.

Files:
- `ORION-IMPROVEMENT-BLUEPRINT.md`

Message:
```text
docs: correct HTTP intent-routing remediation in blueprint
```

## Commit 3: Add freshness metadata to planning pack
**Purpose:** make stale/current status visible.

Files:
- `ORION-SYSTEM-CANON.md`
- `ORION-IMPROVEMENT-BLUEPRINT.md`
- `ideal-system-plan.md`
- `automation-guardrails-plan.md`
- any additional active planning docs

Message:
```text
docs: add validation metadata to planning documents
```

## Commit 4: Publish AI-assistance trust contract
**Purpose:** make honesty and verification explicit product behavior.

Files:
- `ORION-SYSTEM-CANON.md`
- `CLAUDE.md`
- optionally `copilot-instructions.md`

Message:
```text
docs: codify AI assistance honesty and verification rules
```

## Commit 5: Mark rollback-only units
**Purpose:** prevent operator and assistant confusion.

Files:
- `ops/server.service`
- `ops/telegram.service`

Message:
```text
ops: mark legacy systemd units as rollback-only
```

## Commit 6: Document Phase 2 boundary
**Purpose:** define the generator handoff cleanly.

Files:
- `ARCHITECTURE.md`
- `ORION-SYSTEM-CANON.md` or dedicated planning note

Message:
```text
docs: define canon and generated architecture map boundaries
```

## Optional Commit 7: Historical finding cleanup
**Purpose:** make audit follow-up docs usable again.

Files:
- `automation-guardrails-plan.md`

Message:
```text
docs: mark resolved and superseded guardrail findings
```

---

## Risks and mitigations

### Risk 1: Runtime KB count still unknown
**Impact:** one contradiction may be replaced with another later if guessed.

**Mitigation:** prefer qualified wording until runtime SQL verification exists.

### Risk 2: Over-editing canon with generated detail
**Impact:** canon becomes noisy and starts drifting again.

**Mitigation:** keep canon principle-based and citation-backed; move inventories to generated output.

### Risk 3: Historical planning docs lose value if over-normalized
**Impact:** audit history becomes harder to follow.

**Mitigation:** preserve historical findings, but mark current state explicitly.

### Risk 4: File-level annotations drift from ops docs
**Impact:** rollback status becomes inconsistent.

**Mitigation:** keep rollback wording minimal and reference `OPERATIONS.md`.

### Risk 5: AI-trust language stays vague and becomes ceremonial
**Impact:** assistants continue sounding confident without being reliably grounded.

**Mitigation:** encode concrete behaviors, labels, and acceptance criteria rather than aspirational language.

---

## Dependencies and inputs

## Required to complete Phase 1 docs work
None. The documentation hardening can proceed from the source audit already available.

## Optional but useful
- runtime DB count for KB rows if exact numeric language is desired
- confirmation of preferred long-term location for generated architecture output:
  - separate `ARCHITECTURE-MAP.md`, or
  - generated appendix within `ARCHITECTURE.md`

If these are unavailable, Phase 1 can still complete by using qualified wording and a temporary generated-output placeholder decision.

---

## Suggested implementation order

1. Remove contradictory KB counts.
2. Correct Blueprint P1.1.
3. Add metadata blocks to planning docs.
4. Publish AI-assistance trust contract.
5. Mark rollback-only unit files.
6. Record Phase 2 boundary and generator starter scope.
7. Sweep historical audit follow-up docs for stale findings.

---

## Definition of done
Phase 1 is done when a user or assistant can open the docs and reliably answer all of the following without stepping on a rake:

- Which docs are authoritative for what?
- Which claims are confirmed versus inferred?
- Which deployment path is current and which is rollback-only?
- Which planning findings are still open versus already fixed?
- What should the assistant do when evidence is incomplete or contradictory?
- What exact documentation groundwork is complete before generator implementation starts?

If the docs still allow a confident but wrong answer to any of those, Phase 1 is not done.
