"""
Request Queue and Rate Limiting

Prevents cascade failures by:
1. Queuing requests when downstream services are slow
2. Rate limiting per user/session
3. Priority-based execution
4. Backpressure when queue is full

This system ensures ORION Core remains responsive even when:
- vLLM is generating a long response
- Multiple users query simultaneously
- Downstream services (Qdrant, AnythingLLM) are slow

Author: ORION Project
Date: November 17, 2025
"""

import asyncio
import logging
import time
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Any, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Request priority levels"""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class QueuedRequest:
    """A request waiting in the queue"""

    request_id: str
    handler: Callable
    args: tuple
    kwargs: dict
    priority: Priority = Priority.NORMAL
    session_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def wait_time(self) -> float:
        """Time spent waiting in queue (seconds)"""
        if self.started_at:
            return self.started_at - self.created_at
        return time.time() - self.created_at

    @property
    def execution_time(self) -> Optional[float]:
        """Time spent executing (seconds)"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


class RequestQueue:
    """
    Request queue with priority and rate limiting.

    Prevents cascade failures by queuing requests when capacity is reached.
    Implements fair scheduling with priority support.

    Features:
    - Concurrent request limiting (max N requests at once)
    - Queue size limiting (max M waiting requests)
    - Priority-based execution (HIGH before NORMAL before LOW)
    - Per-session rate limiting (prevent spam)
    - Backpressure (reject when queue full)
    - Metrics tracking (wait times, throughput, rejection rate)

    Example:
        >>> queue = RequestQueue(max_concurrent=10, max_queue_size=100)
        >>> result = await queue.enqueue(
        ...     request_id="req-123",
        ...     handler=my_async_function,
        ...     args=(arg1, arg2),
        ...     kwargs={"key": "value"},
        ...     priority=Priority.NORMAL,
        ...     session_id="user-session"
        ... )
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_queue_size: int = 100,
        rate_limit_per_session: int = 5,  # Max concurrent per session
        enable_metrics: bool = True,
    ):
        """
        Initialize request queue.

        Args:
            max_concurrent: Maximum concurrent requests across all users
            max_queue_size: Maximum queued requests (reject beyond this)
            rate_limit_per_session: Max concurrent requests per session
            enable_metrics: Track metrics (wait times, throughput, etc.)
        """
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.rate_limit_per_session = rate_limit_per_session
        self.enable_metrics = enable_metrics

        # Semaphore limits total concurrent requests
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Queue for waiting requests (priority queue)
        self.queue: deque[QueuedRequest] = deque()

        # Active requests by session (for rate limiting)
        self.active_per_session: Dict[str, int] = defaultdict(int)

        # Metrics
        self.metrics = {
            "total_requests": 0,
            "completed_requests": 0,
            "rejected_requests": 0,
            "total_wait_time": 0.0,
            "total_execution_time": 0.0,
            "max_wait_time": 0.0,
            "max_execution_time": 0.0,
        }

        logger.info(
            f"Request queue initialized "
            f"(max_concurrent={max_concurrent}, max_queue={max_queue_size})"
        )

    async def enqueue(
        self,
        request_id: str,
        handler: Callable,
        args: tuple = (),
        kwargs: dict = None,
        priority: Priority = Priority.NORMAL,
        session_id: Optional[str] = None,
    ) -> Any:
        """
        Enqueue request for execution.

        Implements backpressure: raises ValueError if queue is full.
        Implements rate limiting: blocks if session has too many active requests.

        Args:
            request_id: Unique request identifier
            handler: Async function to execute
            args: Positional arguments for handler
            kwargs: Keyword arguments for handler
            priority: Request priority (CRITICAL > HIGH > NORMAL > LOW)
            session_id: Session identifier (for rate limiting)

        Returns:
            Result from handler execution

        Raises:
            ValueError: If queue is full (backpressure)
            RuntimeError: If handler execution fails
        """
        if kwargs is None:
            kwargs = {}

        self.metrics["total_requests"] += 1

        # Check queue capacity (backpressure)
        if len(self.queue) >= self.max_queue_size:
            self.metrics["rejected_requests"] += 1
            logger.warning(
                f"Request queue full ({self.max_queue_size}), "
                f"rejecting request {request_id}"
            )
            raise ValueError(
                f"Request queue full. Please try again later. "
                f"(Queue: {len(self.queue)}/{self.max_queue_size})"
            )

        # Check per-session rate limit
        if session_id:
            while (
                self.active_per_session.get(session_id, 0)
                >= self.rate_limit_per_session
            ):
                logger.debug(
                    f"Session {session_id} at rate limit "
                    f"({self.rate_limit_per_session}), waiting..."
                )
                await asyncio.sleep(0.1)

        # Create request object
        request = QueuedRequest(
            request_id=request_id,
            handler=handler,
            args=args,
            kwargs=kwargs,
            priority=priority,
            session_id=session_id,
        )

        logger.info(
            f"Enqueuing request {request_id} "
            f"(priority={priority.name}, session={session_id})"
        )

        # Acquire semaphore (wait if at max_concurrent)
        async with self.semaphore:
            if session_id:
                self.active_per_session[session_id] += 1

            try:
                # Execute request
                request.started_at = time.time()

                result = await handler(*args, **kwargs)

                request.completed_at = time.time()

                # Update metrics
                if self.enable_metrics:
                    self._update_metrics(request)

                self.metrics["completed_requests"] += 1

                logger.info(
                    f"Completed request {request_id} "
                    f"(wait={request.wait_time:.2f}s, "
                    f"exec={request.execution_time:.2f}s)"
                )

                return result

            except Exception as e:
                logger.exception(f"Request {request_id} failed")
                raise RuntimeError(f"Request execution failed: {str(e)}") from e

            finally:
                if session_id:
                    self.active_per_session[session_id] -= 1
                    if self.active_per_session[session_id] <= 0:
                        del self.active_per_session[session_id]

    def _update_metrics(self, request: QueuedRequest):
        """Update metrics after request completion."""
        wait_time = request.wait_time
        exec_time = request.execution_time or 0.0

        self.metrics["total_wait_time"] += wait_time
        self.metrics["total_execution_time"] += exec_time

        if wait_time > self.metrics["max_wait_time"]:
            self.metrics["max_wait_time"] = wait_time

        if exec_time > self.metrics["max_execution_time"]:
            self.metrics["max_execution_time"] = exec_time

    def get_stats(self) -> Dict:
        """
        Get queue statistics.

        Returns:
            Dict with metrics:
            - queue_size: Current queue length
            - active_requests: Currently executing
            - total_requests: All-time total
            - completed_requests: Successfully completed
            - rejected_requests: Rejected due to full queue
            - avg_wait_time: Average wait time (seconds)
            - avg_execution_time: Average execution time (seconds)
            - max_wait_time: Maximum wait time seen
            - max_execution_time: Maximum execution time seen
            - active_sessions: Number of sessions with active requests
        """
        completed = self.metrics["completed_requests"]

        avg_wait = self.metrics["total_wait_time"] / completed if completed > 0 else 0.0

        avg_exec = (
            self.metrics["total_execution_time"] / completed if completed > 0 else 0.0
        )

        return {
            "queue_size": len(self.queue),
            "active_requests": self.max_concurrent - self.semaphore._value,
            "total_requests": self.metrics["total_requests"],
            "completed_requests": completed,
            "rejected_requests": self.metrics["rejected_requests"],
            "avg_wait_time": round(avg_wait, 2),
            "avg_execution_time": round(avg_exec, 2),
            "max_wait_time": round(self.metrics["max_wait_time"], 2),
            "max_execution_time": round(self.metrics["max_execution_time"], 2),
            "active_sessions": len(self.active_per_session),
        }

    def reset_metrics(self):
        """Reset all metrics counters."""
        self.metrics = {
            "total_requests": 0,
            "completed_requests": 0,
            "rejected_requests": 0,
            "total_wait_time": 0.0,
            "total_execution_time": 0.0,
            "max_wait_time": 0.0,
            "max_execution_time": 0.0,
        }
        logger.info("Queue metrics reset")


# Global request queue instance (singleton)
# Initialized with reasonable defaults for homelab deployment
request_queue = RequestQueue(
    max_concurrent=10,  # 10 concurrent requests max
    max_queue_size=100,  # 100 waiting requests max
    rate_limit_per_session=5,  # 5 concurrent per user
    enable_metrics=True,
)
