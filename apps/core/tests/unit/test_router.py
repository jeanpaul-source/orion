"""
Tests for Intelligence Router

Tests the IntelligenceRouter class which routes messages to appropriate
subsystems based on intent classification.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import httpx
from unittest.mock import Mock, AsyncMock, patch
import json

from src.router import IntelligenceRouter
from src.config import config


# ============================================================================
# Initialization Tests
# ============================================================================


class TestRouterInitialization:
    """Tests for router initialization"""

    @patch("src.router.KnowledgeSubsystem")
    @patch("src.router.ActionSubsystem")
    @patch("src.router.LearningSubsystem")
    @patch("src.router.WatchSubsystem")
    @patch("src.router.DebugTracker")
    def test_router_init(
        self, mock_debug, mock_watch, mock_learning, mock_action, mock_knowledge
    ):
        """Test router initialization"""
        router = IntelligenceRouter()

        # Verify subsystems were created
        mock_knowledge.assert_called_once()
        mock_action.assert_called_once()
        mock_learning.assert_called_once()
        mock_watch.assert_called_once()
        mock_debug.assert_called_once_with(max_breadcrumbs=100)

        # Verify subsystems are stored
        assert router.knowledge is not None
        assert router.action is not None
        assert router.learning is not None
        assert router.watch is not None
        assert router.debug_tracker is not None


# ============================================================================
# Fallback Classification Tests
# ============================================================================


class TestFallbackClassification:
    """Tests for keyword-based fallback classification"""

    @patch("src.router.KnowledgeSubsystem")
    @patch("src.router.ActionSubsystem")
    @patch("src.router.LearningSubsystem")
    @patch("src.router.WatchSubsystem")
    @patch("src.router.DebugTracker")
    def setup_method(
        self, method, mock_debug, mock_watch, mock_learning, mock_action, mock_knowledge
    ):
        """Set up router for each test"""
        self.router = IntelligenceRouter()

    def test_fallback_knowledge_classification(self):
        """Test knowledge intent classification via keywords"""
        # Test various knowledge keywords
        assert (
            self.router._fallback_classification("What is Kubernetes?") == "knowledge"
        )
        assert (
            self.router._fallback_classification("How do I configure PostgreSQL?")
            == "knowledge"
        )
        assert (
            self.router._fallback_classification("Why is my service failing?")
            == "knowledge"
        )
        assert (
            self.router._fallback_classification("Explain GPU passthrough")
            == "knowledge"
        )
        assert (
            self.router._fallback_classification("Best practices for Docker")
            == "knowledge"
        )
        assert (
            self.router._fallback_classification("guide to setting up RAG")
            == "knowledge"
        )

    def test_fallback_action_classification(self):
        """Test action intent classification via keywords"""
        assert self.router._fallback_classification("Check disk space") == "action"
        assert (
            self.router._fallback_classification("Restart the vllm container")
            == "action"
        )
        assert self.router._fallback_classification("Run docker ps") == "action"
        assert (
            self.router._fallback_classification("Execute the backup script")
            == "action"
        )
        # Note: "show" contains "how" substring, so use "list" instead
        assert self.router._fallback_classification("List all running VMs") == "action"
        assert self.router._fallback_classification("List all containers") == "action"

    def test_fallback_learning_classification(self):
        """Test learning intent classification via keywords"""
        assert (
            self.router._fallback_classification("Learn about PostgreSQL replication")
            == "learning"
        )
        assert (
            self.router._fallback_classification("Research Kubernetes operators")
            == "learning"
        )
        assert (
            self.router._fallback_classification("Study vector databases") == "learning"
        )
        assert (
            self.router._fallback_classification("Teach yourself about GPU passthrough")
            == "learning"
        )

    def test_fallback_watch_classification(self):
        """Test watch intent classification via keywords"""
        # "system status" without action/knowledge keywords
        assert self.router._fallback_classification("System status") == "watch"
        # "health" without "check"
        assert self.router._fallback_classification("Service health report") == "watch"
        assert self.router._fallback_classification("Monitor resource usage") == "watch"
        # "resources" without action keywords
        assert self.router._fallback_classification("Current resources") == "watch"
        assert self.router._fallback_classification("Disk usage statistics") == "watch"

    def test_fallback_chat_classification(self):
        """Test chat (default) classification"""
        assert self.router._fallback_classification("Hello") == "chat"
        assert self.router._fallback_classification("Thanks!") == "chat"
        assert self.router._fallback_classification("Good morning") == "chat"
        assert self.router._fallback_classification("Random message") == "chat"

    def test_fallback_case_insensitive(self):
        """Test that classification is case-insensitive"""
        assert self.router._fallback_classification("WHAT IS DOCKER?") == "knowledge"
        assert self.router._fallback_classification("CHECK DISK SPACE") == "action"
        assert self.router._fallback_classification("LEARN ABOUT K8S") == "learning"


# ============================================================================
# Intent Classification Tests (with vLLM mocking)
# ============================================================================


class TestIntentClassification:
    """Tests for vLLM-based intent classification"""

    @patch("src.router.KnowledgeSubsystem")
    @patch("src.router.ActionSubsystem")
    @patch("src.router.LearningSubsystem")
    @patch("src.router.WatchSubsystem")
    @patch("src.router.DebugTracker")
    def setup_method(
        self, method, mock_debug, mock_watch, mock_learning, mock_action, mock_knowledge
    ):
        """Set up router for each test"""
        self.router = IntelligenceRouter()

    @pytest.mark.asyncio
    async def test_classify_intent_success(self):
        """Test successful intent classification via vLLM"""
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "knowledge",
                                "confidence": 0.95,
                                "reasoning": "User is asking a question",
                            }
                        )
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            intent, confidence = await self.router._classify_intent(
                "What is Kubernetes?", {}
            )

            assert intent == "knowledge"
            assert confidence == 0.95

    @pytest.mark.asyncio
    async def test_classify_intent_fallback_on_error(self):
        """Test fallback to keyword classification on vLLM error"""
        with patch("httpx.AsyncClient") as mock_client:
            # Simulate connection error
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            intent, confidence = await self.router._classify_intent(
                "What is Docker?", {}
            )

            # Should fall back to keyword classification
            assert intent == "knowledge"  # "What" triggers knowledge
            assert confidence == 0.5  # Fallback confidence

    @pytest.mark.asyncio
    async def test_classify_intent_handles_invalid_json(self):
        """Test handling of invalid JSON from vLLM"""
        mock_response = {"choices": [{"message": {"content": "Not valid JSON"}}]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            intent, confidence = await self.router._classify_intent(
                "Check disk space", {}
            )

            # Should fall back
            assert intent == "action"  # "Check" triggers action
            assert confidence == 0.5

    @pytest.mark.asyncio
    async def test_classify_intent_uses_api_key_if_provided(self):
        """Test that API key is included in headers if configured"""
        original_key = config.vllm_api_key
        config.vllm_api_key = "test-api-key"  # pragma: allowlist secret

        try:
            mock_response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "chat",
                                    "confidence": 0.8,
                                    "reasoning": "Greeting",
                                }
                            )
                        }
                    }
                ]
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(
                    return_value=Mock(
                        json=Mock(return_value=mock_response), raise_for_status=Mock()
                    )
                )
                mock_client.return_value.__aenter__.return_value.post = mock_post

                await self.router._classify_intent("Hello", {})

                # Verify headers were passed
                call_kwargs = mock_post.call_args[1]
                assert "headers" in call_kwargs
                assert call_kwargs["headers"]["Authorization"] == "Bearer test-api-key"

        finally:
            config.vllm_api_key = original_key


# ============================================================================
# Route Method Tests
# ============================================================================


class TestRouteMethod:
    """Tests for main route() method"""

    @patch("src.router.KnowledgeSubsystem")
    @patch("src.router.ActionSubsystem")
    @patch("src.router.LearningSubsystem")
    @patch("src.router.WatchSubsystem")
    @patch("src.router.DebugTracker")
    def setup_method(
        self, method, mock_debug, mock_watch, mock_learning, mock_action, mock_knowledge
    ):
        """Set up router for each test"""
        self.router = IntelligenceRouter()

        # Set up mock subsystems
        self.router.knowledge.handle = AsyncMock(return_value="Knowledge response")
        self.router.action.handle = AsyncMock(return_value="Action response")
        self.router.learning.handle = AsyncMock(return_value="Learning response")
        self.router.watch.handle = AsyncMock(return_value="Watch response")

        # Mock methods needed for system prompt building
        self.router.knowledge.get_knowledge_stats = AsyncMock(
            return_value={"vectors_count": 1200000, "recommended_commands": []}
        )
        self.router.watch.get_full_status = AsyncMock(
            return_value={
                "gpu": {"temperature": 65, "utilization": 80},
                "resources": {"cpu": {"percent": 25}, "memory": {"percent": 45}},
            }
        )

        # Mock debug tracker
        self.router.debug_tracker.track = AsyncMock()
        self.router.debug_tracker.analyze_error = AsyncMock(
            return_value={"divergence_point": "Test error", "suggestions": []}
        )

    @pytest.mark.asyncio
    async def test_route_to_knowledge(self):
        """Test routing to knowledge subsystem"""
        # Ensure knowledge subsystem is enabled
        from src.config import config

        original_enable = config.enable_knowledge
        config.enable_knowledge = True

        try:
            # Mock intent classification
            with patch.object(
                self.router, "_classify_intent", return_value=("knowledge", 0.9)
            ):
                response = await self.router.route("What is Docker?", {})

                assert response == "Knowledge response"
                self.router.knowledge.handle.assert_called_once()
        finally:
            config.enable_knowledge = original_enable

    @pytest.mark.asyncio
    async def test_route_to_action(self):
        """Test routing to action subsystem"""
        from src.config import config

        original_enable = config.enable_action
        config.enable_action = True

        try:
            with patch.object(
                self.router, "_classify_intent", return_value=("action", 0.85)
            ):
                response = await self.router.route("Check disk usage", {})

                assert response == "Action response"
                self.router.action.handle.assert_called_once()
        finally:
            config.enable_action = original_enable

    @pytest.mark.asyncio
    async def test_route_to_learning(self):
        """Test routing to learning subsystem"""
        from src.config import config

        original_enable = config.enable_learning
        config.enable_learning = True

        try:
            with patch.object(
                self.router, "_classify_intent", return_value=("learning", 0.8)
            ):
                response = await self.router.route("Learn about PostgreSQL", {})

                assert response == "Learning response"
                self.router.learning.handle.assert_called_once()
        finally:
            config.enable_learning = original_enable

    @pytest.mark.asyncio
    async def test_route_to_watch(self):
        """Test routing to watch subsystem"""
        from src.config import config

        original_enable = config.enable_watch
        config.enable_watch = True

        try:
            with patch.object(
                self.router, "_classify_intent", return_value=("watch", 0.82)
            ):
                response = await self.router.route("What's the system status?", {})

                assert response == "Watch response"
                self.router.watch.handle.assert_called_once()
        finally:
            config.enable_watch = original_enable

    @pytest.mark.asyncio
    async def test_route_to_chat(self):
        """Test routing to general chat"""
        with patch.object(self.router, "_classify_intent", return_value=("chat", 0.95)):
            with patch.object(
                self.router, "_general_chat", return_value="Chat response"
            ) as mock_chat:
                response = await self.router.route("Hello!", {})

                assert response == "Chat response"
                mock_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_disabled_subsystem_falls_back_to_chat(self):
        """Test that disabled subsystems fall back to chat"""
        original_enable = config.enable_knowledge
        config.enable_knowledge = False

        try:
            with patch.object(
                self.router, "_classify_intent", return_value=("knowledge", 0.9)
            ):
                with patch.object(
                    self.router, "_general_chat", return_value="Chat fallback"
                ) as mock_chat:
                    response = await self.router.route("What is Docker?", {})

                    assert response == "Chat fallback"
                    mock_chat.assert_called_once()
                    # Knowledge subsystem should NOT be called
                    self.router.knowledge.handle.assert_not_called()

        finally:
            config.enable_knowledge = original_enable

    @pytest.mark.asyncio
    async def test_route_handles_subsystem_error(self):
        """Test error handling when subsystem fails"""
        from src.config import config

        original_enable = config.enable_knowledge
        config.enable_knowledge = True

        try:
            # Make knowledge subsystem raise an error
            self.router.knowledge.handle = AsyncMock(
                side_effect=Exception("Subsystem error")
            )

            with patch.object(
                self.router, "_classify_intent", return_value=("knowledge", 0.9)
            ):
                response = await self.router.route("What is Docker?", {})

                # Should return error message in format: "I encountered an error processing your message: ..."
                assert "encountered an error" in response.lower()
                assert "Subsystem error" in response

                # Error analysis should have been called
                self.router.debug_tracker.analyze_error.assert_called_once()
        finally:
            config.enable_knowledge = original_enable

    @pytest.mark.asyncio
    async def test_route_tracks_debug_breadcrumbs(self):
        """Test that routing tracks debug breadcrumbs"""
        with patch.object(
            self.router, "_classify_intent", return_value=("knowledge", 0.9)
        ):
            await self.router.route("What is Docker?", {})

            # Verify debug tracker was called
            assert self.router.debug_tracker.track.call_count >= 3
            # Should track: message_received, intent_classified, routing_to_X, response_generated


# ============================================================================
# General Chat Tests
# ============================================================================


class TestGeneralChat:
    """Tests for general conversation handling"""

    @patch("src.router.KnowledgeSubsystem")
    @patch("src.router.ActionSubsystem")
    @patch("src.router.LearningSubsystem")
    @patch("src.router.WatchSubsystem")
    @patch("src.router.DebugTracker")
    def setup_method(
        self, method, mock_debug, mock_watch, mock_learning, mock_action, mock_knowledge
    ):
        """Set up router for each test"""
        self.router = IntelligenceRouter()

    @pytest.mark.asyncio
    async def test_general_chat_success(self):
        """Test successful general chat response"""
        mock_response = {
            "choices": [{"message": {"content": "Hello! How can I help you today?"}}]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            response = await self.router._general_chat("Hello", {})

            assert response == "Hello! How can I help you today?"

    @pytest.mark.asyncio
    async def test_general_chat_includes_history(self):
        """Test that general chat includes conversation history"""
        mock_response = {
            "choices": [{"message": {"content": "Sure, I can help with that."}}]
        }

        context = {
            "history": [
                {"role": "user", "content": "Previous message"},
                {"role": "assistant", "content": "Previous response"},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await self.router._general_chat("New message", context)

            # Verify history was included in messages
            call_kwargs = mock_post.call_args[1]
            messages = call_kwargs["json"]["messages"]

            # Should have: system, previous user, previous assistant, new user
            assert len(messages) >= 4

    @pytest.mark.asyncio
    async def test_general_chat_limits_history(self):
        """Test that general chat limits history to last 5 messages"""
        # Create 10 messages in history
        history = []
        for i in range(10):
            history.append({"role": "user", "content": f"Message {i}"})
            history.append({"role": "assistant", "content": f"Response {i}"})

        context = {"history": history}

        mock_response = {"choices": [{"message": {"content": "Response"}}]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await self.router._general_chat("New message", context)

            # Verify only last 5 history messages were included
            call_kwargs = mock_post.call_args[1]
            messages = call_kwargs["json"]["messages"]

            # Should have: system + 5 history + new message = 7 messages
            assert len(messages) == 7

    @pytest.mark.asyncio
    async def test_general_chat_error_handling(self):
        """Test error handling in general chat"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            response = await self.router._general_chat("Hello", {})

            # Should return error message
            assert "trouble" in response.lower()


# ============================================================================
# Dynamic System Prompt Tests
# ============================================================================


class TestDynamicSystemPrompt:
    """Tests for dynamic system prompt generation"""

    @patch("src.router.KnowledgeSubsystem")
    @patch("src.router.ActionSubsystem")
    @patch("src.router.LearningSubsystem")
    @patch("src.router.WatchSubsystem")
    @patch("src.router.DebugTracker")
    def setup_method(
        self, method, mock_debug, mock_watch, mock_learning, mock_action, mock_knowledge
    ):
        """Set up router for each test"""
        self.router = IntelligenceRouter()

    @pytest.mark.asyncio
    async def test_build_dynamic_system_prompt_success(self):
        """Test successful dynamic system prompt building"""
        # Mock subsystem responses
        self.router.knowledge.get_knowledge_stats = AsyncMock(
            return_value={"vectors_count": 1200000, "collections": ["technical-docs"]}
        )

        self.router.watch.get_full_status = AsyncMock(
            return_value={
                "gpu": {
                    "available": True,
                    "name": "RTX 3090 Ti",
                    "memory": {"total_gb": 24},
                },
                "resources": {"cpu": {"percent": 25.0}, "memory": {"percent": 60.0}},
            }
        )

        prompt = await self.router._build_dynamic_system_prompt()

        # Verify key elements in prompt
        assert "ORION" in prompt
        assert "1,200,000 vectors" in prompt or "1200000 vectors" in prompt
        assert "RTX 3090 Ti" in prompt
        assert "CPU: 25.0%" in prompt
        assert "RAM: 60.0%" in prompt

    @pytest.mark.asyncio
    async def test_build_dynamic_system_prompt_empty_kb(self):
        """Test system prompt with empty knowledge base"""
        self.router.knowledge.get_knowledge_stats = AsyncMock(
            return_value={
                "vectors_count": 0,
                "recommended_commands": ["orion process", "orion embed-index"],
            }
        )

        self.router.watch.get_full_status = AsyncMock(
            return_value={"gpu": {"available": False}, "resources": {}}
        )

        prompt = await self.router._build_dynamic_system_prompt()

        # Should warn about empty KB and provide rebuild commands
        assert "Empty" in prompt or "rebuild" in prompt
        assert "orion" in prompt

    @pytest.mark.asyncio
    async def test_build_dynamic_system_prompt_fallback_on_error(self):
        """Test fallback prompt on error"""
        # Make subsystems raise errors
        self.router.knowledge.get_knowledge_stats = AsyncMock(
            side_effect=Exception("KB error")
        )

        prompt = await self.router._build_dynamic_system_prompt()

        # Should return minimal fallback prompt
        assert "ORION" in prompt
        assert len(prompt) < 500  # Fallback is much shorter


# ============================================================================
# Integration Tests
# ============================================================================


class TestRouterIntegration:
    """Integration tests for complete routing workflows"""

    @patch("src.router.KnowledgeSubsystem")
    @patch("src.router.ActionSubsystem")
    @patch("src.router.LearningSubsystem")
    @patch("src.router.WatchSubsystem")
    @patch("src.router.DebugTracker")
    def setup_method(
        self, method, mock_debug, mock_watch, mock_learning, mock_action, mock_knowledge
    ):
        """Set up router for each test"""
        self.router = IntelligenceRouter()

        # Set up mock subsystems
        self.router.knowledge.handle = AsyncMock(
            return_value="Knowledge: Docker is a containerization platform"
        )
        self.router.action.handle = AsyncMock(return_value="Action: Disk usage is 45%")
        self.router.learning.handle = AsyncMock(
            return_value="Learning: Started learning about PostgreSQL"
        )
        self.router.watch.handle = AsyncMock(
            return_value="Watch: All systems operational"
        )

        # Mock debug tracker
        self.router.debug_tracker.track = AsyncMock()
        self.router.debug_tracker.analyze_error = AsyncMock()

    @pytest.mark.asyncio
    async def test_complete_knowledge_workflow(self):
        """Test complete workflow for knowledge query"""
        from src.config import config

        original_enable = config.enable_knowledge
        config.enable_knowledge = True

        try:
            # Mock knowledge subsystem to return realistic response
            self.router.knowledge.handle = AsyncMock(
                return_value="Docker is a containerization platform that allows developers to package applications..."
            )

            # Mock vLLM classification
            mock_classification_response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "knowledge",
                                    "confidence": 0.95,
                                    "reasoning": "Technical question",
                                }
                            )
                        }
                    }
                ]
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(
                    return_value=Mock(
                        json=Mock(return_value=mock_classification_response),
                        raise_for_status=Mock(),
                    )
                )
                mock_client.return_value.__aenter__.return_value.post = mock_post

                response = await self.router.route(
                    "What is Docker and how does it work?", {"history": []}
                )

                # Verify response contains Docker info
                assert "Docker" in response
                assert "containerization" in response

                # Verify knowledge subsystem was called
                self.router.knowledge.handle.assert_called_once()
        finally:
            config.enable_knowledge = original_enable

    @pytest.mark.asyncio
    async def test_fallback_to_keywords_on_vllm_failure(self):
        """Test fallback to keyword classification when vLLM fails"""
        from src.config import config

        original_enable = config.enable_action
        config.enable_action = True

        try:
            # Mock action subsystem to return realistic response
            self.router.action.handle = AsyncMock(
                return_value="Disk usage on nvme2: 45% used (850GB / 1.8TB)"
            )

            with patch("httpx.AsyncClient") as mock_client:
                # Simulate vLLM failure
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=httpx.ConnectError("Connection refused")
                )

                response = await self.router.route(
                    "Check disk space on nvme2",
                    {},  # Should trigger "action" via keywords
                )

                # Should still route correctly via fallback
                assert "Disk" in response or "disk" in response
                self.router.action.handle.assert_called_once()
        finally:
            config.enable_action = original_enable
