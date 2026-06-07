import asyncio
import threading
import queue
import discord
import aiohttp
from PyQt6.QtCore import QObject, pyqtSignal


class DiscordSignals(QObject):
    status_changed = pyqtSignal(str)


class DiscordManager:
    def __init__(self, config):
        self.config = config
        self.signals = DiscordSignals()
        self.bot = None
        self.loop = None
        self.thread = None

        # Thread-safe queue: UI polls this instead of receiving cross-thread signals
        # Each item is a tuple: ("msg", author, content) or ("status", text)
        self.message_queue = queue.Queue()

    def send_webhook_message(self, content):
        """Send a message via webhook — runs async on the bot's event loop (non-blocking)."""
        webhook_url = self.config.get("webhook_url")
        if not webhook_url:
            return

        username = self.config.get("username", "Player")

        async def _send_async():
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        webhook_url,
                        json={"content": content, "username": username},
                        timeout=aiohttp.ClientTimeout(total=5)
                    )
            except Exception as e:
                print(f"Webhook error: {e}")

        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(_send_async(), self.loop)

    def start_bot(self):
        self.thread = threading.Thread(target=self._run_bot, daemon=True)
        self.thread.start()

    def _run_bot(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        intents = discord.Intents.default()
        intents.message_content = True

        self.bot = discord.Client(intents=intents)

        @self.bot.event
        async def on_ready():
            msg = f"✅ Connected as {self.bot.user}"
            self.message_queue.put(("status", msg))

        @self.bot.event
        async def on_message(message):
            # Ignore bot's own messages
            if message.author == self.bot.user:
                return
            # Only listen to the configured channel
            if str(message.channel.id) == str(self.config.get("channel_id", "")):
                self.message_queue.put(("msg", message.author.display_name, message.content))

        @self.bot.event
        async def on_disconnect():
            self.message_queue.put(("status", "⚠️ Disconnected — reconnecting..."))

        try:
            self.loop.run_until_complete(self.bot.start(self.config["bot_token"]))
        except Exception as e:
            self.message_queue.put(("status", f"❌ Error: {e}"))
            print(f"Bot error: {e}")

    def stop_bot(self):
        if self.loop and self.bot and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.bot.close(), self.loop)
