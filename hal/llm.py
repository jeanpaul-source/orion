"""LLM clients — OllamaClient (embeddings only) and VLLMClient (chat via OpenAI-compatible API)."""

import time

import requests

from hal.logging_utils import get_logger
from hal.prometheus import Counter, Histogram
from hal.tracing import get_tracer

# Metrics (no-op unless PROM_PUSHGATEWAY is configured)
LLM_REQ_TOTAL = Counter("hal_llm_requests_total", labels=("endpoint", "outcome"))
LLM_REQ_LATENCY = Histogram("hal_llm_request_latency_seconds", labels=("endpoint",))

log = get_logger(__name__)


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
        t0 = time.perf_counter()
        outcome = "ok"
        with get_tracer().start_as_current_span("hal.llm.chat_with_tools") as span:
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.message_count", len(messages))
            span.set_attribute("llm.tool_count", len(tools))
            payload = {
                "model": self.model,
                "messages": self._messages(messages, system),
                "tools": tools,
            }
            try:
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
                data = r.json()
            except Exception as e:
                outcome = "error"
                LLM_REQ_TOTAL.inc(endpoint="chat_with_tools", outcome=outcome)
                LLM_REQ_LATENCY.observe(
                    time.perf_counter() - t0, endpoint="chat_with_tools"
                )
                log.error("vllm chat_with_tools failed: %s", e)
                raise
            result = data["choices"][0]["message"]
            has_tool_calls = bool(result.get("tool_calls"))
            span.set_attribute("llm.has_tool_calls", has_tool_calls)
            if has_tool_calls:
                names = [
                    tc.get("function", {}).get("name", "")
                    for tc in result["tool_calls"]
                ]
                span.set_attribute("llm.tool_calls", ",".join(names))
            # Basic token accounting if server returns usage
            usage = data.get("usage") if "data" in locals() else None
            if usage:
                span.set_attribute("llm.prompt_tokens", usage.get("prompt_tokens", 0))
                span.set_attribute(
                    "llm.completion_tokens", usage.get("completion_tokens", 0)
                )
            LLM_REQ_TOTAL.inc(endpoint="chat_with_tools", outcome=outcome)
            LLM_REQ_LATENCY.observe(
                time.perf_counter() - t0, endpoint="chat_with_tools"
            )
            return result

    def chat(
        self, messages: list[dict], system: str | None = None, timeout: int = 120
    ) -> str:
        """Non-streaming chat — returns full response string."""
        t0 = time.perf_counter()
        outcome = "ok"
        with get_tracer().start_as_current_span("hal.llm.chat") as span:
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.message_count", len(messages))
            payload = {
                "model": self.model,
                "messages": self._messages(messages, system),
            }
            try:
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
                data = r.json()
            except Exception as e:
                outcome = "error"
                LLM_REQ_TOTAL.inc(endpoint="chat", outcome=outcome)
                LLM_REQ_LATENCY.observe(time.perf_counter() - t0, endpoint="chat")
                log.error("vllm chat failed: %s", e)
                raise
            content = data["choices"][0]["message"]["content"]
            span.set_attribute("llm.response_len", len(content))
            usage = data.get("usage")
            if usage:
                span.set_attribute("llm.prompt_tokens", usage.get("prompt_tokens", 0))
                span.set_attribute(
                    "llm.completion_tokens", usage.get("completion_tokens", 0)
                )
            LLM_REQ_TOTAL.inc(endpoint="chat", outcome=outcome)
            LLM_REQ_LATENCY.observe(time.perf_counter() - t0, endpoint="chat")
            return content
