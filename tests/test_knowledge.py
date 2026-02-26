"""Tests for hal/knowledge.py — KnowledgeBase semantic search.

Pure unit tests — no live pgvector or Ollama connection required.
All external I/O is mocked at the network boundary (psycopg2.connect,
register_vector, and OllamaClient.embed).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hal.knowledge import _GROUND_TRUTH_BOOST, KnowledgeBase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DSN = "postgresql://user:pw@localhost/knowledge_base"


def _make_conn(rows: list[tuple]) -> tuple[MagicMock, MagicMock]:
    """Return (conn_mock, cursor_mock) with fetchall returning *rows*."""
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def _make_llm(embed: list[float] | None = None) -> MagicMock:
    llm = MagicMock()
    llm.embed.return_value = embed or [0.1] * 8  # small vector, enough for np.array()
    return llm


# ---------------------------------------------------------------------------
# Proof 1 — result shape
# ---------------------------------------------------------------------------


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_returns_correct_result_count(mock_connect, mock_reg):
    """search() returns one dict per DB row."""
    rows = [
        ("content A", "file_a.md", "lab", 0.80, "reference"),
        ("content B", "file_b.md", "lab", 0.70, "reference"),
    ]
    conn, _ = _make_conn(rows)
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    results = kb.search("query", top_k=2)

    assert len(results) == 2


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_result_dict_has_expected_keys(mock_connect, mock_reg):
    """Each result dict must have exactly {content, file, category, score, doc_tier}."""
    rows = [("text", "f.md", "cat", 0.75, "reference")]
    conn, _ = _make_conn(rows)
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    result = kb.search("q")[0]

    assert set(result.keys()) == {"content", "file", "category", "score", "doc_tier"}
    assert result["content"] == "text"
    assert result["file"] == "f.md"
    assert result["category"] == "cat"
    assert result["score"] == pytest.approx(0.75)
    assert result["doc_tier"] == "reference"


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_empty_result_returns_empty_list(mock_connect, mock_reg):
    """search() returns [] when the DB returns no rows."""
    conn, _ = _make_conn([])
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    assert kb.search("obscure query") == []


# ---------------------------------------------------------------------------
# Proof 2 — ground-truth boost
# ---------------------------------------------------------------------------


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_ground_truth_score_boosted(mock_connect, mock_reg):
    """ground-truth doc gets +_GROUND_TRUTH_BOOST added to its score."""
    rows = [("text", "f.md", "lab", 0.80, "ground-truth")]
    conn, _ = _make_conn(rows)
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    result = kb.search("q")[0]

    assert result["score"] == pytest.approx(0.80 + _GROUND_TRUTH_BOOST)


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_ground_truth_score_capped_at_one(mock_connect, mock_reg):
    """Boosted score must not exceed 1.0."""
    rows = [("text", "f.md", "lab", 0.96, "ground-truth")]
    conn, _ = _make_conn(rows)
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    result = kb.search("q")[0]

    assert result["score"] <= 1.0


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_reference_score_unchanged(mock_connect, mock_reg):
    """reference doc_tier must not have its score modified."""
    rows = [("text", "f.md", "lab", 0.70, "reference")]
    conn, _ = _make_conn(rows)
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    result = kb.search("q")[0]

    assert result["score"] == pytest.approx(0.70)


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_boost_reorders_lower_raw_score_ground_truth_first(
    mock_connect, mock_reg
):
    """A lower raw-score ground-truth doc should sort first after boost."""
    rows = [
        ("ref", "ref.md", "lab", 0.82, "reference"),  # stays 0.82
        ("gt", "gt.md", "lab", 0.76, "ground-truth"),  # becomes 0.86
    ]
    conn, _ = _make_conn(rows)
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    results = kb.search("q")

    assert results[0]["file"] == "gt.md"


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_boost_disabled_preserves_order(mock_connect, mock_reg):
    """boost_ground_truth=False must preserve DB-order scores unchanged."""
    rows = [
        ("ref", "ref.md", "lab", 0.82, "reference"),
        ("gt", "gt.md", "lab", 0.76, "ground-truth"),
    ]
    conn, _ = _make_conn(rows)
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    results = kb.search("q", boost_ground_truth=False)

    assert results[0]["file"] == "ref.md"
    assert results[1]["score"] == pytest.approx(0.76)


# ---------------------------------------------------------------------------
# Proof 3 — embed called with query
# ---------------------------------------------------------------------------


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_calls_embed_with_query_string(mock_connect, mock_reg):
    """search() must call llm.embed() exactly once with the user query."""
    conn, _ = _make_conn([])
    mock_connect.return_value = conn
    llm = _make_llm()
    kb = KnowledgeBase(_DSN, llm)

    kb.search("what is the server IP?")

    llm.embed.assert_called_once_with("what is the server IP?")


# ---------------------------------------------------------------------------
# Proof 4 — connection lifecycle
# ---------------------------------------------------------------------------


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_closes_connection_on_success(mock_connect, mock_reg):
    """search() must call conn.close() after a successful query."""
    conn, _ = _make_conn([])
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    kb.search("q")

    conn.close.assert_called_once()


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_search_registers_vector_on_connection(mock_connect, mock_reg):
    """search() must call register_vector(conn) before querying."""
    conn, _ = _make_conn([])
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    kb.search("q")

    mock_reg.assert_called_once_with(conn)


# ---------------------------------------------------------------------------
# Proof 5 — categories()
# ---------------------------------------------------------------------------


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_categories_returns_list_of_tuples(mock_connect, mock_reg):
    """categories() must return a list of (category, count) tuples."""
    cat_rows = [("lab", 150), ("ops", 75)]
    conn, cur = _make_conn([])  # reuse helper; override fetchall below
    cur.fetchall.return_value = cat_rows
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    result = kb.categories()

    assert result == [("lab", 150), ("ops", 75)]


@patch("hal.knowledge.register_vector")
@patch("hal.knowledge.psycopg2.connect")
def test_categories_closes_connection(mock_connect, mock_reg):
    """categories() must call conn.close()."""
    conn, cur = _make_conn([])
    cur.fetchall.return_value = []
    mock_connect.return_value = conn
    kb = KnowledgeBase(_DSN, _make_llm())

    kb.categories()

    conn.close.assert_called_once()
