"""Collectors — gather real lab state from local system.
Runs on the server where everything is localhost.
Each collector returns a list of Document dicts ready for ingestion.
"""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def _run(cmd: str) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)  # noqa: S602 -- all callers pass hardcoded command strings, never user input
    return result.stdout.strip()


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text()
    except (OSError, PermissionError):
        return None


# --- helpers ---


def _doc(
    file_path: str,
    file_name: str,
    category: str,
    content: str,
    metadata: dict | None = None,
    doc_tier: str = "reference",
) -> dict:
    return {
        "file_path": file_path,
        "file_name": file_name,
        "category": category,
        "content": content.strip(),
        "metadata": metadata or {},
        "doc_tier": doc_tier,
    }


# --- collectors ---


def collect_ground_truth() -> list[dict]:
    """Ingest hand-written ground-truth docs from the knowledge/ directory.

    These are the highest-priority documents — the user's own description
    of their lab, goals, and constraints.  They live in the git repo and
    travel with push/pull.
    """
    repo_root = Path(__file__).resolve().parent.parent
    knowledge_dir = repo_root / "knowledge"

    if not knowledge_dir.exists():
        return []

    docs = []
    for file_path in sorted(knowledge_dir.rglob("*.md")):
        if not file_path.is_file() or file_path.name == "README.md":
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not content.strip():
            continue
        docs.append(
            _doc(
                file_path=str(file_path),
                file_name=file_path.name,
                category="ground-truth",
                content=content,
                metadata={"source_path": str(file_path)},
                doc_tier="ground-truth",
            )
        )
    return docs


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

        # Get mount/volume info (never shell=True — name comes from docker ps)
        try:
            mounts = subprocess.run(  # noqa: S603 -- name comes from docker ps output, not user input
                [  # noqa: S607 -- known binary, PATH controlled
                    "docker",
                    "inspect",
                    name,
                    "--format",
                    "{{range .Mounts}}{{.Type}}:{{.Source}}->{{.Destination}} {{end}}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
        except Exception:
            mounts = ""

        content = f"""Docker container: {name}
  Image:    {image}
  Status:   {status}
  Ports:    {ports}
  Networks: {networks}
  Mounts:   {mounts or "none"}"""

        docs.append(
            _doc(
                file_path=f"lab://docker/containers/{name}",
                file_name=f"container:{name}",
                category="lab-state",
                content=content,
                metadata={"image": image, "ports": ports},
                doc_tier="live-state",
            )
        )

    return docs


def collect_system_state(ollama_host: str = "http://localhost:11434") -> list[dict]:
    """Disk, memory, listening ports, running services."""
    docs = []
    ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M")

    # Disk
    disk = _run(
        "df -h --output=target,size,used,avail,pcent | grep -v tmpfs | grep -v 'Filesystem'"
    )
    docs.append(
        _doc(
            file_path="lab://state/disk",
            file_name="system:disk",
            category="lab-state",
            content=f"Disk usage (as of {ts}):\n{disk}",
            doc_tier="live-state",
        )
    )

    # Memory
    mem = _run("free -h")
    swap_info = _run("free -m | grep Swap")
    swap_warn = ""
    try:
        parts = swap_info.split()
        total, used = int(parts[1]), int(parts[2])
        if total > 0 and (used / total) > 0.8:
            swap_warn = f"\nWARNING: swap {used}M/{total}M used ({used * 100 // total}%) — investigate despite free RAM"
    except (IndexError, ValueError, ZeroDivisionError):
        pass

    docs.append(
        _doc(
            file_path="lab://state/memory",
            file_name="system:memory",
            category="lab-state",
            content=f"Memory usage (as of {ts}):\n{mem}{swap_warn}",
            doc_tier="live-state",
        )
    )

    # Listening ports (non-loopback)
    ports = _run("ss -tlnp | grep -v '127.0.0.1\\|::1\\|State'")
    docs.append(
        _doc(
            file_path="lab://state/ports",
            file_name="system:ports",
            category="lab-state",
            content=f"Listening ports on all interfaces (as of {ts}):\n{ports}",
            doc_tier="live-state",
        )
    )

    # Running systemd services (non-kernel)
    services = _run(
        "systemctl list-units --type=service --state=running --no-pager --plain "
        "| grep -v '●' | awk '{print $1, $3, $4}' | grep -v '^$'"
    )
    docs.append(
        _doc(
            file_path="lab://state/services",
            file_name="system:services",
            category="lab-state",
            content=f"Running systemd services (as of {ts}):\n{services}",
            doc_tier="live-state",
        )
    )

    # Ollama models
    models = _run(
        f"curl -s {ollama_host}/api/tags | python3 -c \"import json,sys; d=json.load(sys.stdin); [print(m['name'], m['size']) for m in d['models']]\" 2>/dev/null"
    )
    if models:
        docs.append(
            _doc(
                file_path="lab://state/ollama-models",
                file_name="system:ollama-models",
                category="lab-state",
                content=f"Ollama models available (as of {ts}):\n{models}",
                doc_tier="live-state",
            )
        )

    return docs


def collect_hardware() -> list[dict]:
    """Static hardware info — rarely changes."""
    cpu = _run("lscpu | grep -E 'Model name|CPU\\(s\\)|Thread|Socket|MHz'")
    mem_total = _run("grep MemTotal /proc/meminfo")
    gpu = _run(
        "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null || echo 'nvidia-smi not available'"
    )
    kernel = _run("uname -r")
    os_info = _run("cat /etc/os-release | grep -E '^NAME|^VERSION='")
    storage = _run("lsblk -d -o NAME,SIZE,MODEL,TYPE | grep disk")

    content = f"""Lab hardware

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
    return [
        _doc(
            file_path="lab://hardware/summary",
            file_name="hardware:summary",
            category="lab-infrastructure",
            content=content,
            doc_tier="live-state",
        )
    ]


def collect_config_files(
    infra_base: str = "/opt/homelab-infrastructure",
) -> list[dict]:
    """Read config files from the infra base directory.

    Discovers docker-compose.yml and prometheus.yml files via glob so new
    stacks are picked up automatically without source changes.
    """
    docs = []
    base = Path(infra_base)

    # Discover compose + prometheus configs under any subdirectory
    config_globs = ["*/docker-compose.yml", "*/prometheus.yml"]
    found: list[Path] = []
    for pattern in config_globs:
        found.extend(sorted(base.glob(pattern)))

    for full_path in found:
        content = _read(str(full_path))
        if not content:
            continue
        docs.append(
            _doc(
                file_path=str(full_path),
                file_name=full_path.name,
                category="lab-infrastructure",
                content=f"# {full_path}\n\n{content}",
                metadata={"source_path": str(full_path)},
                doc_tier="live-state",
            )
        )

    # README if present
    readme = _read(str(base / "README.md"))
    if readme:
        docs.append(
            _doc(
                file_path=str(base / "README.md"),
                file_name="README.md",
                category="lab-infrastructure",
                content=readme,
                doc_tier="live-state",
            )
        )

    return docs


def collect_systemd_units(
    units: tuple[str, ...] = ("ollama.service", "pgvector-kb-api.service"),
) -> list[dict]:
    """Read key systemd unit files."""
    docs = []

    for unit in units:
        content = _run(f"systemctl cat {unit} 2>/dev/null")
        if not content:
            continue
        docs.append(
            _doc(
                file_path=f"lab://systemd/{unit}",
                file_name=unit,
                category="lab-infrastructure",
                content=f"systemd unit: {unit}\n\n{content}",
                doc_tier="live-state",
            )
        )

    return docs


# Extensions that are treated as plain text for ingestion
_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".rst",
    ".conf",
    ".yaml",
    ".yml",
    ".json",
    ".sh",
    ".py",
    ".toml",
    ".ini",
}
_HTML_EXTENSIONS = {".html", ".htm"}
_PDF_EXTENSIONS = {".pdf"}
_ALL_EXTENSIONS = _TEXT_EXTENSIONS | _HTML_EXTENSIONS | _PDF_EXTENSIONS
_STATIC_DOCS_ROOT = Path("/data/orion/orion-data/documents/raw")


def collect_static_docs(root: Path = _STATIC_DOCS_ROOT) -> list[dict]:
    """Ingest pre-scraped documents from the raw documents directory.

    Each top-level subdirectory becomes a category (e.g.
    ``ai-agents-and-multi-agent-systems``).  Supports plain text, HTML
    (via trafilatura), and PDF (via pymupdf).  MIME detection from magic
    bytes catches files whose extension doesn't match their content.
    The raw files are never moved or modified.
    """
    from harvest.parsers import detect_mime, parse_html, parse_pdf

    if not root.exists():
        return []

    docs = []
    for category_dir in sorted(root.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name  # use dir name verbatim as category
        for file_path in sorted(category_dir.rglob("*")):
            if not file_path.is_file():
                continue
            ext = file_path.suffix.lower()
            if ext not in _ALL_EXTENSIONS:
                continue

            # Detect actual type (catches .html that are really PDFs)
            mime = detect_mime(file_path)

            content = None
            if mime == "application/pdf" or ext in _PDF_EXTENSIONS:
                content = parse_pdf(file_path)
            elif (
                mime in ("text/html", "application/xhtml+xml")
                or ext in _HTML_EXTENSIONS
            ):
                content = parse_html(file_path)
            elif ext in _TEXT_EXTENSIONS:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

            if not content or not content.strip():
                continue
            docs.append(
                _doc(
                    file_path=str(file_path),
                    file_name=file_path.name,
                    category=category,
                    content=f"# {file_path.name}\n\n{content}",
                    metadata={"source_path": str(file_path), "category": category},
                )
            )
    return docs


def collect_all(
    ollama_host: str = "http://localhost:11434",
    infra_base: str = "/opt/homelab-infrastructure",
    static_docs_root: str = "/data/orion/orion-data/documents/raw",
    harvest_systemd_units: str = "ollama.service pgvector-kb-api.service",
) -> list[dict]:
    units = tuple(harvest_systemd_units.split())
    collectors = [
        ("ground truth", collect_ground_truth),
        ("docker containers", collect_docker_containers),
        ("system state", lambda: collect_system_state(ollama_host)),
        ("hardware", collect_hardware),
        ("config files", lambda: collect_config_files(infra_base)),
        ("systemd units", lambda: collect_systemd_units(units)),
        ("static docs", lambda: collect_static_docs(Path(static_docs_root))),
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
