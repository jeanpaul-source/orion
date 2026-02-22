# ORION Core Testing Guide

**Quick guide to running tests that actually validate your system works.**

## 🎯 TL;DR - Run Tests Now

```bash
# 1. Navigate to project
cd /home/jp/Laptop-MAIN/applications/orion-core

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Run smoke tests (fast - checks services are up)
pytest tests/smoke/ -v

# 4. Run real integration tests (slower - tests actual APIs)
pytest tests/real_integration/ -v -s
```

## 📍 Where to Run Tests

**You should run tests from your LAPTOP**, not the lab host.

```bash
# Always start here:
cd /home/jp/Laptop-MAIN/applications/orion-core

# Make sure venv is activated:
source .venv/bin/activate

# Verify you're in the right place:
pwd
# Should show: /home/jp/Laptop-MAIN/applications/orion-core
```

## 🧪 Test Types Explained

### 1. Unit Tests (Already Working ✅)

**What:** Test individual functions with mocked external services
**Speed:** Very fast (< 2 seconds)
**Purpose:** Verify code logic works

```bash
pytest tests/unit/ -v
```

These pass, but they don't prove the system works because everything is mocked.

### 2. Integration Tests (Currently Mocked ⚠️)

**What:** Test component integration (but currently with mocks)
**Speed:** Fast (< 5 seconds)
**Purpose:** Verify components work together

```bash
pytest tests/integration/ -v
```

These also pass, but they're testing mocks, not real services.

### 3. Smoke Tests (NEW! 🎉)

**What:** Quick checks that external services are reachable
**Speed:** Fast (< 10 seconds)
**Purpose:** Validate environment is ready

```bash
pytest tests/smoke/ -v
```

**Run these FIRST** before anything else. If smoke tests fail, services aren't running.

### 4. Real Integration Tests (NEW! 🔥)

**What:** Test actual API calls to real services
**Speed:** Slower (30-60 seconds)
**Purpose:** Prove the system actually works

```bash
pytest tests/real_integration/ -v -s
```

These will fail if services aren't running or configured properly. **That's good!** It shows reality.

## 🏷️ Pytest markers you can use

All ORION Core tests declare explicit [pytest markers](pytest.ini) so you can target just the suites you need.
Pytest runs with `--strict-markers`, so misspelled markers will fail fast.

| Marker | Meaning | Typical command |
| --- | --- | --- |
| `unit` | Pure Python logic with mocks, fastest validation | `pytest -m unit tests/unit/ -v` |
| `integration` | Component wiring (currently still mocked) | `pytest -m integration tests/integration/ -v` |
| `smoke` | Laptop → lab reachability checks for vLLM/Qdrant/AnythingLLM and env flags | `pytest -m smoke tests/smoke/ -v` |
| `real` | Calls live services with no mocks (lab stack **must** be running) | `pytest -m real tests/real_integration/ -v -s` |
| `asyncio` | Marks coroutine tests so pytest spins an event loop | Usually automatic, but deselect with `-m "not asyncio"` if debugging |
| `e2e` | Reserved for Playwright/browser flows | `pytest -m e2e tests/e2e/ -v` once UI tests land |
| `slow` | Expensive tests (LLM prompts, large data) | Skip with `pytest -m "not slow"` or run explicitly with `pytest -m slow` |

Quick discovery:

```bash
cd /home/jp/Laptop-MAIN/applications/orion-core
source .venv/bin/activate
pytest --markers | sed -n '1,20p'
```

This prints the authoritative definitions straight from pytest so you can keep docs and config aligned.

## 🚀 Recommended Testing Workflow

### First Time Setup

```bash
# 1. Navigate to project
cd /home/jp/Laptop-MAIN/applications/orion-core

# 2. Activate venv
source .venv/bin/activate

# 3. Check pytest is installed
pytest --version
# Should show: pytest 8.4.2 or similar

# 4. Update .env with service URLs
nano .env

# Add these lines (if running from laptop):
ORION_VLLM_URL=http://192.168.5.10:8000
ORION_QDRANT_URL=http://192.168.5.10:6333
ORION_ANYTHINGLLM_URL=http://192.168.5.10:3001
ORION_ANYTHINGLLM_API_KEY=your-actual-key-here
```

### Running Tests

```bash
# Step 1: Smoke tests (are services reachable?)
pytest tests/smoke/ -v

# If smoke tests PASS → Continue to step 2
# If smoke tests FAIL → Fix services first (see Troubleshooting below)

# Step 2: Real integration tests (does it actually work?)
pytest tests/real_integration/ -v -s

# Step 3 (optional): All tests including unit tests
pytest tests/ -v
```

## 📊 Understanding Test Output

### ✅ All Smoke Tests Pass

```
tests/smoke/test_services_reachable.py::test_vllm_service_reachable PASSED
tests/smoke/test_services_reachable.py::test_qdrant_service_reachable PASSED
tests/smoke/test_services_reachable.py::test_anythingllm_service_reachable PASSED
✅ vLLM reachable at http://192.168.5.10:8000
✅ Qdrant reachable at http://192.168.5.10:6333
✅ AnythingLLM reachable at http://192.168.5.10:3001

```

**This means:** Services are up and your laptop can reach them. Ready for integration tests!

### ❌ Smoke Tests Fail

```
tests/smoke/test_services_reachable.py::test_vllm_service_reachable FAILED
❌ Cannot connect to vLLM at http://192.168.5.10:8000: Connection refused

```

**This means:** Services aren't running. See "Troubleshooting" section.

### ⚠️ Integration Tests Pass with Warnings

```
tests/real_integration/test_real_knowledge_subsystem.py::test_knowledge_base_gate_check PASSED
⚠️  Knowledge base gate returned warning (expected):
   Qdrant collection is empty. Rebuild required...

```

**This means:** Code works, but knowledge base is empty (expected after Nov 17, 2025).

To fix: See "Rebuilding Knowledge Base" section.

## 🔧 Troubleshooting

### Problem: "Cannot connect to service"

**Symptoms:**

```
❌ Cannot connect to vLLM at http://192.168.5.10:8000: Connection refused

```

**Solution:**

```bash
# Check if services are running on lab host
ssh lab "docker compose ps"

# If nothing shows, start services:
ssh lab "cd /mnt/nvme2/orion-project/setup && docker compose up -d"

# Wait 2 minutes for vLLM to load model, then try tests again
```

### Problem: "API key invalid"

**Symptoms:**

```
❌ AnythingLLM API key is INVALID

```

**Solution:**

1. Open AnythingLLM UI: <http://192.168.5.10:3001>
2. Go to: Settings → API Keys
3. Copy your API key
4. Update `.env`:

   ```bash
   nano .env
   # Set: ORION_ANYTHINGLLM_API_KEY=your-actual-key-here
   ```

### Problem: "Collection not found"

**Symptoms:**

```
⚠️  Collection 'orion_homelab' NOT FOUND

```

**Solution:**

The knowledge base was cleared on Nov 17, 2025. Rebuild it:

```bash
cd /home/jp/Laptop-MAIN/applications/orion-rag/harvester
source .venv/bin/activate
orion embed-index --collection orion_homelab
```

### Problem: "Module not found"

**Symptoms:**

```
ModuleNotFoundError: No module named 'httpx'

```

**Solution:**

```bash
# Make sure venv is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

## 📖 Detailed Test Documentation

For more details, see:

- **[tests/smoke/README.md](tests/smoke/)** - Smoke test documentation
- **[tests/real_integration/README.md](tests/real_integration/README.md)** - Real integration test guide
- **[TEST-ANALYSIS-CRITICAL.md](TEST-ANALYSIS-CRITICAL.md)** - Analysis of current test quality

## 🎯 What You Should See

After running all tests successfully:

```bash
$ pytest tests/smoke/ tests/real_integration/ -v

===== test session starts =====
collected 15 items

tests/smoke/test_services_reachable.py::test_vllm_service_reachable PASSED
tests/smoke/test_services_reachable.py::test_qdrant_service_reachable PASSED
tests/smoke/test_services_reachable.py::test_qdrant_collections_api PASSED
tests/smoke/test_services_reachable.py::test_anythingllm_service_reachable PASSED
tests/smoke/test_services_reachable.py::test_anythingllm_api_key_valid PASSED
tests/smoke/test_docker_environment.py::test_environment_variables_set PASSED
tests/smoke/test_docker_environment.py::test_subsystems_enabled PASSED

tests/real_integration/test_real_knowledge_subsystem.py::test_knowledge_subsystem_initializes PASSED
tests/real_integration/test_real_knowledge_subsystem.py::test_knowledge_base_gate_check PASSED
tests/real_integration/test_real_knowledge_subsystem.py::test_fetch_collection_stats PASSED
tests/real_integration/test_real_knowledge_subsystem.py::test_real_knowledge_query PASSED

tests/real_integration/test_real_router.py::test_router_initializes PASSED
tests/real_integration/test_real_router.py::test_fallback_classification PASSED
tests/real_integration/test_real_router.py::test_real_intent_classification_with_vllm PASSED
tests/real_integration/test_real_router.py::test_real_route_message_end_to_end PASSED

===== 15 passed in 45.23s =====
```

**This proves your system ACTUALLY WORKS!** 🎉

## 🚨 Important Notes

1. **Run from laptop** - Tests are designed to run from your laptop, hitting services on lab host
2. **Services must be running** - Smoke tests will fail if Docker services aren't up
3. **Real API calls** - Integration tests make actual HTTP requests (not mocked)
4. **Slow is normal** - Real integration tests take 30-60 seconds because they call real APIs
5. **Failures are good** - If tests fail, they're showing you real problems (unlike mocks)

## 🎓 Next Steps

Once tests pass:

1. **Add more test cases** to cover edge cases
2. **Set up CI/CD** to run tests automatically
3. **Add E2E tests** with Playwright for full user flows
4. **Monitor test results** to catch regressions early

## 📞 Getting Help

If you're stuck:

1. Check this file first (you're reading it now!)
2. Look at test output - it shows detailed errors
3. Read [TEST-ANALYSIS-CRITICAL.md](TEST-ANALYSIS-CRITICAL.md) for background
4. Check logs: `docker compose logs <service-name>`

---

**Remember:** Tests that make real API calls are the only tests that prove your system works!
