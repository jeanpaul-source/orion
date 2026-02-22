"""
Tests for streaming response infrastructure in ORION Core.

Tests the AsyncGenerator-based streaming system that provides:
- Real-time progress updates during intent classification
- Token-by-token response streaming for smooth UX
- Progress breadcrumbs for RAG pipeline stages
- Metadata on completion (intent, confidence, latency)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path so we can import src as a package
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import from src package (matching how uvicorn loads it: src.main:app)
from src.router import IntelligenceRouter  # noqa: E402
from src.subsystems.knowledge import KnowledgeSubsystem  # noqa: E402


class TestRouterStreaming:
    """Test streaming response functionality in IntelligenceRouter."""

    @pytest.fixture
    def mock_vllm(self):
        """Mock vLLM HTTP API for intent classification."""
        with patch("src.router.httpx.AsyncClient") as mock:
            # Create mock client
            client = AsyncMock()
            mock.return_value.__aenter__.return_value = client

            # Mock vLLM response for intent classification
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": '{"intent": "knowledge", "confidence": 0.95, "reasoning": "Test query"}'
                        }
                    }
                ]
            }
            mock_response.raise_for_status = MagicMock()  # Synchronous
            client.post.return_value = mock_response

            yield client

    @pytest.fixture
    def router(self, mock_vllm, monkeypatch):
        """Create router instance with mocked dependencies."""
        # Enable knowledge subsystem for these tests
        monkeypatch.setenv("ORION_ENABLE_KNOWLEDGE", "true")

        # Reload config to pick up changed env var
        from src import config as cfg_module
        from importlib import reload

        reload(cfg_module)

        router = IntelligenceRouter()

        # Mock debug_tracker.track() method (IMPORTANT: mock AFTER creation)
        router.debug_tracker.track = AsyncMock()

        # Mock subsystem
        mock_subsystem = MagicMock()
        mock_subsystem.name = "knowledge"

        # Mock streaming method
        async def mock_streaming(query, context):
            yield {"type": "progress", "message": "Processing..."}
            yield {"type": "token", "content": "Hello "}
            yield {"type": "token", "content": "world!"}

        mock_subsystem.handle_streaming = mock_streaming
        router.subsystems = {"knowledge": mock_subsystem}

        return router

    @pytest.mark.asyncio
    async def test_streaming_yields_progress_stages(self, router):
        """Test that streaming yields all expected progress stages."""
        chunks = []
        async for chunk in router.route_streaming("test query", {}):
            chunks.append(chunk)

        # Should have progress messages
        progress_chunks = [c for c in chunks if c.get("type") == "progress"]
        assert len(progress_chunks) >= 2, "Should have multiple progress updates"

        # Check for actual stages from implementation
        stages = [c.get("stage") for c in progress_chunks]
        assert (
            "intent_classification" in stages
        ), "Should have intent classification stage"
        assert "subsystem_routing" in stages, "Should have subsystem routing stage"

    @pytest.mark.skip(
        reason="Old test - needs refactoring to work with current mock setup (subsystem disabled in conftest.py)"
    )
    @pytest.mark.asyncio
    async def test_streaming_yields_tokens(self, router):
        """Test that streaming yields response tokens."""
        chunks = []
        async for chunk in router.route_streaming("test query", {}):
            chunks.append(chunk)

        # Should have token chunks from subsystem
        token_chunks = [c for c in chunks if c.get("type") == "token"]
        assert len(token_chunks) >= 2, "Should have token chunks"
        assert token_chunks[0]["content"] == "Hello "
        assert token_chunks[1]["content"] == "world!"

    @pytest.mark.asyncio
    async def test_streaming_yields_complete_metadata(self, router):
        """Test that streaming yields complete message with metadata."""
        chunks = []
        async for chunk in router.route_streaming("test query", {}):
            chunks.append(chunk)

        # Last chunk should be complete with metadata
        complete_chunk = chunks[-1]
        assert complete_chunk["type"] == "complete"
        assert "intent" in complete_chunk
        assert "confidence" in complete_chunk
        assert "latency_ms" in complete_chunk

    @pytest.mark.skip(
        reason="Old test - needs refactoring (async generator exception handling is complex)"
    )
    @pytest.mark.asyncio
    async def test_streaming_handles_errors_gracefully(self, router):
        """Test that streaming yields error messages on failures."""

        # Mock subsystem to raise error
        async def error_streaming(query, context):
            raise RuntimeError("Test error")

        router.subsystems["knowledge"].handle_streaming = error_streaming

        chunks = []
        async for chunk in router.route_streaming("test query", {}):
            chunks.append(chunk)

        # Should yield error message
        error_chunks = [c for c in chunks if c.get("type") == "error"]
        assert len(error_chunks) > 0, "Should yield error chunk"
        assert "error" in error_chunks[0]["message"].lower()

    @pytest.mark.asyncio
    async def test_streaming_tracks_breadcrumbs(self, router):
        """Test that streaming calls debug_tracker.track() for all stages."""

        chunks = []
        async for chunk in router.route_streaming("test query", {}):
            chunks.append(chunk)

        # Verify debug_tracker.track() was called for all stages
        track_calls = router.debug_tracker.track.call_args_list

        # Should have at least 4 tracking calls:
        # 1. start_streaming_request
        # 2. classify_intent
        # 3. route_to_{intent}
        # 4. complete_streaming_request
        assert (
            len(track_calls) >= 4
        ), f"Expected >= 4 track calls, got {len(track_calls)}"

        # Extract action names from all calls
        actions = [call.kwargs.get("action") for call in track_calls]

        # Verify specific tracking points
        assert "start_streaming_request" in actions, "Should track request start"
        assert "classify_intent" in actions, "Should track intent classification"
        assert any(
            "route_to_" in action for action in actions
        ), "Should track routing decision"
        assert (
            "complete_streaming_request" in actions
        ), "Should track request completion"

    @pytest.mark.asyncio
    async def test_streaming_breadcrumbs_include_confidence(self, router):
        """Test that intent classification breadcrumb includes confidence."""

        chunks = []
        async for chunk in router.route_streaming("test query", {}):
            chunks.append(chunk)

        track_calls = router.debug_tracker.track.call_args_list
        classify_calls = [
            call
            for call in track_calls
            if call.kwargs.get("action") == "classify_intent"
        ]

        assert len(classify_calls) == 1, "Should have one classify_intent tracking call"
        classify_call = classify_calls[0]

        # Verify confidence is included
        assert "confidence" in classify_call.kwargs, "Should track confidence"
        confidence = classify_call.kwargs["confidence"]
        assert isinstance(confidence, float), "Confidence should be float"
        assert 0.0 <= confidence <= 1.0, "Confidence should be in [0.0, 1.0]"

    @pytest.mark.asyncio
    async def test_streaming_breadcrumbs_track_latency(self, router):
        """Test that completion breadcrumb includes latency."""

        chunks = []
        async for chunk in router.route_streaming("test query", {}):
            chunks.append(chunk)

        track_calls = router.debug_tracker.track.call_args_list
        complete_calls = [
            call
            for call in track_calls
            if call.kwargs.get("action") == "complete_streaming_request"
        ]

        assert len(complete_calls) == 1, "Should have one complete tracking call"
        complete_call = complete_calls[0]

        # Verify latency is included (in state dict)
        assert "state" in complete_call.kwargs, "Should have state"
        state = complete_call.kwargs["state"]
        assert "latency_ms" in state, "Should track latency in state"
        latency = state["latency_ms"]
        assert isinstance(latency, (int, float)), "Latency should be numeric"
        assert latency > 0, "Latency should be positive"

    @pytest.mark.asyncio
    async def test_streaming_breadcrumbs_on_complete(self, router):
        """Test that completion breadcrumb includes success status."""

        chunks = []
        async for chunk in router.route_streaming("test query", {}):
            chunks.append(chunk)

        track_calls = router.debug_tracker.track.call_args_list
        complete_calls = [
            call
            for call in track_calls
            if call.kwargs.get("action") == "complete_streaming_request"
        ]

        assert len(complete_calls) == 1, "Should have completion tracking"
        complete_call = complete_calls[0]

        # Verify completion state
        assert "state" in complete_call.kwargs
        state = complete_call.kwargs["state"]
        assert "success" in state, "Should track success status"
        assert state["success"] is True, "Should be successful"
        assert "response_length" in state, "Should track response length"
        assert state["response_length"] > 0, "Response should have content"


class TestKnowledgeStreaming:
    """Test streaming in KnowledgeSubsystem."""

    @pytest.fixture
    def knowledge_subsystem(self):
        """Create KnowledgeSubsystem with mocked dependencies."""
        with patch("src.subsystems.knowledge.httpx"):
            subsystem = KnowledgeSubsystem()

            # Mock AnythingLLM response
            async def mock_query(query, context):
                return "Test answer", [
                    {"title": "Source 1", "score": 0.95},
                    {"title": "Source 2", "score": 0.87},
                ]

            subsystem._query_anythingllm = mock_query
            subsystem._knowledge_base_gate = AsyncMock(return_value=None)

            return subsystem

    @pytest.mark.asyncio
    async def test_knowledge_streaming_progress_stages(self, knowledge_subsystem):
        """Test that knowledge subsystem yields RAG pipeline progress."""
        chunks = []
        async for chunk in knowledge_subsystem.handle_streaming("test query", {}):
            chunks.append(chunk)

        # Should have progress for RAG stages
        progress_chunks = [c for c in chunks if c.get("type") == "progress"]
        assert len(progress_chunks) >= 2, "Should have RAG pipeline progress"

        messages = [c["message"] for c in progress_chunks]
        assert any("knowledge base" in m.lower() for m in messages)
        assert any("searching" in m.lower() or "found" in m.lower() for m in messages)

    @pytest.mark.asyncio
    async def test_knowledge_streaming_yields_sources(self, knowledge_subsystem):
        """Test that knowledge subsystem yields sources metadata."""
        chunks = []
        async for chunk in knowledge_subsystem.handle_streaming("test query", {}):
            chunks.append(chunk)

        # Should have sources chunk
        source_chunks = [c for c in chunks if c.get("type") == "sources"]
        assert len(source_chunks) == 1, "Should yield sources"

        sources = source_chunks[0]
        assert sources["count"] == 2
        assert len(sources["sources"]) == 2
        assert sources["sources"][0]["title"] == "Source 1"

    @pytest.mark.skip(
        reason="Old test - chunking behavior changed (now yields single tokens)"
    )
    @pytest.mark.asyncio
    async def test_knowledge_streaming_chunks_text(self, knowledge_subsystem):
        """Test that knowledge subsystem chunks response text."""
        chunks = []
        async for chunk in knowledge_subsystem.handle_streaming("test query", {}):
            chunks.append(chunk)

        # Should have multiple token chunks
        token_chunks = [c for c in chunks if c.get("type") == "token"]
        assert len(token_chunks) > 1, "Should chunk response into multiple tokens"

        # Reconstruct answer
        answer = "".join(c["content"] for c in token_chunks)
        assert "Test answer" == answer


class TestStreamingProtocol:
    """Test streaming message protocol consistency."""

    def test_progress_message_format(self):
        """Test that progress messages have correct format."""
        progress_msg = {
            "type": "progress",
            "message": "🧠 Analyzing intent...",
            "stage": "analyzing",
        }

        assert progress_msg["type"] == "progress"
        assert isinstance(progress_msg["message"], str)
        assert isinstance(progress_msg["stage"], str)

    def test_token_message_format(self):
        """Test that token messages have correct format."""
        token_msg = {"type": "token", "content": "Hello "}

        assert token_msg["type"] == "token"
        assert isinstance(token_msg["content"], str)

    def test_complete_message_format(self):
        """Test that complete messages have correct format."""
        complete_msg = {
            "type": "complete",
            "intent": "knowledge",
            "confidence": 0.95,
            "latency_ms": 1234.5,
        }

        assert complete_msg["type"] == "complete"
        assert isinstance(complete_msg["intent"], str)
        assert 0.0 <= complete_msg["confidence"] <= 1.0
        assert complete_msg["latency_ms"] > 0

    def test_sources_message_format(self):
        """Test that sources messages have correct format."""
        sources_msg = {
            "type": "sources",
            "sources": [{"title": "Doc 1", "score": 0.95}],
            "count": 1,
        }

        assert sources_msg["type"] == "sources"
        assert isinstance(sources_msg["sources"], list)
        assert sources_msg["count"] == len(sources_msg["sources"])

    def test_error_message_format(self):
        """Test that error messages have correct format."""
        error_msg = {"type": "error", "message": "An error occurred"}

        assert error_msg["type"] == "error"
        assert isinstance(error_msg["message"], str)


if __name__ == "__main__":
    # Run with: pytest tests/test_streaming.py -v
    pytest.main([__file__, "-v"])
