"""Tests for harvest collectors and ingestion logic."""

from harvest.collect import _doc, collect_ground_truth
from harvest.ingest import _chunk
from harvest.parsers import content_hash

# --- _doc helper ---


def test_doc_includes_doc_tier():
    d = _doc("p", "f", "c", "content", doc_tier="ground-truth")
    assert d["doc_tier"] == "ground-truth"


def test_doc_default_tier():
    d = _doc("p", "f", "c", "content")
    assert d["doc_tier"] == "reference"


def test_doc_strips_content():
    d = _doc("p", "f", "c", "  hello  ")
    assert d["content"] == "hello"


# --- _chunk ---


def test_chunk_short_text():
    chunks = _chunk("short text")
    assert len(chunks) == 1
    assert chunks[0] == "short text"


def test_chunk_long_text_splits():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(50))
    chunks = _chunk(text)
    assert len(chunks) > 1
    for chunk in chunks:
        # Each chunk should be roughly within CHUNK_SIZE, accounting for overlap
        assert len(chunk) <= 1000  # generous upper bound


def test_chunk_overlap():
    """Verify chunks overlap — last chars of chunk N appear in chunk N+1."""
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(50))
    chunks = _chunk(text)
    if len(chunks) >= 2:
        tail = chunks[0][-50:]
        assert tail in chunks[1]


# --- collect_ground_truth ---


def test_collect_ground_truth_reads_md_files(tmp_path, monkeypatch):
    """Ground truth collector reads .md files from knowledge/ dir."""
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "TEST.md").write_text("# Test\nThis is ground truth content.")
    (knowledge / "README.md").write_text("# README\nShould be skipped.")
    (knowledge / "notes.txt").write_text("Not a markdown file — should be skipped.")

    # Patch __file__ so repo_root resolves to tmp_path
    # collect_ground_truth does: Path(__file__).resolve().parent.parent / "knowledge"
    # So __file__ needs to be tmp_path / "harvest" / "collect.py"
    fake_file = str(tmp_path / "harvest" / "collect.py")
    import harvest.collect as mod

    monkeypatch.setattr(mod, "__file__", fake_file)

    docs = collect_ground_truth()
    assert len(docs) == 1  # only TEST.md — README.md and .txt skipped
    assert docs[0]["doc_tier"] == "ground-truth"
    assert docs[0]["category"] == "ground-truth"
    assert docs[0]["file_name"] == "TEST.md"


# --- content_hash in metadata ---


def test_content_hash_used_in_incremental():
    """Verify content_hash produces consistent results for chunk comparison."""
    chunk = "This is a test chunk of text for hashing."
    h1 = content_hash(chunk)
    h2 = content_hash(chunk)
    assert h1 == h2
    # Different content → different hash
    h3 = content_hash(chunk + " modified")
    assert h1 != h3
