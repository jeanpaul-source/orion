#!/usr/bin/env python3
"""HAL HTTP server — FastAPI wrapper around the HAL agent.
# why locked: Layer 4 — FastAPI HTTP interface; reactivate after REPL (Layer 0) is bulletproof

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
from hal.bootstrap import dispatch_intent, get_system_prompt, setup_clients
from hal.executor import SSHExecutor
from hal.sanitize import strip_tool_call_artifacts
from hal.intent import (
    IntentClassifier,
)  # why: intent.py graduated to Layer 1 — moved from hal/_unlocked/
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import VLLMClient
from hal.logging_utils import setup_logging
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient, start_metrics_heartbeat
from hal.tracing import setup_tracing

# ---------------------------------------------------------------------------
# Server-mode Judge: auto-deny tier 1+ (no TTY available over HTTP)
# ---------------------------------------------------------------------------


class ServerJudge(Judge):
    """Judge variant that auto-denies any action requiring interactive approval.

    Only overrides _request_approval to return False unconditionally.
    The parent approve() already calls _log() after _request_approval returns,
    so we must NOT log here — doing so would produce a duplicate entry with
    status "auto" that inflates approved counts in trust metrics.
    """

    def _request_approval(
        self, action_type: str, detail: str, tier: int, reason: str
    ) -> bool:
        return False  # parent approve() logs the denial


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
    start_metrics_heartbeat()

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

app = FastAPI(
    title="HAL — Orion homelab coordinator", version="1.0.0", lifespan=lifespan
)


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

    # Null Console — suppress Rich output, we only need the return value
    console = Console(file=StringIO(), no_color=True, markup=False, highlight=False)

    classifier: IntentClassifier = _state["classifier"]
    llm: VLLMClient = _state["llm"]
    kb: KnowledgeBase = _state["kb"]
    prom: PrometheusClient = _state["prom"]
    executor: SSHExecutor = _state["executor"]
    judge: Judge = _state["judge"]

    def _run() -> tuple[str, str, str]:
        # Classify intent inside the thread — embed() is a blocking HTTP call
        intent, confidence = classifier.classify(req.message)

        # MemoryStore opens a SQLite connection — must be created in the thread
        # that uses it.  asyncio.to_thread runs in a thread-pool thread, so we
        # open and close a fresh store here rather than reusing one from _state.
        mem = MemoryStore()
        try:
            if req.session_id:
                # Caller provided an explicit session ID — honour it.
                # Create the session on first use (e.g. Telegram bot's tg-<chat_id>).
                session_id = req.session_id
                if not mem.session_exists(session_id):
                    mem.create_session(session_id)
            else:
                session_id = mem.last_session_id() or mem.new_session()
            history = mem.load_turns(session_id)

            response = dispatch_intent(
                req.message,
                history,
                llm,
                prom,
                kb,
                executor,
                judge,
                mem,
                session_id,
                get_system_prompt(),
                console,
                ntopng_url=config.ntopng_url,
                tavily_api_key=config.tavily_api_key,
            )
            return response, session_id, intent
        finally:
            mem.close()

    response, session_id, intent = await asyncio.to_thread(_run)
    response = strip_tool_call_artifacts(response)
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
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8087, help="Bind port (default: 8087)"
    )
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
