---
applyTo: "tests/**/*.py"
---

# Tests — Orion

- Tests must be offline (no network calls) unless in `test_intent.py`.
- Mock external services (Ollama, vLLM, pgvector) — never call real endpoints.
- Check `tests/conftest.py` for existing fixtures before creating new mocks.
- When a test fails: explain what it tests and why the change broke it before fixing.
