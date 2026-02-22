"""
Test Suite for ORION System Prompt

Tests the effectiveness of the system prompt based on 2025 best practices:
- Honest limitation disclosure
- Infrastructure knowledge
- Knowledge base awareness
- Personality (JARVIS-like)
- Prompt injection resistance
- Dynamic context injection

Author: ORION Project
Date: November 21, 2025
"""

import pytest
from unittest.mock import AsyncMock
from src.router import IntelligenceRouter


@pytest.fixture
def mock_knowledge_stats():
    """Mock knowledge base statistics."""
    return {
        "collection": "technical-docs",
        "vectors_count": 0,
        "rebuild_required": True,
        "recommended_commands": ["orion process --max-files 50", "orion embed-index"],
        "status": "empty",
    }


@pytest.fixture
def mock_knowledge_stats_populated():
    """Mock knowledge base statistics with data."""
    return {
        "collection": "technical-docs",
        "vectors_count": 1_200_000,
        "rebuild_required": False,
        "recommended_commands": [],
        "status": "healthy",
    }


@pytest.fixture
def mock_watch_status():
    """Mock watch subsystem status."""
    return {
        "timestamp": "2025-11-21T10:00:00",
        "services": {
            "vllm": {"status": "healthy", "name": "vLLM", "latency_ms": 15.2},
            "qdrant": {"status": "healthy", "name": "Qdrant", "latency_ms": 8.1},
            "anythingllm": {
                "status": "healthy",
                "name": "AnythingLLM",
                "latency_ms": 42.3,
            },
        },
        "resources": {
            "cpu": {"percent": 35.2, "status": "healthy"},
            "memory": {
                "percent": 42.1,
                "used_gb": 26.3,
                "total_gb": 62.0,
                "status": "healthy",
            },
            "disk": {
                "percent": 55.8,
                "used_gb": 1004.4,
                "total_gb": 1800.0,
                "status": "healthy",
            },
        },
        "gpu": {
            "available": True,
            "name": "NVIDIA GeForce RTX 3090 Ti",
            "utilization": 78.5,
            "memory": {
                "used_gb": 18.4,
                "total_gb": 24.0,
                "percent": 76.7,
            },
            "temperature": 72.0,
            "power_draw": 320.5,
            "status": "healthy",
        },
        "overall": "healthy",
    }


class TestSystemPromptDynamicContext:
    """Test dynamic context injection in system prompt."""

    @pytest.mark.asyncio
    async def test_prompt_includes_current_timestamp(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt includes current timestamp."""
        router = IntelligenceRouter()

        # Mock the subsystem methods
        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        assert "as of" in prompt.lower()
        assert "2025" in prompt or "UTC" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_gpu_info(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt includes actual GPU information."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        assert "RTX 3090 Ti" in prompt or "NVIDIA GeForce RTX 3090 Ti" in prompt
        assert "24GB" in prompt or "24.0GB" in prompt

    @pytest.mark.asyncio
    async def test_prompt_reflects_empty_knowledge_base(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt accurately reflects empty knowledge base."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Should indicate RAG is empty
        assert "Empty" in prompt or "empty" in prompt or "⚠️" in prompt
        # Should include rebuild commands
        assert "orion process" in prompt or "orion embed-index" in prompt

    @pytest.mark.asyncio
    async def test_prompt_reflects_populated_knowledge_base(
        self, mock_knowledge_stats_populated, mock_watch_status
    ):
        """Verify system prompt accurately reflects populated knowledge base."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats_populated
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Should show vector count
        assert "1,200,000" in prompt or "1200000" in prompt
        # Should indicate ready/indexed
        assert (
            "ready" in prompt.lower() or "indexed" in prompt.lower() or "✅" in prompt
        )

    @pytest.mark.asyncio
    async def test_prompt_includes_current_resource_usage(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt includes current CPU/RAM usage."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Should include CPU and RAM percentages
        assert "35.2%" in prompt or "42.1%" in prompt  # CPU or RAM from mock
        assert "CPU:" in prompt or "RAM:" in prompt


class TestSystemPromptSecurity:
    """Test prompt injection resistance and security boundaries."""

    @pytest.mark.asyncio
    async def test_prompt_includes_security_boundaries(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt includes security boundary instructions."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        assert "SECURITY BOUNDARIES" in prompt
        assert "UNTRUSTED" in prompt or "untrusted" in prompt.lower()
        assert (
            "Ignore previous instructions" in prompt
            or "ignore previous" in prompt.lower()
        )

    @pytest.mark.asyncio
    async def test_prompt_includes_example_responses_for_attacks(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt includes example responses for prompt injection attempts."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Should include scripted responses for common attacks
        assert "Example responses" in prompt or "example responses" in prompt.lower()
        assert (
            "system prompt" in prompt.lower()
        )  # Example for "What's your system prompt?"


class TestSystemPromptPersonality:
    """Test JARVIS-like personality elements."""

    @pytest.mark.asyncio
    async def test_prompt_includes_personality_examples(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt includes personality guidance."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Check for personality section with actual content
        assert "YOUR PERSONALITY:" in prompt
        assert "JARVIS" in prompt
        assert "honest" in prompt.lower() and "helpful" in prompt.lower()

    @pytest.mark.asyncio
    async def test_prompt_includes_jarvis_reference(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt references JARVIS personality."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        assert "JARVIS" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_reasoning_directive(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt encourages showing reasoning process."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Check for reasoning guidance in the prompt
        assert "reasoning" in prompt.lower() or "let it show" in prompt.lower()


class TestSystemPromptLimitations:
    """Test honest limitation disclosure."""

    @pytest.mark.asyncio
    async def test_prompt_lists_capabilities_and_limitations(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt clearly separates what AI can and can't do."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        assert "What you DO have:" in prompt or "CAPABILITIES" in prompt
        assert "What you CAN'T do:" in prompt or "LIMITATIONS" in prompt

    @pytest.mark.asyncio
    async def test_prompt_mentions_action_subsystem_status(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt accurately reflects action subsystem status."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Should mention action subsystem status
        assert (
            "action subsystem" in prompt.lower() or "tool execution" in prompt.lower()
        )


class TestSystemPromptFallback:
    """Test fallback behavior when status fetching fails."""

    @pytest.mark.asyncio
    async def test_fallback_prompt_on_exception(self):
        """Verify graceful fallback to minimal prompt on error."""
        router = IntelligenceRouter()

        # Simulate exception when getting stats
        router.knowledge.get_knowledge_stats = AsyncMock(
            side_effect=Exception("Test error")
        )
        router.watch.get_full_status = AsyncMock(side_effect=Exception("Test error"))

        prompt = await router._build_dynamic_system_prompt()

        # Should still return a valid prompt (fallback)
        assert "ORION" in prompt
        assert len(prompt) > 0
        assert "homelab" in prompt.lower()


class TestSystemPromptIntegration:
    """Integration tests for complete system prompt behavior."""

    @pytest.mark.asyncio
    async def test_prompt_is_valid_markdown(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt uses valid markdown structure."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Should have markdown sections
        assert "##" in prompt  # Headers
        assert "**" in prompt or "*" in prompt  # Bold or italic

    @pytest.mark.asyncio
    async def test_prompt_length_is_reasonable(
        self, mock_knowledge_stats, mock_watch_status
    ):
        """Verify system prompt is not excessively long."""
        router = IntelligenceRouter()

        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt = await router._build_dynamic_system_prompt()

        # Updated to allow for comprehensive prompt with security boundaries
        assert 500 < len(prompt) < 4000

    @pytest.mark.asyncio
    async def test_prompt_updates_between_calls(
        self, mock_knowledge_stats, mock_knowledge_stats_populated, mock_watch_status
    ):
        """Verify system prompt changes when system state changes."""
        router = IntelligenceRouter()

        # First call - empty knowledge base
        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats
        )
        router.watch.get_full_status = AsyncMock(return_value=mock_watch_status)

        prompt1 = await router._build_dynamic_system_prompt()

        # Second call - populated knowledge base
        router.knowledge.get_knowledge_stats = AsyncMock(
            return_value=mock_knowledge_stats_populated
        )

        prompt2 = await router._build_dynamic_system_prompt()

        # Prompts should be different
        assert prompt1 != prompt2
        # Second should mention higher vector count
        assert (
            "1,200,000" in prompt2 or "1200000" in prompt2
        ) and "1,200,000" not in prompt1


# Run with: pytest tests/test_system_prompt.py -v --tb=short
