"""Sanitise HAL response text — strip tool-call artefacts and CJK language leaks.

The LLM occasionally leaks a tool-call into its prose response instead of
issuing it via the structured ``tool_calls`` field.  Two patterns are caught:

1. **Bare JSON object** — ``{"name": ..., "arguments": ...}`` appended to or
   forming the entire response text.
2. **Fenced JSON block** — `````json {"name":..., "arguments":...}````` blocks
   hallucinated inside prose.

Qwen-family models also leak Mandarin Chinese mid-response due to their
multilingual training data.  ``has_excessive_cjk`` and ``strip_cjk_lines``
handle detection and cleanup.

Single canonical implementations live here; ``agent.py``, ``server.py``,
and ``memory.py`` all delegate to these functions.
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


# ---------------------------------------------------------------------------
# CJK language-leak detection and cleanup
# ---------------------------------------------------------------------------

# Unicode ranges for CJK characters and common CJK punctuation.
# Covers CJK Unified Ideographs, Extension A, Compatibility Ideographs,
# and fullwidth punctuation (used in Chinese/Japanese/Korean text).
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff"  # CJK Unified Ideographs
    r"\u3400-\u4dbf"  # CJK Unified Ideographs Extension A
    r"\uf900-\ufaff"  # CJK Compatibility Ideographs
    r"\u3000-\u303f"  # CJK Symbols and Punctuation
    r"\uff00-\uffef]"  # Fullwidth Forms (Chinese punctuation)
)


def _cjk_ratio(text: str) -> float:
    """Return the fraction of non-whitespace characters that are CJK."""
    chars = text.replace(" ", "").replace("\t", "").replace("\n", "")
    if not chars:
        return 0.0
    cjk_count = len(_CJK_RE.findall(chars))
    return cjk_count / len(chars)


def has_excessive_cjk(text: str, threshold: float = 0.15) -> bool:
    """Return True if more than *threshold* of the response is CJK characters.

    Default 0.15 (15%) is deliberately generous — a single quoted Chinese term
    in an otherwise-English response won't trigger it, but a paragraph that
    switches language will.

    Used by :func:`memory.is_poison_response` to prevent CJK-heavy turns
    from being saved to session history (which would compound the problem
    in future sessions).
    """
    return _cjk_ratio(text) > threshold


def strip_cjk_lines(text: str) -> str:
    """Remove lines that are majority CJK, keeping English content.

    Splits on newlines, drops any line where >50% of non-whitespace characters
    are CJK.  Preserves the useful English portion of a mixed response.
    Returns the surviving text re-joined and stripped of excess blank lines.
    """
    kept = [line for line in text.split("\n") if _cjk_ratio(line) <= 0.50]
    # Collapse runs of blank lines left by removed CJK lines
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(kept))
    return result.strip()
