"""Coverage ratchet — update .coverage-threshold to the current coverage floor.

Runs pytest with --cov to measure coverage, then:
- If coverage >= current threshold, updates the file to the new value.
- If coverage < current threshold, prints a warning and exits non-zero.

Usage:
    make ratchet
    # or directly:
    python scripts/update_coverage_threshold.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

THRESHOLD_FILE = Path(__file__).resolve().parent.parent / ".coverage-threshold"


def _read_threshold() -> int:
    """Read current threshold from .coverage-threshold."""
    if not THRESHOLD_FILE.exists():
        return 0
    text = THRESHOLD_FILE.read_text().strip()
    return int(text) if text else 0


def _run_coverage() -> int | None:
    """Run pytest with --cov and parse the TOTAL line for coverage %."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--ignore=tests/test_intent.py",
            "--cov=hal",
            "--cov-report=term-missing",
            "-q",
            "--no-header",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
    )
    # Look for the TOTAL line: "TOTAL  3127  1031  67%"
    for line in result.stdout.splitlines():
        if line.startswith("TOTAL"):
            parts = line.split()
            for part in parts:
                if part.endswith("%"):
                    return int(part.rstrip("%"))
    return None


def main() -> None:
    current = _read_threshold()
    print(f"Current threshold: {current}%")

    measured = _run_coverage()
    if measured is None:
        print("ERROR: Could not parse coverage from pytest output.", file=sys.stderr)
        sys.exit(1)

    print(f"Measured coverage: {measured}%")

    if measured > current:
        THRESHOLD_FILE.write_text(f"{measured}\n")
        print(f"Ratchet updated: {current}% → {measured}%")
    elif measured == current:
        print("Coverage unchanged — threshold stays the same.")
    else:
        print(
            f"WARNING: Coverage dropped from {current}% to {measured}%. "
            "Threshold NOT updated (ratchet holds).",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
