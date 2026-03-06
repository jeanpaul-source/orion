# Chat 2 — Ruff Auto-fix + Manual Fixes

**Copy this entire file as your opening message in a new Copilot Chat session.**

---

## Context

I'm doing a code quality hardening pass on the Orion project (`/home/jp/orion`). In a previous chat I updated `pyproject.toml` to enforce 16 ruff rule groups (commit `f7e4902`, already pushed to `main`). There are now **179 ruff violations** to fix. This chat handles the **non-security** violations — the security ones (S-rules) go to a separate chat.

The project is a Python 3.12 homelab AI assistant. Read `.github/copilot-instructions.md` and `.github/instructions/python.instructions.md` for project conventions. Read `CLAUDE.md` for the mandatory before-every-change format.

## CRITICAL: Pre-existing uncommitted changes

These files have uncommitted changes from BEFORE this hardening work. **Do NOT touch, stage, or commit changes to these files:**

```
 M hal/agent.py
 M hal/bootstrap.py
 M hal/server.py
 M hal/static/app.js
 M hal/static/style.css
 M notes/containerization-plan.md
 M tests/test_server.py
?? notes/multi-agent-recommendation.md
?? notes/research-multi-agent-architecture.md
```

If a ruff violation exists in one of these files, **skip it** and note that it was skipped. We'll fix those after the pre-existing changes are committed separately.

## Workflow

1. Follow the CLAUDE.md format: explain root cause, proposed change, why correct, confidence — then wait for approval before each change.
2. One commit per logical group (e.g., "all UP017 fixes" = one commit, "all DTZ005 fixes" = one commit).
3. After each commit, run `make test` to verify nothing broke.
4. Use conventional commits: `chore: fix UP017 — use datetime.UTC alias`

## Phase 1: Auto-fixable violations (52 total)

Run `ruff check hal/ tests/ harvest/ eval/ --fix` to auto-fix these. Then review the diff before committing. The auto-fixable violations are:

### UP — pyupgrade (modernize syntax)
- `UP035` — Import from `collections.abc` instead of `typing`: `hal/healthcheck.py:17`, `hal/trust_metrics.py:30`
- `UP006` — Use `dict` instead of `Dict`: `hal/logging_utils.py:29`, `hal/trust_metrics.py:74,282(×3),287,288,311`
- `UP037` — Remove quotes from type annotation: `hal/logging_utils.py:62`, `hal/playbooks.py:133,134`, `hal/tools.py:49,50,51,52`
- `UP045` — Use `X | None` instead of `Optional[X]`: `hal/trust_metrics.py:63,97,141,149,324,348`
- `UP015` — Unnecessary mode argument: `hal/trust_metrics.py:212,239`
- `UP017` — Use `datetime.UTC` alias: `hal/judge.py:719,906,955`, `hal/playbooks.py:98,121`, `hal/postmortem.py:42`, `hal/server.py:161,200` (⚠️ server.py has pre-existing changes — SKIP these two)
  - Also in tests: `tests/test_playbooks.py:163,182,347`, `tests/test_postmortem.py:36`

### RUF — ruff-specific
- `RUF100` — Unused `noqa` directives: `hal/logging_utils.py:28`, `hal/server.py:257` (⚠️ SKIP — pre-existing changes), `hal/telegram.py:92,101,112,171,174`, `hal/tracing.py:128,131`

### PT — pytest
- `PT001` — Use `@pytest.fixture` over `@pytest.fixture()`: `tests/test_memory.py:62`, `tests/test_playbooks.py:224,234,241`

### SIM
- `SIM105` — Use `contextlib.suppress()`: `hal/main.py:285` (note: main.py)
- `SIM117` — Single `with` statement: `tests/test_web.py:347` (and several more in that file)
- `SIM300` — Yoda condition: `tests/test_security.py:273`

**Approach:** Run `ruff check --fix`, then `git diff` to review changes. Stage only clean files (not the pre-existing modified ones). Commit as `chore: apply ruff auto-fixes (UP, RUF100, PT001, SIM)`.

## Phase 2: Manual fixes (non-security)

These require human judgment — ruff can flag them but not auto-fix safely.

### DTZ005 — `datetime.now()` without timezone (12 violations)
All of these use `datetime.datetime.now()` without a `tz` argument (a "naive" datetime — meaning it has no timezone info, which causes subtle bugs when comparing datetimes). Fix: add `tz=datetime.UTC` to each call. If the file already imports `datetime`, just add `UTC` to the import.

**Files (skip hal/bootstrap.py and hal/server.py — pre-existing changes):**
- `hal/bootstrap.py:44` — ⚠️ SKIP
- `hal/knowledge.py:135`
- `hal/memory.py:68,77,96`
- `hal/watchdog.py:76,111,136,468,510`
- `harvest/collect.py:144`
- `harvest/main.py:76`
- `harvest/snapshot.py:29`
- `tests/test_memory.py:128,155,180`
- `tests/test_watchdog.py:114,133,182,195,351,363`

### RUF005 — Use iterable unpacking instead of concatenation (3 violations)
Example: `[a] + list` → `[a, *list]`. More Pythonic and slightly faster.
- `hal/agent.py:182` — ⚠️ SKIP (pre-existing changes)
- `hal/bootstrap.py:283` — ⚠️ SKIP
- `hal/judge.py:575`
- `hal/llm.py:63`

### RUF012 — Mutable default value for class attribute (7 violations)
Class attributes like `allowed: list = []` need `ClassVar[list]` annotation or `field(default_factory=list)`. This prevents the mutable default bug (where all instances share the same list).
- `eval/evaluate.py:50,72`
- `hal/executor.py:20`
- `tests/test_judge_hardening.py:45,124,163,182`

### RUF059 — Unpacked variable never used (5 violations)
Variables from tuple unpacking that are never used. Convention: prefix with `_`.
- `hal/server.py:388` — ⚠️ SKIP
- `tests/test_judge.py:414,443,471,637`
- `tests/test_telegram.py:235`

### RUF013 — Implicit Optional (1 violation)
- `harvest/collect.py:32` — `def fn(x: str = None)` should be `def fn(x: str | None = None)`

### RUF043 — Unescaped regex metacharacters in `match=` (2 violations)
- `tests/test_web.py:309,315` — use raw strings (`r"..."`) for regex patterns in `pytest.raises(match=...)`

### RUF015 — Prefer `next(...)` over single element slice (1 violation)
- `tests/test_trust_metrics.py:163`

### B — bugbear (5 violations)
- `B905` — `zip()` without `strict=`: `hal/intent.py:165`
- `B904` — `raise` without `from`: `hal/web.py:86,182` — add `from err` or `from None`
- `B007` — Unused loop variable: `hal/watchdog.py:483`, `hal/web.py:184` — prefix with `_`

### PERF — performance (4 violations)
- `PERF401` — Use list comprehension or `list.extend`: `hal/healthcheck.py:324`, `hal/tools.py:804`, `hal/watchdog.py:394`, `hal/web.py:95`

### PIE — misc (2 violations)
- `PIE810` — Call `startswith` once with tuple: `hal/judge.py:489,805` — e.g., `x.startswith(("a", "b"))` instead of `x.startswith("a") or x.startswith("b")`

### SIM102 — Collapsible nested if (1 violation)
- `hal/judge.py:488` — combine nested `if` into single `if x and y:`

### PT006 — Wrong type for parametrize first arg (4 violations)
- `tests/test_judge_hardening.py:60,103,152,171` — pass a tuple, not a list, to `@pytest.mark.parametrize` first argument

### PT019 — Fixture without value injected as parameter (12 violations)
- `tests/test_web.py:253,258,307,313,322,336,357,373,393,405,418` — use `@pytest.mark.usefixtures("_mock")` decorator instead of injecting as a parameter

## Phase 3: Unicode fixes (7 violations, currently suppressed)

These are suppressed by `ignore = ["RUF001", "RUF002", "RUF003"]` in `pyproject.toml`. Fix the characters FIRST, THEN remove those three codes from the `ignore` list.

- `eval/evaluate.py:280` — en-dash `–` → hyphen `-`
- `hal/bootstrap.py:136,169` — ⚠️ SKIP (pre-existing changes)
- `hal/judge.py:624` — en-dash in comment → hyphen
- `hal/knowledge.py:30` — multiplication sign `×` in comment → `x`
- `hal/server.py:69` — ⚠️ SKIP (pre-existing changes)
- `tests/test_judge_hardening.py:1` — en-dash in docstring → hyphen

After fixing the non-skipped ones, remove `"RUF001", "RUF002", "RUF003"` from the `ignore` list in `pyproject.toml` and add per-file ignores for the skipped files instead:
```toml
"hal/bootstrap.py" = ["RUF001"]
"hal/server.py" = ["RUF003"]
```

## Verification

After all changes:
```bash
ruff check hal/ tests/ harvest/ eval/   # should show only S-rule and skipped-file violations
make test                                # all 787+ offline tests pass
```

## Commit sequence (suggested)

1. `chore: apply ruff auto-fixes (UP, RUF100, PT001, SIM)`
2. `chore: fix DTZ005 — add timezone to all datetime.now() calls`
3. `chore: fix RUF005/RUF012/RUF059 — iterable unpacking, ClassVar, unused vars`
4. `chore: fix B904/B905/B007 — raise-from, zip-strict, unused loop vars`
5. `chore: fix PERF401/PIE810/SIM102 — comprehensions, startswith tuple, nested if`
6. `chore: fix PT006/PT019 — pytest parametrize and fixture style`
7. `chore: fix RUF013/RUF015/RUF043 — implicit Optional, next(), raw regex`
8. `chore: replace unicode chars with ASCII and remove RUF001-3 global ignore`

Add `Co-Authored-By: Claude <noreply@anthropic.com>` to each commit.
