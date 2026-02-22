"""
Debug Tracker - Breadcrumb Trail & State Diff System

Provides time-travel debugging capabilities for ORION:
- Records every action and state change
- Automatic root cause analysis on errors
- State diff visualization
- Real-time streaming to WebSocket clients

Author: ORION Project
Date: November 19, 2025
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from copy import deepcopy
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Breadcrumb:
    """Single breadcrumb in execution trail"""

    timestamp: str
    action: str
    reasoning: str
    state_snapshot: Dict[str, Any]
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "reasoning": self.reasoning,
            "state_snapshot": self.state_snapshot,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class StateDiff:
    """Difference between two state snapshots"""

    before_label: str
    after_label: str
    added: List[str]
    removed: List[str]
    modified: Dict[str, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "before": self.before_label,
            "after": self.after_label,
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
        }

    def summary(self) -> str:
        """Human-readable summary of changes"""
        parts = []
        if self.added:
            parts.append(f"Added: {', '.join(self.added)}")
        if self.removed:
            parts.append(f"Removed: {', '.join(self.removed)}")
        if self.modified:
            parts.append(f"Modified: {', '.join(self.modified.keys())}")
        return " | ".join(parts) if parts else "No changes"


class DebugTracker:
    """
    Tracks execution breadcrumbs and state changes for debugging.

    Features:
    - Records every action with reasoning and state
    - Automatic state diff calculation
    - Root cause analysis on errors
    - Real-time WebSocket streaming
    - Replay capability for debugging
    """

    def __init__(self, max_breadcrumbs: int = 100):
        """
        Initialize debug tracker.

        Args:
            max_breadcrumbs: Maximum breadcrumbs to keep (prevents memory bloat)
        """
        self.breadcrumbs: List[Breadcrumb] = []
        self.max_breadcrumbs = max_breadcrumbs
        self.ws_clients: List[Any] = []  # WebSocket clients for streaming
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"Debug tracker initialized (session: {self.session_id})")

    def add_ws_client(self, client):
        """Add WebSocket client for real-time streaming"""
        self.ws_clients.append(client)
        logger.debug(f"Added WebSocket client (total: {len(self.ws_clients)})")

    def remove_ws_client(self, client):
        """Remove WebSocket client"""
        if client in self.ws_clients:
            self.ws_clients.remove(client)
            logger.debug(f"Removed WebSocket client (total: {len(self.ws_clients)})")

    async def track(
        self,
        action: str,
        reasoning: str,
        state: Dict[str, Any],
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Record a breadcrumb.

        Args:
            action: What action is being taken
            reasoning: Why this action was chosen
            state: Current state snapshot
            confidence: Confidence in this decision (0-1)
            metadata: Additional context
        """
        breadcrumb = Breadcrumb(
            timestamp=datetime.now().isoformat(),
            action=action,
            reasoning=reasoning,
            state_snapshot=deepcopy(state),
            confidence=confidence,
            metadata=metadata or {},
        )

        self.breadcrumbs.append(breadcrumb)

        # Trim old breadcrumbs if needed
        if len(self.breadcrumbs) > self.max_breadcrumbs:
            removed = self.breadcrumbs.pop(0)
            logger.debug(f"Trimmed old breadcrumb: {removed.action}")

        logger.debug(
            f"Breadcrumb: {action} (confidence: {confidence:.2f}, "
            f"total: {len(self.breadcrumbs)})"
        )

        # Stream to WebSocket clients
        await self._broadcast_breadcrumb(breadcrumb)

    async def _broadcast_breadcrumb(self, breadcrumb: Breadcrumb):
        """Broadcast breadcrumb to all WebSocket clients"""
        if not self.ws_clients:
            return

        message = {
            "type": "debug_breadcrumb",
            "data": breadcrumb.to_dict(),
        }

        # Send to all connected clients
        disconnected = []
        for client in self.ws_clients:
            try:
                await client.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send to client: {e}")
                disconnected.append(client)

        # Remove disconnected clients
        for client in disconnected:
            self.remove_ws_client(client)

    def get_state_diff(self, steps_back: int = 1) -> Optional[StateDiff]:
        """
        Calculate state diff between current and N steps back.

        Args:
            steps_back: How many steps to look back

        Returns:
            StateDiff object or None if insufficient history
        """
        if len(self.breadcrumbs) < steps_back + 1:
            return None

        before = self.breadcrumbs[-steps_back - 1]
        after = self.breadcrumbs[-1]

        before_state = before.state_snapshot
        after_state = after.state_snapshot

        # Calculate differences
        before_keys = set(before_state.keys())
        after_keys = set(after_state.keys())

        added = list(after_keys - before_keys)
        removed = list(before_keys - after_keys)

        # Find modified values
        modified = {}
        for key in before_keys & after_keys:
            if before_state[key] != after_state[key]:
                modified[key] = {
                    "before": before_state[key],
                    "after": after_state[key],
                }

        return StateDiff(
            before_label=before.action,
            after_label=after.action,
            added=added,
            removed=removed,
            modified=modified,
        )

    async def analyze_error(
        self, error: Exception, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze error and provide root cause analysis.

        Args:
            error: The exception that occurred
            context: Additional error context

        Returns:
            Analysis with breadcrumb trail, likely cause, and suggestions
        """
        logger.info(f"Analyzing error: {type(error).__name__}: {error}")

        # Get recent breadcrumbs (last 10)
        recent_trail = self.breadcrumbs[-10:] if self.breadcrumbs else []

        # Find divergence point (where confidence dropped or state changed unexpectedly)
        divergence_point = self._find_divergence_point()

        # Calculate state diff if we have history
        state_diff = (
            self.get_state_diff(steps_back=1) if len(self.breadcrumbs) >= 2 else None
        )

        analysis = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "breadcrumb_trail": [b.to_dict() for b in recent_trail],
            "total_steps": len(self.breadcrumbs),
            "divergence_point": divergence_point,
            "state_at_failure": recent_trail[-1].state_snapshot if recent_trail else {},
            "state_diff": state_diff.to_dict() if state_diff else None,
            "context": context,
            "suggested_fixes": self._generate_suggestions(error, recent_trail),
        }

        # Broadcast analysis to WebSocket clients
        await self._broadcast_analysis(analysis)

        return analysis

    def _find_divergence_point(self) -> Optional[Dict[str, Any]]:
        """
        Find the point where things likely went wrong.

        Looks for:
        - Sudden confidence drop
        - Unexpected state changes
        - Actions that were marked as risky
        """
        if len(self.breadcrumbs) < 2:
            return None

        for i in range(len(self.breadcrumbs) - 1, 0, -1):
            current = self.breadcrumbs[i]
            previous = self.breadcrumbs[i - 1]

            # Check for confidence drop
            if previous.confidence >= 0.8 and current.confidence < 0.7:
                return {
                    "index": i,
                    "reason": "confidence_drop",
                    "action": current.action,
                    "confidence_before": previous.confidence,
                    "confidence_after": current.confidence,
                    "reasoning": current.reasoning,
                }

            # Check for risky action markers
            if "risky" in current.metadata or "uncertain" in current.metadata:
                return {
                    "index": i,
                    "reason": "risky_action",
                    "action": current.action,
                    "metadata": current.metadata,
                }

        # No obvious divergence found, return last action
        if self.breadcrumbs:
            last = self.breadcrumbs[-1]
            return {
                "index": len(self.breadcrumbs) - 1,
                "reason": "last_action",
                "action": last.action,
                "reasoning": last.reasoning,
            }

        return None

    def _generate_suggestions(
        self, error: Exception, trail: List[Breadcrumb]
    ) -> List[Dict[str, str]]:
        """
        Generate suggestions based on error and execution trail.

        Args:
            error: The exception
            trail: Recent breadcrumb trail

        Returns:
            List of suggested fixes
        """
        suggestions = []

        # Generic suggestions based on error type
        error_type = type(error).__name__

        if "Connection" in error_type or "Network" in error_type:
            suggestions.append(
                {
                    "action": "Check service availability",
                    "reason": "Network/connection error detected",
                    "priority": "high",
                }
            )

        if "Permission" in error_type or "Denied" in error_type:
            suggestions.append(
                {
                    "action": "Verify permissions and authentication",
                    "reason": "Permission error detected",
                    "priority": "high",
                }
            )

        if "Timeout" in error_type:
            suggestions.append(
                {
                    "action": "Increase timeout or check service performance",
                    "reason": "Operation timed out",
                    "priority": "medium",
                }
            )

        # Add trail-based suggestions
        if trail and trail[-1].confidence < 0.7:
            suggestions.append(
                {
                    "action": "Review last action - low confidence detected",
                    "reason": f"Last action had {trail[-1].confidence:.0%} confidence",
                    "priority": "high",
                }
            )

        # Always suggest checking logs
        suggestions.append(
            {
                "action": "Review execution trail for unexpected state changes",
                "reason": "Standard debugging practice",
                "priority": "low",
            }
        )

        return suggestions

    async def _broadcast_analysis(self, analysis: Dict[str, Any]):
        """Broadcast error analysis to WebSocket clients"""
        if not self.ws_clients:
            return

        message = {
            "type": "debug_analysis",
            "data": analysis,
        }

        disconnected = []
        for client in self.ws_clients:
            try:
                await client.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send analysis to client: {e}")
                disconnected.append(client)

        for client in disconnected:
            self.remove_ws_client(client)

    def get_trail(self, last_n: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent breadcrumb trail.

        Args:
            last_n: Number of recent breadcrumbs to return

        Returns:
            List of breadcrumb dictionaries
        """
        trail = self.breadcrumbs[-last_n:] if self.breadcrumbs else []
        return [b.to_dict() for b in trail]

    def clear(self):
        """Clear all breadcrumbs (start fresh)"""
        old_count = len(self.breadcrumbs)
        self.breadcrumbs.clear()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Cleared {old_count} breadcrumbs (new session: {self.session_id})")

    def summary(self) -> str:
        """Get human-readable summary of current state"""
        if not self.breadcrumbs:
            return "No execution history"

        last = self.breadcrumbs[-1]
        avg_confidence = sum(b.confidence for b in self.breadcrumbs) / len(
            self.breadcrumbs
        )

        return (
            f"Session {self.session_id}: {len(self.breadcrumbs)} steps, "
            f"last action: {last.action}, avg confidence: {avg_confidence:.2f}"
        )
