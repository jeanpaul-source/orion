"""Shared test fixtures for the HAL test suite.

conftest.py is a special pytest file — fixtures defined here are automatically
available to all test files in this directory without needing to import them.
"""

import os

import pytest

from hal.intent import IntentClassifier  # why: intent.py graduated to Layer 1
from hal.llm import OllamaClient

# Read Ollama URL from environment, defaulting to server-local address.
# On the laptop, set OLLAMA_HOST=http://192.168.5.10:11434 before running tests.
_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text:latest")


@pytest.fixture(scope="session")
def classifier():
    """
    Real IntentClassifier built with the live embedding model.

    scope="session" means this is created ONCE for the entire test run —
    all 39 example sentences are embedded at startup, then reused for every test.
    This keeps the test suite fast (one batch of embed calls, not one per test).

    Requires Ollama to be running. If unreachable, tests are skipped via the
    autouse fixture below.
    """
    ollama = OllamaClient(
        base_url=_OLLAMA_HOST,
        embed_model=_EMBED_MODEL,
    )
    return IntentClassifier(ollama)


@pytest.fixture(scope="session")
def require_ollama(classifier):
    """
    Skip Ollama-dependent tests when the embedding model is unreachable.

    NOT autouse — only tests that explicitly request this fixture (or modules
    that declare pytestmark = pytest.mark.usefixtures("require_ollama")) will
    be skipped.  Pure unit tests (judge, memory) must not be affected by
    Ollama availability.
    """
    if not classifier._ready:
        pytest.skip(
            f"Ollama not reachable at {_OLLAMA_HOST} — "
            "intent classifier could not build embeddings. "
            "Start Ollama and re-run, or set OLLAMA_HOST to the correct URL."
        )
