"""Build and write a point-in-time lab snapshot for temporal diff queries.

The snapshot is a single JSON file (knowledge/harvest_snapshot.json) committed
to git on each successful harvest run.  Git history becomes the diff layer —
'what changed since Tuesday?' is answered with:

    git diff HEAD@{2026-03-10} -- knowledge/harvest_snapshot.json
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def build_snapshot(
    docs: list[dict],
    infra_base: str = "/opt/homelab-infrastructure",
) -> dict:
    """Derive a structured snapshot from collected docs.

    Uses the same *docs* list that was ingested — no second collection pass.
    Containers, services, disks, ports, and models are parsed from content/
    metadata.  Config files are represented as SHA-256 hashes (first 16 hex
    chars) so changes are visible in the diff without embedding full YAML.
    All list fields are sorted for stable diffs.
    """
    snapshot: dict = {
        "harvested_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "containers": [],
        "services": [],
        "disks": [],
        "ports": [],
        "ollama_models": [],
        "config_hashes": {},
        "systemd_units": [],
    }

    infra_path = Path(infra_base)

    for doc in docs:
        fp = doc.get("file_path", "")
        category = doc.get("category", "")
        content = doc.get("content", "")
        metadata = doc.get("metadata", {})

        # --- live-state docs ---

        if fp.startswith("lab://docker/containers/"):
            name = fp.removeprefix("lab://docker/containers/")
            image = metadata.get("image", "")
            snapshot["containers"].append({"name": name, "image": image})

        elif fp == "lab://state/services":
            snapshot["services"] = _parse_services(content)

        elif fp == "lab://state/disk":
            snapshot["disks"] = _parse_disks(content)

        elif fp == "lab://state/ports":
            snapshot["ports"] = _parse_ports(content)

        elif fp == "lab://state/ollama-models":
            snapshot["ollama_models"] = _parse_models(content)

        # --- infrastructure docs (config files with real file paths) ---

        elif category == "lab-infrastructure" and metadata.get("source_path"):
            src = Path(metadata["source_path"])
            try:
                rel = src.relative_to(infra_path)
                key = str(rel)
            except ValueError:
                key = src.name
            h = hashlib.sha256(content.encode()).hexdigest()[:16]
            snapshot["config_hashes"][key] = h

        # --- systemd unit docs ---

        elif fp.startswith("lab://systemd/"):
            unit = fp.removeprefix("lab://systemd/")
            snapshot["systemd_units"].append(unit)

    # Sort everything so git diffs are line-level and stable
    snapshot["containers"].sort(key=lambda c: c["name"])
    snapshot["services"].sort()
    snapshot["disks"].sort(key=lambda d: d["mount"])
    snapshot["ports"].sort()
    snapshot["ollama_models"].sort()
    snapshot["config_hashes"] = dict(sorted(snapshot["config_hashes"].items()))
    snapshot["systemd_units"].sort()

    return snapshot


def write_snapshot(path: Path, data: dict) -> None:
    """Serialise *data* to *path* as indented JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Private parsers — each strips the prose header line that collect.py adds
# ---------------------------------------------------------------------------


def _parse_services(content: str) -> list[str]:
    """Extract *.service names from systemctl list-units output."""
    services = []
    for line in content.splitlines():
        if not line.strip() or line.startswith("Running systemd"):
            continue
        name = line.split()[0]
        if name.endswith(".service"):
            services.append(name)
    return services


def _parse_disks(content: str) -> list[dict]:
    """Parse df -h --output=target,size,used,avail,pcent output."""
    disks = []
    for line in content.splitlines():
        if not line.strip() or line.startswith("Disk usage"):
            continue
        parts = line.split()
        if len(parts) >= 5:
            disks.append(
                {
                    "mount": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "avail": parts[3],
                    "pcent": parts[4],
                }
            )
    return disks


def _parse_ports(content: str) -> list[str]:
    """Extract unique local-address:port strings from ss -tlnp output."""
    ports = set()
    for line in content.splitlines():
        if not line.strip() or line.startswith("Listening ports"):
            continue
        # ss columns: State Recv-Q Send-Q Local_Address:Port Peer_Address:Port …
        parts = line.split()
        if len(parts) >= 4:
            ports.add(parts[3])
    return sorted(ports)


def _parse_models(content: str) -> list[str]:
    """Extract model names (first token per line) from Ollama models output."""
    models = []
    for line in content.splitlines():
        if not line.strip() or line.startswith("Ollama models"):
            continue
        name = line.split()[0]
        if name:
            models.append(name)
    return models
