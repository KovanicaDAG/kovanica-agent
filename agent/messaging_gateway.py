"""
Multi-Platform Messaging Gateway Framework for Kovanica Agent.

Provides unified interface for Telegram, Discord, Slack, and Matrix.
"""
from __future__ import annotations

import abc
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from agent.kovanica_sdk import KovanicaClient, ChatReply

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Unified message format across platforms."""
    platform: str
    user_id: str
    username: Optional[str]
    text: str
    channel_id: Optional[str] = None
    thread_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class GatewayConfig:
    """Configuration for a messaging gateway."""
    platform: str
    bot_token: str
    allowed_users: Optional[List[str]] = None
    api_url: str = "http://localhost:13080"
    api_token: Optional[str] = None
    default_session: str = "gateway-default"
    timeout: int = 180


class BaseGateway(abc.ABC):
    """Abstract base class for messaging gateways."""
    
    def __init__(self, config: GatewayConfig):
        self.config = config
        self.client = KovanicaClient(
            base_url=config.api_url,
            token=config.api_token,
            timeout=config.timeout,
        )
        self.default_session = config.default_session
        self.allowed_users = set(config.allowed_users) if config.allowed_users else None
        self._running = False
    
    def _check_user(self, user_id: str) -> bool:
        """Check if user is allowed."""
        if self.allowed_users is None:
            return True
        return user_id in self.allowed_users
    
    def _get_session_id(self, channel_id: Optional[str], thread_id: Optional[str]) -> str:
        """Generate session ID from channel/thread."""
        if thread_id:
            return f"{self.default_session}-{thread_id}"
        elif channel_id:
            return f"{self.default_session}-{channel_id}"
        return self.default_session
    
    async def process_message(self, message: Message) -> Optional[str]:
        """Process incoming message and return response."""
        if not self._check_user(message.user_id):
            return "❌ Not authorized to use this bot."
        
        session_id = self._get_session_id(message.channel_id, message.thread_id)
        
        try:
            reply: ChatReply = self.client.chat(session_id, message.text)
            
            if reply.is_error:
                return f"❌ **Error**: {reply.error or reply.detail}"
            elif reply.is_pending:
                return f"⏳ **Pending Confirmation**\n\n{reply.reply}\n\nDetails: {reply.detail}"
            else:
                return reply.reply
                
        except Exception as e:
            logger.exception("Error processing message")
            return f"❌ **Error**: {str(e)}"
    
    @abc.abstractmethod
    async def start(self) -> None:
        """Start the gateway."""
        pass
    
    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the gateway."""
        pass
    
    @abc.abstractmethod
    async def send_message(self, channel_id: str, text: str, thread_id: Optional[str] = None) -> bool:
        """Send a message to a channel."""
        pass


class TelegramGateway(BaseGateway):
    """Telegram bot gateway using python-telegram-bot."""
    
    def __init__(self, config: GatewayConfig):
        super().__init__(config)
        self._app = None
        self._bot_token = config.bot_token
    
    async def start(self) -> None:
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
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
            return
        
        self._app = Application.builder().token(self._bot_token).build()
        
        # Add handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("session", self._cmd_session))
        self._app.add_handler(CommandHandler("new", self._cmd_new_session))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        
        self._running = True
        logger.info("Starting Telegram gateway...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    async def stop(self) -> None:
        if self._app:
            self._running = False
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
    
    async def send_message(self, channel_id: str, text: str, thread_id: Optional[str] = None) -> bool:
        if not self._app:
            return False
        try:
            chat_id = int(channel_id)
            if thread_id:
                await self._app.bot.send_message(chat_id=chat_id, text=text, message_thread_id=int(thread_id))
            else:
                await self._app.bot.send_message(chat_id=chat_id, text=text)
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._cmd_start(update, context)
    
    async def _cmd_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_user(update.effective_user.id):
            return
        
        user_message = update.message.text
        if not user_message:
            return
        
        # Send typing indicator
        await update.message.chat.send_action("typing")
        
        # Create message object
        message = Message(
            platform="telegram",
            user_id=str(update.effective_user.id),
            username=update.effective_user.username,
            text=user_message,
            channel_id=str(update.effective_chat.id),
            thread_id=str(update.message.message_thread_id) if update.message.message_thread_id else None,
        )
        
        # Process and reply
        response = await self.process_message(message)
        if response:
            # Split long messages
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000], parse_mode="Markdown")
            else:
                await update.message.reply_text(response, parse_mode="Markdown")


class DiscordGateway(BaseGateway):
    """Discord bot gateway using discord.py."""
    
    def __init__(self, config: GatewayConfig):
        super().__init__(config)
        self._bot = None
        self._bot_token = config.bot_token
    
    async def start(self) -> None:
        try:
            import discord
            from discord.ext import commands
        except ImportError:
            logger.error("discord.py not installed. Run: pip install discord.py")
            return
        
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        
        self._bot = commands.Bot(command_prefix="/", intents=intents)
        
        @self._bot.event
        async def on_ready():
            logger.info(f"Discord gateway logged in as {self._bot.user}")
        
        @self._bot.command(name="start")
        async def cmd_start(ctx):
            if not self._check_user(str(ctx.author.id)):
                await ctx.send("❌ Not authorized to use this bot.")
                return
            await ctx.send(
                "🤖 **Kovanica Agent Connected**\n\n"
                "Send me messages and I'll forward them to the Kovanica agent.\n\n"
                "Commands:\n"
                "  /help - Show this help\n"
                "  /session [id] - Show or set current session\n"
                "  /new - Start a new session\n"
                "  /status - Show agent health status\n\n"
                f"Current session: `{self.default_session}`",
            )
        
        @self._bot.command(name="help")
        async def cmd_help(ctx):
            await cmd_start(ctx)
        
        @self._bot.command(name="session")
        async def cmd_session(ctx, *, session_id: str = None):
            if not self._check_user(str(ctx.author.id)):
                return
            
            if not session_id:
                await ctx.send(f"Current session: `{self.default_session}`\nUsage: `/session <session_id>` to change")
                return
            
            self.default_session = session_id
            await ctx.send(f"✅ Session changed to: `{session_id}`")
        
        @self._bot.command(name="status")
        async def cmd_status(ctx):
            if not self._check_user(str(ctx.author.id)):
                return
            
            try:
                health = self.client.healthz()
                await ctx.send(f"🟢 **Agent Status**: {health.get('status', 'unknown')}\nName: {health.get('name', 'unknown')}")
            except Exception as e:
                await ctx.send(f"🔴 **Agent Unreachable**: {e}")
        
        @self._bot.event
        async def on_message(message):
            if message.author.bot:
                return
            
            if not self._check_user(str(message.author.id)):
                return
            
            # Process commands first
            await self._bot.process_commands(message)
            
            # If not a command, process as chat
            if not message.content.startswith("/"):
                async with message.channel.typing():
                    message_obj = Message(
                        platform="discord",
                        user_id=str(message.author.id),
                        username=str(message.author),
                        text=message.content,
                        channel_id=str(message.channel.id),
                        thread_id=str(message.thread.id) if message.thread else None,
                    )
                    
                    response = await self.process_message(message_obj)
                    if response:
                        # Split long messages
                        if len(response) > 2000:
                            for i in range(0, len(response), 2000):
                                await message.channel.send(response[i:i+2000])
                        else:
                            await message.channel.send(response)
        
        self._running = True
        logger.info("Starting Discord gateway...")
        await self._bot.start(self._bot_token)
    
    async def stop(self) -> None:
        if self._bot:
            self._running = False
            await self._bot.close()
    
    async def send_message(self, channel_id: str, text: str, thread_id: Optional[str] = None) -> bool:
        if not self._bot:
            return False
        try:
            channel = self._bot.get_channel(int(channel_id))
            if channel:
                if thread_id:
                    thread = self._bot.get_channel(int(thread_id))
                    if thread:
                        await thread.send(text)
                else:
                    await channel.send(text)
                return True
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
        return False


class SlackGateway(BaseGateway):
    """Slack bot gateway using slack_bolt."""
    
    def __init__(self, config: GatewayConfig):
        super().__init__(config)
        self._app = None
        self._bot_token = config.bot_token
        self._signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
    
    async def start(self) -> None:
        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        except ImportError:
            logger.error("slack_bolt not installed. Run: pip install slack_bolt")
            return
        
        if not self._signing_secret:
            logger.error("SLACK_SIGNING_SECRET environment variable required")
            return
        
        self._app = AsyncApp(
            token=self._bot_token,
            signing_secret=self._signing_secret,
        )
        
        @self._app.command("/kovanica")
        async def cmd_kovanica(ack, say, command):
            await ack()
            user_id = command["user_id"]
            
            if not self._check_user(user_id):
                await say("❌ Not authorized to use this bot.")
                return
            
            text = command["text"].strip()
            if not text:
                await say(
                    "🤖 **Kovanica Agent Connected**\n\n"
                    "Send me messages and I'll forward them to the Kovanica agent.\n\n"
                    "Commands:\n"
                    "  `/kovanica help` - Show this help\n"
                    "  `/kovanica session [id]` - Show or set current session\n"
                    "  `/kovanica new` - Start a new session\n"
                    "  `/kovanica status` - Show agent health status\n\n"
                    f"Current session: `{self.default_session}`",
                )
                return
            
            parts = text.split(maxsplit=1)
            subcommand = parts[0].lower()
            
            if subcommand == "help":
                await cmd_help(say)
            elif subcommand == "session":
                if len(parts) < 2:
                    await say(f"Current session: `{self.default_session}`\nUsage: `/kovanica session <session_id>` to change")
                else:
                    self.default_session = parts[1]
                    await say(f"✅ Session changed to: `{parts[1]}`")
            elif subcommand == "status":
                try:
                    health = self.client.healthz()
                    await say(f"🟢 **Agent Status**: {health.get('status', 'unknown')}\nName: {health.get('name', 'unknown')}")
                except Exception as e:
                    await say(f"🔴 **Agent Unreachable**: {e}")
            else:
                await say(f"Unknown subcommand: {subcommand}. Use `/kovanica help` for help.")
        
        @self._app.event("app_mention")
        async def handle_mention(event, say):
            user_id = event["user"]
            if not self._check_user(user_id):
                return
            
            text = event["text"]
            # Remove bot mention
            import re
            text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
            
            if not text:
                return
            
            message = Message(
                platform="slack",
                user_id=user_id,
                username=user_id,
                text=text,
                channel_id=event["channel"],
                thread_id=event.get("thread_ts"),
            )
            
            response = await self.process_message(message)
            if response:
                await say(response)
        
        @self._app.event("message")
        async def handle_message(event, say):
            # Only respond to DMs, not channel messages (unless mentioned)
            if event.get("channel_type") == "im":
                user_id = event["user"]
                if not self._check_user(user_id):
                    return
                
                text = event["text"]
                if not text:
                    return
                
                message = Message(
                    platform="slack",
                    user_id=user_id,
                    username=user_id,
                    text=text,
                    channel_id=event["channel"],
                    thread_id=event.get("thread_ts"),
                )
                
                response = await self.process_message(message)
                if response:
                    await say(response)
        
        self._running = True
        logger.info("Starting Slack gateway...")
        
        # Use Socket Mode for simpler deployment
        app_token = os.environ.get("SLACK_APP_TOKEN")
        if app_token:
            handler = AsyncSocketModeHandler(self._app, app_token)
            await handler.start_async()
        else:
            # Fallback to HTTP mode (requires public URL)
            logger.warning("SLACK_APP_TOKEN not set, using HTTP mode (requires public URL)")
            await self._app.start_async()
    
    async def stop(self) -> None:
        if self._app:
            self._running = False
            await self._app.stop_async()
    
    async def send_message(self, channel_id: str, text: str, thread_id: Optional[str] = None) -> bool:
        if not self._app:
            return False
        try:
            await self._app.client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_id,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")
            return False


class MatrixGateway(BaseGateway):
    """Matrix bot gateway using matrix-nio."""
    
    def __init__(self, config: GatewayConfig):
        super().__init__(config)
        self._client = None
        self._homeserver = os.environ.get("MATRIX_HOMESERVER", "https://matrix.org")
        self._user_id = os.environ.get("MATRIX_USER_ID")
        self._access_token = config.bot_token  # Use bot_token as access token
    
    async def start(self) -> None:
        try:
            from nio import AsyncClient, MatrixRoom, RoomMessageText
        except ImportError:
            logger.error("matrix-nio not installed. Run: pip install matrix-nio")
            return
        
        if not self._user_id or not self._access_token:
            logger.error("MATRIX_USER_ID and MATRIX_ACCESS_TOKEN environment variables required")
            return
        
        self._client = AsyncClient(self._homeserver, self._user_id)
        self._client.access_token = self._access_token
        self._client.user_id = self._user_id
        
        @self._client.on(RoomMessageText)
        async def message_callback(room: MatrixRoom, event: RoomMessageText):
            if event.sender == self._user_id:
                return  # Ignore own messages
            
            if not self._check_user(event.sender):
                return
            
            message = Message(
                platform="matrix",
                user_id=event.sender,
                username=event.sender,
                text=event.body,
                channel_id=room.room_id,
                thread_id=None,  # Matrix doesn't have threads in same way
            )
            
            response = await self.process_message(message)
            if response:
                await self._client.room_send(
                    room_id=room.room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": response},
                )
        
        self._running = True
        logger.info("Starting Matrix gateway...")
        await self._client.login(self._access_token)
        await self._client.sync_forever(timeout=30000)
    
    async def stop(self) -> None:
        if self._client:
            self._running = False
            await self._client.close()
    
    async def send_message(self, channel_id: str, text: str, thread_id: Optional[str] = None) -> bool:
        if not self._client:
            return False
        try:
            await self._client.room_send(
                room_id=channel_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": text},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Matrix message: {e}")
            return False


# Gateway factory
GATEWAYS: Dict[str, type] = {
    "telegram": TelegramGateway,
    "discord": DiscordGateway,
    "slack": SlackGateway,
    "matrix": MatrixGateway,
}


def create_gateway(platform: str, config: GatewayConfig) -> Optional[BaseGateway]:
    """Create a gateway instance for the given platform."""
    gateway_class = GATEWAYS.get(platform.lower())
    if gateway_class:
        return gateway_class(config)
    return None


async def run_gateways(configs: List[GatewayConfig]) -> None:
    """Run multiple gateways concurrently."""
    gateways = []
    for config in configs:
        gateway = create_gateway(config.platform, config)
        if gateway:
            gateways.append(gateway)
    
    if not gateways:
        logger.error("No valid gateways configured")
        return
    
    # Start all gateways
    tasks = [gateway.start() for gateway in gateways]
    await asyncio.gather(*tasks, return_exceptions=True)


def main():
    """Main entry point for running gateways."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kovanica Multi-Platform Messaging Gateway")
    parser.add_argument("--platform", choices=["telegram", "discord", "slack", "matrix", "all"], 
                       default="telegram", help="Platform to run")
    parser.add_argument("--token", help="Bot token")
    parser.add_argument("--api-url", default="http://localhost:13080", help="Agent API URL")
    parser.add_argument("--api-token", help="Agent API token")
    parser.add_argument("--allowed-users", nargs="+", help="Allowed user IDs")
    parser.add_argument("--session", default="gateway-default", help="Default session ID")
    parser.add_argument("--timeout", type=int, default=180, help="Request timeout")
    
    args = parser.parse_args()
    
    # Build configs
    configs = []
    platforms = ["telegram", "discord", "slack", "matrix"] if args.platform == "all" else [args.platform]
    
    for platform in platforms:
        token = args.token or os.environ.get(f"{platform.upper()}_BOT_TOKEN")
        if not token:
            logger.warning(f"No token for {platform}, skipping")
            continue
        
        configs.append(GatewayConfig(
            platform=platform,
            bot_token=token,
            allowed_users=args.allowed_users,
            api_url=args.api_url,
            api_token=args.api_token,
            default_session=args.session,
            timeout=args.timeout,
        ))
    
    if not configs:
        logger.error("No valid platform configurations")
        return
    
    asyncio.run(run_gateways(configs))


if __name__ == "__main__":
    main()