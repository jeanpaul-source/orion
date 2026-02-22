"""
Real Integration Tests for ORION Core

These tests call ACTUAL external services without mocks.
They require:
- Services running (docker compose up -d)
- Valid API keys configured
- Network connectivity

These tests will FAIL if:
- Services are not running
- Configuration is wrong
- Knowledge base is empty (expected after Nov 17, 2025)

Run with: pytest tests/real_integration/ -v --tb=short
"""
