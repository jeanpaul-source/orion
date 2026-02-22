"""
ORION Telegram Bot
Mobile interface for homelab management via Telegram

Features:
- Command execution (/status, /query, /action)
- Push notifications for alerts
- Secure (user whitelist)
- Interactive keyboard
- Rich message formatting
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
    )
    from telegram.constants import ParseMode

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logging.warning("python-telegram-bot not installed. Telegram bot disabled.")

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    ORION Telegram Bot for mobile access and notifications.

    Commands:
    - /start - Welcome message and setup
    - /status - System status summary
    - /query <question> - Ask ORION a question
    - /action <command> - Execute an action (with confirmation)
    - /alerts - View recent alerts
    - /help - Show help message
    """

    def __init__(
        self,
        token: str,
        allowed_user_ids: List[int],
        router,
        conversation_manager,
    ):
        """
        Initialize Telegram bot.

        Args:
            token: Telegram bot token (from @BotFather)
            allowed_user_ids: List of allowed Telegram user IDs (security)
            router: ORION intelligence router
            conversation_manager: ORION conversation manager
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError(
                "python-telegram-bot not installed. "
                "Install with: pip install python-telegram-bot"
            )

        self.token = token
        self.allowed_user_ids = set(allowed_user_ids)
        self.router = router
        self.conversation_manager = conversation_manager

        # Build application
        self.application = Application.builder().token(token).build()

        # Register handlers
        self._register_handlers()

        # Alert queue (for push notifications)
        self.alert_queue: asyncio.Queue = asyncio.Queue()
        self.alerts_history: List[Dict[str, Any]] = []

        logger.info(
            f"Telegram bot initialized. Allowed users: {len(self.allowed_user_ids)}"
        )

    def _register_handlers(self):
        """Register command and message handlers."""
        app = self.application

        # Commands
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("query", self.cmd_query))
        app.add_handler(CommandHandler("action", self.cmd_action))
        app.add_handler(CommandHandler("alerts", self.cmd_alerts))

        # Callback query handler (for inline buttons)
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        # Message handler (for conversational queries)
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

    def _check_authorization(self, user_id: int) -> bool:
        """Check if user is authorized."""
        return user_id in self.allowed_user_ids

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        user_id = user.id

        if not self._check_authorization(user_id):
            await update.message.reply_text(
                "🚫 *Access Denied*\n\n"
                f"Your user ID ({user_id}) is not authorized.\n\n"
                "Contact your homelab administrator to grant access.",
                parse_mode=ParseMode.MARKDOWN,
            )
            logger.warning(f"Unauthorized access attempt: {user.username} ({user_id})")
            return

        welcome_message = (
            "🌌 *Welcome to ORION*\n\n"
            "I'm your AI homelab assistant, now accessible from Telegram!\n\n"
            "*Available Commands:*\n"
            "/status - Get system status\n"
            "/query <question> - Ask me anything\n"
            "/action <command> - Execute actions\n"
            "/alerts - View recent alerts\n"
            "/help - Show detailed help\n\n"
            "*Quick Actions:*"
        )

        # Inline keyboard for quick actions
        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("🧠 Query", callback_data="query_prompt"),
            ],
            [
                InlineKeyboardButton("🚨 Alerts", callback_data="alerts"),
                InlineKeyboardButton("❓ Help", callback_data="help"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            welcome_message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
        )

        logger.info(f"User {user.username} ({user_id}) started bot")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._check_authorization(update.effective_user.id):
            return

        help_text = (
            "🌌 *ORION Telegram Bot - Help*\n\n"
            "*Commands:*\n\n"
            "📊 */status* - Get system status\n"
            "Shows health of all services, resource usage, and uptime.\n\n"
            "🧠 */query* `<question>` - Ask ORION\n"
            "Example: `/query What are Kubernetes best practices?`\n"
            "The knowledge base is rebuilding after the Nov 17 fresh start. You'll either get a cited answer or clear rebuild instructions.\n\n"
            "⚙️ */action* `<command>` - Execute action\n"
            "Example: `/action restart vllm`\n"
            "Requires confirmation for safety.\n\n"
            "🚨 */alerts* - View recent alerts\n"
            "Shows critical alerts, warnings, and notifications.\n\n"
            "*Features:*\n"
            "✅ Secure (only authorized users)\n"
            "✅ Push notifications for critical events\n"
            "✅ Conversational interface\n"
            "✅ Rich formatting & buttons\n\n"
            "*Security:*\n"
            f"Your user ID: `{update.effective_user.id}`\n"
            "All commands are logged and audited.\n\n"
            "*Need more help?*\n"
            "Visit the dashboard: https://orion.lab/"
        )

        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._check_authorization(update.effective_user.id):
            return

        await update.message.reply_text("⏳ Gathering system status...")

        try:
            # Get status from watch subsystem
            status = await self.router.watch.get_full_status()

            # Format status message
            status_text = self._format_status(status)

            # Inline keyboard for actions
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Refresh", callback_data="status"),
                    InlineKeyboardButton("📊 Dashboard", url="https://orion.lab/"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                status_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )

        except Exception as e:
            logger.exception("Error getting status")
            await update.message.reply_text(
                f"❌ *Error getting status*\n\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
            )

    async def cmd_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /query command."""
        if not self._check_authorization(update.effective_user.id):
            return

        # Get query text
        query_text = " ".join(context.args) if context.args else None

        if not query_text:
            await update.message.reply_text(
                "🧠 *Query ORION*\n\n"
                "Usage: `/query <your question>`\n\n"
                "Examples:\n"
                "• `/query What are Docker best practices?`\n"
                "• `/query How to optimize PostgreSQL?`\n"
                "• `/query Kubernetes autoscaling guide`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        await update.message.reply_text(
            f"🧠 Searching knowledge base for:\n_{query_text}_",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            # Create session
            session_id = f"telegram_{update.effective_user.id}"
            session = self.conversation_manager.get_session(session_id)

            # Add to history
            session.add_message("user", query_text)

            # Route through intelligence router
            context_data = {
                "session_id": session_id,
                "history": session.get_history(limit=5),
                "source": "telegram",
            }

            response = await self.router.route(query_text, context_data)

            # Add response to history
            session.add_message("assistant", response)

            # Split response if too long (Telegram limit: 4096 chars)
            if len(response) > 4000:
                chunks = [response[i : i + 4000] for i in range(0, len(response), 4000)]
                for chunk in chunks:
                    await update.message.reply_text(
                        chunk, parse_mode=ParseMode.MARKDOWN
                    )
            else:
                await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.exception("Error processing query")
            await update.message.reply_text(
                f"❌ *Error processing query*\n\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
            )

    async def cmd_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /action command (requires confirmation)."""
        if not self._check_authorization(update.effective_user.id):
            return

        action_text = " ".join(context.args) if context.args else None

        if not action_text:
            await update.message.reply_text(
                "⚙️ *Execute Action*\n\n"
                "Usage: `/action <command>`\n\n"
                "Examples:\n"
                "• `/action restart vllm`\n"
                "• `/action check disk space`\n"
                "• `/action update system`\n\n"
                "⚠️ Actions require confirmation for safety.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Show confirmation button
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Confirm", callback_data=f"action_confirm:{action_text}"
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="action_cancel"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚙️ *Confirm Action*\n\n"
            f"Command: `{action_text}`\n\n"
            f"⚠️ This will execute the action on your homelab.\n"
            f"Are you sure?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )

    async def cmd_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alerts command."""
        if not self._check_authorization(update.effective_user.id):
            return

        if not self.alerts_history:
            await update.message.reply_text(
                "🚨 *Alerts*\n\n" "No recent alerts.\n\n" "✅ All systems nominal.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Format alerts (last 10)
        alerts_text = "🚨 *Recent Alerts*\n\n"
        for alert in self.alerts_history[-10:]:
            icon = {"critical": "🔴", "warning": "🟡", "info": "🟢"}.get(
                alert.get("severity", "info"), "🔵"
            )
            time_str = alert.get("timestamp", "Unknown time")
            message = alert.get("message", "No message")
            alerts_text += f"{icon} *{time_str}*\n{message}\n\n"

        await update.message.reply_text(alerts_text, parse_mode=ParseMode.MARKDOWN)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks."""
        query = update.callback_query
        await query.answer()

        if not self._check_authorization(query.from_user.id):
            return

        data = query.data

        # Route callback
        if data == "status":
            # Refresh status
            await query.edit_message_text("⏳ Refreshing status...")
            await self.cmd_status(update, context)

        elif data == "query_prompt":
            await query.edit_message_text(
                "🧠 *Ask ORION*\n\nSend me your question or use:\n`/query <your question>`",
                parse_mode=ParseMode.MARKDOWN,
            )

        elif data == "alerts":
            await self.cmd_alerts(update, context)

        elif data == "help":
            await self.cmd_help(update, context)

        elif data.startswith("action_confirm:"):
            # Execute confirmed action
            action = data.replace("action_confirm:", "")
            await query.edit_message_text(
                f"⚙️ Executing: `{action}`...", parse_mode=ParseMode.MARKDOWN
            )

            try:
                # Route through action subsystem
                result = await self.router.action.execute(action)
                await query.message.reply_text(
                    f"✅ *Action Complete*\n\n{result}", parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await query.message.reply_text(
                    f"❌ *Action Failed*\n\n`{str(e)}`", parse_mode=ParseMode.MARKDOWN
                )

        elif data == "action_cancel":
            await query.edit_message_text("❌ Action cancelled.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (conversational mode)."""
        if not self._check_authorization(update.effective_user.id):
            return

        # Treat as query
        context.args = update.message.text.split()
        await self.cmd_query(update, context)

    def _format_status(self, status: Dict[str, Any]) -> str:
        """Format status dict as Telegram message."""
        services = status.get("services", {})

        text = "📊 *ORION System Status*\n\n"

        # Service status
        for service_name, service_data in services.items():
            status_icon = {"healthy": "🟢", "degraded": "🟡", "down": "🔴"}.get(
                service_data.get("status", "unknown"), "⚪"
            )
            text += f"{status_icon} *{service_name.replace('_', ' ').title()}*: "
            text += f"{service_data.get('status', 'unknown').upper()}\n"

        # Resources
        resources = status.get("resources", {})
        text += "\n*Resources:*\n"

        if "gpu" in resources:
            gpu = resources["gpu"]
            text += f"🎮 GPU: {gpu.get('percent', 0):.0f}% ({gpu.get('used', 0) / 1024**3:.1f}GB / {gpu.get('total', 0) / 1024**3:.1f}GB)\n"

        if "disk" in resources:
            disk = resources["disk"]
            text += f"💾 Disk: {disk.get('percent', 0):.0f}% ({disk.get('used', 0) / 1024**3:.0f}GB / {disk.get('total', 0) / 1024**3:.0f}GB)\n"

        if "memory" in resources:
            mem = resources["memory"]
            text += f"🧠 Memory: {mem.get('percent', 0):.0f}% ({mem.get('used', 0) / 1024**3:.0f}GB / {mem.get('total', 0) / 1024**3:.0f}GB)\n"

        text += f"\n🕐 Updated: {datetime.now().strftime('%H:%M:%S')}"

        return text

    async def send_notification(
        self,
        user_id: int,
        message: str,
        severity: str = "info",
        buttons: Optional[List[List[InlineKeyboardButton]]] = None,
    ):
        """
        Send push notification to user.

        Args:
            user_id: Telegram user ID
            message: Notification message
            severity: "critical", "warning", or "info"
            buttons: Optional inline keyboard buttons
        """
        if user_id not in self.allowed_user_ids:
            logger.warning(
                f"Attempted to send notification to unauthorized user: {user_id}"
            )
            return

        icon = {"critical": "🔴", "warning": "🟡", "info": "🟢"}.get(severity, "🔵")
        formatted_message = f"{icon} *Alert*\n\n{message}"

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        try:
            await self.application.bot.send_message(
                chat_id=user_id,
                text=formatted_message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )

            # Add to alerts history
            self.alerts_history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "severity": severity,
                    "message": message,
                    "user_id": user_id,
                }
            )

            logger.info(f"Sent {severity} notification to user {user_id}")

        except Exception:
            logger.exception("Failed to send notification")

    async def start(self):
        """Start the bot."""
        logger.info("Starting Telegram bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram bot started successfully")

    async def stop(self):
        """Stop the bot."""
        logger.info("Stopping Telegram bot...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        logger.info("Telegram bot stopped")
