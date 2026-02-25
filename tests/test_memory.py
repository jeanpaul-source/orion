"""Unit tests for hal/memory.py — is_poison_response(), save_turn() guard, prune_old_turns().

These tests require no external services. They use MemoryStore with a real SQLite
file in a tmp directory so the path/schema logic is also exercised.

Run with: pytest tests/test_memory.py -v
"""

from datetime import datetime, timedelta

import pytest

from hal.memory import MemoryStore, is_poison_response

# ---------------------------------------------------------------------------
# is_poison_response — detection logic
# ---------------------------------------------------------------------------

POISON_STRINGS = [
    '{"name": "run_command", "arguments": {"command": "ls -la"}}',
    '{"name": "get_metrics", "arguments": {}}',
    '{"name": "search_kb", "arguments": {"query": "list of all AWS regions"}}',
    '  {"name": "read_file", "arguments": {"path": "/etc/passwd"}}  ',  # whitespace padded
    '{"name": "<function-name>", "arguments": {}}',  # exact pattern from SESSION_FINDINGS B1
]

CLEAN_STRINGS = [
    "The CPU is at 40% usage.",
    "Prometheus is running on port 9091.",
    "",
    '{"error": "something went wrong"}',  # JSON but not a tool call
    '{"status": "ok", "code": 200}',  # JSON but not a tool call
    "Sure, I can help with that.",
    "I don't know the answer to that question.",
    # Partial matches should not trigger
    'The "name" of the service is "arguments".',  # contains both words but not JSON
]


@pytest.mark.parametrize("text", POISON_STRINGS)
def test_poison_detection_true(text):
    """is_poison_response must catch raw tool-call JSON dumps."""
    assert is_poison_response(text), f"Expected poison, got clean for: {text!r}"


@pytest.mark.parametrize("text", CLEAN_STRINGS)
def test_poison_detection_false(text):
    """is_poison_response must not flag legitimate responses."""
    assert not is_poison_response(text), f"False positive for: {text!r}"


# ---------------------------------------------------------------------------
# MemoryStore — save_turn() poison guard
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    """MemoryStore backed by a temp directory — isolated per test."""
    monkeypatch.setattr("hal.memory.DB_PATH", tmp_path / "memory.db")
    store = MemoryStore()
    yield store
    store.close()


def test_save_turn_stores_normal_assistant_response(mem):
    """Clean assistant responses must be persisted as usual."""
    sid = mem.new_session()
    mem.save_turn(sid, "assistant", "The CPU is at 40% usage.")
    turns = mem.load_turns(sid)
    assert len(turns) == 1
    assert turns[0]["content"] == "The CPU is at 40% usage."


def test_save_turn_drops_poison_assistant_response(mem):
    """Poison assistant turns (raw tool-call JSON) must be silently dropped."""
    sid = mem.new_session()
    poison = '{"name": "run_command", "arguments": {"command": "ls"}}'
    mem.save_turn(sid, "assistant", poison)
    turns = mem.load_turns(sid)
    assert len(turns) == 0, "Poison turn should not have been saved"


def test_save_turn_always_stores_user_turns(mem):
    """User turns are never filtered — even if they look like JSON."""
    sid = mem.new_session()
    # User could paste a JSON string into the prompt — we must keep it
    user_content = '{"name": "run_command", "arguments": {}}'
    mem.save_turn(sid, "user", user_content)
    turns = mem.load_turns(sid)
    assert len(turns) == 1
    assert turns[0]["role"] == "user"


def test_save_turn_mixed_session(mem):
    """In a real exchange, user turns are kept and poison assistant turns are dropped."""
    sid = mem.new_session()
    mem.save_turn(sid, "user", "check the lab")
    mem.save_turn(
        sid, "assistant", '{"name": "get_metrics", "arguments": {}}'
    )  # poison
    mem.save_turn(sid, "user", "what is the CPU usage?")
    mem.save_turn(sid, "assistant", "CPU is at 35%.")  # clean

    turns = mem.load_turns(sid)
    assert len(turns) == 3
    roles = [t["role"] for t in turns]
    contents = [t["content"] for t in turns]
    assert roles == ["user", "user", "assistant"]
    assert "CPU is at 35%." in contents
    assert not any('{"name"' in c for c in contents)


# ---------------------------------------------------------------------------
# MemoryStore — prune_old_turns()
# ---------------------------------------------------------------------------


def test_prune_removes_old_turns(mem):
    """Turns older than the cutoff must be deleted."""
    sid = mem.new_session()
    # Insert a turn with a timestamp 40 days in the past
    old_ts = (datetime.now() - timedelta(days=40)).isoformat()
    mem.conn.execute(
        "INSERT INTO turns (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (sid, "user", "old message", old_ts),
    )
    mem.conn.commit()

    deleted = mem.prune_old_turns(days=30)
    assert deleted == 1
    turns = mem.load_turns(sid)
    assert len(turns) == 0


def test_prune_keeps_recent_turns(mem):
    """Turns within the cutoff must not be touched."""
    sid = mem.new_session()
    mem.save_turn(sid, "user", "recent message")

    deleted = mem.prune_old_turns(days=30)
    assert deleted == 0
    turns = mem.load_turns(sid)
    assert len(turns) == 1


def test_prune_removes_orphaned_sessions(mem):
    """Sessions with no remaining turns must be deleted after pruning."""
    sid = mem.new_session()
    old_ts = (datetime.now() - timedelta(days=40)).isoformat()
    mem.conn.execute(
        "INSERT INTO turns (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (sid, "user", "old", old_ts),
    )
    mem.conn.commit()

    mem.prune_old_turns(days=30)
    assert not mem.session_exists(sid)


def test_prune_keeps_sessions_with_recent_turns(mem):
    """Sessions that still have recent turns must survive pruning."""
    sid = mem.new_session()
    mem.save_turn(sid, "user", "still here")

    mem.prune_old_turns(days=30)
    assert mem.session_exists(sid)


def test_prune_mixed(mem):
    """Old turns are pruned; recent turns and their session survive."""
    old_sid = mem.new_session()
    new_sid = mem.new_session()

    old_ts = (datetime.now() - timedelta(days=40)).isoformat()
    mem.conn.execute(
        "INSERT INTO turns (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (old_sid, "user", "ancient history", old_ts),
    )
    mem.conn.commit()
    mem.save_turn(new_sid, "user", "recent message")

    deleted = mem.prune_old_turns(days=30)
    assert deleted == 1
    assert not mem.session_exists(old_sid)
    assert mem.session_exists(new_sid)


# ---------------------------------------------------------------------------
# MemoryStore — create_session() (caller-chosen ID)
# ---------------------------------------------------------------------------


def test_create_session_with_custom_id(mem):
    """create_session() should accept an arbitrary string ID."""
    sid = mem.create_session("tg-999")
    assert sid == "tg-999"
    assert mem.session_exists("tg-999")


def test_create_session_supports_turns(mem):
    """Turns can be saved and loaded against a caller-chosen session."""
    sid = mem.create_session("tg-42")
    mem.save_turn(sid, "user", "hello")
    mem.save_turn(sid, "assistant", "hi there")
    turns = mem.load_turns(sid)
    assert len(turns) == 2
    assert turns[0]["content"] == "hello"
    assert turns[1]["content"] == "hi there"
