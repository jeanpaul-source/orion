# ORION Core Tests - User Guide

**You do NOT need to understand Python code to use these tests!**

This guide explains the test structure in plain English and shows you how to run tests from the terminal.

---

## Test Types Explained

### Unit Tests (tests/unit/)

**What they are:**

- Tests for individual pieces of code in isolation
- Check that a single function or method works correctly on its own
- Do NOT connect to real services (no databases, no APIs, no external systems)

**Examples:**

- Testing that the router can classify a message like "Check disk space" as an "action" intent
- Testing that a configuration parser correctly reads settings
- Testing that a utility function formats dates properly

**When to add them:**

- When you want to verify a specific function works correctly
- When you need to test logic that doesn't require real services
- When you want fast tests that run in milliseconds

---

### Integration Tests (tests/integration/)

**What they are:**

- Tests that check how different parts of the application work together
- May use the FastAPI test client to simulate HTTP requests
- Still avoid real external services, but test the full request/response flow

**Examples:**

- Testing that the `/health` endpoint returns the correct status
- Testing that the `/api/status` endpoint combines data from multiple subsystems
- Testing that the chat endpoint handles messages properly (without actually calling the real LLM)

**When to add them:**

- When you want to test a complete API endpoint
- When you need to verify that multiple components work together
- When you want to ensure the application responds correctly to HTTP requests

---

### End-to-End Tests (tests/e2e/)

**What they are:**

- Tests that simulate real user scenarios from start to finish
- May connect to actual services (if configured)
- Test the complete system as a user would experience it

**Examples:**

- Starting a WebSocket chat session and sending real messages
- Testing the full knowledge query flow (from browser → backend → Qdrant → response)
- Testing the complete learning workflow (query → harvest → process → embed)

**When to add them:**

- When you want to test complete user workflows
- When you need to verify the system works with real dependencies
- When you want to catch integration issues between services

---

## Running Tests

You can run tests from the terminal using simple commands. You don't need to understand what they do - just copy
and paste them!

### Run all tests

```bash
cd /home/jp/Laptop-MAIN/applications/orion-core
pytest
```

### Run only unit tests (fast)

```bash
pytest tests/unit
```

### Run only integration tests

```bash
pytest tests/integration
```

### Run only end-to-end tests

```bash
pytest tests/e2e
```

### Run with more detail (verbose)

```bash
pytest -v
```

### Run a specific test file

```bash
pytest tests/integration/test_health.py
```

---

## What Tests Look For

Tests check things like:

- **Does the endpoint return a 200 status code?** (success)
- **Does the response have the expected fields?** (like "status", "app", "version")
- **Does the function return the right value?** (like classifying "Check disk space" as "action")
- **Does the system handle errors gracefully?** (like when a service is down)

---

## Reading Test Results

When you run tests, you'll see output like this:

```
tests/unit/test_router_fallback.py ....                     [100%]
tests/integration/test_health.py .                          [100%]

================= 5 passed in 0.23s =================
```

- **Green dots (.) or "passed"** = Test succeeded ✓
- **Red F or "failed"** = Test failed ✗
- **Yellow s or "skipped"** = Test was skipped

---

## Need Help?

- If tests fail, read the error message - it usually tells you what went wrong
- You can ask for help interpreting test failures
- You can request new tests by describing what you want to check in plain English

**Remember:** You don't need to write or understand Python to benefit from these tests. Just run them and read the results!
