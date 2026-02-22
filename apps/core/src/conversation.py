"""
Conversation Manager

Manages dialogue sessions, context, and multi-turn conversations.
Stores conversation history and maintains user context.

Features:
- TTL-based session expiration (configurable, default 24 hours)
- LRU eviction when max sessions reached (default 1000)
- Automatic cleanup task (runs every hour)
- Session activity tracking

Author: ORION Project
Date: November 17, 2025
"""

import logging
import json
import sqlite3
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

from .config import config

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversation sessions and history.

    Features:
    - Multi-turn dialogue tracking
    - Context preservation
    - Conversation history storage
    - Session management
    """

    def __init__(
        self,
        session_ttl_hours: int = 24,
        max_sessions: int = 1000,
        cleanup_interval_minutes: int = 60,
    ):
        self.db_path = config.conversations_db
        self.sessions: Dict[str, ConversationSession] = {}

        # Session management configuration
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.max_sessions = max_sessions
        self.cleanup_interval = cleanup_interval_minutes * 60  # Convert to seconds

        self._init_database()

        # Start background cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(
            f"Conversation manager initialized "
            f"(db: {self.db_path}, TTL: {session_ttl_hours}h, max: {max_sessions})"
        )

    def _init_database(self):
        """Initialize SQLite database for conversation history."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata TEXT
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_id
            ON conversations(session_id)
        """
        )

        conn.commit()
        conn.close()

    def get_session(self, session_id: str) -> "ConversationSession":
        """
        Get or create conversation session.

        Automatically enforces max_sessions limit via LRU eviction.

        Args:
            session_id: Unique session identifier

        Returns:
            ConversationSession instance
        """
        if session_id not in self.sessions:
            # Enforce max_sessions limit before creating new session
            if len(self.sessions) >= self.max_sessions:
                self._evict_oldest_session()

            self.sessions[session_id] = ConversationSession(session_id, self.db_path)
            logger.info(f"Created new session: {session_id}")
        else:
            # Update last activity
            self.sessions[session_id].last_activity = datetime.now()

        return self.sessions[session_id]

    def end_session(self, session_id: str):
        """End and cleanup session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Ended session: {session_id}")

    async def _cleanup_loop(self):
        """
        Background task that periodically cleans up expired sessions.

        Runs every cleanup_interval seconds (default: 1 hour).
        Removes sessions older than session_ttl (default: 24 hours).
        """
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)

                now = datetime.now()
                expired_sessions = []

                # Find expired sessions
                for session_id, session in self.sessions.items():
                    age = now - session.last_activity
                    if age > self.session_ttl:
                        expired_sessions.append(session_id)

                # Remove expired sessions
                for session_id in expired_sessions:
                    del self.sessions[session_id]
                    logger.info(f"Cleaned up expired session: {session_id}")

                if expired_sessions:
                    logger.info(
                        f"Session cleanup: removed {len(expired_sessions)} "
                        f"expired sessions, {len(self.sessions)} active"
                    )

            except asyncio.CancelledError:
                logger.info("Cleanup loop cancelled")
                break
            except Exception:
                logger.exception("Error in cleanup loop")
                # Continue despite errors

    def _evict_oldest_session(self):
        """
        Evict the least recently used session when max_sessions is reached.

        Uses LRU (Least Recently Used) strategy based on last_activity.
        """
        if not self.sessions:
            return

        # Find oldest session
        oldest_id = min(self.sessions.items(), key=lambda x: x[1].last_activity)[0]

        del self.sessions[oldest_id]
        logger.warning(
            f"Evicted session {oldest_id} due to max_sessions limit "
            f"({self.max_sessions})"
        )

    def get_stats(self) -> Dict:
        """
        Get conversation manager statistics.

        Returns:
            Dict with active_sessions, max_sessions, oldest_session_age
        """
        if not self.sessions:
            return {
                "active_sessions": 0,
                "max_sessions": self.max_sessions,
                "oldest_session_age_minutes": 0,
            }

        now = datetime.now()
        oldest_age = max(
            (now - session.last_activity).total_seconds() / 60
            for session in self.sessions.values()
        )

        return {
            "active_sessions": len(self.sessions),
            "max_sessions": self.max_sessions,
            "oldest_session_age_minutes": round(oldest_age, 1),
        }

    async def shutdown(self):
        """Gracefully shutdown cleanup task."""
        if hasattr(self, "_cleanup_task"):
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Conversation manager shutdown complete")


class ConversationSession:
    """
    Individual conversation session.

    Tracks messages, context, and provides history.
    """

    def __init__(self, session_id: str, db_path: Path):
        self.session_id = session_id
        self.db_path = db_path
        self.messages: List[Dict] = []
        self.context: Dict = {}
        self.created_at = datetime.now()
        self.last_activity = datetime.now()  # Track for TTL and LRU

        # Load existing history
        self._load_history()

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """
        Add message to conversation.

        Updates last_activity timestamp for TTL tracking.

        Args:
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata dict
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        self.messages.append(message)

        # Update activity timestamp
        self.last_activity = datetime.now()

        # Save to database
        self._save_message(message)

        logger.debug(f"Added {role} message to session {self.session_id}")

    def get_history(
        self, limit: Optional[int] = None, include_system: bool = False
    ) -> List[Dict]:
        """
        Get conversation history.

        Args:
            limit: Maximum messages to return (most recent)
            include_system: Include system messages

        Returns:
            List of message dicts
        """
        messages = self.messages

        if not include_system:
            messages = [m for m in messages if m["role"] != "system"]

        if limit:
            messages = messages[-limit:]

        return messages

    def get_context_summary(self) -> str:
        """
        Get summary of conversation context for LLM.

        Returns:
            Context summary string
        """
        if not self.messages:
            return "This is the start of the conversation."

        recent = self.get_history(limit=5)

        summary = "Recent conversation:\n"
        for msg in recent:
            role = msg["role"].upper()
            content = (
                msg["content"][:100] + "..."
                if len(msg["content"]) > 100
                else msg["content"]
            )
            summary += f"{role}: {content}\n"

        return summary

    def _load_history(self):
        """Load conversation history from database."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT role, message, timestamp, metadata
                FROM conversations
                WHERE session_id = ?
                ORDER BY timestamp ASC
            """,
                (self.session_id,),
            )

            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                role, content, timestamp, metadata_json = row
                metadata = json.loads(metadata_json) if metadata_json else {}

                self.messages.append(
                    {
                        "role": role,
                        "content": content,
                        "timestamp": timestamp,
                        "metadata": metadata,
                    }
                )

            logger.debug(
                f"Loaded {len(self.messages)} messages for session {self.session_id}"
            )

        except Exception as e:
            logger.error(f"Failed to load history: {e}")

    def _save_message(self, message: Dict):
        """Save message to database."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO conversations (session_id, timestamp, role, message, metadata)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    self.session_id,
                    message["timestamp"],
                    message["role"],
                    message["content"],
                    json.dumps(message.get("metadata", {})),
                ),
            )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to save message: {e}")
