"""Shared compiled regex patterns used by multiple HAL modules."""

import re

# Matches ```json {...} ``` code fences containing JSON objects. Used by:
#   - memory.py: detect poison tool-call responses before persisting to SQLite
#   - server.py: strip hallucinated tool-call blocks from HTTP responses
TOOL_CALL_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
