# Orion Engineering Practices — Session Prompts

This file contains self-contained prompts for multi-chat engineering sessions.
Each session prompt is a single block designed to be copy-pasted into a fresh
Copilot Chat window. The AI in that window gets full project context, immutable
operating rules, and exactly 2 scoped items to complete.

**How to use:**

1. Open a new Copilot Chat window
2. Copy the entire session block (from `# Session N` to the next `---` divider)
3. Paste it as your first message
4. The AI will read the referenced files, follow the rules, implement the items
5. At the end it will produce a HANDOFF block and generate the next session's prompt
6. Paste the next session's prompt into a new chat window and repeat

**Maintenance:** After each session completes, update the MASTER BACKLOG checkboxes
in ALL subsequent session prompts. The completing session's HANDOFF block tells you
what to mark done.

---

## Session 1 — Fix CI + Dependency Pinning

## PROJECT GROUND TRUTH

Orion is a homelab AI assistant at `/home/jp/orion`. Python 3.12, venv at `.venv/`.
It uses vLLM (chat), Ollama (embeddings only), pgvector (KB), Prometheus (metrics).
The repo is `jeanpaul-source/orion` on GitHub, branch `main`.

### Key commands

```bash
make lint         # ruff check hal/ tests/ harvest/ eval/
make lint-md      # pre-commit run markdownlint-cli2 --all-files
make format       # ruff format
make test         # pytest --ignore=tests/test_intent.py (530 offline tests)
make test-full    # full suite including 35 intent tests (needs live Ollama)
make typecheck    # mypy hal/ (warn-only, currently 13 errors in 8 files)
make coverage     # pytest-cov
```

### Required reading — read these files FIRST before any work

- `CLAUDE.md` — mandatory format before every code change
- `CONTRIBUTING.md` — git workflow, test commands, commit conventions
- `notes/engineering-practices-audit.md` — living reference for engineering gaps

### Files you will modify in this session (current contents below for reference)

**`.github/workflows/test.yml` (CURRENT — this is what's broken):**

```yaml
name: Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        # azure-ai-evaluation is excluded — it's only needed for eval/ (run manually on server)
        # intent tests (test_intent.py) are excluded — they require a live Ollama instance
        run: pip install -r requirements.txt pytest ruff mypy

      - name: Lint
        run: ruff check .

      - name: Format check
        run: ruff format --check .

      - name: Type check (warn-only)
        run: mypy hal/
        continue-on-error: true

      - name: Test (offline)
        run: pytest tests/test_judge.py tests/test_memory.py tests/test_agent_loop.py -v
```

**`Makefile` (CURRENT — do not modify, use these targets):**

```makefile
.PHONY: lint lint-md format test test-full coverage typecheck

lint:
.venv/bin/ruff check hal/ tests/ harvest/ eval/

lint-md:
pre-commit run markdownlint-cli2 --all-files

format:
.venv/bin/ruff format hal/ tests/ harvest/ eval/

test:
.venv/bin/pytest tests/ --ignore=tests/test_intent.py -v

test-full:
OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v

coverage:
.venv/bin/pytest tests/ --ignore=tests/test_intent.py --cov=hal --cov-report=term-missing

typecheck:
.venv/bin/mypy hal/
```

**`requirements.txt` (CURRENT — human-edited source, keep as-is):**

```text
psycopg2-binary>=2.9
pgvector>=0.3
requests>=2.31
python-dotenv>=1.0
rich>=13.0
numpy>=1.26
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp-proto-http>=1.20.0
fastapi>=0.115
uvicorn>=0.30
python-telegram-bot>=21.0
pymupdf>=1.24
trafilatura>=1.12
python-magic>=0.4.27
tavily-python>=0.5
```

**`requirements-dev.txt` (CURRENT — you will add pip-tools here):**

```text
pytest>=8.0
ruff>=0.4.0
mypy>=1.10
pre-commit>=3.7
pytest-cov>=5.0
azure-ai-evaluation>=0.4.0
```

**`.pre-commit-config.yaml` (CURRENT — for reference):**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.2
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/DavidAnson/markdownlint-cli2
    rev: v0.17.2
    hooks:
      - id: markdownlint-cli2
```

---

## IMMUTABLE RULES (copy verbatim into every subsequent session — only SESSION ITEMS and BACKLOG checkboxes change)

1. **CLAUDE.md format is mandatory.** Before every code change, state: root cause (not symptom), proposed change (exact files + lines), why it's correct long-term, and confidence level. Then STOP and wait for operator approval. Do not write or modify any code until approved.

2. **Scope lock.** Complete ONLY the items listed in SESSION ITEMS below. Do not refactor unrelated code. Do not "improve" things you notice in passing unless rule 3 applies.

3. **Discovery protocol.** If you find a new issue while working:
   - If it takes <5 minutes AND is directly related to your session items → fix inline, note in commit message.
   - Otherwise → append one line to `notes/engineering-practices-audit.md` under a `## Discovered Issues` section (create it if missing). Format: `- **[Pn]** <description> — discovered in session N`
   - You may fix AT MOST 1–2 trivial discovered issues per session. No more.

4. **Commit discipline.** One logical change per commit. Conventional Commits format: `feat|fix|docs|refactor|test|chore: subject`. Both `make lint` and `make test` must pass before every commit. Add `Co-Authored-By: Claude <noreply@anthropic.com>` as the last line of the commit body.

5. **Verification after each change:**
   - `make lint` passes
   - `make test` passes (expect 530+ offline tests)
   - `make lint-md` passes (if any `.md` files were touched)
   - `ruff format --check .` produces no diffs

6. **Session handoff.** When ALL session items are complete, output this block:

   ```text
   ### HANDOFF — Session N complete
   Completed: <what was done, with commit hashes>
   Discovered (logged): <any issues appended to audit file, or "none">
   Next session items: <the 2 items for session N+1>
   Remaining backlog: <items not yet started>
   ```

   Then generate the COMPLETE prompt for the next session: copy this entire document (GROUND TRUTH + IMMUTABLE RULES + updated SESSION ITEMS + updated BACKLOG). Update inline file contents to reflect the changes made in this session. The next-session prompt must be fully self-contained — a new AI with zero prior context must be able to work from it alone.

7. **Immutability.** Rules 1–7 are immutable across all sessions. Never modify them. Only the SESSION ITEMS section, BACKLOG checkboxes, and inline file contents change between sessions.

---

## SESSION ITEMS — Session 1

### Item 1: Fix the CI workflow

**File:** `.github/workflows/test.yml` (already exists — do NOT create a new file)

**Problems with the current CI:**

- Only tests 3 of 17 test files (`test_judge.py`, `test_memory.py`, `test_agent_loop.py`) — 527 offline tests are silently skipped, giving a false green badge
- No markdownlint step — markdown regressions not caught
- Ad-hoc `pip install pytest ruff mypy` instead of using `requirements-dev.txt` — causes version drift between CI and local dev
- mypy `continue-on-error: true` is intentional for now (graduation is backlog item 4)

**Target state — replace the file with:**

- `actions/setup-python@v5` with `cache: pip`
- Install: `pip install -r requirements.txt` then `pip install -r requirements-dev.txt` (this gets pytest, ruff, mypy, pre-commit, pytest-cov — skip `azure-ai-evaluation` which is eval-only and heavy)
- Steps: `make lint` → `ruff format --check .` → `make typecheck` (continue-on-error: true) → `make lint-md` → `make test`
- `make test` runs ALL 530 offline tests, not 3 cherry-picked files

**IMPORTANT for CI:** The Makefile targets use `.venv/bin/` prefixed commands. In CI (GitHub Actions ubuntu-latest), there's no `.venv` — tools are installed globally via pip. Either: (a) adjust the workflow to create a venv matching the Makefile, or (b) run the underlying commands directly without the `.venv/bin/` prefix. Choose whichever approach is cleaner and explain your reasoning.

**Acceptance criteria:**

- Workflow YAML is syntactically valid
- All referenced commands/targets exist
- No test files are cherry-picked — the full offline suite runs

### Item 2: Dependency pinning with pip-compile

**Current state:** `requirements.txt` and `requirements-dev.txt` use `>=` lower bounds only. No lock files exist anywhere in the repo.

**Steps:**

1. Add `pip-tools>=7.0` to `requirements-dev.txt`
2. Install pip-tools: `.venv/bin/pip install pip-tools`
3. Generate lock files:
   - `.venv/bin/pip-compile requirements.txt -o requirements.lock` (try `--generate-hashes` first; if it fails due to missing sdists for any package, drop hashes and note why)
   - `.venv/bin/pip-compile requirements-dev.txt -o requirements-dev.lock` (same strategy; exclude `azure-ai-evaluation` from the lock if it causes issues — it's only needed for eval)
4. Update `.github/workflows/test.yml` to install from lock files instead of `.txt` files
5. Update `CONTRIBUTING.md` dev setup instructions to mention `pip-sync`
6. Do NOT delete or modify `requirements.txt` or `requirements-dev.txt` — these remain the human-edited source files that pip-compile reads from

**Acceptance criteria:**

- `requirements.lock` and `requirements-dev.lock` exist and are committed
- CI installs from lock files
- `make lint` + `make test` still pass
- `CONTRIBUTING.md` setup section is updated

### Known trivial discovery to fix inline

`CONTRIBUTING.md` has stale numbers: says "495 offline tests" (should be 530) and "10 errors in baseline" for mypy (should be 13). Fix these inline when you're already editing CONTRIBUTING.md for the pip-sync instructions (Item 2, step 5). Mention the correction in the commit message.

---

## MASTER BACKLOG (reference only — do NOT work items not in SESSION ITEMS)

1. ⬜ Fix CI workflow (`test.yml` is incomplete) — **this session**
2. ⬜ Dependency pinning (`pip-compile` → lock files) — **this session**
3. ⬜ Secret scanning (`detect-secrets` pre-commit hook)
4. ⬜ mypy graduation (13→0 errors, then strict on `judge.py` + `agent.py`)
5. ⬜ `bandit` security scanning
6. ⬜ Markdownlint fixes in ARCHITECTURE.md, OPERATIONS.md, ROADMAP.md, internet-access-plan.md (41 pre-existing errors)

---

## Session 2 — Secret Scanning + mypy Graduation

Do not use until Session 1 HANDOFF is complete. Update inline file contents and
backlog checkboxes first.

## SESSION ITEMS — Session 2

### Item 1: Secret scanning with detect-secrets

**Current state:** No secret scanning exists. The project has real secrets (`TAVILY_API_KEY`, `PGVECTOR_DSN` with DB password, `TELEGRAM_BOT_TOKEN`) that could accidentally be committed.

**Steps:**

1. Add `detect-secrets` to `requirements-dev.txt`
2. Add a `detect-secrets` hook to `.pre-commit-config.yaml` (use the `Yelp/detect-secrets` repo)
3. Run `detect-secrets scan > .secrets.baseline` to establish baseline
4. Audit the baseline for false positives — add allowlist entries as needed
5. Test: `pre-commit run detect-secrets --all-files` passes
6. Update `requirements-dev.lock` if lock files were created in Session 1

**Acceptance criteria:**

- `.secrets.baseline` file exists and is committed
- `detect-secrets` hook is in `.pre-commit-config.yaml`
- `pre-commit run detect-secrets --all-files` passes cleanly
- No false positives on existing code

### Item 2: mypy graduation — get baseline to 0

**Current state:** 13 mypy errors in 8 files. `make typecheck` runs but never gates anything.

**Steps:**

1. Run `make typecheck` and categorize every error
2. For third-party stub issues (e.g., `requests`, `trafilatura`): add `# type: ignore[import-untyped]` with a comment explaining why
3. For genuine type errors: fix them properly
4. Goal: `make typecheck` exits 0 with no errors
5. Once at 0: add `--strict` overrides for `hal/judge.py` and `hal/agent.py` only (in `pyproject.toml` under `[tool.mypy]` per-module overrides)
6. Fix any new strict-mode errors in those two files
7. Update CI to remove `continue-on-error: true` from the mypy step (it can now gate)

**Acceptance criteria:**

- `make typecheck` exits 0
- `hal/judge.py` and `hal/agent.py` pass `--strict`
- CI mypy step no longer has `continue-on-error: true`
- `make lint` + `make test` still pass

---

## MASTER BACKLOG

1. ✅ Fix CI workflow — completed in Session 1
2. ✅ Dependency pinning — completed in Session 1
3. ⬜ Secret scanning (`detect-secrets`) — **this session**
4. ⬜ mypy graduation (13→0, strict on judge + agent) — **this session**
5. ⬜ `bandit` security scanning
6. ⬜ Markdownlint fixes in ARCHITECTURE.md, OPERATIONS.md, ROADMAP.md, internet-access-plan.md

---

## Session 3 — Bandit + Markdownlint Cleanup

Do not use until Session 2 HANDOFF is complete. Update inline file contents and
backlog checkboxes first.

## SESSION ITEMS — Session 3

### Item 1: bandit security scanning

**Steps:**

1. Add `bandit>=1.7` to `requirements-dev.txt`
2. Add `make security-scan` target to `Makefile`: `.venv/bin/bandit -r hal/ -c pyproject.toml`
3. Add `[tool.bandit]` config to `pyproject.toml` — skip rules that conflict with the project's intentional `subprocess` usage in `hal/executor.py` (document each skip)
4. Run `make security-scan` and fix or suppress any findings
5. Optionally add to CI as a non-blocking step (like mypy was before graduation)

**Acceptance criteria:**

- `make security-scan` exists and runs cleanly
- Any suppressions are documented in `pyproject.toml` comments
- `make lint` + `make test` still pass

### Item 2: Markdownlint cleanup across all docs

**Current state:** 41 markdownlint errors across 4 files: `ARCHITECTURE.md`, `OPERATIONS.md`, `ROADMAP.md`, `notes/internet-access-plan.md`.

**Common errors:**

- MD040 — fenced code blocks without language specified
- MD032 — lists not surrounded by blank lines
- MD012 — multiple consecutive blank lines
- MD034 — bare URLs (need angle brackets or markdown link syntax)
- MD036 — emphasis used instead of heading

**Steps:**

1. Run `make lint-md` to get the full error list
2. Fix all errors file by file — one commit per file
3. After all fixes: `make lint-md` passes with 0 errors

**Acceptance criteria:**

- `make lint-md` passes cleanly (0 errors across all files)
- Each file is a separate commit
- No content meaning is changed — only formatting fixes

---

## MASTER BACKLOG

1. ✅ Fix CI workflow
2. ✅ Dependency pinning
3. ✅ Secret scanning
4. ✅ mypy graduation
5. ⬜ `bandit` security scanning — **this session**
6. ⬜ Markdownlint fixes — **this session**
