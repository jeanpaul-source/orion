---
applyTo: "hal/**/*.py,harvest/**/*.py,eval/**/*.py,scripts/**/*.py"
---

# Python Code — Orion Project

When editing Python files in this project:

## Style & Quality

- Format with `ruff` (not black). Run `ruff check --fix` and `ruff format` after changes.
- Type hints on all new function signatures. Explain what a type hint means the first time.
- Imports: stdlib first, then third-party, then local. Alphabetical within each group.

## Project Patterns

- All tool calls go through `hal/judge.py` — never bypass the Judge.
- LLM chat goes through `VLLMClient` in `hal/llm.py`. Ollama is embeddings only.
- Config values come from `hal/config.py` (loads from `.env`). Never hardcode IPs or ports.
- Use structured logging from `hal/logging_utils.py`, not bare `print()` statements.

## Safety

- Run `make test` (or `pytest tests/ --ignore=tests/test_intent.py -v`) after any change.
- Run `ruff check hal/ tests/` after any change.
- If a test fails, explain what the test checks and why the change broke it before fixing.
