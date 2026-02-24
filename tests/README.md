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
| --- | --- | --- |
| `conversational` | Greetings, acknowledgements, casual chat | `run_conversational()` — no tools, no KB |
| `health` | Questions about live metrics / system state | `run_health()` — no tools |
| `fact` | Questions about documented config / infrastructure | `run_fact()` — no tools |
| `agentic` | Multi-step investigation or action requests | `run_agent()` — full tool loop |

**Requires live Ollama** (real embeddings). Skipped automatically when Ollama is unreachable.

---

**`test_judge.py`** — The policy gate (`hal/judge.py`).

Parametrized tests for `classify_command()` and `tier_for()` across ~60 commands covering
tier 0 (read-only), tier 1 (service restart), tier 2 (config changes), and tier 3
(destructive). No external services needed.

---

**`test_memory.py`** — The session store (`hal/memory.py`).

Unit tests for `is_poison_response()`, `save_turn()` (poison guard), and `prune_old_turns()`.
Uses an in-memory SQLite database — no external services needed.

---

**`test_agent_loop.py`** — The agentic tool loop (`hal/agent.py — run_agent`).

Integration tests that mock all external I/O and verify the orchestration logic:

| Test | What it verifies |
| --- | --- |
| `test_direct_text_response` | LLM finishes without any tool calls — loop exits in one step |
| `test_single_tool_call_then_answer` | Tool called, result fed back, final answer produced; `tool_call_id` correctly propagated |
| `test_duplicate_tool_call_injects_loop_breaker` | Repeated tool call is deduped; loop-breaker message injected into context |
| `test_max_iterations_guard` | Exhausting `MAX_ITERATIONS` without a final answer returns the sentinel string |
| `test_tool_output_is_truncated` | Tool output > 8000 chars is capped and annotated before being fed back |
| `test_search_kb_returns_no_results_when_empty` | `_dispatch("search_kb")` returns human-readable string when KB has no hits |
| `test_unknown_tool_returns_graceful_error` | Unrecognised tool name returns error string, does not raise |
| `test_get_metrics_prometheus_unavailable` | `get_metrics` returns fallback error string when Prometheus is down |
| `test_kb_context_injected_for_high_score_chunks` | Chunks with score ≥ 0.75 are prepended to the first user message |
| `test_kb_context_not_injected_for_low_score_chunks` | Chunks with score < 0.75 are silently discarded |

No external services needed — all LLM, KB, Prometheus, SSH, and Judge calls are mocked.

## What is NOT tested here (and why)

- **LLM response quality** — non-deterministic outputs can't be asserted exactly. The eval
  harness (`eval/`) covers this with scored baselines instead.
- **Real SSH command side effects** — running `run_command` in tests could affect the server.
  The agent loop tests mock the executor entirely.

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

```text
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
