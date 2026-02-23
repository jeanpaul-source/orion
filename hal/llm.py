"""LLM clients — OllamaClient (embeddings only) and VLLMClient (chat via OpenAI-compatible API)."""
import json
import re
import uuid
import requests

from hal.tracing import get_tracer

# Qwen2.5-Coder with --tool-call-parser hermes outputs tool calls wrapped in
# <tools> or <tool_call> tags instead of the OpenAI tool_calls field.
# These patterns extract them so the agent loop works without parser changes.
_TOOL_TAG_RE = re.compile(
    r"<(?:tool_call|tools)>\s*(?P<json>\{.*?\})\s*</(?:tool_call|tools)>",
    re.DOTALL,
)


def _extract_tool_calls_from_content(content: str) -> list[dict]:
    """Parse tool call JSON blocks from model content when tool_calls is empty.

    Handles both <tool_call>{json}</tool_call> (Hermes) and
    <tools>{json}</tools> (Qwen2.5-Coder native) wrappers.
    Returns a list of OpenAI-style tool_call dicts, or [] if nothing found.
    """
    calls = []
    for m in _TOOL_TAG_RE.finditer(content):
        try:
            data = json.loads(m.group("json"))
        except json.JSONDecodeError:
            continue
        name = data.get("name") or data.get("function", {}).get("name", "")
        args = data.get("arguments") or data.get("parameters") or {}
        if not name:
            continue
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": args if isinstance(args, str) else json.dumps(args),
            },
        })
    return calls


class OllamaClient:
    def __init__(self, base_url: str, embed_model: str):
        self.base_url = base_url.rstrip("/")
        self.embed_model = embed_model

    def ping(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def embed(self, text: str) -> list[float]:
        r = requests.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.embed_model, "prompt": text},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["embedding"]


class VLLMClient:
    """Chat client for vLLM's OpenAI-compatible API. No embedding support — use OllamaClient for that."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._headers = {"Authorization": "Bearer not-needed"}

    def ping(self) -> bool:
        """Return True only when vLLM is fully loaded and ready to serve.

        /v1/models returns 200 as soon as the API server starts — before the
        model weights are in VRAM.  /health only returns 200 once the model is
        actually ready to accept completions requests.
        """
        try:
            r = requests.get(f"{self.base_url}/health", timeout=3)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _messages(self, messages: list[dict], system: str | None) -> list[dict]:
        if system:
            return [{"role": "system", "content": system}] + messages
        return messages

    def chat_with_tools(
        self, messages: list[dict], tools: list[dict], system: str | None = None
    ) -> dict:
        """Non-streaming chat with tool schemas. Returns the full message dict."""
        with get_tracer().start_as_current_span("hal.llm.chat_with_tools") as span:
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.message_count", len(messages))
            span.set_attribute("llm.tool_count", len(tools))
            payload = {
                "model": self.model,
                "messages": self._messages(messages, system),
                "tools": tools,
            }
            r = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers,
                timeout=120,
            )
            if r.status_code == 404:
                raise RuntimeError(
                    f"vLLM returned 404 — model '{self.model}' is still loading. "
                    "Wait ~30 s and try again."
                )
            r.raise_for_status()
            result = r.json()["choices"][0]["message"]
            # Fallback: Qwen2.5-Coder emits tool calls as <tools>/{json}</tools>
            # in content rather than in the tool_calls field when using the
            # hermes parser. Extract them so the agent loop sees proper calls.
            if not result.get("tool_calls") and result.get("content"):
                extracted = _extract_tool_calls_from_content(result["content"])
                if extracted:
                    result = dict(result)
                    result["tool_calls"] = extracted
                    result["content"] = None  # consumed; prevent poison detection
            has_tool_calls = bool(result.get("tool_calls"))
            span.set_attribute("llm.has_tool_calls", has_tool_calls)
            if has_tool_calls:
                names = [tc.get("function", {}).get("name", "") for tc in result["tool_calls"]]
                span.set_attribute("llm.tool_calls", ",".join(names))
            return result

    def chat(
        self, messages: list[dict], system: str | None = None, timeout: int = 120
    ) -> str:
        """Non-streaming chat — returns full response string."""
        with get_tracer().start_as_current_span("hal.llm.chat") as span:
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.message_count", len(messages))
            payload = {
                "model": self.model,
                "messages": self._messages(messages, system),
            }
            r = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers,
                timeout=timeout,
            )
            if r.status_code == 404:
                raise RuntimeError(
                    f"vLLM returned 404 — model '{self.model}' is still loading. "
                    "Wait ~30 s and try again."
                )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            span.set_attribute("llm.response_len", len(content))
            return content
