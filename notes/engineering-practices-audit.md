# Engineering Practices Audit — Feb 26, 2026

*Analysis by Copilot of what practice categories exist, what the project already has,
what is genuinely missing, and why each gap matters. See ROADMAP.md for the strategic
backlog; this note is the reference for tooling decisions.*

---

## What "engineering practices" actually means

Programming discipline breaks into six distinct categories. Each can fail
independently — a project can have perfect tests and no secret scanning, or
beautiful CI and no style enforcement. The categories are:

| Category | Question it answers | Failure mode if absent |
| --- | --- | --- |
| **Formatting** | Does the code look consistent? | Style debates, noisy diffs |
| **Linting** | Does the code have obvious errors or bad patterns? | Bugs, import chaos |
| **Type checking** | Are types used consistently? | Subtle bugs, worse IDE support |
| **Testing** | Does the code do what it claims? | Silent regressions |
| **Dependency hygiene** | Are dependencies reproducible and safe? | "Works on my machine", supply chain risk |
| **Workflow discipline** | Do bad states reach the repo? | Broken main, leaked secrets, drift |

Markdown linting (what prompted this note) is **documentation quality tooling** —
the same philosophy as code linting, applied to prose. It belongs under Workflow
discipline: the question is "does documentation meet a quality bar before it lands?"

---

## Current state — what this project has

### ✅ Formatting — `ruff format`

`ruff format` is the formatter, enforced in two places:

- `pre-commit` hook fires on every `git commit` (auto-fixes in place)
- `make format` for manual runs

Result: no "tabs vs spaces" arguments, consistent 88-char line width, deterministic
import grouping. **This is done correctly.**

### ✅ Linting — `ruff check`

`ruff check` with `E4`, `E7`, `E9`, `F`, `I` rule groups covers:

- Pyflakes (undefined names, unused imports)
- Pycodestyle errors (not style — actual errors)
- isort (import ordering)

Also enforced in `pre-commit` with `--fix`. `make lint` for manual runs.

Per-file ignores in `pyproject.toml` for `hal/server.py` (intentional `sys.path`
manipulation that violates E402/I001). **This is done correctly.**

### ⚠️ Type checking — `mypy` (warn-only)

`mypy` runs via `make typecheck` but is **not** commit-gated. Current baseline:
13 errors across 8 files (as of Feb 26, 2026). This is a deliberate starting
position — enforcing strict mypy from day one on a project with third-party libs
that lack stubs is painful.

Risk: errors accumulate silently — the baseline has already drifted upward from
the original 10 errors. Once the baseline is stable, specific high-value files
(`judge.py`, `agent.py`) should be tightened to `--strict` incrementally.

### ✅ Testing — `pytest` + `pytest-cov`

565 tests across two tiers:

- **35 intent classifier tests** — require live Ollama (run on server)
- **530 offline tests** — run anywhere, no external services needed

Coverage baseline: 34% (2,000 statements). Notable hotspots: `memory.py` 92%,
`trust_metrics.py` 87%. Agent loop and security workers are under-covered.

`make test` / `make test-full`. **This is done correctly for the project's stage.**

### ✅ Documentation quality — `markdownlint-cli2`

Added Feb 26, 2026. `.markdownlint.jsonc` contains explicit, commented rule
decisions. Hook enforced in `pre-commit` and `make lint-md`. Key rule decisions:

- MD013 disabled — prose lines are intentionally long
- MD024 disabled — ROADMAP has multiple "Feb 23" subsections
- MD046 fenced — consistent with all existing code blocks
- MD060 spaced — matches `| --- |` table style used throughout

### ✅ Workflow discipline — `pre-commit`

Current hooks (in order):

1. `ruff` (check + fix) — Python lint
2. `ruff-format` — Python format
3. `markdownlint-cli2` — Markdown lint

Server-side push hook also runs `make lint` + `make test` as a secondary gate.

---

## Gaps — what is missing and why it matters

### ⚠️ P1 — GitHub Actions CI (exists but incomplete)

**What exists:** `.github/workflows/test.yml` already runs on push/PR to `main`.
It checks ruff lint, ruff format, and mypy (warn-only via `continue-on-error`).

**What's wrong with it:**

- **Only tests 3 of 17 test files** (`test_judge.py`, `test_memory.py`,
  `test_agent_loop.py`) — 527 offline tests are skipped, giving false green.
- **No markdownlint** — markdown regressions are not caught.
- **Ad-hoc pip install** — installs `pytest ruff mypy` inline instead of using
  `requirements-dev.txt`, causing version drift between CI and local dev.
- **mypy `continue-on-error: true`** — can never gate, errors drift silently.

**Why it matters:** Incomplete CI is worse than no CI — the green badge creates
false confidence. Someone can push code that breaks 490+ tests and CI stays green.

**Effort:** Update existing `test.yml` to use `make` targets and run all offline
tests. ~15 min.

---

### ❌ P2 — Dependency pinning

**What it is:** `requirements.txt` uses `>=` lower bounds, not exact versions.
`pip-compile` (from `pip-tools`) generates a `requirements.lock` with exact package
versions and SHA-256 hashes.

**Why it matters:** `pip install -r requirements.txt` today may install different
versions than in 6 months. Silent drift in transitive dependencies has caused real
production outages. A `requirements.lock` makes the environment fully reproducible
and makes version bumps an explicit, reviewable commit.

**Effort:** `pip install pip-tools && pip-compile requirements.txt`. Add
`pip-sync requirements.lock` to the setup instructions in CONTRIBUTING.md.

---

### ❌ P3 — Secret scanning

**What it is:** The `detect-secrets` pre-commit hook scans staged files for patterns
matching API keys, tokens, connection strings, and high-entropy strings before they
land in git history.

**Why it matters:** Once a secret is in git history, it is effectively leaked — even
if you delete the file, the history is public unless you do a full `git filter-repo`
rewrite. This project has multiple real secrets: `TAVILY_API_KEY`, `PGVECTOR_DSN`
(contains database password), `TELEGRAM_BOT_TOKEN`. The risk is low today (private
repo, single contributor) but grows as the project expands.

**Effort:** Add `detect-secrets` to `.pre-commit-config.yaml`. Run
`detect-secrets scan > .secrets.baseline` once to whitelist any false positives
(e.g. base64 strings in test fixtures).

---

### ⚠️ P4 — `mypy` is warn-only (graduation path needed)

**What it is:** Currently `make typecheck` produces output but never fails a commit
or CI run. This means type errors accumulate silently.

**Why it matters:** The project started at 10 mypy errors and has already drifted
to 13 errors in 8 files — exactly the failure mode predicted above. Without a plan
to address them, the number continues upward and type checking becomes noise.

**Recommended path:** Don't go `--strict` globally. Instead, add
`# type: ignore` to known-broken third-party call sites, get the baseline to 0,
then enable `--strict` on the two most critical files: `hal/judge.py` and
`hal/agent.py`. These are the security-critical paths where type safety matters most.

---

### 💡 P5 — `bandit` security scanning (low priority, not urgent)

**What it is:** Static analysis specifically for security anti-patterns in Python —
hardcoded passwords, use of `subprocess` with `shell=True`, `pickle.loads()`, etc.

**Why it matters for this project specifically:** `hal/executor.py` uses `subprocess`
in security-sensitive ways. `bandit` would catch regressions where the shell=False
discipline slips.

**Why it's low priority:** The Judge + audit log already provide runtime security
gating. `bandit` is a compile-time complement, not a replacement. Add as
`make security-scan` after CI is working.

---

## Priority order

| Priority | Item | Effort | Value |
| --- | --- | --- | --- |
| **1** | Fix CI workflow (test.yml is incomplete) | 15 min | Stops false-green badge; gates all 530 offline tests |
| **2** | Dependency pinning (`pip-compile`) | 15 min | Reproducible environments |
| **3** | Secret scanning (`detect-secrets`) | 10 min | Prevents the unrecoverable mistake |
| **4** | mypy graduation plan (13→0 errors) | ~1 hr | Type safety in security-critical paths |
| **5** | `bandit` security scan | 10 min | Defence-in-depth for subprocess usage |

Items 2 and 3 have the best effort-to-risk ratio. Item 1 is the most urgent because
the current CI gives false confidence.

---

## Draft: replacement for `.github/workflows/test.yml`

```yaml
# .github/workflows/test.yml
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

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint (ruff)
        run: make lint

      - name: Format check
        run: ruff format --check .

      - name: Type check (warn-only)
        run: make typecheck
        continue-on-error: true

      - name: Lint (markdownlint)
        run: make lint-md

      - name: Test (all offline — no Ollama in CI)
        run: make test
```

Notes on the draft:

- **Replaces** the existing incomplete `test.yml`, not a new file
- Uses `actions/setup-python@v5` with pip cache — fast installs after first run
- Installs from both requirements files (unlike the current ad-hoc install)
- Runs **all 530 offline tests** via `make test` (not just 3 cherry-picked files)
- Intent tests require live Ollama and cannot run in GitHub-hosted runners without
  a self-hosted runner pointed at the lab — that's a later enhancement
- `make lint-md` works in CI because `pre-commit run` installs its own Node env
  via `pre-commit`'s isolation mechanism
- mypy stays `continue-on-error: true` until the graduation plan (P4) is complete

---

## What is deliberately skipped

| Tool | Reason skipped |
| --- | --- |
| `flake8`, `pylint`, `isort` | `ruff` covers all of these |
| `black` | `ruff format` is a drop-in replacement |
| `vulture` (dead code) | Useful but low priority; codebase is young enough to audit manually |
| `radon` (complexity metrics) | Nice to have, not actionable yet |
| `commitizen` | Conventional Commits convention is already enforced by discipline, not tooling |
| Spell checking (`codespell`) | Low value for a technical document set |
| `safety` / `pip-audit` | Good for production; add alongside dependency pinning (P2) |
