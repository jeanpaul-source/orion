"""
Chaos engineering tests for ORION resilience validation.

Tests service behavior under adverse conditions:
- Network failures
- Service unavailability
- Resource exhaustion
- Timeout scenarios
"""

import pytest
import asyncio
import aiohttp
from unittest.mock import Mock, patch

# Skip all chaos tests - these are cross-project integration tests that require
# orion_rag and other external ORION projects to be installed as packages
pytestmark = pytest.mark.skip(
    reason="Cross-project integration tests require orion_rag and other ORION components as installed packages"
)


class TestServiceResilience:
    """Test resilience to service failures."""

    @pytest.mark.asyncio
    async def test_qdrant_unavailable_graceful_degradation(self, orion_app):
        """System should degrade gracefully when Qdrant is unavailable."""
        with patch("qdrant_client.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value.search.side_effect = ConnectionError(
                "Qdrant unavailable"
            )

            # Query should not crash, should return error message
            response = await orion_app.query("test query")

            assert response is not None
            assert "unavailable" in response.lower() or "error" in response.lower()
            # Should NOT raise exception

    @pytest.mark.asyncio
    async def test_vllm_timeout_recovery(self, orion_app):
        """System should recover from vLLM timeouts."""
        with patch("aiohttp.ClientSession.post") as mock_post:
            # Simulate timeout
            mock_post.side_effect = asyncio.TimeoutError()

            response = await orion_app.query("test query")

            # Should return timeout message, not crash
            assert response is not None
            assert any(
                word in response.lower() for word in ["timeout", "slow", "try again"]
            )

    @pytest.mark.asyncio
    async def test_anythingllm_500_error_handling(self, anythingllm_client):
        """Client should handle 500 errors gracefully."""
        with patch("requests.Session.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"error": "Internal Server Error"}
            mock_post.return_value = mock_response

            # Should not raise, should return error result
            result = anythingllm_client.query("test")

            assert "error" in result or not result.get("success", True)


class TestNetworkResilience:
    """Test resilience to network issues."""

    @pytest.mark.asyncio
    async def test_connection_refused_handling(self, orion_app):
        """Handle connection refused gracefully."""
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.side_effect = aiohttp.ClientConnectorError(
                connection_key=None, os_error=None
            )

            response = await orion_app.query("test")

            assert response is not None
            assert "connect" in response.lower() or "unavailable" in response.lower()

    def test_http_retry_on_transient_errors(self, http_session):
        """HTTP client should retry on 503, 502, 500."""
        from orion_rag.common.http_utils import create_session

        session = create_session(total_retries=3, backoff_factor=0.1)

        with patch("requests.adapters.HTTPAdapter.send") as mock_send:
            # Simulate 503, 503, 200 sequence
            responses = [
                Mock(status_code=503, headers={}),
                Mock(status_code=503, headers={}),
                Mock(status_code=200, headers={}, text="Success"),
            ]
            mock_send.side_effect = responses

            response = session.get("http://example.com/test")

            # Should retry and eventually succeed
            assert response.status_code == 200
            assert mock_send.call_count == 3


class TestResourceExhaustion:
    """Test behavior under resource constraints."""

    @pytest.mark.asyncio
    async def test_queue_backpressure(self, request_queue):
        """Queue should reject requests when full."""
        from orion_core.src.queue import RequestQueue, Priority

        queue = RequestQueue(max_concurrent=2, max_queue_size=5)

        # Fill queue beyond capacity
        async def slow_handler(*args):
            await asyncio.sleep(10)  # Never completes in test
            return "done"

        # Enqueue max_queue_size + max_concurrent requests
        tasks = []
        for i in range(8):  # More than 5 + 2
            try:
                task = queue.enqueue(
                    request_id=f"req-{i}",
                    handler=slow_handler,
                    args=(),
                    priority=Priority.NORMAL,
                    session_id="test",
                )
                tasks.append(task)
            except ValueError as e:
                # Expected: queue full
                assert "full" in str(e).lower() or "busy" in str(e).lower()
                break

        # Should have rejected at least one request
        assert len(tasks) < 8

    @pytest.mark.asyncio
    async def test_concurrent_request_limit_per_session(self, request_queue):
        """Enforce per-session rate limit."""
        from orion_core.src.queue import RequestQueue, Priority

        queue = RequestQueue(max_concurrent=10, max_per_session=3)

        async def handler(*args):
            await asyncio.sleep(5)
            return "done"

        # Try to enqueue 5 requests from same session
        tasks = []
        for i in range(5):
            try:
                task = queue.enqueue(
                    request_id=f"req-{i}",
                    handler=handler,
                    args=(),
                    priority=Priority.NORMAL,
                    session_id="same-session",
                )
                tasks.append(task)
            except ValueError as e:
                # Expected: too many from same session
                assert "session" in str(e).lower()
                break

        # Should have limited to 3 per session
        assert len(tasks) <= 3

    def test_memory_efficient_large_document_processing(self):
        """Process large documents without OOM."""
        # Simulate 100MB document
        large_content = "a" * (100 * 1024 * 1024)

        from orion_rag.harvester.src.ingest.pdf_processor import PDFProcessor

        processor = PDFProcessor()

        # Should chunk instead of loading all at once
        # Should not raise MemoryError
        chunks = processor.chunk_text(large_content, max_chunk_size=1000)

        assert len(chunks) > 100  # Should be split into many chunks
        assert all(len(chunk) <= 1000 for chunk in chunks)


class TestDataIntegrity:
    """Test data consistency under failures."""

    def test_database_transaction_rollback_on_error(self, ingestion_registry):
        """Registry should rollback on error."""
        from orion_rag.research_qa.src.registry import IngestionRegistry

        registry = IngestionRegistry()

        # Start transaction
        with pytest.raises(Exception):
            with registry.connection:
                registry.mark_processed("/test/file.pdf", "hash123")
                # Simulate error mid-transaction
                raise ValueError("Simulated error")

        # Should not be marked as processed after rollback
        assert not registry.is_processed("/test/file.pdf")

    def test_duplicate_prevention_race_condition(self, ingestion_registry):
        """Prevent duplicates even under concurrent inserts."""
        from orion_rag.research_qa.src.registry import IngestionRegistry
        import threading

        registry = IngestionRegistry()
        results = []

        def try_insert():
            try:
                registry.mark_processed("/test/file.pdf", "hash123")
                results.append("success")
            except Exception:
                results.append("duplicate")

        # Simulate concurrent inserts
        threads = [threading.Thread(target=try_insert) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one should succeed
        assert results.count("success") == 1
        assert results.count("duplicate") == 9


class TestAlertSystem:
    """Test alert generation and recovery."""

    @pytest.mark.asyncio
    async def test_alert_on_service_down(self, watch_subsystem):
        """Watch subsystem should create alert when service is down."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = aiohttp.ClientConnectorError(
                connection_key=None, os_error=None
            )

            # Trigger health check
            await watch_subsystem.check_services()

            # Should have created critical alert
            alerts = watch_subsystem.get_active_alerts()
            assert len(alerts) > 0
            assert any(alert.severity == "critical" for alert in alerts)

    @pytest.mark.asyncio
    async def test_alert_auto_resolve_on_recovery(self, watch_subsystem):
        """Alert should auto-resolve when service recovers."""
        # First check: service down
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = aiohttp.ClientConnectorError(
                connection_key=None, os_error=None
            )
            await watch_subsystem.check_services()

        # Second check: service recovered
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = Mock()
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            await watch_subsystem.check_services()

        # Alert should be resolved
        active_alerts = watch_subsystem.get_active_alerts()
        assert len(active_alerts) == 0


class TestConfigurationResilience:
    """Test handling of configuration errors."""

    def test_missing_api_key_graceful_handling(self):
        """Missing API key should not crash, should log warning."""
        from orion_core.src.config import ORIONConfig
        import os

        # Remove API key
        old_key = os.environ.pop("ANYTHINGLLM_API_KEY", None)

        try:
            config = ORIONConfig()

            # Should not crash
            assert (
                config.anythingllm_api_key is None or config.anythingllm_api_key == ""
            )
        finally:
            # Restore
            if old_key:
                os.environ["ANYTHINGLLM_API_KEY"] = old_key

    def test_invalid_profile_fallback_to_default(self):
        """Invalid profile should fallback to default."""
        from devia.config import DeviaConfig

        # Try loading invalid profile
        config = DeviaConfig.from_profile("nonexistent-profile")

        # Should fallback to default settings
        assert config is not None
        assert config.ollama_host is not None


@pytest.fixture
def orion_app():
    """Mock ORION app for testing."""
    from orion_core.src.main import app

    # Setup test app
    yield app


@pytest.fixture
def request_queue():
    """Create request queue for testing."""
    from orion_core.src.queue import RequestQueue

    return RequestQueue(max_concurrent=10, max_queue_size=50)


@pytest.fixture
def watch_subsystem():
    """Create watch subsystem for testing."""
    from orion_core.src.subsystems.watch import WatchSubsystem

    return WatchSubsystem()


@pytest.fixture
def anythingllm_client():
    """Create AnythingLLM client for testing."""
    from orion_rag.research_qa.src.anythingllm_client import AnythingLLMClient

    return AnythingLLMClient(
        base_url="http://test:3001",
        api_key="test-key",  # pragma: allowlist secret
        workspace_slug="test",
    )


@pytest.fixture
def ingestion_registry(tmp_path):
    """Create temporary ingestion registry."""
    from orion_rag.research_qa.src.registry import IngestionRegistry

    db_path = tmp_path / "test_registry.db"
    return IngestionRegistry(db_path=str(db_path))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
