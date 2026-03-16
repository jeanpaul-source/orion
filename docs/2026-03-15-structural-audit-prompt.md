# Orion Structural Audit Prompt

> **Created:** 2026-03-15T18:30:00Z
> **Purpose:** Instruct a Claude (Copilot/chat) agent to perform a read-only
> structural audit of the Orion repo. The output feeds a future planning pass.
> **Designed for:** Agent with VS Code workspace file access tools.

---

## Role

You are in **AUDIT MODE ONLY** for the Orion repo. Your sole job is to read
files and produce a structured report.

**You must not:**

- Edit, create, or delete any file.
- Propose commits, branches, or PRs.
- Plan implementation steps.
- Suggest "could also" alternatives or brainstorm.

**You must:**

- Read files directly using workspace tools before making claims about them.
- Cite file paths and line numbers for every factual claim.
- Distinguish between **confirmed** (you read the code/file) and **inferred**
  (you are reasoning from indirect evidence). Use the labels `[CONFIRMED]` and
  `[INFERRED]` inline.
- Say **"I don't know"** when you cannot determine something from the files
  available. Do not guess. Do not fill gaps with plausible-sounding assumptions.
- If a file you expected to exist is missing, say so explicitly.

---

## Honesty Rules

These override all other instructions. Violating them makes the audit useless.

1. **Never fabricate file contents, line numbers, or structural claims.** If you
   haven't read the file, don't describe what's in it. Read it first.
2. **Never present inference as fact.** If you're deducing something (e.g., "this
   is probably the entrypoint because..."), mark it `[INFERRED]` and explain
   your reasoning.
3. **Never round up confidence.** If you checked 3 of 5 files and found a
   pattern, say "3 of 5 checked; pattern holds so far" — not "all files follow
   this pattern."
4. **Contradictions are findings, not problems to resolve.** When two files
   disagree, report both sides with citations. Do not pick a winner unless the
   evidence is unambiguous.
5. **Absence of evidence is not evidence of absence.** If you searched for
   something and didn't find it, say "not found in files searched" — not "does
   not exist."
6. **Acknowledge your limitations.** You have source-file access only, not
   runtime access. You cannot run `docker ps`, `systemctl status`, or query
   live databases. "Runtime truth" in this audit means "what deploy configs and
   code declare," not what is actually running on the server right now.

---

## Goal

Produce a birds-eye report that answers: **What is the actual structure of this
repo, where do its sources of truth disagree, and what does an external planner
need to know to generate a reliable architecture/documentation plan?**

Prioritize source-code evidence over documentation claims.

---

## Prior Work

The file `docs/planning-pack/audit-findings.md` contains 72 verified
code-level findings from a prior audit (safety, routing, knowledge pipeline,
runtime, observability). **Treat it as ground truth for code-level bugs.** Do
not re-audit those findings. Your job is the structural and documentation layer
that the code audit did not cover:

- Which documents are authoritative vs. stale vs. duplicative?
- What are the actual system boundaries and entrypoints?
- What can be auto-generated vs. what must be hand-maintained?
- Where will future AI assistants get confused by contradictions?

Also reference these planning-pack files for context (read them, assess their
accuracy, note where they conflict with source code):

- `docs/planning-pack/ORION-SYSTEM-CANON.md`
- `docs/planning-pack/ORION-2026-BEST-PRACTICES-GAP-ANALYSIS.md`
- `docs/planning-pack/ORION-IMPROVEMENT-BLUEPRINT.md`
- `docs/planning-pack/ORION-VSCODE-COPILOT-FRAMEWORK.md`
- `docs/planning-pack/ORION-PLANNING-PACK-INDEX.md`

---

## Scope — Files to Inspect

Read every file in each group. If a file listed here does not exist, report
that as a finding.

### Group 1: Documentation and canon candidates

| File | Expected role |
| --- | --- |
| `README.md` | Project overview, key files table |
| `ARCHITECTURE.md` | System design, data flow |
| `OPERATIONS.md` | Deploy, .env, systemd, known traps |
| `CONTRIBUTING.md` | Dev workflow, tests, git conventions |
| `ROADMAP.md` | Backlog, future direction |
| `CLAUDE.md` | AI-assistant operating contract |
| `memory/SUMMARY.md` | AI-maintained project state |
| `docs/ideal-system-plan.md` | Long-term vision doc |
| `docs/automation-guardrails-plan.md` | Guardrails planning |

### Group 2: AI-assistant instruction files

| File | Expected role |
| --- | --- |
| `.github/copilot-instructions.md` | Global Copilot system prompt |
| `.github/instructions/python.instructions.md` | Python code conventions |
| `.github/instructions/tests.instructions.md` | Test conventions |
| `.github/instructions/ops.instructions.md` | Ops file conventions |
| `.github/instructions/markdown.instructions.md` | Markdown conventions |
| `.github/instructions/webui.instructions.md` | Web UI conventions |

### Group 3: Core control plane

| File | Key things to note |
| --- | --- |
| `hal/agent.py` | Agent loop, tool dispatch |
| `hal/bootstrap.py` | Client wiring, `dispatch_intent()` |
| `hal/server.py` | FastAPI app, routes, lifespan |
| `hal/main.py` | REPL entrypoint |
| `hal/judge.py` | Tier system, evasion patterns, safe tokens |
| `hal/memory.py` | SQLite session store |
| `hal/intent.py` | Intent classifier, Ollama embeddings |
| `hal/tools.py` | Tool registry, tool definitions |
| `hal/config.py` | Env vars, host registry, defaults |
| `hal/llm.py` | vLLM client |
| `hal/executor.py` | Shell command runner |
| `hal/workers.py` | File/git operations |

### Group 4: Knowledge pipeline

| File | Key things to note |
| --- | --- |
| `harvest/collect.py` | Shell collectors, static docs |
| `harvest/ingest.py` | Embedding, pgvector upsert |
| `harvest/main.py` | Harvest entrypoint |
| `harvest/snapshot.py` | Snapshot writer |
| `harvest/parsers.py` | Doc parsers |
| `hal/knowledge.py` | KB search, remember, categories |

### Group 5: Safety and runtime edge

| File | Key things to note |
| --- | --- |
| `hal/sandbox.py` | Docker sandbox for code execution |
| `hal/web.py` | URL fetch, SSRF protection, search |
| `hal/watchdog.py` | Health checks, alerts, recovery |
| `hal/security.py` | Security event tools |
| `hal/prometheus.py` | Prometheus query client |
| `hal/notify.py` | Notification dispatch |
| `hal/tracing.py` | OpenTelemetry integration |
| `hal/trust_metrics.py` | Audit log analysis |
| `hal/falco_noise.py` | Falco event filtering |

### Group 6: Runtime and deploy

| File | Key things to note |
| --- | --- |
| `docker-compose.yml` | Container services, ports, volumes |
| `Dockerfile` | Main image build |
| `Dockerfile.sandbox` | Sandbox image build |
| `.env.example` | Documented env vars |
| `Makefile` | Build/test/deploy targets |
| `pyproject.toml` | Package metadata, tool config, entry points |
| `package.json` | Node.js toolchain (commitlint) |
| `commitlint.config.mjs` | Commit message rules |
| `pytest.ini` | Test configuration |
| `requirements.txt` | Production dependencies |
| `requirements-dev.txt` | Dev dependencies |
| `requirements-eval.txt` | Eval dependencies |

### Group 7: Systemd units and ops scripts

| File | Key things to note |
| --- | --- |
| `ops/server.service` | HAL server unit |
| `ops/telegram.service` | Telegram bot unit |
| `ops/vllm.service` | vLLM inference unit |
| `ops/harvest.service` | Harvest oneshot unit |
| `ops/harvest.timer` | Harvest schedule |
| `ops/watchdog.service` | Watchdog oneshot unit |
| `ops/watchdog.timer` | Watchdog schedule |
| `ops/gpu-metrics.service` | GPU metrics unit |
| `ops/gpu-metrics.timer` | GPU metrics schedule |
| `ops/supervisord.conf` | Process supervisor config |

### Group 8: CI/CD and quality

| File | Key things to note |
| --- | --- |
| `.github/workflows/test.yml` | CI test pipeline |
| `.github/workflows/build.yml` | Build pipeline |
| `.github/workflows/deploy.yml` | Deploy pipeline |
| `.github/workflows/dependabot-automerge.yml` | Dependabot automation |
| `.github/dependabot.yml` | Dependency update config |
| `.github/pull_request_template.md` | PR template |
| `scripts/check_doc_drift.py` | Doc-drift CI check |
| `scripts/update_coverage_threshold.py` | Coverage threshold updater |

### Group 9: Web UI

| File | Key things to note |
| --- | --- |
| `hal/static/index.html` | Web UI markup |
| `hal/static/style.css` | Web UI styles |
| `hal/static/app.js` | Web UI logic |

### Catch-all

If you encounter files during inspection that are architecturally significant
but not listed above, include them in your report. Do not silently skip them.

---

## Questions to Answer

Answer these in order. A–C are required. D–H depend on what you find in A–C.
If you run out of context window, prioritize A–C.

### A. Truth Layers

What documents currently function as each of these roles? A single document
may serve multiple roles. Some roles may have no document, or competing
documents.

- **Architecture truth:** Describes what the system is and how parts connect.
- **Operational truth:** Describes how to deploy, configure, and operate.
- **Planning truth:** Describes what to build next and why.
- **AI-assistant guidance:** Instructs AI tools on rules and conventions.

For each document you assign to a role, state whether it is **current**
(matches source code), **partially stale** (some claims outdated), or
**stale** (majority outdated). Cite specific discrepancies.

### B. Drift and Contradictions

List every case where two or more files disagree about the same fact. Format:

| Severity | Files | What they disagree about | Which appears correct and why |
| --- | --- | --- | --- |

Severity: HIGH (would cause wrong action if trusted), MED (confusing but not
dangerous), LOW (cosmetic or minor).

### C. Runtime Boundaries

What are the actual system entrypoints and boundaries **as declared in source
code**? For each, cite the file and line where you confirmed it.

- Docker services (from `docker-compose.yml`)
- Systemd units (from `ops/*.service`, `ops/*.timer`)
- FastAPI routes (from `hal/server.py`)
- CLI entrypoints (from `hal/main.py`, `hal/__main__.py`, `harvest/__main__.py`)
- Tool surfaces (from `hal/tools.py` tool registry)
- Judge tier boundaries (from `hal/judge.py`)
- Sandbox boundaries (from `hal/sandbox.py`, `Dockerfile.sandbox`)
- Knowledge pipeline stages (from `harvest/` modules)
- Makefile targets (from `Makefile`)
- CI workflows (from `.github/workflows/`)

### D. Auto-Generatable Architecture Map

What parts of the system can be **mechanically discovered** from source files
by a script or agent? For each, name the source file and the extraction
method:

- FastAPI route definitions
- Python module import graph
- Tool registrations and their schemas
- Judge action tiers and command rules
- Env vars and config fields (required vs. optional, defaults)
- Docker services, ports, volumes, networks
- Systemd unit metadata (type, exec, dependencies)
- Makefile targets and their dependencies
- CI workflow triggers and steps

### E. Hand-Maintained Sections

What architectural facts **cannot** be safely auto-generated and must remain
in a hand-maintained document? Examples that may or may not apply — verify:

- System invariants (e.g., "Ollama is embeddings-only")
- Design rationale (why the Judge exists, why no bypass)
- Trust model semantics
- Known operational traps
- Future direction and non-goals

### F. Minimum Generator Input Set

What is the smallest set of source files a generator script would need to
read to build a current, accurate architecture map? List them with what each
contributes.

### G. Top Confusion Risks for AI Assistants

What contradictions or ambiguities in the current docs would most likely cause
a future AI assistant to take wrong action? Rank by likelihood × impact.

### H. Open Unknowns

What questions about the repo structure or runtime behavior **cannot be
answered from source files alone** and would require runtime inspection or
operator confirmation? List them explicitly so the planner knows what to
verify.

---

## Report Format

Target **1500–3000 words**. Use bullet points, not prose paragraphs. Cite
files as `path/to/file.py:L123` format.

```
## 1. TRUTH LAYERS
...

## 2. DRIFT AND CONTRADICTIONS
| Severity | Files | Disagreement | Likely correct |
| --- | --- | --- | --- |
...

## 3. RUNTIME BOUNDARIES
...

## 4. AUTO-GENERATABLE SECTIONS
...

## 5. HAND-MAINTAINED SECTIONS
...

## 6. MINIMUM GENERATOR INPUTS
...

## 7. AI-ASSISTANT CONFUSION RISKS
...

## 8. OPEN UNKNOWNS
...

## 9. FINAL ASSESSMENT
State clearly: Can Orion support a canon doc + auto-generated architecture
map model right now? What are the blockers if not? Be direct.
```

---

## Reading Strategy

You have source access only, not runtime. To manage context efficiently:

1. Read the first ~150 lines of each documentation file (Group 1, 2) to
   assess structure and currency.
2. For code files (Groups 3–5), read the module docstring + imports + key
   function/class signatures. Go deeper only when you find a contradiction
   or need to verify a specific claim.
3. For deploy files (Groups 6–8), read fully — they are short.
4. For the web UI (Group 9), skim for entrypoint connections (API URLs, etc.)
5. Cross-reference `scripts/check_doc_drift.py` — it already codifies some
   truth relationships. Note what it checks and what it misses.
6. Cross-reference the planning-pack files against what you find in source.
   Note where they are accurate, where they are stale, and where they make
   claims you cannot verify.

**Stop reading more files once you have enough evidence to answer A–H with
citations. Do not read every line of every file.**
