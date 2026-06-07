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

    def send_webhook_message(self, content, attachment=None):
        """Send a message via webhook — runs async on the bot's event loop (non-blocking)."""
        webhook_url = self.config.get("webhook_url")
        if not webhook_url:
            return

        username = self.config.get("username", "Player")

        async def _send_async():
            if not getattr(self, 'session', None) or self.session.closed:
                self.session = aiohttp.ClientSession()
            file_handle = None
            try:
                data = aiohttp.FormData()
                if content:
                    data.add_field("content", content)
                data.add_field("username", username)

                if attachment:
                    import os
                    if "path" in attachment:
                        file_handle = open(attachment["path"], "rb")
                        data.add_field("file", file_handle, filename=os.path.basename(attachment["path"]))
                    elif "bytes" in attachment and "filename" in attachment:
                        data.add_field("file", attachment["bytes"], filename=attachment["filename"])

                await self.session.post(
                    webhook_url,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=15)
                )
            except Exception as e:
                print(f"Webhook error: {e}")
            finally:
                if file_handle:
                    file_handle.close()

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
                content = message.content
                if message.attachments:
                    import os
                    import tempfile
                    temp_dir = tempfile.gettempdir()
                    for att in message.attachments:
                        if att.content_type and att.content_type.startswith('image/'):
                            local_path = os.path.join(temp_dir, f"{att.id}_{att.filename}")
                            html_path = local_path.replace("\\", "/")
                            try:
                                await att.save(local_path)
                                content += f"<br><img src='{html_path}' width='200'>"
                            except Exception as e:
                                print(f"Failed to save attachment: {e}")
                                content += f"<br>[Image: {att.filename}]"
                        else:
                            content += f"<br>[Attachment: {att.filename}]"
                self.message_queue.put(("msg", message.author.display_name, content))

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
            if getattr(self, 'session', None) and not self.session.closed:
                asyncio.run_coroutine_threadsafe(self.session.close(), self.loop)
            asyncio.run_coroutine_threadsafe(self.bot.close(), self.loop)
