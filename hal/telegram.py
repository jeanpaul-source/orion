"""Telegram bot interface for HAL.
# why locked: Layer 4 — Telegram bot interface; reactivate after server.py (Layer 4) is stable

Thin async wrapper that POSTs to the HAL HTTP server's ``/chat`` endpoint.
Inherits ``ServerJudge`` behaviour (tier 0 only — no interactive approvals).
Uses long-polling (no webhook — no public HTTPS on the homelab).

Run directly::

    python hal/telegram.py

Or via systemd::

    systemctl --user start telegram.service
"""

import logging
import re
import sys
import time

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

import hal.config as cfg

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HAL_CHAT_URL = "http://127.0.0.1:8087/chat"
TIMEOUT = 120.0  # LLM inference can be slow on the 3090 Ti
MAX_TG_LEN = 4096  # Telegram message length limit

_SECRETS_RE = re.compile(r"/run/homelab-secrets/\S+")

# ---------------------------------------------------------------------------
# Session tracking
# ---------------------------------------------------------------------------

# chat_id → current session_id.  Default (absent) resolves to "tg-{chat_id}".
# /new overrides the value with a timestamped variant.
# On bot restart the dict is empty → falls back to the original session
# (full history preserved).
_sessions: dict[int, str] = {}


def _get_session_id(chat_id: int) -> str:
    return _sessions.get(chat_id, f"tg-{chat_id}")


# ---------------------------------------------------------------------------
# Output sanitisation
# ---------------------------------------------------------------------------


def _sanitize(text: str) -> str:
    """Redact sensitive paths and enforce Telegram length limit."""
    text = _SECRETS_RE.sub("[redacted]", text)
    if len(text) > MAX_TG_LEN:
        text = text[: MAX_TG_LEN - 5] + "\n[…]"
    return text


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

# Populated in main() after config is loaded.
ALLOWED_USER_ID: int = 0


def _authorized(update: Update) -> bool:
    return (
        update.effective_user is not None
        and update.effective_user.id == ALLOWED_USER_ID
    )


async def cmd_start(update: Update, context) -> None:  # noqa: ARG001
    """/start — greeting."""
    if not _authorized(update):
        return
    if update.message is None:
        return
    await update.message.reply_text("HAL online. Send any message.")


async def cmd_new(update: Update, context) -> None:  # noqa: ARG001
    """/new — reset session."""
    if not _authorized(update):
        return
    if update.effective_chat is None or update.message is None:
        return
    chat_id = update.effective_chat.id
    _sessions[chat_id] = f"tg-{chat_id}-{int(time.time())}"
    await update.message.reply_text("Session reset.")


async def handle_message(update: Update, context) -> None:  # noqa: ARG001
    """Process a plain-text message: thinking → POST /chat → edit reply."""
    if not _authorized(update):
        return
    if not update.message or not update.message.text or update.effective_chat is None:
        return

    thinking = await update.message.reply_text("thinking\u2026")
    session_id = _get_session_id(update.effective_chat.id)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                HAL_CHAT_URL,
                json={"message": update.message.text, "session_id": session_id},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = _sanitize(data["response"])
    except httpx.ConnectError:
        reply = "HAL server is offline."
        log.warning("Could not connect to HAL HTTP server at %s", HAL_CHAT_URL)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            reply = "HAL is starting up — try again in a minute."
        else:
            reply = f"HAL returned an error (HTTP {exc.response.status_code})."
        log.warning("HAL HTTP error: %s", exc)
    except Exception:
        reply = "Something went wrong. Check the server logs."
        log.exception("Unexpected error in handle_message")

    await thinking.edit_text(reply)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        level=logging.INFO,
    )

    config = cfg.load()

    if not config.telegram_bot_token:
        log.error("TELEGRAM_BOT_TOKEN is not set — exiting.")
        sys.exit(1)
    if not config.telegram_allowed_user_id:
        log.error("TELEGRAM_ALLOWED_USER_ID is not set — exiting.")
        sys.exit(1)

    global ALLOWED_USER_ID  # noqa: PLW0603
    ALLOWED_USER_ID = config.telegram_allowed_user_id

    app = Application.builder().token(config.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info(
        "Telegram bot starting (allowed_user_id=%d)", config.telegram_allowed_user_id
    )
    app.run_polling(allowed_updates=[Update.MESSAGE])


if __name__ == "__main__":
    main()
