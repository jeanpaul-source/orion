# E2E Testing with Playwright

This directory contains end-to-end browser tests using Playwright.

## Setup

Already completed:

```bash
pip install pytest-playwright playwright
playwright install chromium
```

## Running Tests

### Run all E2E tests

```bash
# From orion-core directory
pytest tests/test_command_palette_e2e.py -v
```

### Run with browser visible (headed mode)

```bash
pytest tests/test_command_palette_e2e.py --headed
```

### Run a specific test

```bash
pytest tests/test_command_palette_e2e.py::TestCommandPalette::test_command_palette_opens_with_cmd_k -v
```

### Run only E2E tests (excluding other tests)

```bash
pytest -m e2e -v
```

### Skip slow tests

```bash
pytest -m "e2e and not slow" -v
```

## Prerequisites

**ORION Core must be running before tests:**

```bash
# Start the server in another terminal
cd applications/orion-core
source .venv/bin/activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 5000
```

Or use Docker:

```bash
docker compose up -d
```

Then run tests pointing to the server (default: <http://localhost:5000>).

## Test Structure

- **test_command_palette_e2e.py**: Command palette keyboard shortcuts, search, navigation
- Tests use real Chromium browser (headless by default)
- Playwright fixtures: `page` (browser page), `base_url` (app URL)

## Common Issues

### "Connection refused"

- Make sure ORION Core is running on <http://localhost:5000>
- Check with: `curl http://localhost:5000/health`

### "Element not found"

- Frontend may need time to load: Playwright auto-waits but complex UIs may need explicit waits
- Use `page.wait_for_selector()` if needed

### Tests timing out

- Increase timeout: `pytest --timeout=30`
- Or mark specific tests with `@pytest.mark.timeout(60)`

## Browser Selection

Run with different browsers:

```bash
pytest --browser firefox  # Not installed by default
pytest --browser webkit   # Not installed by default
```

Install other browsers:

```bash
playwright install firefox webkit
```

## CI/CD Integration

For headless CI environments:

```bash
pytest tests/test_command_palette_e2e.py --browser chromium --headed=false
```
