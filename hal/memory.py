"""SQLite-backed session and conversation history store."""
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / ".orion" / "memory.db"
TURN_WINDOW = 40  # messages loaded into LLM context (20 exchanges)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            started_at  TEXT NOT NULL,
            label       TEXT
        );
        CREATE TABLE IF NOT EXISTS turns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(id),
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            timestamp   TEXT NOT NULL
        );
    """)
    conn.commit()


class MemoryStore:
    def __init__(self):
        self.conn = _connect()

    def new_session(self) -> str:
        sid = str(uuid.uuid4())[:8]
        self.conn.execute(
            "INSERT INTO sessions (id, started_at) VALUES (?, ?)",
            (sid, datetime.now().isoformat()),
        )
        self.conn.commit()
        return sid

    def last_session_id(self) -> str | None:
        row = self.conn.execute(
            "SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None

    def save_turn(self, session_id: str, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO turns (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, role, content, datetime.now().isoformat()),
        )
        # Auto-label the session with the first user message
        if role == "user":
            row = self.conn.execute(
                "SELECT label FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row and not row["label"]:
                label = content[:60].replace("\n", " ")
                self.conn.execute(
                    "UPDATE sessions SET label = ? WHERE id = ?",
                    (label, session_id),
                )
        self.conn.commit()

    def load_turns(self, session_id: str, limit: int = TURN_WINDOW) -> list[dict]:
        rows = self.conn.execute(
            """SELECT role, content FROM turns
               WHERE session_id = ?
               ORDER BY id DESC LIMIT ?""",
            (session_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def list_sessions(self, n: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """SELECT s.id, s.started_at, s.label,
                      COUNT(t.id) as turn_count
               FROM sessions s
               LEFT JOIN turns t ON t.session_id = s.id
               GROUP BY s.id
               ORDER BY s.started_at DESC
               LIMIT ?""",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_sessions(self, query: str, n: int = 20) -> list[dict]:
        """Full-text search across all sessions. Returns matching turns, newest first."""
        rows = self.conn.execute(
            """SELECT t.session_id, t.role, t.content, t.timestamp
               FROM turns t
               WHERE t.content LIKE ?
               ORDER BY t.timestamp DESC
               LIMIT ?""",
            (f"%{query}%", n),
        ).fetchall()
        return [dict(r) for r in rows]

    def session_exists(self, session_id: str) -> bool:
        row = self.conn.execute(
            "SELECT id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self.conn.close()
