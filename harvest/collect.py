"""Collectors — gather real lab state from local system.
Runs on the server where everything is localhost.
Each collector returns a list of Document dicts ready for ingestion.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path


def _run(cmd: str) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text()
    except (OSError, PermissionError):
        return None


# --- helpers ---

def _doc(file_path: str, file_name: str, category: str, content: str, metadata: dict = None) -> dict:
    return {
        "file_path": file_path,
        "file_name": file_name,
        "category": category,
        "content": content.strip(),
        "metadata": metadata or {},
    }


# --- collectors ---

def collect_docker_containers() -> list[dict]:
    """One doc per running container with full context."""
    raw = _run("docker ps --format '{{json .}}'")
    if not raw:
        return []

    docs = []
    for line in raw.splitlines():
        try:
            c = json.loads(line)
        except json.JSONDecodeError:
            continue

        name = c.get("Names", "unknown")
        image = c.get("Image", "")
        ports = c.get("Ports", "none")
        status = c.get("Status", "")
        networks = c.get("Networks", "")

        # Get mount/volume info
        mounts = _run(f"docker inspect {name} --format '{{{{range .Mounts}}}}{{{{.Type}}}}:{{{{.Source}}}}->{{{{.Destination}}}} {{{{end}}}}'")

        content = f"""Docker container: {name}
  Image:    {image}
  Status:   {status}
  Ports:    {ports}
  Networks: {networks}
  Mounts:   {mounts or 'none'}"""

        docs.append(_doc(
            file_path=f"lab://docker/containers/{name}",
            file_name=f"container:{name}",
            category="lab-state",
            content=content,
            metadata={"image": image, "ports": ports},
        ))

    return docs


def collect_system_state() -> list[dict]:
    """Disk, memory, listening ports, running services."""
    docs = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Disk
    disk = _run("df -h --output=target,size,used,avail,pcent | grep -v tmpfs | grep -v 'Filesystem'")
    docs.append(_doc(
        file_path="lab://state/disk",
        file_name="system:disk",
        category="lab-state",
        content=f"Disk usage (as of {ts}):\n{disk}",
    ))

    # Memory
    mem = _run("free -h")
    swap_info = _run("free -m | grep Swap")
    swap_warn = ""
    try:
        parts = swap_info.split()
        total, used = int(parts[1]), int(parts[2])
        if total > 0 and (used / total) > 0.8:
            swap_warn = f"\nWARNING: swap {used}M/{total}M used ({used*100//total}%) — investigate despite free RAM"
    except (IndexError, ValueError, ZeroDivisionError):
        pass

    docs.append(_doc(
        file_path="lab://state/memory",
        file_name="system:memory",
        category="lab-state",
        content=f"Memory usage (as of {ts}):\n{mem}{swap_warn}",
    ))

    # Listening ports (non-loopback)
    ports = _run("ss -tlnp | grep -v '127.0.0.1\\|::1\\|State'")
    docs.append(_doc(
        file_path="lab://state/ports",
        file_name="system:ports",
        category="lab-state",
        content=f"Listening ports on all interfaces (as of {ts}):\n{ports}",
    ))

    # Running systemd services (non-kernel)
    services = _run(
        "systemctl list-units --type=service --state=running --no-pager --plain "
        "| grep -v '●' | awk '{print $1, $3, $4}' | grep -v '^$'"
    )
    docs.append(_doc(
        file_path="lab://state/services",
        file_name="system:services",
        category="lab-state",
        content=f"Running systemd services (as of {ts}):\n{services}",
    ))

    # Ollama models
    models = _run("curl -s http://localhost:11434/api/tags | python3 -c \"import json,sys; d=json.load(sys.stdin); [print(m['name'], m['size']) for m in d['models']]\" 2>/dev/null")
    if models:
        docs.append(_doc(
            file_path="lab://state/ollama-models",
            file_name="system:ollama-models",
            category="lab-state",
            content=f"Ollama models available (as of {ts}):\n{models}",
        ))

    return docs


def collect_hardware() -> list[dict]:
    """Static hardware info — rarely changes."""
    cpu = _run("lscpu | grep -E 'Model name|CPU\\(s\\)|Thread|Socket|MHz'")
    mem_total = _run("grep MemTotal /proc/meminfo")
    gpu = _run("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null || echo 'nvidia-smi not available'")
    kernel = _run("uname -r")
    os_info = _run("cat /etc/os-release | grep -E '^NAME|^VERSION='")
    storage = _run("lsblk -d -o NAME,SIZE,MODEL,TYPE | grep disk")

    content = f"""Lab hardware: the-lab (192.168.5.10)

OS: {os_info}
Kernel: {kernel}

CPU:
{cpu}

Memory: {mem_total}

GPU:
{gpu}

Storage:
{storage}
"""
    return [_doc(
        file_path="lab://hardware/summary",
        file_name="hardware:summary",
        category="lab-infrastructure",
        content=content,
    )]


def collect_config_files() -> list[dict]:
    """Read actual config files from /opt/homelab-infrastructure/."""
    docs = []
    base = Path("/opt/homelab-infrastructure")

    configs = [
        ("monitoring-stack/docker-compose.yml",   "lab-infrastructure"),
        ("monitoring-stack/prometheus.yml",        "lab-infrastructure"),
        ("pgvector-kb/docker-compose.yml",         "lab-infrastructure"),
        ("agent-zero/docker-compose.yml",          "lab-infrastructure"),
    ]

    for rel_path, category in configs:
        full_path = base / rel_path
        content = _read(str(full_path))
        if not content:
            continue
        docs.append(_doc(
            file_path=str(full_path),
            file_name=full_path.name,
            category=category,
            content=f"# {full_path}\n\n{content}",
            metadata={"source_path": str(full_path)},
        ))

    # README if present
    readme = _read(str(base / "README.md"))
    if readme:
        docs.append(_doc(
            file_path=str(base / "README.md"),
            file_name="README.md",
            category="lab-infrastructure",
            content=readme,
        ))

    return docs


def collect_systemd_units() -> list[dict]:
    """Read key systemd unit files."""
    docs = []
    units = ["ollama.service", "pgvector-kb-api.service"]

    for unit in units:
        content = _run(f"systemctl cat {unit} 2>/dev/null")
        if not content:
            continue
        docs.append(_doc(
            file_path=f"lab://systemd/{unit}",
            file_name=unit,
            category="lab-infrastructure",
            content=f"systemd unit: {unit}\n\n{content}",
        ))

    return docs


def collect_all() -> list[dict]:
    collectors = [
        ("docker containers", collect_docker_containers),
        ("system state",      collect_system_state),
        ("hardware",          collect_hardware),
        ("config files",      collect_config_files),
        ("systemd units",     collect_systemd_units),
    ]
    all_docs = []
    for name, fn in collectors:
        try:
            docs = fn()
            all_docs.extend(docs)
            print(f"  collected {name}: {len(docs)} documents")
        except Exception as e:
            print(f"  WARNING: {name} collector failed: {e}")
    return all_docs
