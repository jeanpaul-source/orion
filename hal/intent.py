"""Intent classifier — routes queries to the right handler before the LLM sees them.

Uses embedding similarity against a fixed set of example sentences per category.
Routing is deterministic and fast: one embed call per query, no LLM needed.

Categories:
  health  — questions about live metrics and current system state
  fact    — questions about documented configuration and infrastructure facts
  agentic — multi-step investigation, diagnosis, or action requests

If confidence is below THRESHOLD, defaults to 'agentic' (safest fallback).
If the embedding model is unavailable at startup, always returns 'agentic'.
"""
import math
from typing import Literal

from hal.llm import OllamaClient
from hal.tracing import get_tracer

Intent = Literal["health", "fact", "agentic", "conversational"]

# Minimum cosine similarity score to trust a health or fact classification.
# Below this, the query falls through to the agentic loop.
THRESHOLD = 0.65

# ~13 example sentences per category covering natural variation in phrasing.
# To fix a misroute: add a sentence here that looks like the misrouted query.
EXAMPLES: dict[str, list[str]] = {
    "conversational": [
        "hi",
        "hello",
        "hey",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
        "ok",
        "cool",
        "got it",
        "makes sense",
        "sounds good",
        "nice",
        "great",
        "cheers",
    ],
    "health": [
        "how's the lab?",
        "is everything ok?",
        "what's the current CPU usage?",
        "how much memory is free?",
        "give me a status update",
        "is the server healthy?",
        "what's the load average right now?",
        "how's RAM usage?",
        "is the server running ok?",
        "how's disk space looking?",
        "what's the system status?",
        "how busy is the server?",
        "any resource issues right now?",
    ],
    "fact": [
        "what port does prometheus run on?",
        "is ollama in docker or bare metal?",
        "where are secrets stored?",
        "what models are available in ollama?",
        "where is the monitoring stack compose file?",
        "what database does the knowledge base use?",
        "which directory is the lab config in?",
        "what's the server's IP address?",
        "how many CPU cores does the server have?",
        "where does grafana run?",
        "how is authentication handled?",
        "what's the prometheus URL?",
        "which port does ollama listen on?",
    ],
    "agentic": [
        "check the lab for anything that seems off",
        "why is prometheus not responding?",
        "restart the monitoring stack",
        "investigate the high memory usage",
        "look at the logs for grafana",
        "find out why the CPU is high",
        "run a full health check on all services",
        "what's wrong with the system?",
        "check if all services are running correctly",
        "show me recent errors in the logs",
        "help me debug this problem",
        "is anything consuming too much disk space?",
        "diagnose why this service is failing",
        # Security queries
        "anything suspicious on the server?",
        "any falco alerts?",
        "what security events happened recently?",
        "what's listening on the server?",
        "show me open ports",
        "what processes are listening?",
        "who is connected to the server right now?",
        "show me active network connections",
        "what's on the LAN?",
        "scan the network",
        "what devices are on 192.168.5.0/24?",
        "how much traffic is the server seeing?",
        "any unusual network activity?",
        "show me the busiest network flows",
        "is anything making suspicious outbound connections?",
    ],
}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class IntentClassifier:
    """Classifies a query into health / fact / agentic using embedding similarity."""

    def __init__(self, ollama: OllamaClient):
        self._ollama = ollama
        self._embeddings: dict[str, list[list[float]]] = {}
        self._ready = False
        self._build()

    def _build(self) -> None:
        """Embed all example sentences once at startup and cache them in memory."""
        try:
            for category, sentences in EXAMPLES.items():
                self._embeddings[category] = [
                    self._ollama.embed(s) for s in sentences
                ]
            self._ready = True
        except Exception:
            # Ollama unavailable or embed failed — degrade gracefully.
            # classify() will return ("agentic", 0.0) until this succeeds.
            self._ready = False

    def classify(self, query: str) -> tuple[Intent, float]:
        """
        Return (intent, confidence score 0-1).
        Always returns ("agentic", 0.0) on any failure or low confidence.
        """
        with get_tracer().start_as_current_span("hal.intent.classify") as span:
            span.set_attribute("intent.query", query[:200])
            if not self._ready:
                span.set_attribute("intent.result", "agentic")
                span.set_attribute("intent.confidence", 0.0)
                span.set_attribute("intent.classifier_ready", False)
                return "agentic", 0.0
            try:
                q_vec = self._ollama.embed(query)
                best_intent: Intent = "agentic"
                best_score = 0.0
                for category, vecs in self._embeddings.items():
                    # Best-matching example within this category
                    score = max(_cosine(q_vec, v) for v in vecs)
                    if score > best_score:
                        best_score = score
                        best_intent = category  # type: ignore[assignment]
                if best_score < THRESHOLD:
                    span.set_attribute("intent.result", "agentic")
                    span.set_attribute("intent.confidence", best_score)
                    span.set_attribute("intent.below_threshold", True)
                    return "agentic", best_score
                span.set_attribute("intent.result", best_intent)
                span.set_attribute("intent.confidence", best_score)
                span.set_attribute("intent.below_threshold", False)
                return best_intent, best_score
            except Exception:
                span.set_attribute("intent.result", "agentic")
                span.set_attribute("intent.confidence", 0.0)
                return "agentic", 0.0
