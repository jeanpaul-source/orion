"""LLM clients — OllamaClient (embeddings only) and VLLMClient (chat via OpenAI-compatible API)."""
import requests

from hal.tracing import get_tracer


class OllamaClient:
    def __init__(self, base_url: str, model: str, embed_model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
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
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=3)
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
            r.raise_for_status()
            result = r.json()["choices"][0]["message"]
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
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            span.set_attribute("llm.response_len", len(content))
            return content
