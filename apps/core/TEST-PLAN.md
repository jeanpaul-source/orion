<!-- markdownlint-disable MD013 MD036 -->

# ORION Core - Test Plan

**Last Updated:** November 22, 2025

This document provides a plain-language overview of ORION Core's testing strategy. You don't need to be a programmer to understand this - it's written for everyone!

---

## Overview

ORION Core has three types of tests:

1. **Unit Tests** - Test individual functions in isolation
2. **Integration Tests** - Test how components work together
3. **End-to-End (E2E) Tests** - Test complete user workflows

Each type serves a different purpose and helps ensure the system works correctly.

---

## Test Types in Plain English

### Unit Tests

**What:** Tests that check a single piece of code works correctly on its own.

**Example:** Testing that when you give the router the message "Check disk space", it correctly identifies this as an "action" intent.

**Speed:** Very fast (milliseconds)

**When to add:** When you have a specific function or method that needs verification.

---

### Integration Tests

**What:** Tests that check multiple parts working together, like testing an API endpoint.

**Example:** Testing that when you call the `/health` endpoint, you get back a response with status code 200 and the correct information.

**Speed:** Fast (seconds)

**When to add:** When you want to verify an API endpoint works correctly or multiple components interact properly.

---

### End-to-End Tests

**What:** Tests that simulate real user scenarios from start to finish.

**Example:** Opening a WebSocket connection, sending a chat message, and verifying you get a response back.

**Speed:** Slower (may take minutes if connecting to real services)

**When to add:** When you want to test a complete workflow as a user would experience it.

---

## Running Tests

Copy and paste these commands into your terminal:

### Run all tests

```bash
cd /home/jp/Laptop-MAIN/applications/orion-core
pytest
```

### Run only unit tests

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

### Run with detailed output

```bash
pytest -v
```

### Run with coverage report

```bash
pytest --cov=src --cov-report=html
```

---

## Complete Test Inventory

**Total: 214 tests across all categories**

### 📂 Tests Organization

```
tests/
├── unit/                          # 7 tests - Fast, isolated function tests
│   └── test_router_fallback.py   # Intent classification logic
│
├── integration/                   # 9 tests - API endpoint tests
│   ├── test_health.py             # Health endpoint (5 tests)
│   └── test_api_knowledge_stats.py # Knowledge stats API (4 tests)
│
├── e2e/                           # 0 tests - Full user workflow tests
│   └── (empty - ready for future tests)
│
└── (root level tests)             # 198 tests - Comprehensive system tests
    ├── test_router.py             # Router comprehensive tests
    ├── test_knowledge_subsystem.py # Knowledge subsystem tests
    ├── test_action_subsystem.py   # Action subsystem tests
    ├── test_learning_subsystem.py # Learning subsystem tests
    ├── test_watch_subsystem.py    # Watch subsystem tests
    ├── test_streaming.py          # WebSocket streaming tests
    ├── test_system_prompt.py      # System prompt tests
    ├── test_chaos.py              # Resilience/chaos tests
    ├── test_websocket_e2e.py      # WebSocket E2E tests
    ├── test_chat_streaming_e2e.py # Chat streaming E2E tests
    ├── test_command_palette_e2e.py # Command palette E2E tests
    └── test_app_integration_e2e.py # Full app integration tests
```

### ✅ Your Recent Test Files (November 22, 2025)

These are the **new** tests we just created together:

| File | Location | Tests | Status |
|------|----------|-------|--------|
| `test_router_fallback.py` | `tests/unit/` | 7 | ✅ All passing |
| `test_health.py` | `tests/integration/` | 5 | ✅ All passing |
| `test_api_knowledge_stats.py` | `tests/integration/` | 4 | ✅ All passing |

**Total new tests: 16 (all passing!)**

### 📊 Complete Feature Coverage

#### **Core API Endpoints**

| Feature | Test File | Location | Tests | Status |
|---------|-----------|----------|-------|--------|
| Health endpoint | `test_health.py` | `integration/` | 5 | ✅ Complete |
| Knowledge stats API | `test_api_knowledge_stats.py` | `integration/` | 4 | ✅ Complete |

#### **Routing & Intent Classification**

| Feature | Test File | Location | Tests | Status |
|---------|-----------|----------|-------|--------|
| Fallback intent classifier | `test_router_fallback.py` | `unit/` | 7 | ✅ Complete |
| Full router with LLM | `test_router.py` | `root/` | 30+ | ✅ Complete |

#### **Subsystems**

| Subsystem | Test File | Location | Tests | Status |
|-----------|-----------|----------|-------|--------|
| Knowledge (RAG) | `test_knowledge_subsystem.py` | `root/` | 35+ | ✅ Complete |
| Action (DevOps) | `test_action_subsystem.py` | `root/` | 22+ | ✅ Complete |
| Learning (Self-teaching) | `test_learning_subsystem.py` | `root/` | 15+ | ✅ Complete |
| Watch (Monitoring) | `test_watch_subsystem.py` | `root/` | 18+ | ✅ Complete |

#### **WebSocket & Streaming**

| Feature | Test File | Location | Tests | Status |
|---------|-----------|----------|-------|--------|
| WebSocket connection | `test_websocket_e2e.py` | `root/` | 6+ | ✅ Complete |
| Chat streaming | `test_chat_streaming_e2e.py` | `root/` | 7+ | ✅ Complete |
| Streaming protocol | `test_streaming.py` | `root/` | 15+ | ✅ Complete |

#### **UI Components**

| Feature | Test File | Location | Tests | Status |
|---------|-----------|----------|-------|--------|
| Command palette | `test_command_palette_e2e.py` | `root/` | 8+ | ✅ Complete |
| Full app integration | `test_app_integration_e2e.py` | `root/` | 8+ | ✅ Complete |

#### **System Resilience**

| Feature | Test File | Location | Tests | Status |
|---------|-----------|----------|-------|--------|
| Chaos engineering | `test_chaos.py` | `root/` | 12+ | ✅ Complete |
| System prompts | `test_system_prompt.py` | `root/` | 13+ | ✅ Complete |

---

## Test Coverage Goals

- **Unit Tests:** Aim for 80%+ coverage of core logic
- **Integration Tests:** Cover all API endpoints
- **E2E Tests:** Cover critical user workflows

---

## Adding New Tests

When a new feature is added, follow this process:

1. **Identify what needs testing** - What functionality was added?
2. **Choose the test type** - Unit, integration, or E2E?
3. **Write a descriptive test name** - Like `test_knowledge_query_returns_citations()`
4. **Update this document** - Add the new test to the mapping table above

---

## Test Naming Conventions

- **Files:** `test_<feature>.py` (e.g., `test_router_fallback.py`)
- **Functions:** `test_<behavior>()` (e.g., `test_fallback_classifies_action_intent()`)
- **Be descriptive:** The name should explain what's being tested

---

## Continuous Integration

Tests should be run:

- **Before committing** - Ensure your changes don't break existing functionality
- **In CI/CD pipeline** - Automated testing on every push
- **Before deployment** - Final verification before going live

---

## Need Help?

- Don't understand a test failure? Ask for help interpreting the error message
- Want to add a new test? Describe in plain English what you want to verify
- Tests running slow? We can help optimize them

**Remember:** Tests are your safety net. They catch problems before users do!
