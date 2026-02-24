#!/usr/bin/env python3
"""HAL HTTP server — FastAPI wrapper around the HAL agent.

Run directly:    python hal/server.py [--host 127.0.0.1] [--port 8087]
Or via module:   python -m hal.server

Tier 1+ judge actions (write/restart/etc.) are auto-denied in HTTP mode
because there is no TTY for interactive approval prompts.  Use the CLI
(python -m hal) for those operations.

Endpoints:
  GET  /health  — liveness probe
  POST /chat    — send a message, get a response + session_id + intent
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable so `import hal.*` works regardless
# of how this script is launched (e.g. python hal/server.py from outside).
_workspace_root = str(Path(__file__).resolve().parent.parent)
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

import argparse
import asyncio
from contextlib import asynccontextmanager
from io import StringIO
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rich.console import Console

import hal.config as cfg
from hal.agent import run_agent, run_conversational, run_fact, run_health
from hal.executor import SSHExecutor
from hal.intent import IntentClassifier
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import VLLMClient
from hal.logging_utils import setup_logging
from hal.main import SYSTEM_PROMPT, setup_clients
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient
from hal.tracing import setup_tracing


# ---------------------------------------------------------------------------
# Server-mode Judge: auto-deny tier 1+ (no TTY available over HTTP)
# ---------------------------------------------------------------------------

class ServerJudge(Judge):
    """Judge variant that auto-denies any action requiring interactive approval."""

    def _request_approval(
        self, action_type: str, detail: str, tier: int, reason: str
    ) -> bool:
        self._log(action_type, detail, tier, approved=False, auto=True, reason=reason)
        return False  # deny non-read-only ops silently in server mode


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: str


# ---------------------------------------------------------------------------
# Application lifespan — initialise / teardown shared clients
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: RUF029
    import logging as _logging

    _log = _logging.getLogger("hal.server")
    config = cfg.load()
    setup_logging()
    setup_tracing()

    try:
        llm, embed, tunnels = setup_clients(config)
        _state.update(
            {
                "config": config,
                "llm": llm,
                "embed": embed,
                "tunnels": tunnels,
                "kb": KnowledgeBase(config.pgvector_dsn, embed),
                "prom": PrometheusClient(config.prometheus_url),
                "executor": SSHExecutor(config.lab_host, config.lab_user),
                "judge": ServerJudge(llm=llm),
                # MemoryStore (SQLite) is NOT stored here — SQLite connections
                # cannot be shared across threads.  A fresh MemoryStore is
                # opened per-request inside asyncio.to_thread().
                "classifier": IntentClassifier(embed),
            }
        )
        _log.info("HAL services connected — server ready")
    except SystemExit as exc:
        # setup_clients calls sys.exit(1) when vLLM/Ollama aren't reachable.
        # Catch it so uvicorn can still start in degraded mode.
        # /chat will return 503 until services come up.
        _state["_startup_error"] = (
            f"Services unavailable (exit {exc.code}). "
            "Start vLLM and Ollama then restart the server."
        )
        _log.warning("HAL started in degraded mode: %s", _state["_startup_error"])

    yield  # ---------- server is running ----------

    for tunnel in _state.get("tunnels", []):
        tunnel.stop()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="HAL — Orion homelab coordinator", version="1.0.0", lifespan=lifespan)



@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness check — returns 200 once the server is ready."""
    if "_startup_error" in _state:
        return {"status": "degraded", "detail": _state["_startup_error"]}
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Send a message to HAL; returns the assistant response."""
    if "_startup_error" in _state:
        raise HTTPException(status_code=503, detail=_state["_startup_error"])
    if not _state:
        raise HTTPException(status_code=503, detail="Server not yet initialised")

    config = _state["config"]

    # Classify intent (HTTP client call — safe outside the thread)
    classifier: IntentClassifier = _state["classifier"]
    intent, confidence = classifier.classify(req.message)

    # Null Console — suppress Rich output, we only need the return value
    console = Console(file=StringIO(), no_color=True, markup=False, highlight=False)

    llm: VLLMClient = _state["llm"]
    kb: KnowledgeBase = _state["kb"]
    prom: PrometheusClient = _state["prom"]
    executor: SSHExecutor = _state["executor"]
    judge: Judge = _state["judge"]

    def _run() -> tuple[str, str]:
        # MemoryStore opens a SQLite connection — must be created in the thread
        # that uses it.  asyncio.to_thread runs in a thread-pool thread, so we
        # open and close a fresh store here rather than reusing one from _state.
        mem = MemoryStore()
        try:
            session_id = req.session_id or mem.last_session_id() or mem.new_session()
            if not mem.session_exists(session_id):
                session_id = mem.new_session()
            history = mem.load_turns(session_id)

            if intent == "conversational":
                response = run_conversational(
                    req.message, history, llm, mem, session_id, SYSTEM_PROMPT, console
                )
            elif intent == "health":
                response = run_health(
                    req.message, history, llm, prom, mem, session_id, SYSTEM_PROMPT, console
                )
            elif intent == "fact":
                response = run_fact(
                    req.message, history, llm, kb, mem, session_id, SYSTEM_PROMPT, console
                )
            else:
                response = run_agent(
                    req.message,
                    history,
                    llm,
                    kb,
                    prom,
                    executor,
                    judge,
                    mem,
                    session_id,
                    SYSTEM_PROMPT,
                    console,
                    ntopng_url=config.ntopng_url,
                )
            return response, session_id
        finally:
            mem.close()

    response, session_id = await asyncio.to_thread(_run)
    return ChatResponse(response=response, session_id=session_id, intent=intent)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HAL HTTP server")
    parser.add_argument(
        "--server",
        action="store_true",
        default=True,
        help="Run as HTTP server (default; flag accepted for compatibility)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8087, help="Bind port (default: 8087)")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
