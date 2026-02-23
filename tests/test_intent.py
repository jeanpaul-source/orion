"""Tests for the intent classifier (hal/intent.py).

Each test checks that a natural-language query is routed to the correct category.
Tests use the real embedding model — see tests/README.md for prerequisites.

To add a test for a misrouted query you observed:
  1. Add the query string to the appropriate list below.
  2. Run pytest — if it fails, add a matching example sentence to hal/intent.py.
"""
import pytest

# All tests in this module require a live Ollama instance for embeddings.
# They will be skipped automatically when Ollama is unreachable.
pytestmark = pytest.mark.usefixtures("require_ollama")

# ---------------------------------------------------------------------------
# Test data — organised by expected intent
# ---------------------------------------------------------------------------

HEALTH_QUERIES = [
    "how's the lab?",
    "is everything ok?",
    "what's the current CPU usage?",
    "give me a status update",
    "how much memory is being used?",
    "is the server healthy?",
    "any resource issues right now?",
]

FACT_QUERIES = [
    "what port does prometheus run on?",
    "is ollama in docker or bare metal?",
    "where are secrets stored?",
    "what models are available in ollama?",
    "how many CPU cores does the server have?",
    "where does grafana run?",
    "what's the server's IP address?",
]

AGENTIC_QUERIES = [
    "check the lab for anything that seems off",
    "why is prometheus not responding?",
    "restart the monitoring stack",
    "investigate the high memory usage",
    "show me recent errors in the logs",
    "diagnose why this service is failing",
]

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", HEALTH_QUERIES)
def test_health_queries(classifier, query):
    """Health questions should route to the health handler (no tool loop)."""
    intent, confidence = classifier.classify(query)
    assert intent == "health", (
        f"'{query}' → '{intent}' (confidence {confidence:.2f}), expected 'health'. "
        f"Add a matching example to EXAMPLES['health'] in hal/intent.py."
    )


@pytest.mark.parametrize("query", FACT_QUERIES)
def test_fact_queries(classifier, query):
    """Documentation/config questions should route to the fact handler (no tool loop)."""
    intent, confidence = classifier.classify(query)
    assert intent == "fact", (
        f"'{query}' → '{intent}' (confidence {confidence:.2f}), expected 'fact'. "
        f"Add a matching example to EXAMPLES['fact'] in hal/intent.py."
    )


@pytest.mark.parametrize("query", AGENTIC_QUERIES)
def test_agentic_queries(classifier, query):
    """Multi-step or action queries should route to the agentic loop."""
    intent, confidence = classifier.classify(query)
    assert intent == "agentic", (
        f"'{query}' → '{intent}' (confidence {confidence:.2f}), expected 'agentic'. "
        f"Add a matching example to EXAMPLES['agentic'] in hal/intent.py."
    )


def test_low_confidence_falls_back_to_agentic(classifier):
    """Queries with no clear intent match should fall through to agentic (safe default)."""
    # "hello" is deliberately unlike any example sentence — should score below threshold
    intent, confidence = classifier.classify("hello")
    assert intent == "agentic", (
        f"Low-confidence query routed to '{intent}' (confidence {confidence:.2f}). "
        f"Expected 'agentic' fallback for queries that don't match any category well."
    )
