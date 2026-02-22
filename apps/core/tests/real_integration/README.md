# Real Integration Tests for ORION Core

These tests validate ORION Core with **REAL external services** - no mocks, no stubs, just actual API calls.

## What's Different From Unit Tests?

| Aspect | Unit Tests | Real Integration Tests |
|--------|-----------|------------------------|
| **External Services** | Mocked | Real HTTP calls |
| **vLLM** | Mock responses | Actual LLM inference |
| **Qdrant** | Mock vectors | Real vector search |
| **AnythingLLM** | Mock RAG | Real RAG pipeline |
| **Speed** | Fast (milliseconds) | Slow (seconds) |
| **Reliability** | Always pass | Can fail if services down |
| **Value** | Validates code paths | Validates system works |

## Prerequisites

Before running these tests, you must have:

### 1. Services Running

```bash
# On lab host (192.168.5.10)
cd /mnt/nvme2/orion-project/setup
docker compose ps

# Should show:
# - vllm (port 8000)
# - qdrant (port 6333)
# - anythingllm (port 3001)
```

### 2. Environment Variables Set

```bash
# Required in .env or environment
ORION_ANYTHINGLLM_API_KEY=your-actual-api-key
ORION_VLLM_URL=http://vllm:8000
ORION_QDRANT_URL=http://qdrant:6333
ORION_ANYTHINGLLM_URL=http://anythingllm:3001
```

### 3. Network Connectivity

If running from laptop, ensure you can reach lab host:

```bash
# Test connectivity
ping 192.168.5.10
curl http://192.168.5.10:8000/health  # vLLM
curl http://192.168.5.10:6333/        # Qdrant
curl http://192.168.5.10:3001/api/v1/system/ping  # AnythingLLM
```

## Running the Tests

### Quick Start - Smoke Tests First

Start with smoke tests to verify services are reachable:

```bash
# Must be in orion-core directory
cd /home/jp/Laptop-MAIN/applications/orion-core
source .venv/bin/activate

# Run smoke tests (fast, checks service availability)
pytest tests/smoke/ -v
```

**Expected Output:**

```
tests/smoke/test_services_reachable.py::test_vllm_service_reachable PASSED
tests/smoke/test_services_reachable.py::test_qdrant_service_reachable PASSED
tests/smoke/test_services_reachable.py::test_anythingllm_service_reachable PASSED
tests/smoke/test_services_reachable.py::test_anythingllm_api_key_valid PASSED
```

If smoke tests fail, **fix services before running integration tests**.

### Run Real Integration Tests

Once smoke tests pass:

```bash
# Run all real integration tests
pytest tests/real_integration/ -v

# Run specific test file
pytest tests/real_integration/test_real_knowledge_subsystem.py -v

# Run with detailed output
pytest tests/real_integration/ -v -s --tb=short
```

### Run Everything

```bash
# Run smoke tests, then integration tests
pytest tests/smoke/ tests/real_integration/ -v
```

## Understanding Test Results

### ✅ Test Passes - Great

```
tests/real_integration/test_real_knowledge_subsystem.py::test_fetch_collection_stats PASSED
```

This means:

- Code works
- Services are reachable
- APIs respond correctly
- Integration is functional

### ⚠️ Test Passes with Warning

```
tests/real_integration/test_real_knowledge_subsystem.py::test_knowledge_base_gate_check PASSED
⚠️  Knowledge base gate returned warning (expected):
   Qdrant collection is empty. Rebuild required...
```

This means:

- Code works
- Services are reachable
- But knowledge base needs to be rebuilt (expected after Nov 17, 2025)

**To fix:**

```bash
cd /home/jp/Laptop-MAIN/applications/orion-rag/harvester
source .venv/bin/activate
orion process --max-files 50
orion embed-index
```

### ❌ Test Fails - Needs Investigation

```
tests/real_integration/test_real_knowledge_subsystem.py::test_fetch_collection_stats FAILED
❌ Cannot connect to Qdrant at http://qdrant:6333: Connection refused
```

This means:

- **Service is not running**, OR
- **Network configuration is wrong**, OR
- **DNS not resolving service names**

**To diagnose:**

```bash
# Check if services are running
ssh lab "docker compose ps"

# Test connectivity manually
curl http://192.168.5.10:6333/

# Check Docker network
docker network inspect orion-net
```

## Test Categories

### Smoke Tests (`tests/smoke/`)

**Purpose:** Verify services are up and reachable
**Runtime:** < 5 seconds
**Failures:** Usually indicate services not running

Key tests:

- `test_vllm_service_reachable` - vLLM health check
- `test_qdrant_service_reachable` - Qdrant API check
- `test_anythingllm_service_reachable` - AnythingLLM ping
- `test_anythingllm_api_key_valid` - Auth verification

### Real Integration Tests (`tests/real_integration/`)

**Purpose:** Validate actual system functionality
**Runtime:** 10-60 seconds (makes real API calls)
**Failures:** Indicate integration issues or missing data

Key tests:

- `test_real_knowledge_query` - End-to-end RAG query
- `test_real_intent_classification_with_vllm` - vLLM classification
- `test_real_route_message_end_to_end` - Full routing flow
- `test_fetch_collection_stats` - Real Qdrant queries

## Common Issues

### Issue: "Cannot connect to service"

**Cause:** Service not running or wrong URL
**Fix:**

```bash
# Check services
ssh lab "docker compose ps"

# Start if needed
ssh lab "cd /mnt/nvme2/orion-project/setup && docker compose up -d"
```

### Issue: "API key invalid"

**Cause:** `ORION_ANYTHINGLLM_API_KEY` not set or wrong
**Fix:**

```bash
# Get API key from AnythingLLM UI
# Settings → API Keys

# Set in .env
echo "ORION_ANYTHINGLLM_API_KEY=your-key-here" >> .env
```

### Issue: "Collection not found"

**Cause:** Qdrant collection doesn't exist (expected after Nov 17)
**Fix:**

```bash
# Rebuild knowledge base
cd applications/orion-rag/harvester
source .venv/bin/activate
orion embed-index --collection orion_homelab
```

### Issue: "DNS resolution failed"

**Cause:** Not running in Docker network
**Fix:**

If running from laptop (outside Docker), update URLs in `.env`:

```bash
# Use host IPs instead of service names
ORION_VLLM_URL=http://192.168.5.10:8000
ORION_QDRANT_URL=http://192.168.5.10:6333
ORION_ANYTHINGLLM_URL=http://192.168.5.10:3001
```

## Continuous Integration

These tests should be run:

1. **Before deploying** to lab host
2. **After changing** integration code
3. **After service updates** (Docker image changes)
4. **Weekly** to catch configuration drift

## Adding New Real Integration Tests

When adding a new integration test:

1. **Mark with decorators:**

   ```python
   @pytest.mark.integration
   @pytest.mark.real
   @pytest.mark.asyncio  # If async
   ```

2. **No mocks allowed** - Real HTTP calls only

3. **Handle expected failures:**

   ```python
   if response_empty:
       print("⚠️  Expected empty response (KB not rebuilt)")
       pytest.skip("Knowledge base needs rebuild")
   ```

4. **Add helpful output:**

   ```python
   print(f"✅ Test passed: {details}")
   print(f"⚠️  Warning: {issue}")
   print(f"❌ Failed: {error}")
   ```

## Next Steps

After integration tests pass:

1. **Add E2E tests** (`tests/e2e/`) with Playwright
2. **Add load tests** to verify performance
3. **Add chaos tests** to verify error handling
4. **Set up CI/CD** to run automatically

---

**Remember:** These tests prove your system **actually works**, not just that it **might work**.
