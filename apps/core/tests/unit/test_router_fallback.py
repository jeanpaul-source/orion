"""
Unit test for ORION Core router fallback classification.

This test verifies that the IntelligenceRouter's fallback classification
correctly identifies message intents without calling the LLM.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path so we can import src package
parent_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(parent_path))

from src.router import IntelligenceRouter  # noqa: E402


@pytest.fixture
def router():
    """Create a router instance for testing (without LLM dependency)."""
    # Create router - it will use config from environment
    return IntelligenceRouter()


def test_fallback_classifies_knowledge_intent(router):
    """Test that knowledge-related queries are correctly classified."""
    message = "What are Kubernetes best practices?"
    intent = router._fallback_classification(message)
    assert intent == "knowledge"


def test_fallback_classifies_action_intent(router):
    """Test that action-related queries are correctly classified."""
    message = "Check disk space on the host"
    intent = router._fallback_classification(message)
    assert intent == "action"


def test_fallback_classifies_learning_intent(router):
    """Test that learning-related queries are correctly classified."""
    message = "Learn about PostgreSQL replication"
    intent = router._fallback_classification(message)
    assert intent == "learning"


def test_fallback_classifies_watch_intent(router):
    """Test that monitoring-related queries are correctly classified."""
    message = "Display system health and resource usage metrics"
    intent = router._fallback_classification(message)
    assert intent == "watch"


def test_fallback_classifies_chat_intent(router):
    """Test that casual conversation is correctly classified."""
    message = "Hello, good morning! Nice weather today."
    intent = router._fallback_classification(message)
    assert intent == "chat"


def test_fallback_handles_multiple_keywords(router):
    """Test that fallback handles messages with multiple intent keywords."""
    # This message has both "status" (watch) and "disk" (action)
    # Should prioritize the most relevant one
    message = "Check the status of disk usage"
    intent = router._fallback_classification(message)
    # Either "action" or "watch" would be acceptable here
    assert intent in ["action", "watch"]


def test_fallback_is_case_insensitive(router):
    """Test that fallback classification is case-insensitive."""
    message_lower = "what are kubernetes best practices?"
    message_upper = "WHAT ARE KUBERNETES BEST PRACTICES?"
    message_mixed = "What Are Kubernetes Best Practices?"

    intent_lower = router._fallback_classification(message_lower)
    intent_upper = router._fallback_classification(message_upper)
    intent_mixed = router._fallback_classification(message_mixed)

    # All should return the same intent
    assert intent_lower == intent_upper == intent_mixed == "knowledge"
