# Enforcement Design v3 — Final Draft

> **Date:** 2026-02-28
> **Branch:** `reliability/layer-0` (merged to main)
> **Status:** IMPLEMENTED — pre-commit hooks + CI active; this document is retained for historical context

---

## 1. Context & Goals

Orion's current enforcement is ad-hoc: a hand-rolled `pre-push` hook testing 3 of 18 test
files, `continue-on-error: true` on mypy and markdownlint in CI, and markdownlint scanning
only 2 of 20 `.md` files. This plan replaces all of it with a from-scratch design using
2026 best practices.

**Constraints (from operator):**

- Hooks must complete in < 30 seconds (measured total: ~10s — well within budget)
- "If a check exists, it either blocks or it doesn't" — no `continue-on-error`
- Must work offline (laptop is the dev machine; server is deploy-only)
- Fresh clone → full enforcement in one command
- Design for a second contributor even though solo dev now
- No band-aids

**Research sources checked:**

- pre-commit.com official docs (v4.5.1)
- GitHub REST API — repository rulesets
- GitHub Actions official Python CI/CD guide
- Hynek Schlawack — "Python in GitHub Actions"
- Stefanie Molin — pre-commit setup guide

---

## 2. Architecture: Three Walls

```
Wall 1: pre-commit hooks  (~10s, runs on every commit)
Wall 2: GitHub Actions CI  (runs on every push & PR, hard gates)
Wall 3: GitHub Rulesets    (main branch: require PR + CI pass)
```

**Principle:** Wall 1 catches problems before they leave the laptop. Wall 2 is the
authoritative gate — identical checks but on the full codebase. Wall 3 ensures nothing
reaches `main` without passing Wall 2.

---

## 3. Wall 1 — Pre-Commit Hooks

### 3.1 `.pre-commit-config.yaml` (rewrite from scratch)

```yaml
minimum_pre_commit_version: "4.0"
default_install_hook_types: [pre-commit]
fail_fast: false

repos:
  # ── Remote hooks (maintained upstream) ─────────────────────
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.2                    # pin to latest at time of impl
    hooks:
      - id: ruff                    # lint + fix
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format             # format check

  - repo: https://github.com/DavidAnson/markdownlint-cli2
    rev: v0.17.2
    hooks:
      - id: markdownlint-cli2
        args: []                    # config in .markdownlint-cli2.yaml

  # ── Local hooks (use project venv) ────────────────────────
  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: .venv/bin/mypy hal/
        language: unsupported        # pre-commit 4.4+; was "system"
        types: [python]
        pass_filenames: false
        require_serial: true

      - id: pytest
        name: pytest (offline suite)
        entry: .venv/bin/pytest tests/ --ignore=tests/test_intent.py
               --cov=hal --cov-report=term-missing --cov-fail-under=60
               -q --no-header --tb=short
        language: unsupported
        types: [python]
        pass_filenames: false
        require_serial: true
        stages: [pre-push]          # too slow for pre-commit (~8s)

      - id: doc-drift
        name: doc-drift check
        entry: .venv/bin/python scripts/check_doc_drift.py
        language: unsupported
        always_run: true
        pass_filenames: false
        require_serial: true
```

### 3.2 Design decisions

| Decision | Rationale |
|---|---|
| `language: unsupported` not `system` | `system` is deprecated alias in pre-commit 4.4+; `unsupported` is the forward-compatible name (confirmed in official docs) |
| ruff + markdownlint as remote repos | Upstream manages versions; `pre-commit autoupdate` keeps them current |
| mypy/pytest/doc-drift as `repo: local` | They need project venv (deps, stubs, conftest). `pass_filenames: false` because they operate on the whole project |
| pytest on `pre-push` not `pre-commit` | 8s is fine for push, too slow for every commit. Ruff + mypy + markdownlint on commit is ~2s |
| `--cov-fail-under=60` | Current coverage is 62%. Floor of 60% prevents regression without blocking feature work |
| `fail_fast: false` | Show all failures at once so dev can fix in one pass |
| Config in `pyproject.toml` not `args` | ruff and mypy config already lives in `pyproject.toml` — same config applies in hooks, CI, and IDE |
| `default_install_hook_types: [pre-commit]` | Single `pre-commit install` sets up everything |

### 3.3 Timing budget

| Hook | Stage | Measured time |
|---|---|---|
| ruff (lint) | pre-commit | 13ms |
| ruff-format | pre-commit | 18ms |
| mypy | pre-commit | 540ms |
| markdownlint-cli2 | pre-commit | 1.5s |
| **pre-commit total** | | **~2.1s** |
| pytest + coverage | pre-push | 7.9s |
| doc-drift | pre-commit | ~50ms (est.) |
| **pre-push total** | | **~10s** |

Both well within the 30s budget.

### 3.4 `.markdownlint-cli2.yaml` (new file)

```yaml
# Scan all .md files except notes/ (scratch/journal area)
globs:
  - "**/*.md"
  - "!notes/**"

config:
  # Relaxations for documentation style
  MD013: false          # line length — docs have long URLs
  MD033: false          # inline HTML — needed for some formatting
```

Currently markdownlint only scans 2 of 20 `.md` files. This config brings all docs
under enforcement except `notes/`.

---

## 4. Wall 2 — GitHub Actions CI

### 4.1 `.github/workflows/test.yml` (rewrite from scratch)

```yaml
name: CI

on:
  push:
    branches: ["*"]        # every branch, not just main
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-dev.txt

      - name: Ruff lint
        run: ruff check --output-format=github hal/ tests/ harvest/ eval/

      - name: Ruff format
        run: ruff format --check hal/ tests/ harvest/ eval/

      - name: Mypy
        run: mypy hal/

      - name: Markdownlint
        uses: DavidAnson/markdownlint-cli2-action@v19
        with:
          globs: |
            **/*.md
            !notes/**

      - name: Tests + Coverage
        run: |
          pytest tests/ --ignore=tests/test_intent.py \
            --cov=hal --cov-report=term-missing --cov-report=xml \
            --cov-fail-under=60 \
            --junitxml=junit-results.xml \
            -q --no-header

      - name: Doc-drift check
        run: python scripts/check_doc_drift.py

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: |
            junit-results.xml
            coverage.xml
```

### 4.2 Design decisions

| Decision | Rationale |
|---|---|
| `actions/checkout@v5`, `setup-python@v5` | Current stable versions (confirmed in GitHub official docs, Feb 2026) |
| `cache: "pip"` | Built into setup-python v5; no separate cache action needed |
| `--output-format=github` on ruff | Produces inline PR annotations for free |
| No `continue-on-error` anywhere | "If a check exists, it either blocks or it doesn't" |
| `on: push: branches: ["*"]` | CI runs on every branch, not just main. Feature branches get feedback before PR |
| JUnit XML + coverage XML artifacts | Uploadable, parseable, visible in PR checks tab |
| `if: always()` on artifact upload | Publish test results even on failure for post-mortem debugging |
| Single job, not matrix | Solo dev, single Python version (3.12), single OS. No need for matrix complexity |
| `requirements.txt` + `requirements-dev.txt` | Not lock files — CI currently references `.lock` files that may not exist |

---

## 5. Wall 3 — GitHub Rulesets

### 5.1 Ruleset: `main-protection`

Create via GitHub REST API (or Settings → Rules → New ruleset):

```json
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    }
  ],
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_reviews": false,
        "require_last_push_approval": false
      }
    },
    { "type": "required_status_checks",
      "parameters": {
        "strict_status_checks_policy": true,
        "required_status_checks": [
          { "context": "test" }
        ]
      }
    },
    { "type": "deletion" },
    { "type": "non_fast_forward" }
  ]
}
```

### 5.2 Design decisions

| Decision | Rationale |
|---|---|
| Rulesets, not legacy branch protection | Rulesets are GitHub's current-gen system — more granular, API-first, versionable |
| `required_approving_review_count: 0` | Solo dev — PR is required (audit trail) but self-merge is allowed |
| `bypass_actors: RepositoryRole admin` | Emergency escape hatch. `actor_id: 5` = repository admin role. Owner can bypass in genuine emergencies |
| `strict_status_checks_policy: true` | Branch must be up-to-date with main before merging — no stale-base surprises |
| `deletion` + `non_fast_forward` | Prevent force-push and branch deletion on main |
| Status check context: `test` | Matches the job name in the CI workflow |

### 5.3 Workflow change

**Old:** `git push origin main` directly from laptop, server pulls main.

**New:**
```
laptop$ git push origin feat/whatever
# GitHub: CI runs → PR created → CI passes → merge
# Server: git pull main (unchanged)
```

For rapid iteration, you can still push feature branches freely. Only merges to
`main` require CI to pass. The bypass actor means you *can* still push directly to
main in a genuine emergency — but it's deliberate, not default.

---

## 6. Doc-Drift Detection

### 6.1 `scripts/check_doc_drift.py` (new file)

Verified mapping built from reading all 5 key docs against actual codebase:

```python
#!/usr/bin/env python3
"""Doc-drift detector: fails if documented facts don't match code reality.

Checks that files/symbols referenced in documentation actually exist,
and that docs are updated when hal/ modules are added or removed.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Mapping: (doc_file, description) → code_path_that_must_exist ──────
FILE_EXISTENCE_RULES: list[tuple[str, str, str]] = [
    # ARCHITECTURE.md references
    ("ARCHITECTURE.md", "intent classifier",         "hal/intent.py"),
    ("ARCHITECTURE.md", "agent loop",                "hal/agent.py"),
    ("ARCHITECTURE.md", "judge policy gate",         "hal/judge.py"),
    ("ARCHITECTURE.md", "LLM clients",               "hal/llm.py"),
    ("ARCHITECTURE.md", "memory store",              "hal/memory.py"),
    ("ARCHITECTURE.md", "prometheus client",         "hal/prometheus.py"),
    ("ARCHITECTURE.md", "knowledge base",            "hal/knowledge.py"),
    ("ARCHITECTURE.md", "security workers",          "hal/security.py"),
    ("ARCHITECTURE.md", "web search/fetch",          "hal/web.py"),
    ("ARCHITECTURE.md", "config loader",             "hal/config.py"),
    ("ARCHITECTURE.md", "server",                    "hal/server.py"),
    ("ARCHITECTURE.md", "telegram bot",              "hal/telegram.py"),
    ("ARCHITECTURE.md", "falco noise filter",        "hal/falco_noise.py"),

    # OPERATIONS.md references
    ("OPERATIONS.md",   "server systemd unit",       "ops/server.service"),
    ("OPERATIONS.md",   "telegram systemd unit",     "ops/telegram.service"),
    ("OPERATIONS.md",   "vLLM systemd unit",         "ops/vllm.service"),
    ("OPERATIONS.md",   "harvest timer",             "ops/harvest.timer"),
    ("OPERATIONS.md",   "watchdog service",          "ops/watchdog.service"),

    # README.md references
    ("README.md",       "main entry point",          "hal/main.py"),
    ("README.md",       "harvest collector",         "harvest/collect.py"),
    ("README.md",       "harvest ingest",            "harvest/ingest.py"),

    # CONTRIBUTING.md references
    ("CONTRIBUTING.md", "test suite",                "tests/conftest.py"),
    ("CONTRIBUTING.md", "pyproject config",          "pyproject.toml"),
]

# ── Documented hal/*.py modules that must match reality ───────────────
DOCUMENTED_HAL_MODULES = {
    "agent.py", "bootstrap.py", "config.py", "executor.py",
    "falco_noise.py", "intent.py", "judge.py", "knowledge.py",
    "llm.py", "logging_utils.py", "main.py", "memory.py",
    "patterns.py", "postmortem.py", "prometheus.py", "sanitize.py",
    "security.py", "server.py", "telegram.py", "tools.py",
    "tracing.py", "trust_metrics.py", "tunnel.py", "watchdog.py",
    "web.py", "workers.py",
}


def check_file_existence() -> list[str]:
    """Check that every documented code path actually exists."""
    errors = []
    for doc, desc, code_path in FILE_EXISTENCE_RULES:
        if not (ROOT / code_path).exists():
            errors.append(
                f"  {doc} references {code_path} ({desc}) but file does not exist"
            )
    return errors


def check_hal_module_drift() -> list[str]:
    """Check for hal/*.py files added or removed without doc update."""
    errors = []
    actual = {
        p.name
        for p in (ROOT / "hal").glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    }
    added = actual - DOCUMENTED_HAL_MODULES
    removed = DOCUMENTED_HAL_MODULES - actual

    for mod in sorted(added):
        errors.append(
            f"  hal/{mod} exists but is not in DOCUMENTED_HAL_MODULES — "
            "add to docs or update check_doc_drift.py"
        )
    for mod in sorted(removed):
        errors.append(
            f"  hal/{mod} is documented but no longer exists — "
            "remove from docs and update check_doc_drift.py"
        )
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(check_file_existence())
    errors.extend(check_hal_module_drift())

    if errors:
        print("Doc-drift detected:\n")
        print("\n".join(errors))
        print(f"\n{len(errors)} issue(s) found.")
        return 1

    print("Doc-drift check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### 6.2 Design decisions

| Decision | Rationale |
|---|---|
| File-existence checks | Simplest reliable signal — if a doc says "see hal/foo.py" and it doesn't exist, that's drift |
| Module manifest check | Catches the most common drift: adding a new `hal/*.py` without updating any docs |
| No content parsing | Checking *what docs say about code* (e.g. "mypy has 12 errors") requires fragile regex or LLM. Not worth automating — better caught in review |
| Pure Python, no deps | Runs everywhere, no additional install |
| Exit code gating | Non-zero = block. Same contract as every other check |

---

## 7. Bootstrap: One-Command Setup

### 7.1 Makefile `dev-setup` target (add to existing Makefile)

```makefile
.PHONY: dev-setup
dev-setup: ## Fresh clone → full enforcement in one command
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/pre-commit install --install-hooks --overwrite
@echo ""
@echo "✓ Dev environment ready. Hooks installed."
@echo "  Run 'make check' to verify everything passes."
```

### 7.2 Reasoning

- `--install-hooks` pre-downloads hook environments so first commit isn't slow
- `--overwrite` replaces the hand-rolled `pre-push` hook
- Single command: `make dev-setup`

---

## 8. Files: Create / Rewrite / Update / Delete

| Action | File | Notes |
|---|---|---|
| **CREATE** | `scripts/check_doc_drift.py` | New — doc-drift detector (§6) |
| **CREATE** | `.markdownlint-cli2.yaml` | New — scan all `.md` except `notes/` (§3.4) |
| **REWRITE** | `.pre-commit-config.yaml` | Replace current 2-hook config (§3.1) |
| **REWRITE** | `.github/workflows/test.yml` | Replace current soft-gate CI (§4.1) |
| **UPDATE** | `Makefile` | Add `dev-setup` target (§7.1) |
| **UPDATE** | `CONTRIBUTING.md` | New branch policy (PR-required for main); fix stale references (see §9) |
| **DELETE** | `.git/hooks/pre-push` | Hand-rolled hook replaced by pre-commit framework |
| **CONFIGURE** | GitHub repo settings | Create `main-protection` ruleset via API (§5.1) |

---

## 9. Stale References Found During Doc Review

These should be fixed during the CONTRIBUTING.md update:

| Location | Current value | Correct value |
|---|---|---|
| CONTRIBUTING.md | "mypy currently reports ~12 errors" | 0 errors (verified) |
| CONTRIBUTING.md | "Coverage: 34%" | 62% (measured) |
| CONTRIBUTING.md | references `.markdownlint.jsonc` | Should be `.markdownlint-cli2.yaml` |
| OPERATIONS.md | references `hal/_unlocked/security.py` | Should be `hal/falco_noise.py` |
| CLAUDE.md | "Active branch: `docs/reconcile-drift`" | `reliability/layer-0` (current) |

---

## 10. Implementation Order

Each step is one commit. Tests must pass before moving to next.

1. **Delete `.git/hooks/pre-push`** — remove hand-rolled hook
2. **Create `scripts/check_doc_drift.py`** — run it, fix any drift it finds
3. **Create `.markdownlint-cli2.yaml`** — run markdownlint, fix any errors
4. **Rewrite `.pre-commit-config.yaml`** — 6 hooks as designed
5. **Rewrite `.github/workflows/test.yml`** — all hard gates
6. **Update `Makefile`** — add `dev-setup` target
7. **Update `CONTRIBUTING.md`** — new branch policy + fix stale refs
8. **Fix stale refs in OPERATIONS.md and CLAUDE.md** — per §9
9. **Configure GitHub ruleset** — via API or web UI (§5.1)
10. **Verify end-to-end** — `make dev-setup && make check` from clean state

---

## 11. Verification Checklist

After implementation, these must all be true:

- [ ] `pre-commit run --all-files` passes
- [ ] `make check` passes (lint + typecheck + test + markdownlint)
- [ ] `python scripts/check_doc_drift.py` exits 0
- [ ] CI passes on push to any branch
- [ ] Direct push to `main` is blocked (ruleset active)
- [ ] PR to `main` requires CI pass
- [ ] `make dev-setup` from fresh clone installs everything
- [ ] No `continue-on-error` anywhere in CI
- [ ] No hand-rolled hooks in `.git/hooks/`
- [ ] Coverage floor (60%) enforced both locally and in CI
