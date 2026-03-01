#!/usr/bin/env python3
"""Doc-drift detector: fails if documented facts don't match code reality.

Checks that files/symbols referenced in documentation actually exist,
and that docs are updated when hal/ modules are added or removed.
"""

from __future__ import annotations

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
    "intent.py",
    "judge.py",
    "knowledge.py",
    "llm.py",
    "logging_utils.py",
    "main.py",
    "memory.py",
    "postmortem.py",
    "prometheus.py",
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


def check_file_existence() -> list[str]:
    """Check that every documented code path actually exists."""
    errors = []
    for doc, desc, code_path in FILE_EXISTENCE_RULES:
        if not (ROOT / code_path).exists():
            errors.append(
                f"  {doc} references {code_path} ({desc}) but file does not exist"
            )
    return errors


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

    for mod in sorted(added):
        errors.append(
            f"  hal/{mod} exists but is not in DOCUMENTED_HAL_MODULES — "
            "add to docs or update check_doc_drift.py"
        )
    for mod in sorted(removed):
        errors.append(
            f"  hal/{mod} is documented but no longer exists — "
            "remove from docs and update check_doc_drift.py"
        )
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(check_file_existence())
    errors.extend(check_hal_module_drift())

    if errors:
        print("Doc-drift detected:\n")
        print("\n".join(errors))
        print(f"\n{len(errors)} issue(s) found.")
        return 1

    print("Doc-drift check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
