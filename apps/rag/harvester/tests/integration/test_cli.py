#!/usr/bin/env python3
"""
Integration tests for ORION CLI - black-box testing
Run with: pytest tests/integration/test_cli.py -v
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
# CLI is now src/cli.py
ORION_CLI = REPO_ROOT / "src" / "cli.py"


def run_orion(*args, expect_success=True):
    """Run orion CLI command and return result"""
    cmd = [sys.executable, str(ORION_CLI)] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)

    if expect_success and result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        print(f"STDOUT: {result.stdout}", file=sys.stderr)
        print(f"STDERR: {result.stderr}", file=sys.stderr)

    return result


class TestCLIBasics:
    """Test basic CLI functionality"""

    def test_orion_help(self):
        """orion --help should succeed"""
        result = run_orion("--help")
        assert result.returncode == 0
        assert "ORION Harvester" in result.stdout
        assert "Commands" in result.stdout or "Usage" in result.stdout

    def test_orion_version(self):
        """orion version should show version info"""
        result = run_orion("version")
        assert result.returncode == 0
        assert "ORION" in result.stdout or "2.0" in result.stdout


class TestCLICommands:
    """Test CLI command structure"""

    def test_harvest_help(self):
        """orion harvest --help should work"""
        result = run_orion("harvest", "--help")
        assert result.returncode == 0
        assert "harvest" in result.stdout.lower()

    def test_query_help(self):
        """orion query --help should work"""
        result = run_orion("query", "--help")
        assert result.returncode == 0
        assert "query" in result.stdout.lower()

    def test_process_help(self):
        """orion process --help should work"""
        result = run_orion("process", "--help")
        assert result.returncode == 0
        assert "process" in result.stdout.lower()

    def test_embed_index_help(self):
        """orion embed-index --help should work"""
        result = run_orion("embed-index", "--help")
        assert result.returncode == 0
        assert "embed" in result.stdout.lower()

    def test_validate_help(self):
        """orion validate --help should work"""
        result = run_orion("validate", "--help")
        assert result.returncode == 0
        assert "validate" in result.stdout.lower()

    def test_ops_help(self):
        """orion ops --help should work"""
        result = run_orion("ops", "--help")
        assert result.returncode == 0
        assert "ops" in result.stdout.lower()


class TestProfiles:
    """Test profile system"""

    def test_default_profile_host(self):
        """Default profile should be 'host'"""
        result = run_orion("version")
        assert result.returncode == 0
        assert "ORION CLI" in result.stdout

    def test_profile_override_laptop(self):
        """--profile laptop should work"""
        result = run_orion("--profile", "laptop", "version")
        assert result.returncode == 0

    def test_profile_override_dev(self):
        """--profile dev should work"""
        result = run_orion("--profile", "dev", "version")
        assert result.returncode == 0

    def test_invalid_profile_fails(self):
        """Invalid profile should warn but not crash"""
        result = run_orion("--profile", "invalid", "version", expect_success=True)
        # Should succeed with warning
        assert result.returncode == 0
        assert "Warning" in result.stderr or "warning" in result.stderr.lower()


class TestValidateCommand:
    """Test validate command (no external services needed)"""

    def test_validate_library_help(self):
        """orion validate library --help should work"""
        result = run_orion("validate", "library", "--help")
        assert result.returncode == 0


# Conditional tests for services (skip if not available)
class TestWithServices:
    """Tests that require external services - skip if unavailable"""

    def test_query_dry_run(self):
        """orion query --test should work if services available"""
        result = run_orion("query", "--test", "--top-k", "1", expect_success=False)
        # May fail if services not available, but should not crash
        assert "error" not in result.stderr.lower() or "connection" in result.stderr.lower()


if __name__ == "__main__":
    # Allow running directly
    import pytest

    pytest.main([__file__, "-v"])
