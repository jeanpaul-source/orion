"""Sanitise HAL response text — strip tool-call artefacts.

The LLM occasionally leaks a tool-call into its prose response instead of
issuing it via the structured ``tool_calls`` field.  Two patterns are caught:

1. **Bare JSON object** — ``{"name": ..., "arguments": ...}`` appended to or
   forming the entire response text.
2. **Fenced JSON block** — `````json {"name":..., "arguments":...}````` blocks
   hallucinated inside prose.

Single canonical implementations live here; ``agent.py``, ``server.py``,
and ``memory.py`` all delegate to these two functions.
"""

import json
import re

# Matches ```json {...} ``` code fences containing a single JSON object.
# Greedy {.*} is intentional: lazy {.*?} stops at the first } it finds,
# which for nested objects like {"arguments": {"key": "val"}} captures only
# the inner dict, producing invalid JSON that json.loads() rejects and the
# poison check misses.  Greedy captures from the first { to the last } in
# the fence, which is the correct bound for a single top-level object.
TOOL_CALL_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def is_tool_call_artifact(text: str) -> bool:
    """Return True if *text* is or contains a tool-call artifact.

    Catches two patterns:

    1. The entire (stripped) response **is** a bare tool-call JSON object —
       starts with ``{`` and parses as a dict with both ``"name"`` and
       ``"arguments"`` keys.
    2. The response contains one or more `````json {…}````` fences whose body
       parses as a tool-call dict (LLM narrating a call in prose).

    Used as a save-gate by :func:`memory.is_poison_response` before writing
    assistant turns to SQLite.
    """
    stripped = text.strip()

    # Pattern 1: entire response is a bare tool-call object
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict) and "name" in data and "arguments" in data:
                return True
        except (json.JSONDecodeError, ValueError):
            pass

    # Pattern 2: embedded ```json {...} ``` fences containing tool-call objects
    for m in TOOL_CALL_FENCE_RE.finditer(stripped):
        try:
            data = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and "name" in data and "arguments" in data:
            return True

    return False


def strip_tool_call_artifacts(text: str) -> str:
    """Remove tool-call artefacts from *text*; return clean prose.

    Applied in two passes:

    1. Strip `````json {…}````` fences whose body is a tool-call dict.
    2. Strip bare ``{"name": …, "arguments": …}`` JSON objects occurring inline.

    Uses :func:`json.JSONDecoder.raw_decode` for the bare-object pass so that
    nested JSON inside argument strings is handled correctly.  No-op on clean
    text.
    """

    def _strip_fence(m: re.Match) -> str:  # type: ignore[type-arg]
        try:
            data = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            return m.group(0)  # not valid JSON — leave untouched
        if isinstance(data, dict) and "name" in data and "arguments" in data:
            return ""  # tool-call hallucination — strip
        return m.group(0)  # real JSON — leave untouched

    text = TOOL_CALL_FENCE_RE.sub(_strip_fence, text)

    # Pass 2: strip bare JSON objects that are tool-call dicts
    decoder = json.JSONDecoder()
    out: list[str] = []
    pos = 0
    while pos < len(text):
        brace = text.find("{", pos)
        if brace == -1:
            out.append(text[pos:])
            break
        # Append verbatim everything before this opening brace.
        out.append(text[pos:brace])
        try:
            obj, end = decoder.raw_decode(text, brace)
        except (json.JSONDecodeError, ValueError):
            # Not valid JSON at this position — keep the character and advance.
            out.append("{")
            pos = brace + 1
            continue
        if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
            pos = end  # tool-call artifact — drop it
        else:
            out.append(text[brace:end])  # real JSON literal — keep verbatim
            pos = end

    return "".join(out).strip()
