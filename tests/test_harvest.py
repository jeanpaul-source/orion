"""Tests for harvest collectors and ingestion logic."""

import json

from harvest.collect import _doc, collect_ground_truth
from harvest.ingest import _chunk
from harvest.parsers import content_hash
from harvest.snapshot import (
    _parse_disks,
    _parse_models,
    _parse_ports,
    _parse_services,
    build_snapshot,
    write_snapshot,
)

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


# --- snapshot parsers ---


def test_parse_services_extracts_names():
    content = "Running systemd services (as of 2026-03-01 03:00):\nfalco.service running active\ngrafana.service running active"
    assert _parse_services(content) == ["falco.service", "grafana.service"]


def test_parse_services_skips_header_and_blanks():
    content = "Running systemd services (as of 2026-03-01 03:00):\n\nonly.service running active\n"
    result = _parse_services(content)
    assert result == ["only.service"]


def test_parse_disks_basic():
    content = "Disk usage (as of 2026-03-01 03:00):\n/          233G   42G  179G  19%\n/data      1.8T  400G  1.3T  24%"
    result = _parse_disks(content)
    assert len(result) == 2
    assert result[0] == {
        "mount": "/",
        "size": "233G",
        "used": "42G",
        "avail": "179G",
        "pcent": "19%",
    }
    assert result[1]["mount"] == "/data"


def test_parse_disks_skips_header():
    content = "Disk usage (as of 2026-03-01):\n/tmp 10G 1G 9G 10%"
    result = _parse_disks(content)
    assert len(result) == 1
    assert result[0]["mount"] == "/tmp"


def test_parse_ports_deduplicates_and_sorts():
    content = "Listening ports on all interfaces (as of 2026-03-01):\nLISTEN 0 128 0.0.0.0:22 0.0.0.0:* users\nLISTEN 0 128 0.0.0.0:22 0.0.0.0:* users\nLISTEN 0 128 0.0.0.0:80 0.0.0.0:* users"
    result = _parse_ports(content)
    assert result == ["0.0.0.0:22", "0.0.0.0:80"]


def test_parse_models_extracts_names():
    content = "Ollama models available (as of 2026-03-01):\nnomic-embed-text:latest 274877906\nllama3:8b 4661220864"
    result = _parse_models(content)
    assert "nomic-embed-text:latest" in result
    assert "llama3:8b" in result
    assert len(result) == 2


# --- build_snapshot ---


def _make_docs():
    """Minimal doc list covering each snapshot section."""
    return [
        {
            "file_path": "lab://docker/containers/grafana",
            "category": "lab-state",
            "content": "Docker container: grafana\n  Image: grafana/grafana:latest",
            "metadata": {
                "image": "grafana/grafana:latest",
                "ports": "0.0.0.0:3000->3000/tcp",
            },
        },
        {
            "file_path": "lab://state/services",
            "category": "lab-state",
            "content": "Running systemd services (as of 2026-03-01 03:00):\nfoo.service running active",
            "metadata": {},
        },
        {
            "file_path": "lab://state/disk",
            "category": "lab-state",
            "content": "Disk usage (as of 2026-03-01 03:00):\n/ 233G 42G 179G 19%",
            "metadata": {},
        },
        {
            "file_path": "lab://state/ports",
            "category": "lab-state",
            "content": "Listening ports on all interfaces (as of 2026-03-01):\nLISTEN 0 0 0.0.0.0:22 0.0.0.0:* u",
            "metadata": {},
        },
        {
            "file_path": "lab://state/ollama-models",
            "category": "lab-state",
            "content": "Ollama models available (as of 2026-03-01):\nnomic-embed-text:latest 274877906",
            "metadata": {},
        },
        {
            "file_path": "/opt/homelab-infrastructure/monitoring/docker-compose.yml",
            "category": "lab-infrastructure",
            "content": "# /opt/homelab-infrastructure/monitoring/docker-compose.yml\n\nversion: '3'",
            "metadata": {
                "source_path": "/opt/homelab-infrastructure/monitoring/docker-compose.yml"
            },
        },
        {
            "file_path": "lab://systemd/ollama.service",
            "category": "lab-infrastructure",
            "content": "systemd unit: ollama.service\n\n[Unit]\nDescription=Ollama",
            "metadata": {},
        },
    ]


def test_build_snapshot_required_keys():
    snap = build_snapshot(_make_docs())
    for key in (
        "harvested_at",
        "containers",
        "services",
        "disks",
        "ports",
        "ollama_models",
        "config_hashes",
        "systemd_units",
    ):
        assert key in snap, f"missing key: {key}"


def test_build_snapshot_harvested_at_is_iso():
    from datetime import datetime

    snap = build_snapshot(_make_docs())
    dt = datetime.fromisoformat(snap["harvested_at"])  # raises if not valid ISO
    assert dt.year >= 2026


def test_build_snapshot_containers():
    snap = build_snapshot(_make_docs())
    assert snap["containers"] == [
        {"name": "grafana", "image": "grafana/grafana:latest"}
    ]


def test_build_snapshot_config_hashes_key_is_relative():
    snap = build_snapshot(_make_docs(), infra_base="/opt/homelab-infrastructure")
    assert "monitoring/docker-compose.yml" in snap["config_hashes"]
    h = snap["config_hashes"]["monitoring/docker-compose.yml"]
    assert len(h) == 16  # first 16 hex chars of sha256


def test_build_snapshot_config_hash_changes_on_content_change():
    docs = _make_docs()
    snap1 = build_snapshot(docs, infra_base="/opt/homelab-infrastructure")
    docs[-2]["content"] = "# changed\n\nversion: '3'\nnew_line: true"
    snap2 = build_snapshot(docs, infra_base="/opt/homelab-infrastructure")
    assert (
        snap1["config_hashes"]["monitoring/docker-compose.yml"]
        != snap2["config_hashes"]["monitoring/docker-compose.yml"]
    )


def test_build_snapshot_lists_are_sorted():
    docs = _make_docs()
    # Add a second container that should sort before grafana
    docs.append(
        {
            "file_path": "lab://docker/containers/alertmanager",
            "category": "lab-state",
            "content": "Docker container: alertmanager",
            "metadata": {"image": "prom/alertmanager:latest", "ports": ""},
        }
    )
    snap = build_snapshot(docs)
    names = [c["name"] for c in snap["containers"]]
    assert names == sorted(names)


def test_write_snapshot_creates_file(tmp_path):
    path = tmp_path / "knowledge" / "harvest_snapshot.json"
    data = {"harvested_at": "2026-03-01T03:00:00", "containers": []}
    write_snapshot(path, data)
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["harvested_at"] == "2026-03-01T03:00:00"


def test_write_snapshot_trailing_newline(tmp_path):
    path = tmp_path / "snap.json"
    write_snapshot(path, {"x": 1})
    assert path.read_text().endswith("\n")
