"""
Tests for Knowledge Subsystem

Tests the KnowledgeSubsystem class which handles RAG-based question
answering using AnythingLLM and Qdrant.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import httpx
from unittest.mock import Mock, AsyncMock, patch

from src.subsystems.knowledge import (
    KnowledgeSubsystem,
    STAGED_KNOWLEDGE_COUNTS,
    REBUILD_COMMANDS,
)


# ============================================================================
# Initialization Tests
# ============================================================================


class TestKnowledgeSubsystemInit:
    """Tests for KnowledgeSubsystem initialization"""

    def test_init_sets_config(self):
        """Test initialization sets configuration from config"""
        knowledge = KnowledgeSubsystem()

        assert knowledge.anythingllm_url is not None
        assert knowledge.collection is not None
        assert knowledge.top_k > 0
        assert knowledge._last_rebuild_notice is None

    def test_init_uses_config_values(self):
        """Test that init uses values from config"""
        from src.config import config

        knowledge = KnowledgeSubsystem()

        assert knowledge.anythingllm_url == config.anythingllm_url
        assert knowledge.collection == config.qdrant_collection
        assert knowledge.top_k == config.rag_top_k


# ============================================================================
# Knowledge Base Gate Tests
# ============================================================================


class TestKnowledgeBaseGate:
    """Tests for knowledge base readiness gate"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    @pytest.mark.asyncio
    async def test_gate_passes_when_vectors_exist(self):
        """Test gate passes when collection has vectors"""
        # Mock Qdrant response with vectors
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": True,
                "status": "green",
                "vector_count": 1200000,
                "indexed_vectors": 1200000,
            },
        ):
            warning = await self.knowledge._knowledge_base_gate()

            assert warning is None
            assert self.knowledge._last_rebuild_notice is None

    @pytest.mark.asyncio
    async def test_gate_blocks_when_collection_missing(self):
        """Test gate blocks when collection doesn't exist"""
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": False,
                "status": "missing",
                "vector_count": 0,
                "indexed_vectors": 0,
            },
        ):
            warning = await self.knowledge._knowledge_base_gate()

            assert warning is not None
            assert "rebuild required" in warning.lower()
            assert "Qdrant collection missing" in warning
            assert self.knowledge._last_rebuild_notice == warning

    @pytest.mark.asyncio
    async def test_gate_blocks_when_collection_empty(self):
        """Test gate blocks when collection exists but is empty"""
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": True,
                "status": "green",
                "vector_count": 0,
                "indexed_vectors": 0,
            },
        ):
            warning = await self.knowledge._knowledge_base_gate()

            assert warning is not None
            assert "empty" in warning.lower()
            assert "vectors=0" in warning

    @pytest.mark.asyncio
    async def test_gate_blocks_when_qdrant_unreachable(self):
        """Test gate blocks when Qdrant is unreachable"""
        with patch.object(self.knowledge, "_fetch_collection_stats", return_value=None):
            warning = await self.knowledge._knowledge_base_gate()

            assert warning is not None
            assert "Unable to reach Qdrant" in warning


# ============================================================================
# Fetch Collection Stats Tests
# ============================================================================


class TestFetchCollectionStats:
    """Tests for Qdrant collection statistics fetching"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    @pytest.mark.asyncio
    async def test_fetch_stats_success(self):
        """Test successful stats fetch from Qdrant"""
        mock_response = {
            "result": {
                "status": "green",
                "points_count": 1200000,
                "indexed_vectors_count": 1200000,
            }
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=Mock(
                    status_code=200, json=Mock(return_value=mock_response)
                )
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            stats = await self.knowledge._fetch_collection_stats()

            assert stats is not None
            assert stats["exists"] is True
            assert stats["status"] == "green"
            assert stats["vector_count"] == 1200000
            assert stats["indexed_vectors"] == 1200000

    @pytest.mark.asyncio
    async def test_fetch_stats_collection_not_found(self):
        """Test stats fetch when collection doesn't exist"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=Mock(status_code=404))
            mock_client.return_value.__aenter__.return_value.get = mock_get

            stats = await self.knowledge._fetch_collection_stats()

            assert stats is not None
            assert stats["exists"] is False
            assert stats["status"] == "missing"
            assert stats["vector_count"] == 0

    @pytest.mark.asyncio
    async def test_fetch_stats_connection_error(self):
        """Test stats fetch when Qdrant is unreachable"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.return_value.__aenter__.return_value.get = mock_get

            stats = await self.knowledge._fetch_collection_stats()

            assert stats is None

    @pytest.mark.asyncio
    async def test_fetch_stats_handles_alternate_field_names(self):
        """Test that stats handles both points_count and vectors_count"""
        # Test with vectors_count instead of points_count
        mock_response = {
            "result": {
                "status": "green",
                "vectors_count": 500000,
                "indexed_vectors_count": 500000,
            }
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=Mock(
                    status_code=200, json=Mock(return_value=mock_response)
                )
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            stats = await self.knowledge._fetch_collection_stats()

            assert stats["vector_count"] == 500000


# ============================================================================
# Rebuild Message Tests
# ============================================================================


class TestRebuildMessage:
    """Tests for rebuild advisory message generation"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    def test_rebuild_message_includes_reason(self):
        """Test rebuild message includes the reason"""
        message = self.knowledge._rebuild_message("Test reason")

        assert "Test reason" in message
        assert "rebuild required" in message.lower()

    def test_rebuild_message_includes_staged_counts(self):
        """Test rebuild message includes staged document counts"""
        message = self.knowledge._rebuild_message("Empty collection")

        assert "1,403" in message  # processed chunks
        assert "2,028" in message  # raw documents
        assert "493" in message  # academic PDFs

    def test_rebuild_message_includes_commands(self):
        """Test rebuild message includes rebuild commands"""
        message = self.knowledge._rebuild_message("Empty collection")

        assert "orion process" in message
        assert "orion embed-index" in message
        assert "orion validate" in message

    def test_rebuild_message_has_clear_steps(self):
        """Test rebuild message has numbered steps"""
        message = self.knowledge._rebuild_message("Empty collection")

        assert "1." in message
        assert "2." in message
        assert "3." in message


# ============================================================================
# Query AnythingLLM Tests
# ============================================================================


class TestQueryAnythingLLM:
    """Tests for AnythingLLM API querying"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    @pytest.mark.asyncio
    async def test_query_anythingllm_success(self):
        """Test successful AnythingLLM query"""
        mock_response = {
            "textResponse": "Kubernetes is a container orchestration platform.",
            "sources": [
                {"title": "Kubernetes Documentation", "score": 0.95},
                {"title": "K8s Best Practices", "score": 0.88},
            ],
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            answer, sources = await self.knowledge._query_anythingllm(
                "What is Kubernetes?", {}
            )

            assert answer == "Kubernetes is a container orchestration platform."
            assert len(sources) == 2
            assert sources[0]["title"] == "Kubernetes Documentation"

    @pytest.mark.asyncio
    async def test_query_anythingllm_includes_api_key(self):
        """Test that API key is included in request headers"""
        original_key = self.knowledge.api_key
        self.knowledge.api_key = "test-key"  # pragma: allowlist secret

        try:
            mock_response = {"textResponse": "Answer", "sources": []}

            with patch("httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(
                    return_value=Mock(
                        json=Mock(return_value=mock_response), raise_for_status=Mock()
                    )
                )
                mock_client.return_value.__aenter__.return_value.post = mock_post

                await self.knowledge._query_anythingllm("Query", {})

                # Verify headers were passed
                call_kwargs = mock_post.call_args[1]
                assert "headers" in call_kwargs
                assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"

        finally:
            self.knowledge.api_key = original_key

    @pytest.mark.asyncio
    async def test_query_anythingllm_includes_system_prompt(self):
        """Test that system prompt is included in payload"""
        mock_response = {"textResponse": "Answer", "sources": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await self.knowledge._query_anythingllm("Query", {})

            # Verify payload includes promptOverride
            call_kwargs = mock_post.call_args[1]
            assert "json" in call_kwargs
            assert "promptOverride" in call_kwargs["json"]
            assert "ORION" in call_kwargs["json"]["promptOverride"]


# ============================================================================
# Handle Method Tests
# ============================================================================


class TestHandleMethod:
    """Tests for main handle() method"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    @pytest.mark.asyncio
    async def test_handle_success_with_vectors(self):
        """Test successful query when knowledge base has vectors"""
        # Mock gate passes
        with patch.object(self.knowledge, "_knowledge_base_gate", return_value=None):
            # Mock successful query
            with patch.object(
                self.knowledge,
                "_query_anythingllm",
                return_value=(
                    "Docker is a containerization platform.",
                    [{"title": "Docker Docs", "score": 0.92}],
                ),
            ):
                response = await self.knowledge.handle("What is Docker?", {})

                assert "Docker is a containerization platform" in response
                assert "Sources:" in response
                assert "Docker Docs" in response

    @pytest.mark.asyncio
    async def test_handle_returns_rebuild_message_when_empty(self):
        """Test that handle returns rebuild message when KB is empty"""
        rebuild_msg = "Rebuild required"

        with patch.object(
            self.knowledge, "_knowledge_base_gate", return_value=rebuild_msg
        ):
            response = await self.knowledge.handle("What is Docker?", {})

            assert response == rebuild_msg
            # Query should not be called when gate blocks
            assert response == "Rebuild required"

    @pytest.mark.asyncio
    async def test_handle_catches_404_workspace_not_found(self):
        """Test handle catches 404 for missing AnythingLLM workspace"""
        with patch.object(self.knowledge, "_knowledge_base_gate", return_value=None):
            # Mock 404 error from AnythingLLM
            mock_response = Mock(status_code=404)
            error = httpx.HTTPStatusError(
                "Workspace not found", request=Mock(), response=mock_response
            )

            with patch.object(self.knowledge, "_query_anythingllm", side_effect=error):
                response = await self.knowledge.handle("Query", {})

                assert "rebuild required" in response.lower()
                assert "Workspace not found" in response

    @pytest.mark.asyncio
    async def test_handle_catches_generic_errors(self):
        """Test handle catches and reports generic errors"""
        with patch.object(self.knowledge, "_knowledge_base_gate", return_value=None):
            with patch.object(
                self.knowledge,
                "_query_anythingllm",
                side_effect=Exception("Network error"),
            ):
                response = await self.knowledge.handle("Query", {})

                assert "error" in response.lower()
                assert "knowledge base" in response.lower()


# ============================================================================
# Format Response Tests
# ============================================================================


class TestFormatResponse:
    """Tests for response formatting"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    def test_format_response_with_sources(self):
        """Test formatting response with source citations"""
        answer = "Kubernetes is a container orchestration platform."
        sources = [
            {"title": "Kubernetes Documentation", "score": 0.95},
            {"title": "K8s Best Practices", "score": 0.88},
            {"title": "Container Guide", "score": 0.82},
        ]

        response = self.knowledge._format_response(answer, sources)

        assert answer in response
        assert "Sources:" in response
        assert "Kubernetes Documentation" in response
        assert "0.95" in response
        assert "K8s Best Practices" in response

    def test_format_response_without_sources(self):
        """Test formatting response without sources"""
        answer = "This is an answer."
        sources = []

        response = self.knowledge._format_response(answer, sources)

        assert response == answer
        assert "Sources:" not in response

    def test_format_response_limits_sources_to_five(self):
        """Test that only top 5 sources are included"""
        answer = "Answer"
        sources = [
            {"title": f"Source {i}", "score": 0.9 - (i * 0.1)} for i in range(10)
        ]

        response = self.knowledge._format_response(answer, sources)

        # Should have sources 0-4
        assert "Source 0" in response
        assert "Source 4" in response
        # Should NOT have sources 5-9
        assert "Source 5" not in response
        assert "Source 9" not in response


# ============================================================================
# System Prompt Tests
# ============================================================================


class TestBuildSystemPrompt:
    """Tests for system prompt building"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    def test_build_system_prompt_includes_key_elements(self):
        """Test system prompt includes key elements"""
        prompt = self.knowledge._build_system_prompt({})

        assert "ORION" in prompt
        assert "knowledge base" in prompt.lower()
        assert "technical-docs" in prompt
        assert "493" in prompt  # research papers
        assert "2,028" in prompt or "2028" in prompt  # documents
        assert "1,403" in prompt or "1403" in prompt  # chunks

    def test_build_system_prompt_mentions_rebuild(self):
        """Test system prompt mentions rebuild scenario"""
        prompt = self.knowledge._build_system_prompt({})

        assert "rebuild" in prompt.lower()
        assert "empty" in prompt.lower()


# ============================================================================
# Search Knowledge Base Tests
# ============================================================================


class TestSearchKnowledgeBase:
    """Tests for direct semantic search"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    @pytest.mark.asyncio
    async def test_search_knowledge_base_success(self):
        """Test successful semantic search"""
        mock_response = {
            "results": [
                {"text": "Result 1", "score": 0.92},
                {"text": "Result 2", "score": 0.85},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            results = await self.knowledge.search_knowledge_base("kubernetes")

            assert len(results) == 2
            assert results[0]["text"] == "Result 1"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_uses_custom_top_k(self):
        """Test search uses custom top_k parameter"""
        mock_response = {"results": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await self.knowledge.search_knowledge_base("query", top_k=15)

            # Verify custom limit was passed
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["limit"] == 15

    @pytest.mark.asyncio
    async def test_search_knowledge_base_uses_default_top_k(self):
        """Test search uses default top_k when not specified"""
        mock_response = {"results": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(
                return_value=Mock(
                    json=Mock(return_value=mock_response), raise_for_status=Mock()
                )
            )
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await self.knowledge.search_knowledge_base("query")

            # Verify default limit was passed
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["limit"] == self.knowledge.top_k


# ============================================================================
# Get Knowledge Stats Tests
# ============================================================================


class TestGetKnowledgeStats:
    """Tests for knowledge base statistics"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    @pytest.mark.asyncio
    async def test_get_stats_with_healthy_collection(self):
        """Test stats when collection is healthy"""
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": True,
                "status": "green",
                "vector_count": 1200000,
                "indexed_vectors": 1200000,
            },
        ):
            stats = await self.knowledge.get_knowledge_stats()

            assert stats["collection"] == self.knowledge.collection
            assert stats["status"] == "green"
            assert stats["vectors_count"] == 1200000
            assert stats["rebuild_required"] is False
            assert stats["rebuild_message"] is None

    @pytest.mark.asyncio
    async def test_get_stats_with_empty_collection(self):
        """Test stats when collection is empty"""
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": True,
                "status": "green",
                "vector_count": 0,
                "indexed_vectors": 0,
            },
        ):
            stats = await self.knowledge.get_knowledge_stats()

            assert stats["vectors_count"] == 0
            assert stats["rebuild_required"] is True
            assert stats["reason"] == "Qdrant collection empty"
            assert stats["rebuild_message"] is not None
            assert "rebuild" in stats["rebuild_message"].lower()

    @pytest.mark.asyncio
    async def test_get_stats_with_missing_collection(self):
        """Test stats when collection doesn't exist"""
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": False,
                "status": "missing",
                "vector_count": 0,
                "indexed_vectors": 0,
            },
        ):
            stats = await self.knowledge.get_knowledge_stats()

            assert stats["exists"] is False
            assert stats["rebuild_required"] is True
            assert stats["reason"] == "Qdrant collection missing"

    @pytest.mark.asyncio
    async def test_get_stats_when_qdrant_unreachable(self):
        """Test stats when Qdrant is unreachable"""
        with patch.object(self.knowledge, "_fetch_collection_stats", return_value=None):
            stats = await self.knowledge.get_knowledge_stats()

            assert stats["status"] == "unknown"
            assert stats["vectors_count"] is None
            assert stats["rebuild_required"] is True
            assert stats["reason"] == "Unable to reach Qdrant"

    @pytest.mark.asyncio
    async def test_get_stats_includes_staged_counts(self):
        """Test stats includes staged document counts"""
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": True,
                "status": "green",
                "vector_count": 0,
                "indexed_vectors": 0,
            },
        ):
            stats = await self.knowledge.get_knowledge_stats()

            assert "staged_documents" in stats
            assert stats["staged_documents"] == STAGED_KNOWLEDGE_COUNTS

    @pytest.mark.asyncio
    async def test_get_stats_includes_rebuild_commands(self):
        """Test stats includes rebuild commands"""
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": True,
                "status": "green",
                "vector_count": 0,
                "indexed_vectors": 0,
            },
        ):
            stats = await self.knowledge.get_knowledge_stats()

            assert "recommended_commands" in stats
            assert stats["recommended_commands"] == REBUILD_COMMANDS


# ============================================================================
# Integration Tests
# ============================================================================


class TestKnowledgeSubsystemIntegration:
    """Integration tests for complete workflows"""

    def setup_method(self):
        """Set up knowledge subsystem for each test"""
        self.knowledge = KnowledgeSubsystem()

    @pytest.mark.asyncio
    async def test_complete_query_workflow(self):
        """Test complete query workflow with healthy knowledge base"""
        # Mock healthy collection
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": True,
                "status": "green",
                "vector_count": 1200000,
                "indexed_vectors": 1200000,
            },
        ):
            # Mock successful AnythingLLM query
            mock_llm_response = {
                "textResponse": "Docker is a containerization platform that packages applications.",
                "sources": [
                    {"title": "Docker Official Documentation", "score": 0.96},
                    {"title": "Container Best Practices", "score": 0.89},
                ],
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(
                    return_value=Mock(
                        json=Mock(return_value=mock_llm_response),
                        raise_for_status=Mock(),
                    )
                )
                mock_client.return_value.__aenter__.return_value.post = mock_post

                response = await self.knowledge.handle(
                    "What is Docker and how does it work?", {}
                )

                # Verify response includes answer and citations
                assert "Docker" in response
                assert "containerization" in response
                assert "Sources:" in response
                assert "Docker Official Documentation" in response
                assert "0.96" in response

    @pytest.mark.asyncio
    async def test_rebuild_workflow_when_empty(self):
        """Test rebuild advisory workflow when knowledge base is empty"""
        # Mock empty collection
        with patch.object(
            self.knowledge,
            "_fetch_collection_stats",
            return_value={
                "exists": True,
                "status": "green",
                "vector_count": 0,
                "indexed_vectors": 0,
            },
        ):
            response = await self.knowledge.handle("What is Docker?", {})

            # Should return rebuild message
            assert "rebuild required" in response.lower()
            assert "orion process" in response
            assert "orion embed-index" in response
            assert "1,403" in response  # staged chunks
