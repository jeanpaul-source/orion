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
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rich.console import Console

import json as _json

import hal.config as cfg
from hal.bootstrap import dispatch_intent, get_system_prompt, setup_clients
from hal.executor import SSHExecutor
from hal.sanitize import strip_tool_call_artifacts
from hal.intent import (
    IntentClassifier,
)  # why: intent.py graduated to Layer 1 — moved from hal/_unlocked/
from hal.judge import AUDIT_LOG, Judge
from hal.knowledge import KnowledgeBase
from hal.llm import VLLMClient
from hal.logging_utils import setup_logging
from hal.memory import MemoryStore
from hal.notify import send_ntfy_simple
from hal.prometheus import PrometheusClient, start_metrics_heartbeat
from hal.tracing import setup_tracing

import logging as _logging

_log = _logging.getLogger("hal.server")

# ---------------------------------------------------------------------------
# Retry constants — how long to wait for backends after a cold boot
# ---------------------------------------------------------------------------
_RETRY_DELAY = 15  # seconds between attempts
_MAX_RETRIES = 40  # 40 × 15s = 600s = 10 minutes

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


def _populate_state(
    config: cfg.Config, llm: VLLMClient, embed: Any, tunnels: list
) -> None:
    """Fill *_state* with fully-initialised HAL clients.

    Idempotent — safe to call again on retry success.
    """
    _state.update(
        {
            "config": config,
            "llm": llm,
            "embed": embed,
            "tunnels": tunnels,
            "kb": KnowledgeBase(config.pgvector_dsn, embed),
            "prom": PrometheusClient(config.prometheus_url),
            "executor": SSHExecutor(config.lab_host, config.lab_user),
            "judge": ServerJudge(
                llm=llm,
                extra_sensitive_paths=tuple(
                    p
                    for p in config.judge_extra_sensitive_paths.split(":")
                    if p.strip()
                ),
            ),
            # MemoryStore (SQLite) is NOT stored here — SQLite connections
            # cannot be shared across threads.  A fresh MemoryStore is
            # opened per-request inside asyncio.to_thread().
            "classifier": IntentClassifier(embed),
        }
    )
    _state.pop("_startup_error", None)
    _state.pop("_retry_task", None)


def _log_recovery_event(attempt: int, elapsed_seconds: int) -> None:
    """Write a structured recovery event to the audit log (JSON-lines).

    Uses the same format as ``Judge._log()`` so that trust metrics, log
    parsers, and future autonomy features consume it uniformly.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier": 0,
        "status": "auto",
        "action": "system",
        "detail": "recovered_from_degraded_start",
        "reason": f"backends connected on attempt {attempt} after {elapsed_seconds}s",
    }
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as f:
        f.write(_json.dumps(entry, ensure_ascii=False) + "\n")


async def _retry_init(config: cfg.Config) -> None:
    """Background task: retry backend connection until services come up.

    Called automatically when the initial ``setup_clients()`` fails at boot.
    Retries every ``_RETRY_DELAY`` seconds, up to ``_MAX_RETRIES`` times
    (~10 minutes total).  On success, populates ``_state`` and clears the
    degraded flag so ``/health`` returns ``ok`` and ``/chat`` starts serving.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        await asyncio.sleep(_RETRY_DELAY)
        _log.info(
            "Backend retry %d/%d — attempting to connect...",
            attempt,
            _MAX_RETRIES,
        )
        try:
            llm, embed, tunnels = await asyncio.to_thread(setup_clients, config)
        except SystemExit:
            _log.info(
                "Retry %d/%d — backends not ready yet",
                attempt,
                _MAX_RETRIES,
            )
            continue

        _populate_state(config, llm, embed, tunnels)
        elapsed = attempt * _RETRY_DELAY
        recovery_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _state["_last_recovery"] = recovery_ts
        _state["_recovery_attempts"] = attempt

        # Run post-boot health checks to give the operator a full picture
        health_summary = ""
        try:
            from hal.healthcheck import (
                run_all_checks,
                summary_line,
                format_health_table,
            )

            health_results = run_all_checks(config)
            health_summary = summary_line(health_results)
            _state["_post_boot_health"] = format_health_table(health_results)
        except Exception as exc:
            _log.warning("Post-boot health check failed: %s", exc)
            health_summary = "Health check could not run."

        _state["_startup_context"] = (
            f"Note: this server recovered from a degraded start at "
            f"{recovery_ts} UTC after {attempt} retry attempt{'s' if attempt != 1 else ''} "
            f"(backends were unavailable for ~{elapsed} seconds). "
            f"Post-boot health: {health_summary}"
        )
        _log_recovery_event(attempt, elapsed)
        # Notify operator via ntfy
        ntfy_url = getattr(config, "ntfy_url", "") or ""
        if ntfy_url:
            ntfy_lines = [
                f"Server recovered from degraded start after {elapsed}s ({attempt} retries).",
            ]
            if health_summary:
                ntfy_lines.append(health_summary)
            send_ntfy_simple(
                ntfy_url,
                ntfy_lines,
                urgency="default",
                title="Orion Recovery — the-lab",
                tags="white_check_mark,server",
            )
        _log.info(
            "Backends connected on attempt %d — server fully operational",
            attempt,
        )
        return

    _log.error(
        "Gave up connecting to backends after %d retries (%ds). "
        "Manual restart required.",
        _MAX_RETRIES,
        _MAX_RETRIES * _RETRY_DELAY,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: RUF029
    config = cfg.load()
    setup_logging()
    setup_tracing()
    start_metrics_heartbeat()

    try:
        llm, embed, tunnels = setup_clients(config)
        _populate_state(config, llm, embed, tunnels)
        _log.info("HAL services connected — server ready")
    except SystemExit as exc:
        # setup_clients calls sys.exit(1) when vLLM/Ollama aren't reachable.
        # Start in degraded mode and retry in background until they come up.
        _state["_startup_error"] = (
            f"Services unavailable (exit {exc.code}). Retrying in background..."
        )
        _log.warning(
            "HAL started in degraded mode — retrying every %ds (up to %ds)",
            _RETRY_DELAY,
            _RETRY_DELAY * _MAX_RETRIES,
        )
        _state["_retry_task"] = asyncio.create_task(_retry_init(config))

    yield  # ---------- server is running ----------

    # Cancel any in-flight retry task
    retry_task = _state.pop("_retry_task", None)
    if retry_task and not retry_task.done():
        retry_task.cancel()

    for tunnel in _state.get("tunnels", []):
        tunnel.stop()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="HAL — Orion homelab coordinator", version="1.0.0", lifespan=lifespan
)


@app.get("/health")
async def health_check() -> dict[str, str | int]:
    """Liveness check — returns 200 once the server is ready.

    After a degraded→recovered transition, includes ``last_recovery``
    (ISO timestamp) and ``recovery_attempts`` count.
    """
    if "_startup_error" in _state:
        return {"status": "degraded", "detail": _state["_startup_error"]}
    result: dict[str, str | int] = {"status": "ok"}
    if "_last_recovery" in _state:
        result["last_recovery"] = _state["_last_recovery"]
        result["recovery_attempts"] = _state["_recovery_attempts"]
    return result


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

            system_prompt = get_system_prompt(config)
            startup_ctx = _state.get("_startup_context")
            if startup_ctx:
                system_prompt += f"\n\n── STARTUP EVENT ──\n{startup_ctx}"

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
                system_prompt,
                console,
                ntopng_url=config.ntopng_url,
                tavily_api_key=config.tavily_api_key,
                config=config,
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
