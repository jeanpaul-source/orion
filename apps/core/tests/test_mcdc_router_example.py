"""
Example MC/DC Tests for Intelligence Router

Demonstrates Modified Condition/Decision Coverage testing patterns.
These tests ensure each condition independently affects decision outcomes.
"""

import pytest
from unittest.mock import patch

# Adjust import based on your structure
try:
    from src.router import IntelligenceRouter
except ImportError:
    # Fallback for different import styles
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from router import IntelligenceRouter


@pytest.mark.mcdc
class TestMCDC_RouterClassification:
    """
    MC/DC tests for router fallback classification.

    Tests compound condition: if any(keyword in message for keyword in keywords)
    Each test verifies a condition independently affects the outcome.
    """

    @patch("src.router.KnowledgeSubsystem")
    @patch("src.router.ActionSubsystem")
    @patch("src.router.LearningSubsystem")
    @patch("src.router.WatchSubsystem")
    @patch("src.router.DebugTracker")
    def setup_method(self, method, *mocks):
        """Initialize router for each test"""
        self.router = IntelligenceRouter()

    # ========================================================================
    # Decision: Knowledge classification
    # Conditions: "what" OR "how" OR "why" in message
    # ========================================================================

    def test_mcdc_knowledge_what_keyword_alone(self):
        """
        MC/DC: "what" present, others absent → knowledge

        Tests that "what" keyword independently triggers knowledge classification.
        """
        result = self.router._fallback_classification("What is Docker?")
        assert result == "knowledge", "Should classify as knowledge with 'what' keyword"

    def test_mcdc_knowledge_how_keyword_alone(self):
        """
        MC/DC: "how" present, others absent → knowledge

        Tests that "how" keyword independently triggers knowledge classification.
        """
        result = self.router._fallback_classification("How to configure?")
        assert result == "knowledge", "Should classify as knowledge with 'how' keyword"

    def test_mcdc_knowledge_why_keyword_alone(self):
        """
        MC/DC: "why" present, others absent → knowledge

        Tests that "why" keyword independently triggers knowledge classification.
        """
        result = self.router._fallback_classification("Why is service down?")
        assert result == "knowledge", "Should classify as knowledge with 'why' keyword"

    def test_mcdc_knowledge_no_keywords(self):
        """
        MC/DC: No knowledge keywords → NOT knowledge

        Baseline test showing that without knowledge keywords,
        classification is something else (likely action).
        """
        result = self.router._fallback_classification("List containers")
        assert (
            result != "knowledge"
        ), "Should NOT classify as knowledge without keywords"

    # ========================================================================
    # Decision: Action classification
    # Conditions: "check" OR "run" OR "execute" in message
    # ========================================================================

    def test_mcdc_action_check_keyword_alone(self):
        """
        MC/DC: "check" present → action

        Tests that "check" keyword independently triggers action classification.
        """
        result = self.router._fallback_classification("Check disk space")
        assert result == "action", "Should classify as action with 'check' keyword"

    def test_mcdc_action_run_keyword_alone(self):
        """
        MC/DC: "run" present → action

        Tests that "run" keyword independently triggers action classification.
        """
        result = self.router._fallback_classification("Run backup script")
        assert result == "action", "Should classify as action with 'run' keyword"

    def test_mcdc_action_execute_keyword_alone(self):
        """
        MC/DC: "execute" present → action

        Tests that "execute" keyword independently triggers action classification.
        """
        result = self.router._fallback_classification("Execute command")
        assert result == "action", "Should classify as action with 'execute' keyword"


# ============================================================================
# Run these tests with:
# pytest tests/test_mcdc_router_example.py -v -m mcdc
# pytest tests/test_mcdc_router_example.py -v --cov=src.router --cov-branch
# ============================================================================
