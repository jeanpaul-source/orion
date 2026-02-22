"""
Learning Subsystem

Handles self-teaching and knowledge harvesting.
Manages learning requests and coordinates with the harvester.

Architecture:
- Stores learning requests in persistent queue
- Provides status tracking
- Designed for future n8n workflow integration

Author: ORION Project
Date: November 18, 2025
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum

from ..config import config

logger = logging.getLogger(__name__)


class LearningStatus(str, Enum):
    """Status of a learning request."""

    PENDING = "pending"  # Queued, waiting to be processed
    PROCESSING = "processing"  # Currently being harvested
    COMPLETED = "completed"  # Successfully learned
    FAILED = "failed"  # Failed to harvest


class LearningRequest:
    """
    A single learning request.

    Attributes:
        topic: What to learn about
        category: Optional category for organization
        status: Current status
        requested_at: When request was made
        completed_at: When processing finished (if applicable)
        error: Error message if failed
        papers_found: Number of papers harvested
        docs_found: Number of docs harvested
    """

    def __init__(
        self,
        topic: str,
        category: Optional[str] = None,
        status: LearningStatus = LearningStatus.PENDING,
        requested_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        error: Optional[str] = None,
        papers_found: int = 0,
        docs_found: int = 0,
    ):
        self.topic = topic
        self.category = category or "general"
        self.status = status
        self.requested_at = requested_at or datetime.utcnow().isoformat()
        self.completed_at = completed_at
        self.error = error
        self.papers_found = papers_found
        self.docs_found = docs_found

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "topic": self.topic,
            "category": self.category,
            "status": self.status.value,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "papers_found": self.papers_found,
            "docs_found": self.docs_found,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "LearningRequest":
        """Create from dictionary."""
        return cls(
            topic=data["topic"],
            category=data.get("category"),
            status=LearningStatus(data.get("status", "pending")),
            requested_at=data.get("requested_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            papers_found=data.get("papers_found", 0),
            docs_found=data.get("docs_found", 0),
        )


class LearningQueue:
    """
    Persistent queue of learning requests.

    Stored in JSON file on Docker volume for persistence.
    """

    def __init__(self, queue_file: Path):
        self.queue_file = queue_file
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing queue
        self._queue: List[LearningRequest] = self._load()

    def _load(self) -> List[LearningRequest]:
        """Load queue from disk."""
        if not self.queue_file.exists():
            logger.info(
                f"Learning queue file not found, creating new: {self.queue_file}"
            )
            return []

        try:
            with open(self.queue_file, "r") as f:
                data = json.load(f)
                return [LearningRequest.from_dict(item) for item in data]
        except Exception as e:
            logger.error(f"Failed to load learning queue: {e}")
            return []

    def _save(self):
        """Save queue to disk."""
        try:
            with open(self.queue_file, "w") as f:
                data = [req.to_dict() for req in self._queue]
                json.dump(data, f, indent=2)
            logger.debug(f"Saved learning queue ({len(self._queue)} items)")
        except Exception as e:
            logger.error(f"Failed to save learning queue: {e}")

    def add(self, topic: str, category: Optional[str] = None) -> LearningRequest:
        """
        Add a new learning request.

        Args:
            topic: What to learn about
            category: Optional category

        Returns:
            Created learning request
        """
        # Check for duplicates (reuse existing request regardless of status except failed)
        for req in self._queue:
            if req.topic.lower() != topic.lower():
                continue

            if req.status in [
                LearningStatus.PENDING,
                LearningStatus.PROCESSING,
                LearningStatus.COMPLETED,
            ]:
                logger.info(f"Learning request already exists: {topic}")
                return req

        # Create new request
        request = LearningRequest(topic=topic, category=category)
        self._queue.append(request)
        self._save()

        logger.info(f"Added learning request: {topic} (category: {category})")
        return request

    def get_pending(self) -> List[LearningRequest]:
        """Get all pending requests."""
        return [req for req in self._queue if req.status == LearningStatus.PENDING]

    def get_all(self) -> List[LearningRequest]:
        """Get all requests."""
        return self._queue.copy()

    def get_by_topic(self, topic: str) -> Optional[LearningRequest]:
        """Get request by topic (case-insensitive)."""
        for req in self._queue:
            if req.topic.lower() == topic.lower():
                return req
        return None

    def update_status(
        self,
        topic: str,
        status: LearningStatus,
        papers_found: Optional[int] = None,
        docs_found: Optional[int] = None,
        error: Optional[str] = None,
    ):
        """
        Update request status.

        Args:
            topic: Request topic
            status: New status
            papers_found: Number of papers (if applicable)
            docs_found: Number of docs (if applicable)
            error: Error message (if failed)
        """
        request = self.get_by_topic(topic)
        if not request:
            logger.warning(f"Learning request not found: {topic}")
            return

        request.status = status

        if papers_found is not None:
            request.papers_found = papers_found
        if docs_found is not None:
            request.docs_found = docs_found
        if error:
            request.error = error

        if status in [LearningStatus.COMPLETED, LearningStatus.FAILED]:
            request.completed_at = datetime.utcnow().isoformat()

        self._save()
        logger.info(f"Updated learning request: {topic} → {status.value}")

    def get_stats(self) -> Dict:
        """Get queue statistics."""
        pending = sum(1 for req in self._queue if req.status == LearningStatus.PENDING)
        processing = sum(
            1 for req in self._queue if req.status == LearningStatus.PROCESSING
        )
        completed = sum(
            1 for req in self._queue if req.status == LearningStatus.COMPLETED
        )
        failed = sum(1 for req in self._queue if req.status == LearningStatus.FAILED)

        total_papers = sum(req.papers_found for req in self._queue)
        total_docs = sum(req.docs_found for req in self._queue)

        return {
            "total_requests": len(self._queue),
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "total_papers_harvested": total_papers,
            "total_docs_harvested": total_docs,
        }


class LearningSubsystem:
    """
    Learning subsystem for self-teaching capabilities.

    Coordinates:
    - Learning request queue management
    - Integration with harvester (future)
    - Status tracking and reporting

    Phase 1 (Current): Queue management with manual harvesting
    Phase 2 (Future): n8n workflow automation for automatic harvesting
    """

    def __init__(self):
        # Initialize learning queue
        queue_file = config.data_dir / "learning_queue.json"
        self.queue = LearningQueue(queue_file)

        logger.info(
            f"Learning subsystem initialized ({len(self.queue.get_pending())} pending requests)"
        )

    async def handle(self, topic: str, context: Dict) -> str:
        """
        Handle self-learning request.

        Args:
            topic: Topic to learn about
            context: Conversation context (may contain category hint)

        Returns:
            Learning status message with instructions

        Example:
            >>> learning = LearningSubsystem()
            >>> result = await learning.handle(
            ...     "Kubernetes StatefulSets",
            ...     context={}
            ... )
        """
        logger.info(f"Learning request: {topic}")

        try:
            # Extract category from context if provided
            category = context.get("category")

            # Add to queue (returns existing if duplicate)
            request = self.queue.add(topic, category)

            # Check if already processed
            if request.status == LearningStatus.COMPLETED:
                return self._format_already_learned_message(request)

            # Check if already in progress
            if request.status == LearningStatus.PROCESSING:
                return self._format_in_progress_message(request)

            # New or pending request
            return self._format_queued_message(request)

        except Exception as e:
            logger.exception("Learning subsystem error")
            return (
                f"I encountered an error while queuing your learning request: {str(e)}"
            )

    def _format_queued_message(self, request: LearningRequest) -> str:
        """Format message for newly queued request."""
        message = f"📚 **Learning Request Queued: {request.topic}**\n\n"

        message += "I've added this topic to my learning queue!\n\n"

        message += "**To process this request:**\n\n"
        message += "**Option 1: Manual Harvest (Immediate)**\n"
        message += "```bash\n"
        message += "# On laptop:\n"
        message += (
            f'orion harvest --term "{request.topic}" --category {request.category}\n'
        )
        message += "orion process --max-files 50\n"
        message += "orion embed-index\n"
        message += "```\n\n"

        message += "**Option 2: Automated Processing (Future)**\n"
        message += "- Will be handled automatically by n8n workflow\n"
        message += "- Polls learning queue every hour\n"
        message += "- ⚠️ Not yet implemented\n\n"

        message += f"**Status:** Queued at {request.requested_at}\n"
        message += f"**Category:** {request.category}\n\n"

        # Show queue position
        pending = self.queue.get_pending()
        position = next(
            (i + 1 for i, req in enumerate(pending) if req.topic == request.topic), None
        )
        if position:
            message += f"**Queue Position:** {position} of {len(pending)}\n"

        return message

    def _format_in_progress_message(self, request: LearningRequest) -> str:
        """Format message for request currently being processed."""
        message = f"⚙️ **Currently Learning: {request.topic}**\n\n"
        message += "This topic is currently being processed.\n\n"
        message += f"**Started:** {request.requested_at}\n"
        message += "Check back in a few minutes for results!"
        return message

    def _format_already_learned_message(self, request: LearningRequest) -> str:
        """Format message for already completed request."""
        message = f"✅ **Already Learned: {request.topic}**\n\n"
        message += "I've already learned about this topic!\n\n"

        if request.papers_found or request.docs_found:
            message += "**Harvested:**\n"
            if request.papers_found:
                message += f"- {request.papers_found} academic papers\n"
            if request.docs_found:
                message += f"- {request.docs_found} technical documents\n"
            message += "\n"

        message += f"**Completed:** {request.completed_at}\n\n"
        message += "Try asking me questions about this topic!"

        return message

    async def get_learning_status(self) -> Dict:
        """
        Get current learning queue status.

        Returns:
            Status dict with queue stats and recent requests
        """
        stats = self.queue.get_stats()

        # Get recent requests (last 10)
        all_requests = self.queue.get_all()
        recent = sorted(all_requests, key=lambda x: x.requested_at, reverse=True)[:10]

        return {
            **stats,
            "recent_requests": [
                {
                    "topic": req.topic,
                    "category": req.category,
                    "status": req.status.value,
                    "requested_at": req.requested_at,
                }
                for req in recent
            ],
        }

    async def list_pending(self) -> List[Dict]:
        """
        List all pending learning requests.

        Returns:
            List of pending requests
        """
        pending = self.queue.get_pending()
        return [
            {
                "topic": req.topic,
                "category": req.category,
                "requested_at": req.requested_at,
            }
            for req in pending
        ]

    async def mark_completed(
        self, topic: str, papers_found: int = 0, docs_found: int = 0
    ) -> bool:
        """
        Mark a learning request as completed.

        Called externally (e.g., by n8n workflow) after harvesting finishes.

        Args:
            topic: Topic that was learned
            papers_found: Number of papers harvested
            docs_found: Number of docs harvested

        Returns:
            True if request was found and updated
        """
        request = self.queue.get_by_topic(topic)
        if not request:
            logger.warning(f"Cannot mark completed - request not found: {topic}")
            return False

        self.queue.update_status(
            topic,
            LearningStatus.COMPLETED,
            papers_found=papers_found,
            docs_found=docs_found,
        )

        logger.info(
            f"Marked learning request as completed: {topic} ({papers_found} papers, {docs_found} docs)"
        )
        return True

    async def mark_failed(self, topic: str, error: str) -> bool:
        """
        Mark a learning request as failed.

        Args:
            topic: Topic that failed
            error: Error message

        Returns:
            True if request was found and updated
        """
        request = self.queue.get_by_topic(topic)
        if not request:
            logger.warning(f"Cannot mark failed - request not found: {topic}")
            return False

        self.queue.update_status(topic, LearningStatus.FAILED, error=error)

        logger.info(f"Marked learning request as failed: {topic}")
        return True
