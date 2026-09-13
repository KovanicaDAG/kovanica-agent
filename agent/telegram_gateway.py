"""
Telegram Bot Gateway for Kovanica Agent.

Allows communicating with Kovanica via Telegram bot.
Forwards messages to agent-api /chat endpoint and returns responses.

Usage:
    python -m agent.telegram_gateway --token BOT_TOKEN --session SESSION_ID
    python -m agent.telegram_gateway --token BOT_TOKEN --api-url http://localhost:13080
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:
    print("python-telegram-bot not installed. Run: pip install python-telegram-bot")
    sys.exit(1)

from .kovanica_sdk import KovanicaClient, ChatReply

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class TelegramGateway:
    """Telegram bot that forwards messages to Kovanica agent."""

    def __init__(
        self,
        bot_token: str,
        api_url: str = "http://localhost:13080",
        api_token: Optional[str] = None,
        default_session: Optional[str] = None,
        allowed_users: Optional[list[int]] = None,
        timeout: int = 180,
    ):
        """
        Initialize the Telegram gateway.

        Args:
            bot_token: Telegram bot token from @BotFather
            api_url: Kovanica agent-api base URL
            api_token: Optional bearer token for dev role
            default_session: Default session ID to use
            allowed_users: List of allowed Telegram user IDs (None = allow all)
            timeout: Request timeout in seconds (default: 180 for slow LLM responses)
        """
        self.bot_token = bot_token
        self.api_url = api_url
        self.api_token = api_token
        self.default_session = default_session or "telegram-default"
        self.allowed_users = set(allowed_users) if allowed_users else None

        # Initialize Kovanica SDK client with longer timeout for LLM responses
        self.client = KovanicaClient(
            base_url=api_url,
            token=api_token,
            timeout=timeout,
        )

        # Build Telegram application
        self.app = Application.builder().token(bot_token).build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up command and message handlers."""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("session", self.cmd_session))
        self.app.add_handler(CommandHandler("new", self.cmd_new_session))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    def _check_user(self, user_id: int) -> bool:
        """Check if user is allowed."""
        if self.allowed_users is None:
            return True
        return user_id in self.allowed_users

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self._check_user(update.effective_user.id):
            await update.message.reply_text("❌ Not authorized to use this bot.")
            return

        await update.message.reply_text(
            "🤖 **Kovanica Agent Connected**\n\n"
            "Send me messages and I'll forward them to the Kovanica agent.\n\n"
            "Commands:\n"
            "  /help - Show this help\n"
            "  /session [id] - Show or set current session\n"
            "  /new - Start a new session\n"
            "  /status - Show agent health status\n\n"
            f"Current session: `{self.default_session}`",
            parse_mode="Markdown",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not self._check_user(update.effective_user.id):
            return
        await self.cmd_start(update, context)

    async def cmd_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /session command - show or set session."""
        if not self._check_user(update.effective_user.id):
            return

        args = context.args
        if not args:
            await update.message.reply_text(
                f"Current session: `{self.default_session}`\n"
                "Usage: `/session <session_id>` to change",
                parse_mode="Markdown",
            )
            return

        new_session = args[0]
        self.default_session = new_session
        await update.message.reply_text(
            f"✅ Session changed to: `{new_session}`",
            parse_mode="Markdown",
        )

    async def cmd_new_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /new command - create new session."""
        if not self._check_user(update.effective_user.id):
            return

        import uuid
        new_session = f"tg-{uuid.uuid4().hex[:8]}"
        self.default_session = new_session
        await update.message.reply_text(
            f"✅ New session created: `{new_session}`",
            parse_mode="Markdown",
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command - check agent health."""
        if not self._check_user(update.effective_user.id):
            return

        try:
            health = self.client.healthz()
            await update.message.reply_text(
                f"🟢 **Agent Status**: {health.get('status', 'unknown')}\n"
                f"Name: {health.get('name', 'unknown')}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text(f"🔴 **Agent Unreachable**: {e}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages."""
        if not self._check_user(update.effective_user.id):
            return

        user_message = update.message.text
        if not user_message:
            return

        # Send typing indicator
        await update.message.chat.send_action("typing")

        try:
            # Send to Kovanica agent
            reply: ChatReply = self.client.chat(self.default_session, user_message)

            if reply.is_error:
                await update.message.reply_text(
                    f"❌ **Error**: {reply.error or reply.detail}",
                    parse_mode="Markdown",
                )
            elif reply.is_pending:
                await update.message.reply_text(
                    f"⏳ **Pending Confirmation**\n\n{reply.reply}\n\n"
                    f"Details: {reply.detail}",
                    parse_mode="Markdown",
                )
            else:
                # Split long messages (Telegram limit: 4096 chars)
                response = reply.reply
                if len(response) > 4000:
                    # Send in chunks
                    for i in range(0, len(response), 4000):
                        chunk = response[i:i+4000]
                        await update.message.reply_text(chunk, parse_mode="Markdown")
                else:
                    await update.message.reply_text(response, parse_mode="Markdown")

        except Exception as e:
            logger.exception("Error handling message")
            await update.message.reply_text(f"❌ **Error**: {str(e)}")

    def run(self) -> None:
        """Run the bot (blocking)."""
        logger.info("Starting Telegram gateway...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Telegram Bot Gateway for Kovanica Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with defaults
  python -m agent.telegram_gateway --token YOUR_BOT_TOKEN

  # Custom API URL and dev token
  python -m agent.telegram_gateway --token YOUR_BOT_TOKEN \\
    --api-url http://localhost:13080 --api-token YOUR_DEV_TOKEN

  # Restrict to specific users
  python -m agent.telegram_gateway --token YOUR_BOT_TOKEN \\
    --allowed-users 123456789 987654321

Environment variables:
  TELEGRAM_BOT_TOKEN    Bot token (alternative to --token)
  KOVANICA_API_URL      Agent API URL (default: http://localhost:13080)
  KOVANICA_API_TOKEN    Dev bearer token
  KOVANICA_SESSION      Default session ID
  TELEGRAM_ALLOWED_USERS  Comma-separated user IDs
        """,
    )

    parser.add_argument(
        "--token",
        default=os.environ.get("TELEGRAM_BOT_TOKEN"),
        help="Telegram bot token from @BotFather",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("KOVANICA_API_URL", "http://localhost:13080"),
        help="Kovanica agent-api base URL",
    )
    parser.add_argument(
        "--api-token",
        default=os.environ.get("KOVANICA_API_TOKEN"),
        help="Bearer token for dev role (optional)",
    )
    parser.add_argument(
        "--session",
        default=os.environ.get("KOVANICA_SESSION", "telegram-default"),
        help="Default session ID",
    )
    parser.add_argument(
        "--allowed-users",
        nargs="+",
        type=int,
        help="Allowed Telegram user IDs (space-separated)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("KOVANICA_TIMEOUT", "180")),
        help="Request timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.token:
        parser.error("Bot token required. Use --token or set TELEGRAM_BOT_TOKEN env var.")

    gateway = TelegramGateway(
        bot_token=args.token,
        api_url=args.api_url,
        api_token=args.api_token,
        default_session=args.session,
        allowed_users=args.allowed_users,
        timeout=args.timeout,
    )

    try:
        gateway.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()