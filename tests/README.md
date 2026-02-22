# HAL Test Suite

## What this is

This test suite verifies that the **intent classifier** routes queries to the correct
handler. The intent classifier is the front door of HAL — if it misroutes a query,
everything downstream goes wrong silently. These tests make misroutes immediately
visible and catchable before deployment.

## What is tested here

**`test_intent.py`** — The intent classifier (`hal/intent.py`).

Asserts that specific natural-language queries are classified into the right category:

| Category | Meaning | Handler it routes to |
|---|---|---|
| `health` | Questions about live metrics / system state | `run_health()` — no tools |
| `fact` | Questions about documented config / infrastructure | `run_fact()` — no tools |
| `agentic` | Multi-step investigation or action requests | `run_agent()` — full tool loop |

## What is NOT tested here (and why)

- **LLM responses** — they're non-deterministic (slightly different every run), so you
  can't assert an exact output. Testing them would produce false failures constantly.
- **Server commands** — running `run_command` in tests could have real side effects on
  the server. Out of scope until we have a safe sandbox.
- **Full end-to-end HAL sessions** — too complex to set up reliably and too slow for
  routine use. Manual testing covers this for now.

## Prerequisites

These tests use the **real embedding model** (`nomic-embed-text`) to classify queries,
because the quality of classification depends on actual embeddings — not fake ones.

This means **Ollama must be running** when you run the tests.

- **On the server:** Ollama is at `localhost:11434` — tests work with no extra config.
- **On the laptop:** Set `OLLAMA_HOST=http://192.168.5.10:11434` in your environment,
  or have the SSH tunnel active.

If Ollama is unreachable, all tests are **skipped** (not failed) with a clear message.

## How to run

```bash
# On the server (inside the orion venv):
cd ~/orion
.venv/bin/pytest tests/ -v

# Shorter output (just pass/fail summary):
.venv/bin/pytest tests/

# Run only intent tests:
.venv/bin/pytest tests/test_intent.py -v
```

A passing run looks like:

```
tests/test_intent.py::test_health_queries[how's the lab?] PASSED
tests/test_intent.py::test_health_queries[is everything ok?] PASSED
...
tests/test_intent.py::test_agentic_queries[restart the monitoring stack] PASSED
20 passed in 12.34s
```

## How to add a test when you see a misroute

If HAL routes a query to the wrong path (you'll see it in the dim `intent:` label),
add the query to the relevant list in `tests/test_intent.py`:

```python
# Example: "tell me the prometheus port" was misrouted to agentic
# Add it to FACT_QUERIES:
FACT_QUERIES = [
    ...
    "tell me the prometheus port",   # ← add here
]
```

Then run the tests. If it fails, the classifier needs a new example sentence added
to the matching category in `hal/intent.py` → `EXAMPLES["fact"]`.

## Installing test dependencies

Test dependencies are kept separate from production dependencies:

```bash
# Install test deps (from the orion directory):
.venv/bin/pip install -r requirements-dev.txt
```
