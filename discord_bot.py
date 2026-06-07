import asyncio
import threading
import discord
import requests
from PyQt6.QtCore import QObject, pyqtSignal

class DiscordSignals(QObject):
    message_received = pyqtSignal(str, str) # author, content
    status_changed = pyqtSignal(str) # Status messages (e.g., "Connected")

class DiscordManager:
    def __init__(self, config):
        self.config = config
        self.signals = DiscordSignals()
        self.bot = None
        self.loop = None
        self.thread = None

    def send_webhook_message(self, content):
        if not self.config.get("webhook_url"):
            return
        
        data = {
            "content": content,
            "username": self.config.get("username", "Unknown User")
        }
        
        # Run in a separate thread to not block UI
        def _send():
            try:
                requests.post(self.config["webhook_url"], json=data)
            except Exception as e:
                print(f"Failed to send webhook: {e}")
                
        threading.Thread(target=_send, daemon=True).start()

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
            self.signals.status_changed.emit(f"Connected as {self.bot.user}")
            print(f'Logged in as {self.bot.user}')

        @self.bot.event
        async def on_message(message):
            # Ignore our own bot messages
            if message.author == self.bot.user:
                return
                
            # Only listen to the configured channel
            if str(message.channel.id) == str(self.config.get("channel_id")):
                self.signals.message_received.emit(message.author.display_name, message.content)
                
        try:
            self.loop.run_until_complete(self.bot.start(self.config["bot_token"]))
        except Exception as e:
            self.signals.status_changed.emit(f"Error: {e}")
            print(f"Bot error: {e}")

    def stop_bot(self):
        if self.loop and self.bot:
            asyncio.run_coroutine_threadsafe(self.bot.close(), self.loop)
