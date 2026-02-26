# Development Notes & Future Agent Ideas

*Updated: Feb 25, 2026*

---

## Dev Tooling — DONE

All shipped Feb 25, 2026. See ROADMAP.md for details.

- [x] Makefile (`make lint`, `format`, `test`, `test-full`, `coverage`, `typecheck`)
- [x] ruff format (enforced in CI + pre-commit)
- [x] mypy (warn-only, `continue-on-error` in CI)
- [x] pre-commit hooks (ruff check --fix + ruff format)
- [x] pytest-cov (baseline 34%)

---

## Workflow Ideas (low-effort, no prompts needed)

- **`.code-workspace` file** — local VS Code convenience for multi-root
- **Agent context files** — `.github/agents/` YAML for scoping sub-agent context
- **MCP bridge to pgvector** — pgvector API at port 5001 could serve as MCP server

---

## Future Agent Ideas (needs design before implementation)

### A. Extend security agent — highest leverage
`hal/security.py` already has Falco, Osquery, ntopng, Nmap. Missing:
- `block_ip()` via nftables/firewalld — tier 2/3 Judge action
- Falco noise filter for interactive queries (already in backlog)
- Automated alert routing (watchdog → security event → notify)
**Next step:** design `block_ip()` — one tool, one tier decision

### B. Task management
Extend `/remember` with task state (open/done/priority), or lightweight YAML
in `knowledge/` tracked by harvest.
**Next step:** sketch the data model before writing code

### C. File system indexing
`hal/workers.py` has `list_dir`, `read_file`. Missing: indexing arbitrary
paths into pgvector with "catalog" semantics.
**Next step:** define what "catalog" means

### D. Email / Calendar
Entirely new external integrations (IMAP/SMTP, CalDAV/Google).
No existing hooks. Lowest priority — defer until core assistant is stable.

---

## Skipped (redundant or low-value)

flake8, pylint, isort (ruff covers all), black (ruff format), vulture, radon,
safety (needs API key), commitizen, docstring enforcer.

bandit: add as `make security-scan` later — hold off until findings are triaged.
