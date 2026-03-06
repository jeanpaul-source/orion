---
applyTo: "tests/**/*.py"
---

# Tests — Orion Project

When editing or creating test files:

## Conventions

- Test files mirror source: `hal/judge.py` → `tests/test_judge.py`.
- Use `pytest` fixtures from `tests/conftest.py` — check there before creating new mocks.
- Tests must be **offline** (no network calls) unless explicitly in `test_intent.py`.
- Mock external services (Ollama, vLLM, pgvector) — never call real endpoints in tests.

## When Writing New Tests

- Explain what each test verifies in plain language before writing it.
- Test behavior, not implementation: "does it return the right result?" not "does it call this internal function?"
- Use descriptive test names: `test_judge_blocks_rm_rf` not `test_judge_1`.

## When a Test Fails

- First explain what the test is checking and why it exists.
- Then explain why the change caused it to fail.
- Only then propose a fix — and distinguish between "test was wrong" vs. "code was wrong."
