#!/usr/bin/env python3
"""Doc-drift detector: fails if documented facts don't match code reality.

Checks:
1. Files/symbols referenced in documentation actually exist on disk.
2. hal/*.py modules match a tracked set (catches add/remove without doc update).
3. Port numbers in config.py match the OPERATIONS.md services table.
4. Documented test counts haven't drifted wildly from reality.
5. Required env vars in config.py all appear in .env.example.
6. File paths in README.md key-files table exist on disk.
"""

from __future__ import annotations

import contextlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Mapping: (doc_file, description) → code_path_that_must_exist ──────
FILE_EXISTENCE_RULES: list[tuple[str, str, str]] = [
    # ARCHITECTURE.md references
    ("ARCHITECTURE.md", "intent classifier", "hal/intent.py"),
    ("ARCHITECTURE.md", "agent loop", "hal/agent.py"),
    ("ARCHITECTURE.md", "judge policy gate", "hal/judge.py"),
    ("ARCHITECTURE.md", "LLM clients", "hal/llm.py"),
    ("ARCHITECTURE.md", "memory store", "hal/memory.py"),
    ("ARCHITECTURE.md", "prometheus client", "hal/prometheus.py"),
    ("ARCHITECTURE.md", "knowledge base", "hal/knowledge.py"),
    ("ARCHITECTURE.md", "security workers", "hal/security.py"),
    ("ARCHITECTURE.md", "web search/fetch", "hal/web.py"),
    ("ARCHITECTURE.md", "config loader", "hal/config.py"),
    ("ARCHITECTURE.md", "server", "hal/server.py"),
    ("ARCHITECTURE.md", "telegram bot", "hal/telegram.py"),
    ("ARCHITECTURE.md", "falco noise filter", "hal/falco_noise.py"),
    # OPERATIONS.md references
    ("OPERATIONS.md", "server systemd unit", "ops/server.service"),
    ("OPERATIONS.md", "telegram systemd unit", "ops/telegram.service"),
    ("OPERATIONS.md", "vLLM systemd unit", "ops/vllm.service"),
    ("OPERATIONS.md", "harvest timer", "ops/harvest.timer"),
    ("OPERATIONS.md", "watchdog service", "ops/watchdog.service"),
    # README.md references
    ("README.md", "main entry point", "hal/main.py"),
    ("README.md", "harvest collector", "harvest/collect.py"),
    ("README.md", "harvest ingest", "harvest/ingest.py"),
    # CONTRIBUTING.md references
    ("CONTRIBUTING.md", "test suite", "tests/conftest.py"),
    ("CONTRIBUTING.md", "pyproject config", "pyproject.toml"),
]

# ── Documented hal/*.py modules that must match reality ───────────────
DOCUMENTED_HAL_MODULES = {
    "agent.py",
    "bootstrap.py",
    "config.py",
    "executor.py",
    "falco_noise.py",
    "healthcheck.py",
    "intent.py",
    "judge.py",
    "knowledge.py",
    "llm.py",
    "logging_utils.py",
    "main.py",
    "memory.py",
    "notify.py",
    "playbooks.py",
    "postmortem.py",
    "prometheus.py",
    "sandbox.py",
    "sanitize.py",
    "security.py",
    "server.py",
    "telegram.py",
    "tools.py",
    "tracing.py",
    "trust_metrics.py",
    "tunnel.py",
    "watchdog.py",
    "web.py",
    "workers.py",
}

# ── Port numbers: (config_var_pattern, expected_port, service_label) ──
# Each entry maps a variable name in config.py to the port that OPERATIONS.md
# and ARCHITECTURE.md should agree on.
PORT_RULES: list[tuple[str, int, str]] = [
    ("VLLM_URL", 8000, "vLLM"),
    ("OLLAMA_HOST", 11434, "Ollama"),
    ("NTOPNG_URL", 3000, "ntopng"),
    ("PROMETHEUS_URL", 9091, "Prometheus"),
]


# ── Check 0 (original): file existence ──────────────────────────────────


def check_file_existence() -> list[str]:
    """Check that every documented code path actually exists."""
    errors = []
    for doc, desc, code_path in FILE_EXISTENCE_RULES:
        if not (ROOT / code_path).exists():
            errors.append(
                f"  {doc} references {code_path} ({desc}) but file does not exist"
            )
    return errors


# ── Check 1 (original): hal module drift ────────────────────────────────


def check_hal_module_drift() -> list[str]:
    """Check for hal/*.py files added or removed without doc update."""
    errors = []
    actual = {
        p.name
        for p in (ROOT / "hal").glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    }
    added = actual - DOCUMENTED_HAL_MODULES
    removed = DOCUMENTED_HAL_MODULES - actual

    errors.extend(
        f"  hal/{mod} exists but is not in DOCUMENTED_HAL_MODULES — "
        "add to docs or update check_doc_drift.py"
        for mod in sorted(added)
    )
    errors.extend(
        f"  hal/{mod} is documented but no longer exists — "
        "remove from docs and update check_doc_drift.py"
        for mod in sorted(removed)
    )
    return errors


# ── Check 2: port numbers match between config.py and docs ──────────────


def _extract_port(url: str) -> int | None:
    """Pull the port number out of a URL string like 'http://host:8000'."""
    m = re.search(r":(\d{2,5})(?:/|$)", url)
    return int(m.group(1)) if m else None


def check_port_consistency() -> list[str]:
    """Verify that ports in config.py defaults match OPERATIONS.md table."""
    errors = []
    config_src = (ROOT / "hal" / "config.py").read_text()
    ops_src = (ROOT / "OPERATIONS.md").read_text()

    for var_name, expected_port, svc_label in PORT_RULES:
        # --- config.py: find the default URL for this variable ----
        #  Matches patterns like:  os.getenv("VLLM_URL", "http://localhost:8000")
        #  or _required_env("PROMETHEUS_URL") (no default — check OPERATIONS only)
        cfg_match = re.search(rf'"{var_name}"[^)]*"(https?://[^"]+)"', config_src)
        if cfg_match:
            cfg_port = _extract_port(cfg_match.group(1))
            if cfg_port is not None and cfg_port != expected_port:
                errors.append(
                    f"  config.py default for {var_name} uses port {cfg_port}, "
                    f"expected {expected_port} ({svc_label})"
                )

        # --- OPERATIONS.md: service table should list the port ----
        # The table has columns: | Service | How it runs | Port | Notes |
        # We look for a row containing the service label with a port number.
        ops_port_pattern = re.compile(
            rf"\|\s*\**{re.escape(svc_label)}\**\s*\|[^|]*\|\s*(\S+)\s*\|",
            re.IGNORECASE,
        )
        ops_match = ops_port_pattern.search(ops_src)
        if ops_match:
            ops_port = _extract_port(ops_match.group(1))
            # The port column may be just a number like "8000" — try direct int
            if ops_port is None:
                with contextlib.suppress(ValueError):
                    ops_port = int(ops_match.group(1).strip())
            if ops_port is not None and ops_port != expected_port:
                errors.append(
                    f"  OPERATIONS.md lists {svc_label} on port {ops_port}, "
                    f"expected {expected_port}"
                )

    return errors


# ── Check 3: test count sanity ──────────────────────────────────────────


def _count_test_functions(test_dir: Path) -> int:
    """Count ``def test_*`` functions across all test files.

    Uses simple text scanning (no import needed) — counts lines that start
    with ``def test_`` after stripping leading whitespace.  This is a rough
    count (may include commented-out tests) but is fast and offline.
    """
    count = 0
    for tf in sorted(test_dir.glob("test_*.py")):
        for line in tf.read_text().splitlines():
            if line.strip().startswith("def test_"):
                count += 1
    return count


def check_test_count_sanity() -> list[str]:
    """Verify documented test counts haven't drifted beyond 50% of reality.

    Scans ``def test_*`` functions across all test files and compares against
    numbers in CONTRIBUTING.md.  Catches stale counts like "558 tests" when
    reality is 881.
    """
    errors = []
    actual_count = _count_test_functions(ROOT / "tests")

    # Read CONTRIBUTING.md and find lines with "<number> tests" or
    # "<number> offline tests".  These are the claims we validate.
    contrib_src = (ROOT / "CONTRIBUTING.md").read_text()
    # Match patterns like "558 tests", "558 offline tests", "593 tests total"
    count_pattern = re.compile(r"(\d+)\s+(?:offline\s+)?tests", re.IGNORECASE)

    for m in count_pattern.finditer(contrib_src):
        documented_count = int(m.group(1))
        # Skip small numbers about a specific module (e.g. "35 intent tests")
        if documented_count < 50:
            continue
        # Flag if documented count is less than 50% of actual count.
        # This catches "558 tests" when reality is 881, without failing every
        # time someone adds a single test.
        if documented_count < actual_count * 0.5:
            errors.append(
                f"  CONTRIBUTING.md claims {documented_count} tests but "
                f"test files contain ~{actual_count} test functions "
                "— count appears stale"
            )

    return errors


# ── Check 4: required env vars appear in .env.example ────────────────────


def check_required_env_vars() -> list[str]:
    """Every _required_env() variable in config.py must appear in .env.example.

    If a developer adds a new required variable to config.py but forgets to add it
    to .env.example, new users get a cryptic RuntimeError instead of seeing the
    variable in the template.
    """
    errors = []
    config_src = (ROOT / "hal" / "config.py").read_text()
    env_example_src = (ROOT / ".env.example").read_text()

    # Find all _required_env("VAR_NAME") calls in config.py
    required_vars = set(re.findall(r'_required_env\(\s*"([A-Z_]+)"\s*\)', config_src))

    # Find all VAR_NAME= lines in .env.example (including commented-out ones)
    # Lines like: OLLAMA_HOST=..., # INFRA_BASE=...
    env_example_vars = set(
        re.findall(r"^#?\s*([A-Z_]+)=", env_example_src, re.MULTILINE)
    )

    missing = required_vars - env_example_vars
    errors.extend(
        f"  config.py requires {var} via _required_env() but "
        ".env.example does not list it — new users will get a RuntimeError"
        for var in sorted(missing)
    )

    return errors


# ── Check 5: README key-files table paths exist ─────────────────────────


def check_key_file_table() -> list[str]:
    """Verify every file path in README.md's key-files table exists on disk.

    Directories (paths ending with /) are checked with .is_dir().
    Files are checked with .exists().
    """
    errors = []
    readme_src = (ROOT / "README.md").read_text()

    # Match backtick-delimited paths in table rows: | `hal/main.py` | ...
    # Captures paths like "hal/main.py", "harvest/", "eval/", "Dockerfile"
    path_pattern = re.compile(r"\|\s*`([^`]+)`\s*\|")

    for m in path_pattern.finditer(readme_src):
        file_path = m.group(1).strip()
        # Skip paths that are clearly not filesystem paths (e.g. URLs, commands)
        if file_path.startswith("http") or " " in file_path:
            continue
        target = ROOT / file_path
        if file_path.endswith("/"):
            if not target.is_dir():
                errors.append(
                    f"  README.md key-files table lists {file_path} "
                    "but directory does not exist"
                )
        else:
            if not target.exists():
                errors.append(
                    f"  README.md key-files table lists {file_path} "
                    "but file does not exist"
                )

    return errors


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> int:
    errors: list[str] = []
    errors.extend(check_file_existence())
    errors.extend(check_hal_module_drift())
    errors.extend(check_port_consistency())
    errors.extend(check_test_count_sanity())
    errors.extend(check_required_env_vars())
    errors.extend(check_key_file_table())

    if errors:
        print("Doc-drift detected:\n")
        print("\n".join(errors))
        print(f"\n{len(errors)} issue(s) found.")
        return 1

    print("Doc-drift check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
