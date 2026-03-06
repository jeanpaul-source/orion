# Chat 4 — Type Hints + Strict mypy

**Copy this entire file as your opening message in a new Copilot Chat session.**

---

## Context

I'm doing a code quality hardening pass on the Orion project (`/home/jp/orion`). Previous chats handled ruff lint fixes and security fixes. This chat handles **type annotations and mypy strictness**.

The project is a Python 3.12 homelab AI assistant. Read `.github/copilot-instructions.md` and `.github/instructions/python.instructions.md` for project conventions. Read `CLAUDE.md` for the mandatory before-every-change format.

Currently `pyproject.toml` has `check_untyped_defs = true` (checks function bodies even without annotations) but does NOT have `disallow_untyped_defs = true` (which would require annotations on all functions). The goal is to add all missing annotations, fix the 2 existing type bugs, then enable strict mode.

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

If a type error or missing annotation exists in one of these files, **skip it** and note that it was skipped. Note: `hal/bootstrap.py` and `hal/server.py` BOTH have violations but are in the skip list.

## Workflow

1. Follow the CLAUDE.md format: explain root cause, proposed change, why correct, confidence — then wait for approval before each change.
2. One commit per file or logical group.
3. After each commit, run `make typecheck` and `make test` to verify.
4. Use conventional commits: `chore: add type annotations to hal/tunnel.py`

---

## Current state: 2 errors (strict mode off)

```
hal/bootstrap.py:339: error: Incompatible return value type (got "AgentResult", expected "str")  [return-value]
hal/bootstrap.py:342: error: Incompatible return value type (got "AgentResult", expected "str")  [return-value]
```

**⚠️ SKIP** — `hal/bootstrap.py` has pre-existing uncommitted changes. Note this violation for later.

## Future state: 17 errors (with `disallow_untyped_defs = true`)

These are the 15 additional functions that need annotations (the 2 above are type bugs, not missing annotations):

### `hal/tunnel.py` — 2 functions
- Line 57: function missing type annotation
- Line 61: function missing type annotation

Read the file. These are likely small SSH tunnel helper functions. Add parameter and return type annotations.

### `hal/memory.py` — 1 function
- Line 61: missing return type annotation → likely needs `-> None`

### `hal/tracing.py` — 6 functions
- Line 104: missing return type annotation
- Lines 122, 125, 128, 131, 136: missing type annotations

Read the file. These are OpenTelemetry tracing wrappers. Some may be decorators (a decorator is a function that wraps another function to modify its behavior). The type signatures for decorators use `Callable` types. If they're simple wrappers, they may just need `-> None` or `-> Any`.

### `hal/knowledge.py` — 1 function
- Line 39: missing return type annotation

### `hal/telegram.py` — 3 functions
- Lines 92, 101, 112: missing type annotation for one or more arguments

Read the file. These are Telegram bot handler functions. The `python-telegram-bot` library uses specific types (`Update`, `ContextTypes.DEFAULT_TYPE`). Check the existing imports and match the patterns used elsewhere in the file.

### `hal/bootstrap.py` — 2 type bugs (⚠️ SKIP — pre-existing changes)
- Lines 339, 342: returns `AgentResult` but function signature says `-> str`
- The fix is to change the return type annotation to `-> AgentResult` (or `-> str | AgentResult` if both are possible)

### `hal/server.py` — 2 functions (⚠️ SKIP — pre-existing changes)
- Lines 257, 342: missing return type annotations

---

## Adding annotations — guidelines

1. **Type hints explain what a function accepts and returns.** Example:
   ```python
   def greet(name: str) -> str:
       return f"Hello, {name}"
   ```
   This says: `greet` takes a string and returns a string.

2. **For functions that don't return anything**, use `-> None`.

3. **For functions that could return different types**, use union: `-> str | None`

4. **For async functions**, the return type is what the coroutine yields, not `Coroutine[...]`:
   ```python
   async def fetch(url: str) -> dict:  # correct
   ```

5. **Import types from `collections.abc`** (Python 3.12 style), not from `typing`:
   ```python
   from collections.abc import Callable, Sequence
   ```

6. **For decorator functions**, the pattern is typically:
   ```python
   from collections.abc import Callable
   from typing import TypeVar, ParamSpec
   
   P = ParamSpec("P")
   T = TypeVar("T")
   
   def my_decorator(func: Callable[P, T]) -> Callable[P, T]:
       ...
   ```

---

## Enabling strict mode

After all annotations are added and all type errors fixed (or skipped files noted), update `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
check_untyped_defs = true
disallow_untyped_defs = true   # ADD THIS LINE
```

Then run:
```bash
.venv/bin/mypy hal/
```

Expected result: Only the skipped-file errors remain (bootstrap.py return type, server.py missing annotations). These will be fixed when the pre-existing changes are committed.

If new errors appear from the strict mode that weren't in the list above, fix them before committing.

---

## Verification

After all changes:
```bash
make typecheck    # should show only skipped-file errors (bootstrap.py, server.py)
make test         # all 787+ offline tests pass
make lint         # no new ruff violations
```

## Commit sequence (suggested)

1. `chore: add type annotations to hal/tunnel.py`
2. `chore: add type annotations to hal/memory.py and hal/knowledge.py`
3. `chore: add type annotations to hal/tracing.py`
4. `chore: add type annotations to hal/telegram.py`
5. `chore: enable disallow_untyped_defs in mypy config`

Add `Co-Authored-By: Claude <noreply@anthropic.com>` to each commit.
