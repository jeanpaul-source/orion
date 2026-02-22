"""
Unit tests for Learning Subsystem

Tests the learning queue management, request tracking, and status updates.

Author: ORION Project
Date: November 18, 2025
"""

import importlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

sys.modules.setdefault("subsystems", importlib.import_module("src.subsystems"))

from src.subsystems.learning import (  # noqa: E402
    LearningSubsystem,
    LearningQueue,
    LearningRequest,
    LearningStatus,
)


@pytest.fixture
def temp_queue_file():
    """Create a temporary queue file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        yield Path(f.name)
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def learning_queue(temp_queue_file):
    """Create a LearningQueue instance for testing."""
    return LearningQueue(temp_queue_file)


@pytest.fixture
def learning_subsystem(temp_queue_file):
    """Create a LearningSubsystem instance for testing."""
    # Mock config to use temp file
    with patch("subsystems.learning.config") as mock_config:
        mock_config.data_dir = temp_queue_file.parent
        # Create learning subsystem with mocked config
        subsystem = LearningSubsystem.__new__(LearningSubsystem)
        subsystem.queue = LearningQueue(temp_queue_file)
        return subsystem


class TestLearningRequest:
    """Test LearningRequest class."""

    def test_create_request(self):
        """Test creating a learning request."""
        req = LearningRequest(topic="Kubernetes", category="container-platforms")

        assert req.topic == "Kubernetes"
        assert req.category == "container-platforms"
        assert req.status == LearningStatus.PENDING
        assert req.papers_found == 0
        assert req.docs_found == 0
        assert req.requested_at is not None

    def test_to_dict(self):
        """Test converting request to dictionary."""
        req = LearningRequest(topic="PostgreSQL", category="databases")
        data = req.to_dict()

        assert data["topic"] == "PostgreSQL"
        assert data["category"] == "databases"
        assert data["status"] == "pending"
        assert "requested_at" in data

    def test_from_dict(self):
        """Test creating request from dictionary."""
        data = {
            "topic": "Docker",
            "category": "containers",
            "status": "completed",
            "requested_at": "2025-11-18T00:00:00",
            "completed_at": "2025-11-18T01:00:00",
            "papers_found": 15,
            "docs_found": 8,
        }

        req = LearningRequest.from_dict(data)

        assert req.topic == "Docker"
        assert req.category == "containers"
        assert req.status == LearningStatus.COMPLETED
        assert req.papers_found == 15
        assert req.docs_found == 8


class TestLearningQueue:
    """Test LearningQueue class."""

    def test_add_request(self, learning_queue):
        """Test adding a request to the queue."""
        req = learning_queue.add("Prometheus", "monitoring")

        assert req.topic == "Prometheus"
        assert req.category == "monitoring"
        assert len(learning_queue.get_all()) == 1

    def test_duplicate_detection(self, learning_queue):
        """Test that duplicate requests are detected."""
        req1 = learning_queue.add("Grafana", "monitoring")
        req2 = learning_queue.add("grafana", "monitoring")  # Case-insensitive

        assert req1 == req2
        assert len(learning_queue.get_all()) == 1

    def test_get_pending(self, learning_queue):
        """Test getting pending requests."""
        learning_queue.add("Topic1")
        learning_queue.add("Topic2")
        learning_queue.update_status("Topic1", LearningStatus.COMPLETED)

        pending = learning_queue.get_pending()

        assert len(pending) == 1
        assert pending[0].topic == "Topic2"

    def test_update_status(self, learning_queue):
        """Test updating request status."""
        learning_queue.add("Elasticsearch")
        learning_queue.update_status(
            "Elasticsearch",
            LearningStatus.COMPLETED,
            papers_found=20,
            docs_found=12,
        )

        req = learning_queue.get_by_topic("Elasticsearch")

        assert req.status == LearningStatus.COMPLETED
        assert req.papers_found == 20
        assert req.docs_found == 12
        assert req.completed_at is not None

    def test_get_stats(self, learning_queue):
        """Test getting queue statistics."""
        learning_queue.add("Topic1")
        learning_queue.add("Topic2")
        learning_queue.add("Topic3")

        learning_queue.update_status(
            "Topic1", LearningStatus.COMPLETED, papers_found=10
        )
        learning_queue.update_status(
            "Topic2", LearningStatus.FAILED, error="Network error"
        )

        stats = learning_queue.get_stats()

        assert stats["total_requests"] == 3
        assert stats["pending"] == 1
        assert stats["processing"] == 0
        assert stats["completed"] == 1
        assert stats["failed"] == 1
        assert stats["total_papers_harvested"] == 10

    def test_persistence(self, temp_queue_file):
        """Test that queue is persisted to disk."""
        # Create queue and add requests
        queue1 = LearningQueue(temp_queue_file)
        queue1.add("Redis", "databases")
        queue1.add("MongoDB", "databases")

        # Create new queue instance from same file
        queue2 = LearningQueue(temp_queue_file)

        assert len(queue2.get_all()) == 2
        assert queue2.get_by_topic("Redis") is not None
        assert queue2.get_by_topic("MongoDB") is not None


class TestLearningSubsystem:
    """Test LearningSubsystem class."""

    @pytest.mark.asyncio
    async def test_handle_new_request(self, learning_subsystem):
        """Test handling a new learning request."""
        result = await learning_subsystem.handle("Kubernetes", {})

        assert "Learning Request Queued" in result
        assert "Kubernetes" in result
        assert "orion harvest" in result

        # Verify it was added to queue
        pending = learning_subsystem.queue.get_pending()
        assert len(pending) == 1
        assert pending[0].topic == "Kubernetes"

    @pytest.mark.asyncio
    async def test_handle_duplicate_request(self, learning_subsystem):
        """Test handling a duplicate request."""
        # Add first request
        await learning_subsystem.handle("PostgreSQL", {})

        # Try to add duplicate
        result = await learning_subsystem.handle("PostgreSQL", {})

        assert "Learning Request Queued" in result
        # Should still only have 1 request
        assert len(learning_subsystem.queue.get_all()) == 1

    @pytest.mark.asyncio
    async def test_handle_completed_request(self, learning_subsystem):
        """Test handling a request that's already completed."""
        # Add and mark as completed
        learning_subsystem.queue.add("Docker")
        learning_subsystem.queue.update_status(
            "Docker", LearningStatus.COMPLETED, papers_found=15, docs_found=8
        )

        result = await learning_subsystem.handle("Docker", {})

        assert "Already Learned" in result
        assert "15 academic papers" in result
        assert "8 technical documents" in result

    @pytest.mark.asyncio
    async def test_get_learning_status(self, learning_subsystem):
        """Test getting learning status."""
        # Add some requests
        learning_subsystem.queue.add("Topic1")
        learning_subsystem.queue.add("Topic2")
        learning_subsystem.queue.update_status(
            "Topic1", LearningStatus.COMPLETED, papers_found=10
        )

        status = await learning_subsystem.get_learning_status()

        assert status["total_requests"] == 2
        assert status["pending"] == 1
        assert status["completed"] == 1
        assert len(status["recent_requests"]) == 2

    @pytest.mark.asyncio
    async def test_list_pending(self, learning_subsystem):
        """Test listing pending requests."""
        learning_subsystem.queue.add("Topic1")
        learning_subsystem.queue.add("Topic2")
        learning_subsystem.queue.update_status("Topic1", LearningStatus.COMPLETED)

        pending = await learning_subsystem.list_pending()

        assert len(pending) == 1
        assert pending[0]["topic"] == "Topic2"

    @pytest.mark.asyncio
    async def test_mark_completed(self, learning_subsystem):
        """Test marking a request as completed."""
        learning_subsystem.queue.add("Nginx")

        success = await learning_subsystem.mark_completed(
            "Nginx", papers_found=5, docs_found=3
        )

        assert success is True

        req = learning_subsystem.queue.get_by_topic("Nginx")
        assert req.status == LearningStatus.COMPLETED
        assert req.papers_found == 5
        assert req.docs_found == 3

    @pytest.mark.asyncio
    async def test_mark_failed(self, learning_subsystem):
        """Test marking a request as failed."""
        learning_subsystem.queue.add("Apache")

        success = await learning_subsystem.mark_failed("Apache", error="API rate limit")

        assert success is True

        req = learning_subsystem.queue.get_by_topic("Apache")
        assert req.status == LearningStatus.FAILED
        assert req.error == "API rate limit"

    @pytest.mark.asyncio
    async def test_mark_nonexistent_completed(self, learning_subsystem):
        """Test marking a non-existent request as completed."""
        success = await learning_subsystem.mark_completed("NonExistent")

        assert success is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
