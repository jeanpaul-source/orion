---
description: "Scaffold a new HAL tool: tool definition, Judge tier, handler, and tests"
agent: agent
argument-hint: "Describe the tool (e.g., 'query Docker container logs')"
---

# Add Tool

Add a new tool to HAL. Follow these steps in order:

1. **Define the tool** in `hal/tools.py` — add to `TOOL_DEFINITIONS` with name,
   description, and JSON schema for parameters.

2. **Set the Judge tier** in `hal/judge.py` — classify the tool's risk level:
   - Tier 0: read-only, no side effects
   - Tier 1: reversible mutation
   - Tier 2: config change or sandboxed execution
   - Tier 3: destructive or dangerous

3. **Implement the handler** in the appropriate module. The handler must:
   - Accept typed arguments matching the JSON schema
   - Return a string result (the agent sees this as tool output)
   - Use `hal/config.py` for any hosts, ports, or paths
   - Use `hal/logging_utils.py` for logging, not `print()`

4. **Wire dispatch** — add the handler to the dispatch map in `hal/tools.py`.

5. **Write tests** in a new or existing test file:
   - Use `ScriptedExecutor` from `tests/conftest.py` for command mocks
   - Use `ScriptedLLM` if the test needs the agent loop
   - No real network calls — mock everything
   - Test both success and error paths

6. **Run `make check`** to verify lint, types, and tests pass.
