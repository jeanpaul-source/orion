# Instruction & Auto-Loaded Document Audit

**Date:** March 11, 2026
**Purpose:** Line-by-line audit of every file loaded into the AI assistant context
window. Flags duplications, redundancies, contradictions, stale info, bloat, and
things that are just wrong.

**Files audited (10 total):**

| # | File | Lines | Loaded when |
|---|---|---|---|
| 1 | `.github/copilot-instructions.md` | 146 | Every conversation |
| 2 | `CLAUDE.md` | ~200 | Every conversation (attachment) |
| 3 | `.github/instructions/python.instructions.md` | 30 | Editing `hal/**/*.py`, `harvest/**/*.py`, etc. |
| 4 | `.github/instructions/tests.instructions.md` | 28 | Editing `tests/**/*.py` |
| 5 | `.github/instructions/ops.instructions.md` | 36 | Editing `ops/**`, `Dockerfile`, etc. |
| 6 | `.github/instructions/webui.instructions.md` | 26 | Editing `hal/static/**`, `*.html`, etc. |
| 7 | `ARCHITECTURE.md` | ~310 | Every conversation (attachment) |
| 8 | `OPERATIONS.md` | 416 | Every conversation (attachment) |
| 9 | `CONTRIBUTING.md` | 339 | Every conversation (attachment) |
| 10 | `ROADMAP.md` | 162 | Every conversation (attachment) |

**Total context consumed before the user types a single word:** ~1,700 lines / ~50,000+ tokens

---

## Part 1 — Duplications (same information appears in multiple files)

Each entry shows what's duplicated, where it appears, and what to do about it.

---

### D1 — "Explain before acting / root cause, not symptom" rule

**Appears in:**

- `CLAUDE.md` §"REQUIRED FORMAT" (lines 10–42) — full formal block with template
- `CLAUDE.md` §"How I (Claude) Work With the Operator" rule 1 (lines 80–87) — restated
- `copilot-instructions.md` §"Communication contract" rule 1 (lines 11–13) — restated again
- `copilot-instructions.md` §"Conventions" (lines 80–83) — summarized a fourth time
- `CONTRIBUTING.md` §"Before making any change" (lines 7–21) — restated a fifth time
- Copilot system-level setting (injected automatically): "EXPLAIN BEFORE ACTING"

**Count:** 6 appearances of the same rule.

**Recommendation:** Keep one canonical version. `CLAUDE.md` is the right home since it's
the AI operating contract. Remove from `copilot-instructions.md` (lines 11–13 and 80–83)
and `CONTRIBUTING.md` (link to CLAUDE.md instead of restating). The system-level Copilot
setting covers it for sessions without attachments.

---

### D2 — "One change at a time" rule

**Appears in:**

- `CLAUDE.md` §"REQUIRED FORMAT" (lines 33–37) — detailed version
- `CLAUDE.md` §"Rules" rule 2 (line 89) — restated
- `copilot-instructions.md` §"Communication contract" rule 2 (lines 14–16) — restated
- `CONTRIBUTING.md` §"Before making any change" item 3 (line 18) — restated

**Count:** 4 appearances.

**Recommendation:** Same as D1 — keep in `CLAUDE.md`, remove from other files.

---

### D3 — "No band-aids / no workarounds" rule

**Appears in:**

- `CLAUDE.md` §"Rules" rule 3 (lines 91–93) — canonical version
- `copilot-instructions.md` §"Communication contract" rule 3 (lines 17–18) — restated
- `copilot-instructions.md` §"Conventions" (lines 85–86) — restated again

**Count:** 3 appearances.

**Recommendation:** Keep in `CLAUDE.md` only.

---

### D4 — "Ollama is embeddings-only / OLLAMA_NUM_GPU=0 / VRAM OOM" constraint

**Appears in:**

- `copilot-instructions.md` §"LLM backend split" (lines 56–62) — full explanation
- `ARCHITECTURE.md` §"LLM backend split" (lines 195–210) — full explanation (identical content)
- `OPERATIONS.md` §"Prerequisites" services table (line 22) — brief mention
- `OPERATIONS.md` §"Ollama GPU flag" (lines 275–285) — detailed explanation with verify command
- `OPERATIONS.md` §"Key design constraints" bullet 1 (line 347) — restated
- `CONTRIBUTING.md` §"Key design constraints" bullet 1 (line 328) — restated
- `CLAUDE.md` §"Current State" LLM bullet (line 131) — brief mention
- `ROADMAP.md` §"Done" LLM paragraph (line 15) — brief mention
- `ops.instructions.md` (line 12) — brief mention
- `python.instructions.md` (line 14) — brief mention

**Count:** 10 appearances across 8 files.

**Recommendation:** This is the single most repeated fact in the entire project. Keep
the authoritative version in `OPERATIONS.md` §"Ollama GPU flag" (it has the verify command).
Keep the one-liner in `ops.instructions.md` (relevant when editing deployment files).
Remove from `copilot-instructions.md`, `CONTRIBUTING.md` constraint list, and `ROADMAP.md`.
`ARCHITECTURE.md` can keep its design rationale version since it explains *why*, but
the `copilot-instructions.md` version is a pure copy of it.

---

### D5 — "Prometheus is port 9091, not 9090" constraint

**Appears in:**

- `copilot-instructions.md` — not explicitly stated but implied in architecture section
- `OPERATIONS.md` §"Prerequisites" table (line 24) — with bold note
- `OPERATIONS.md` §"Known traps" (lines 373–376) — detailed explanation
- `OPERATIONS.md` §"Key design constraints" bullet 2 (line 348) — restated
- `CONTRIBUTING.md` §"Key design constraints" bullet 2 (line 329) — identical wording
- `ops.instructions.md` (line 13) — mentioned

**Count:** 5 appearances across 4 files.

**Recommendation:** Keep in `OPERATIONS.md` §"Known traps" (canonical) and
`ops.instructions.md` (contextual). Remove from `CONTRIBUTING.md` constraints
(link to OPERATIONS.md instead).

---

### D6 — "vLLM needs VLLM_USE_FLASHINFER_SAMPLER=0 and PYTORCH_CUDA_ALLOC_CONF"

**Appears in:**

- `OPERATIONS.md` §"vLLM" (lines 171–175) — detailed with explanation
- `OPERATIONS.md` §"Key design constraints" bullet 3 (lines 349–351) — restated
- `CONTRIBUTING.md` §"Key design constraints" bullet 3 (lines 330–332) — identical restatement
- `ops.instructions.md` (line 14) — mentioned

**Count:** 4 appearances across 3 files.

**Recommendation:** Keep in `OPERATIONS.md` §"vLLM" (canonical) and `ops.instructions.md`.
Remove from `CONTRIBUTING.md` (it's a copy).

---

### D7 — "Judge has no bypass / no force=True" constraint

**Appears in:**

- `copilot-instructions.md` §"Judge" (lines 68–71) — brief version
- `ARCHITECTURE.md` §"The Judge" (lines 119–128) — design rationale version
- `OPERATIONS.md` §"Key design constraints" bullet 4 (lines 352–354) — restated
- `CONTRIBUTING.md` §"Key design constraints" bullet 4 (lines 333–336) — identical
- `CLAUDE.md` §"Current State" Judge bullet (line 145) — brief mention
- `python.instructions.md` (line 12) — brief mention

**Count:** 6 appearances across 6 files.

**Recommendation:** Keep in `ARCHITECTURE.md` (design rationale) and `python.instructions.md`
(contextual reminder when coding). Remove from `copilot-instructions.md`, `OPERATIONS.md`,
and `CONTRIBUTING.md`.

---

### D8 — Reference docs table

**Appears in:**

- `copilot-instructions.md` §"Reference docs" (lines 26–33) — 5-row table
- `CLAUDE.md` §"Documentation" (lines 97–107) — 7-row table (superset)
- `README.md` §"Documentation" (lines 105–113) — 6-row table
- `CONTRIBUTING.md` §"Before making any change" (lines 7–8) — refers to CLAUDE.md

**Count:** 3 full tables + 1 reference, all listing the same docs.

**Recommendation:** Keep in `README.md` (the project entry point) only. All other files
should say "See README.md for the documentation index." Three identical tables is pure waste.

---

### D9 — Key files table

**Appears in:**

- `copilot-instructions.md` §"Key files" (lines 122–146) — 18-row table
- `README.md` §"Key files" (lines 124–147) — 27-row table (superset)
- `CLAUDE.md` §"Current State" (lines 130–165) — inline list covering same files

**Count:** 3 overlapping file inventories.

**Recommendation:** Keep in `README.md` (most complete). Remove from
`copilot-instructions.md` entirely — it's 25 lines of context that duplicates README.

---

### D10 — Test commands and test counts

**Appears in:**

- `copilot-instructions.md` §"Key commands" (lines 96–99) — test commands
- `CONTRIBUTING.md` §"Tests" (lines 66–88) — detailed test section with counts
- `CLAUDE.md` §"Current State" (line 165) — "1176 offline tests"
- `README.md` §"Current state" (line 56) — "1176 offline tests"
- `ROADMAP.md` §"Done" tooling paragraph (line 36) — "1,176 offline tests"
- `python.instructions.md` (lines 18–19) — "Run make test after any change"
- `tests.instructions.md` — implicit (tests section)

**Count:** Test count "1176" appears 4 times. Test commands appear 3 times.

**Recommendation:** Keep test commands in `CONTRIBUTING.md` (canonical dev workflow doc)
and `python.instructions.md` (contextual). Remove from `copilot-instructions.md`. Test
counts are stale the moment a test is added — keep only in `CONTRIBUTING.md` and accept
it will drift.

---

### D11 — Git workflow / conventional commits / co-author tag

**Appears in:**

- `copilot-instructions.md` §"Conventions" (lines 88–94) — summary
- `CONTRIBUTING.md` §"Git workflow" (lines 150–240) — full canonical version

**Count:** 2 appearances.

**Recommendation:** Keep in `CONTRIBUTING.md` only. `copilot-instructions.md` is
summarizing what's already there.

---

### D12 — Harvest commands

**Appears in:**

- `copilot-instructions.md` §"Key commands" (lines 105–107) — 2 lines
- `CONTRIBUTING.md` §"Harvest" (lines 261–270) — identical commands
- `OPERATIONS.md` §"Harvest" (lines 218–224) — identical commands

**Count:** 3 appearances.

**Recommendation:** Keep in `OPERATIONS.md` (authoritative ops doc). Remove from
`copilot-instructions.md`.

---

### D13 — Deploy commands

**Appears in:**

- `copilot-instructions.md` §"Key commands" (lines 109–111) — 2 lines
- `CONTRIBUTING.md` §"Deploy" (lines 272–300) — full version
- `OPERATIONS.md` §"HAL container" (lines 228–245) — full version

**Count:** 3 appearances.

**Recommendation:** Keep in `OPERATIONS.md`. Remove from `copilot-instructions.md`.

---

### D14 — Architecture overview (component map / intent routing / data flow)

**Appears in:**

- `copilot-instructions.md` §"Architecture" (lines 42–53) — condensed version
- `ARCHITECTURE.md` §"Component map" + §"Data flow" (lines 7–95) — full canonical version
- `CLAUDE.md` §"Current State" (lines 130–165) — restated as bullets

**Count:** 3 versions of the same architecture overview.

**Recommendation:** Keep in `ARCHITECTURE.md` (that's literally what it's for). Remove
from `copilot-instructions.md` entirely. Trim `CLAUDE.md` "Current State" to just list
what's active/broken, not re-describe the architecture.

---

### D15 — "Key design constraints" section

**Appears in:**

- `OPERATIONS.md` §"Key design constraints" (lines 345–354) — 4 bullets
- `CONTRIBUTING.md` §"Key design constraints" (lines 325–336) — identical 4 bullets

**Count:** Exact duplicate across 2 files.

**Recommendation:** Keep in `OPERATIONS.md` (ops decisions belong in ops doc). Remove
from `CONTRIBUTING.md` — replace with "See OPERATIONS.md §Key design constraints."

---

## Part 2 — Redundant Rules (AI already knows this)

Things that are stated as rules but would be followed by a competent AI model anyway,
wasting context space without changing behavior.

---

### R1 — "Use descriptive test names: `test_judge_blocks_rm_rf` not `test_judge_1`"

**File:** `tests.instructions.md` line 12

**Why it's redundant:** This is standard pytest convention. Any AI model trained on
Python codebases already follows this. The existing tests in the project all use
descriptive names, so the pattern is also visible from context.

**Recommendation:** Remove. If the AI produces bad test names, that's a one-off correction,
not a persistent rule.

---

### R2 — "Test behavior, not implementation"

**File:** `tests.instructions.md` line 11

**Why it's redundant:** This is a universal testing best practice that AI models already
follow. It's advice, not a project-specific rule.

**Recommendation:** Remove.

---

### R3 — "Type hints on all new function signatures"

**File:** `python.instructions.md` line 9

**Why it's redundant:** Standard modern Python practice. The codebase already uses type
hints throughout. mypy is in the CI pipeline (`make typecheck`). The AI model would add
them anyway and mypy would catch missing ones.

**Recommendation:** Remove.

---

### R4 — "Imports: stdlib first, then third-party, then local. Alphabetical"

**File:** `python.instructions.md` line 10

**Why it's redundant:** This is PEP 8 / isort standard. Ruff enforces this automatically
(rule I001 is mentioned in `CONTRIBUTING.md`). The pre-commit hook catches violations.

**Recommendation:** Remove. Ruff handles this mechanically.

---

### R5 — "Dark theme, monospace-rooted design. Maintain visual consistency."

**File:** `webui.instructions.md` line 11

**Why it's redundant:** The existing CSS files in `hal/static/` define the dark theme.
Any AI editing those files will see the existing styles and maintain consistency. This
instruction doesn't add information the code itself doesn't already convey.

**Recommendation:** Remove or replace with something specific like "Do not introduce a
light theme — there is no toggle for it."

---

### R6 — "Format with ruff (not black)"

**File:** `python.instructions.md` line 8

**Why it's redundant:** `pyproject.toml` configures ruff, the Makefile targets use ruff,
the pre-commit hooks run ruff. There is no black configuration in the project. The AI
will use whatever formatter the project is configured with.

**Recommendation:** Remove.

---

## Part 3 — Contradictions and Conflicts

---

### C1 — Test count inconsistency

**Files and values:**

- `CONTRIBUTING.md` line 70: "1211 tests total"
- `CONTRIBUTING.md` line 75: "1176 offline tests"
- `CLAUDE.md` line 165: "1176 offline tests"
- `README.md` line 56: "1176 offline tests"
- `ROADMAP.md` line 36: "1,176 offline tests"
- `copilot-instructions.md` line 99 (comment): "no Ollama needed"

**The issue:** `CONTRIBUTING.md` says "1211 tests total" (1176 + 35 intent), but the
other three docs only mention 1176. The numbers may also be stale — any time a test is
added or removed, all four files are wrong.

**Recommendation:** Stop hardcoding test counts in docs. Replace with "Run `make test`
to see current count." If you want a number, keep it in exactly one place
(`CONTRIBUTING.md`) and accept it will be approximate.

---

### C2 — KB chunk count inconsistency

**Files and values:**

- `CLAUDE.md` line 143: "~19,900 chunks"
- `README.md` line 28: "~19,900 chunks"
- `README.md` table line 54: "~17,250 chunks, 18 categories"
- `ROADMAP.md` line 12: "~19,900 chunks"
- `ARCHITECTURE.md`: not stated directly

**The issue:** README.md contradicts itself — "~19,900 chunks" in line 28 vs "~17,250"
in the status table on line 54. One of these is stale.

**Recommendation:** Keep one approximate number in one place. This number changes every
harvest run — it doesn't belong in 4 files.

---

### C3 — README.md status table is stale

**File:** `README.md` lines 55–62

**The issue:** The status table says:

- "Autonomous remediation | Not yet built" — but ROADMAP.md says it was delivered Mar 5, 2026
- "Web UI / Voice interfaces | Not yet built" — but Web UI is working (documented everywhere else)
- "Trust evolution | Not yet built" — but ROADMAP.md says fully delivered Mar 5, 2026

This table hasn't been updated since the early stages of the project. It gives
the opposite impression of the current state.

**Recommendation:** Update the table to match reality, or replace it with a link to
ROADMAP.md which is the authoritative source for what's done.

---

### C4 — SESSION_FINDINGS.md reference doesn't exist

**File:** `README.md` line 112 references `SESSION_FINDINGS.md`
**File:** `copilot-instructions.md` line 86 references `SESSION_FINDINGS.md`

**The issue:** The workspace directory listing shows no `SESSION_FINDINGS.md` file at the
root. There is `notes/session-findings-archive.md` (referenced correctly in CLAUDE.md).
The README and copilot-instructions point to a nonexistent file.

**Recommendation:** Fix the references to point to `notes/session-findings-archive.md`,
or remove them if the content is no longer relevant.

---

### C5 — "Grafana Tempo receiver not yet deployed (planned)"

**File:** `ARCHITECTURE.md` §"Observability" tracing section (line ~260)

**The issue:** This says Tempo is "not yet deployed (planned)." But `OPERATIONS.md` has
a full "Tracing (OTel → Grafana Tempo)" section with deploy commands, verify steps, and
retention config. Tempo IS deployed. The ARCHITECTURE.md text is stale.

**Recommendation:** Update the ARCHITECTURE.md line to reflect that Tempo is deployed.

---

### C6 — Two conflicting interaction philosophies

**Source 1:** Copilot system settings (injected by user preferences): "The user is
learning to code. Explain simply. Teach while working. No jargon without definition."

**Source 2:** `CLAUDE.md` §"REQUIRED FORMAT": Formal proposal blocks with Item N, root
cause analysis, confidence levels, stop-and-wait before every code change.

**The issue:** These describe two fundamentally different interaction modes. One is a
patient teacher who explains things in plain language. The other is a formal engineering
review process with structured proposal templates. The AI tries to do both simultaneously,
which makes interactions feel stiff and slow for simple tasks, and insufficiently formal
for complex ones.

**Recommendation:** Choose one as the default, use the other for specific situations.
Suggested approach: teach-mode is the default. For changes to critical files (judge.py,
config.py, deployment files), elevate to formal proposal mode. This is what Anthropic
calls "risk-proportional" — match the ceremony to the stakes.

---

## Part 4 — Bloat (information that wastes context without helping)

---

### B1 — Full ARCHITECTURE.md loaded every conversation (~310 lines)

**The issue:** Architecture details are only needed when working on architecture. Loading
310 lines about the Judge tier system, KB pipeline, security stack, memory design rationale,
and observability span names into every conversation — including "fix this typo" or "what
does this error mean" — wastes context.

**Recommendation:** Do NOT auto-attach ARCHITECTURE.md. The AI can read it on demand when
working on relevant files. Put a 2-line summary in copilot-instructions.md and let the AI
`read_file` when it needs depth.

---

### B2 — Full OPERATIONS.md loaded every conversation (~416 lines)

**The issue:** Same problem. The full `.env` reference table, systemd unit deploy
procedures, Tempo setup steps, and known traps are only relevant during ops work. 416
lines of ops details consume context on every question, even pure code questions.

**Recommendation:** Do NOT auto-attach OPERATIONS.md. The AI can read it when it needs it.
The critical constraints (Ollama GPU, Prometheus port) can go in a 5-line block in
copilot-instructions.md.

---

### B3 — Full CONTRIBUTING.md loaded every conversation (~339 lines)

**The issue:** Dev setup instructions, pip-compile commands, eval harness details, full
git workflow docs — all loaded every conversation. Most of this is only relevant when
setting up a dev environment or doing a release.

**Recommendation:** Do NOT auto-attach CONTRIBUTING.md. Key commands (test, lint) should be
in copilot-instructions.md. Everything else is on-demand.

---

### B4 — Full ROADMAP.md loaded every conversation (~162 lines)

**The issue:** The roadmap is a record of what's been done and what's planned. It adds
zero value to a coding conversation. The AI doesn't need to know the delivery date of
trust evolution to fix a bug.

**Recommendation:** Do NOT auto-attach ROADMAP.md. The AI can read it if asked "what's on
the roadmap?"

---

### B5 — CLAUDE.md "Current State" section is ~70 lines of architecture recap

**File:** `CLAUDE.md` lines 120–165

**The issue:** This section restates information already in ARCHITECTURE.md, OPERATIONS.md,
and README.md. It lists every tool, every interface, every feature. It was probably useful
when those docs didn't exist yet, but now it's a maintenance burden that drifts (see C1, C2).

**Recommendation:** Shrink to ~10 lines: what branch is active, what's deployed, what's
currently broken. Link to ARCHITECTURE.md for the full picture. The current 70-line version
is a stale copy that will keep contradicting the source docs.

---

### B6 — copilot-instructions.md tries to be a mini-version of every other doc

**File:** `.github/copilot-instructions.md` — all 146 lines

**The issue:** This file contains:
- A condensed copy of CLAUDE.md's rules (lines 11–23)
- A condensed copy of ARCHITECTURE.md (lines 42–66)
- A condensed copy of the Judge design (lines 68–71)
- A condensed copy of git workflow from CONTRIBUTING.md (lines 88–94)
- A condensed copy of commands from CONTRIBUTING.md + OPERATIONS.md (lines 96–111)
- A condensed copy of the key files table from README.md (lines 122–146)
- A reference table pointing to the docs it just summarized (lines 26–33)

It is, by design, a summary of summaries. But because the full docs are ALSO attached
to every conversation, the summary duplicates what's already in the context window.

**Recommendation:** If the full docs stay as attachments, this file should be ~30 lines:
project name, what it does, key commands (test, lint, format), and the 4–5 critical
constraints. Nothing else. If the full docs are removed as attachments (recommended per
B1–B4), then this file should be ~50–80 lines with just enough to orient the AI, plus
"read X for depth" pointers.

---

### B7 — copilot-instructions.md "Key files" table repeats README.md

**File:** `copilot-instructions.md` lines 122–146

**The issue:** 25 lines listing files the AI can discover by reading the workspace
structure. The README has a more complete version. GitHub's own documentation says
custom instructions should not contain "File-by-file descriptions of the codebase."

**Recommendation:** Remove entirely. The AI can `list_dir` or `semantic_search`.

---

## Part 5 — Stale or Wrong Information

---

### S1 — README.md status table is wrong (described in C3)

Three features marked "Not yet built" that are actually shipped. This is the most
user-visible staleness in the project.

---

### S2 — "Grafana Tempo receiver not yet deployed" (described in C5)

ARCHITECTURE.md says planned; OPERATIONS.md says deployed. One is wrong.

---

### S3 — SESSION_FINDINGS.md path wrong (described in C4)

Two files reference a nonexistent path.

---

### S4 — CLAUDE.md mentions `hal/_unlocked/`

**File:** `CLAUDE.md` line 120: "nothing remains in `hal/_unlocked/` except the empty
`__init__.py`"

**The issue:** This refers to a staged-unlock system from early development. If
`_unlocked/` only contains an empty `__init__.py`, this line is irrelevant historical
context that tells the AI nothing useful.

**Recommendation:** Remove the mention entirely — it's a relic.

---

### S5 — CLAUDE.md "observability aid" sentence is orphaned

**File:** `CLAUDE.md` line 72: "Observability aid: I will also emit structured logs with
session_id and trace correlation for each approved change when running code paths, and I
will update README and SESSION_FINDINGS as I go to prevent documentation drift."

**The issue:** This sentence appears between the CLAUDE.md maintenance rule and the "How
I Work With the Operator" section. It reads like a self-commitment from a previous session
that was pasted in and never cleaned up. "I will update SESSION_FINDINGS" — but
SESSION_FINDINGS.md doesn't exist at the path implied. The sentence describes operational
behavior, not a rule. It doesn't fit in a rules document.

**Recommendation:** Remove. If structured logging is desired, it should be a rule
("Always include session_id in log messages") not a first-person commitment.

---

### S6 — `CONTRIBUTING.md` §"Key design constraints" is a full copy of `OPERATIONS.md`

**File:** `CONTRIBUTING.md` lines 325–336

**The issue:** Four bullets that are word-for-word identical to `OPERATIONS.md` lines
345–354. This guarantees they will diverge when one is updated and the other isn't.

**Recommendation:** Replace with: "See [OPERATIONS.md](OPERATIONS.md#key-design-constraints)
for load-bearing configuration constraints."

---

## Part 6 — Summary of Recommendations

### Immediate (zero risk, pure cleanup)

1. **Fix README.md status table** — update the three "Not yet built" items that are shipped (C3)
2. **Fix SESSION_FINDINGS.md references** — correct path in README.md and copilot-instructions.md (C4)
3. **Fix ARCHITECTURE.md Tempo status** — remove "not yet deployed (planned)" (C5)
4. **Remove stale content from CLAUDE.md** — `_unlocked/` mention (S4), orphaned observability sentence (S5)
5. **Pick one test count** — remove hardcoded "1176" from all files except CONTRIBUTING.md (C1)
6. **Pick one KB chunk count** — remove from all files except one, fix the README contradiction (C2)

### Medium effort (reduces context bloat significantly)

7. **Stop auto-attaching the four reference docs** — ARCHITECTURE.md, OPERATIONS.md, CONTRIBUTING.md, ROADMAP.md should NOT be Copilot attachments. The AI reads them on demand. This saves ~1,200 lines of context per conversation.
8. **Slim copilot-instructions.md to ~50 lines** — project summary, key commands, critical constraints, doc pointers. Remove everything that duplicates CLAUDE.md or the reference docs.
9. **Slim CLAUDE.md "Current State" to ~10 lines** — branch, deployment status, known issues. Link to ARCHITECTURE.md for the full picture.
10. **Remove "Key design constraints" from CONTRIBUTING.md** — link to OPERATIONS.md (D15, S6)
11. **Remove the key files table from copilot-instructions.md** — it duplicates README.md (D9, B7)

### Requires a design decision (C6 — interaction mode)

12. **Decide on risk-proportional proposal mode** — Formal CLAUDE.md-style proposals for high-risk changes (Judge, config, deployment, architecture). Simple explain-and-proceed for low-risk changes (typos, tests, docs, formatting). This is the single highest-impact change for workflow efficiency.

### What would remain after all recommendations

| File | Purpose | Approx lines |
|---|---|---|
| `copilot-instructions.md` | Orientation: what is Orion, key commands, critical constraints, doc pointers | ~50 |
| `CLAUDE.md` | AI operating contract: proposal format for high-risk changes, rules, current status | ~80 |
| `python.instructions.md` | Python-specific: Judge is sacred, use structured logging, run tests after changes | ~12 |
| `tests.instructions.md` | Test-specific: offline tests, use conftest.py fixtures, explain failures | ~12 |
| `ops.instructions.md` | Ops-specific: high-risk zone warning, key constraints, rollback commands | ~20 |
| `webui.instructions.md` | Web-specific: vanilla JS, no build step, dark theme | ~10 |

**Total always-loaded context:** ~130 lines (down from ~1,700)
**Reduction:** ~92%
