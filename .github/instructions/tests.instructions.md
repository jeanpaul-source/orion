---
applyTo: "tests/**/*.py"
---

# Tests — Orion

- Tests must be offline (no network calls) unless in `test_intent.py`.
- Mock external services (Ollama, vLLM, pgvector) — never call real endpoints.
- Check `tests/conftest.py` for existing fixtures before creating new mocks.
  Key doubles: `ScriptedLLM`, `ScriptedExecutor`, `FakeClassifier`, `StubKB`, `StubProm`.
- Property-based tests use Hypothesis (see `test_judge_properties.py` for pattern).
- When a test fails: explain what it tests and why the change broke it before fixing.
