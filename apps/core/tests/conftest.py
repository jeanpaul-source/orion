"""
pytest configuration for ORION Core tests.

Sets up test environment with proper paths and mocks.
"""

# IMPORTANT: Set environment variables BEFORE any imports
# This is because src/config.py creates a global config instance at module level
import tempfile
import os
from pathlib import Path

# Create temporary directory for test data
TEST_DATA_DIR = tempfile.mkdtemp(prefix="orion_test_")

# Set environment variables for test paths BEFORE importing src modules
os.environ["ORION_DATA_DIR"] = TEST_DATA_DIR
os.environ["ORION_LOGS_DIR"] = str(Path(TEST_DATA_DIR) / "logs")
os.environ["ORION_CACHE_DIR"] = str(Path(TEST_DATA_DIR) / "cache")

# Set test environment
os.environ["ORION_ENVIRONMENT"] = "test"

# Disable external services for unit tests (can be overridden in integration tests)
os.environ["ORION_ENABLE_KNOWLEDGE"] = "false"
os.environ["ORION_ENABLE_ACTION"] = "false"
os.environ["ORION_ENABLE_LEARNING"] = "false"
os.environ["ORION_ENABLE_WATCH"] = "false"

import pytest  # noqa: E402 - Must import after setting env vars


# ============================================================================
# E2E Test Fixtures (Playwright)
# ============================================================================


@pytest.fixture(scope="session")
def base_url() -> str:
    """
    Base URL for E2E tests.

    Defaults to localhost:5000.
    Can be overridden with ORION_TEST_URL environment variable.
    """
    return os.getenv("ORION_TEST_URL", "http://localhost:5000")


import pytest  # noqa: E402


@pytest.fixture
def temp_data_dir():
    """Provide temporary data directory for tests that need it."""
    return Path(TEST_DATA_DIR)
