# Notes Triage Plan

Derived from `Notes`. Two categories: code quality tooling and agent ideas.

---

## What Already Exists

| Tool | Status |
|------|--------|
| ruff (lint + isort) | ✓ — `pyproject.toml`, `requirements-dev.txt`, CI |
| pytest | ✓ — `pytest.ini`, CI |
| GitHub Actions CI | ✓ — runs ruff + offline tests on push/PR |
| ruff format / mypy / pre-commit / pytest-cov / Makefile | ✗ not set up |

---

## Easy — Implement Now

Order matters — each item builds on the previous.

### 1. Makefile
Convenience targets so common commands aren't typed from scratch every time.
- `make lint` `make format` `make test` `make test-full` `make coverage` `make typecheck`
- Files: `Makefile` (new)

### 2. ruff format (replaces black — no new dep)
- Add `[tool.ruff.format]` section to `pyproject.toml`
- Add `ruff format --check` step to CI
- Files: `pyproject.toml`, `.github/workflows/test.yml`

### 3. mypy (warn-only — don't block CI yet)
- Add `mypy>=1.10` to `requirements-dev.txt`
- Add `[tool.mypy]` to `pyproject.toml` (`ignore_missing_imports = true`, `check_untyped_defs = true`)
- Add mypy step to CI with `continue-on-error: true`
- Files: `pyproject.toml`, `requirements-dev.txt`, `.github/workflows/test.yml`

### 4. pre-commit hooks
- Create `.pre-commit-config.yaml`: `ruff check --fix` + `ruff format`
- Add `pre-commit>=3.7` to `requirements-dev.txt`
- Files: `.pre-commit-config.yaml`, `requirements-dev.txt`

### 5. pytest-cov
- Add `pytest-cov>=5.0` to `requirements-dev.txt`
- Add `make coverage` target (not baked into default test run — keeps tests fast)
- Files: `requirements-dev.txt`, `Makefile` (update)

**Skipping as redundant/low-value:** flake8, pylint, isort (ruff covers all three), black
(ruff format), vulture, radon, safety (needs API key now), commitizen, docstring enforcer.

**bandit:** add as `make security-scan` later — hold off until existing findings are triaged first.

---

## Harder — Plan Only (no implementation yet)

### A. Extend security agent (highest leverage — foundation already built)
`hal/security.py` has Falco, Osquery, ntopng, Nmap. Missing:
- Active blocking: `block_ip()` via nftables/firewalld — tier 2/3 Judge action
- Falco noise filter: `systemd-userwork`/`/etc/shadow` entries (already in backlog)
- Automated alert routing (watchdog → security event → notify)
**Next step:** design `block_ip()` worker (one tool, one tier decision)

### B. File system agent
`hal/workers.py` already has `list_dir`, `read_file`. Missing:
- Indexing arbitrary paths into pgvector
- "Organize" semantics (metadata only? content-indexed?)
**Next step:** define what "catalog" means before writing any code

### C. Task agent
Natural fit: extend `hal/facts.py` `/remember` with task state (open/done/priority).
Or: lightweight YAML in `knowledge/` tracked by harvest.
**Next step:** sketch the data model

### D. Email / Calendar agents
Entirely new external integrations (IMAP/SMTP or Gmail API, CalDAV or Google Calendar).
No existing hooks. Lowest priority — defer until core lab assistant is stable.

### E. Dev workflow (`.claude/agents/`, MCP server, multi-root workspace)
- `.github/agents/` sub-agent YAML files — low effort, useful for scoping context
- VSCode `.code-workspace` file — local convenience
- MCP server wrapping `knowledge/` — pgvector API already at port 5001; could bridge directly

---

## Verification Checklist (after each easy item)

- `make lint` — clean
- `make format` — no diffs on existing code
- `make test` — all offline tests pass (currently 151)
- `make typecheck` — runs without crashing (type errors expected initially, that's fine)
- `pre-commit run --all-files` — hooks execute without errors
