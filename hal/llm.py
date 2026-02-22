"""Ollama client — embedding and streaming chat."""
import json
from typing import Generator

import requests


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

    def chat_with_tools(
        self, messages: list[dict], tools: list[dict], system: str | None = None
    ) -> dict:
        """Non-streaming chat with tool schemas. Returns the full message dict.
        The returned dict may contain 'tool_calls' if the model wants to call a tool."""
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
        }
        if system:
            payload["system"] = system
        r = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]

    def chat(
        self, messages: list[dict], system: str | None = None, timeout: int = 120
    ) -> str:
        """Non-streaming chat — returns full response string."""
        payload = {"model": self.model, "messages": messages, "stream": False}
        if system:
            payload["system"] = system
        r = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def stream_chat(
        self, messages: list[dict], system: str | None = None
    ) -> Generator[str, None, None]:
        """Streaming chat — yields text tokens as they arrive."""
        payload = {"model": self.model, "messages": messages, "stream": True}
        if system:
            payload["system"] = system
        with requests.post(
            f"{self.base_url}/api/chat", json=payload, stream=True, timeout=120
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                if not chunk.get("done"):
                    yield chunk["message"]["content"]
