# 🎮 Discord Overlay

A transparent, always-on-top Discord chat overlay for Windows. Built for gaming with friends — chat over Discord without alt-tabbing out of your game.

> Originally built for playing Roblox with friends after the in-game chat was restricted.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-green)
![Discord](https://img.shields.io/badge/Discord-Bot-5865F2?logo=discord)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)

---

## ✨ Features

- 🪟 **Transparent overlay** — sits on top of any game, fully see-through
- 🔒 **Lock / Unlock** — Press `Insert` to toggle click-through mode so it doesn't interfere with gameplay
- 🔃 **Real-time Discord chat** — reads messages from your specific Discord channel live
- 📤 **Send messages** — type and press Enter to send directly to Discord
- 🖱️ **Draggable** — drag the header bar to move it anywhere on screen
- 📐 **Resizable** — drag the bottom-right corner to resize
- 🎨 **Customizable** — adjust opacity, colors, and hotkey via `config.json`
- 📦 **Standalone EXE** — distribute to friends without needing Python installed

---

## 📋 Requirements (for running from source)

- Python 3.10+
- A Discord Bot Token
- A Discord Webhook URL for the channel

---

## 🚀 Quick Start (EXE — for friends)

1. **Download** the latest `DiscordOverlay.zip` from the [Releases](../../releases) page
2. **Extract** the ZIP anywhere on your PC
3. **Open** `config.json` in Notepad and fill in:
   - `"username"` — your display name in the chat
   - `"bot_token"` — get this from your server host
   - `"webhook_url"` — get this from your server host
   - `"channel_id"` — get this from your server host
4. **Run** `DiscordOverlay.exe`

---

## ⚙️ Config Reference

Copy `config.example.json` to `config.json` and fill in your values:

```json
{
    "username": "YourNameHere",
    "bot_token": "PASTE_YOUR_BOT_TOKEN_HERE",
    "webhook_url": "PASTE_YOUR_WEBHOOK_URL_HERE",
    "channel_id": "PASTE_YOUR_CHANNEL_ID_HERE",
    "hotkey": "insert",
    "opacity": 0.8,
    "bg_color": "rgba(30, 30, 30, 200)",
    "text_color": "#ffffff",
    "accent_color": "#7289da"
}
```

| Field | Description |
|---|---|
| `username` | Your name shown on sent messages |
| `bot_token` | Discord bot token (keep this private!) |
| `webhook_url` | Discord webhook URL for the channel |
| `channel_id` | The Discord channel ID to read messages from |
| `hotkey` | Key to toggle lock/unlock (default: `insert`) |
| `opacity` | Window opacity from `0.0` (invisible) to `1.0` (solid) |
| `accent_color` | Color of the input box border |

---

## 🔑 Hotkeys

| Key | Action |
|---|---|
| `Insert` | Toggle lock (click-through) / unlock (interactive) mode |
| `Enter` | Send message |

---

## 🔒 Security Notes

- **Never share your `config.json`** — it contains your bot token and webhook URL
- The bot token and webhook URL act like passwords for your Discord bot
- If you ever leak them, go to the [Discord Developer Portal](https://discord.com/developers/applications) and **reset your token**, and delete/recreate the webhook in your server settings
- This app makes **no external connections** except directly to Discord's official servers

---

## 🛠️ Building the EXE (for developers)

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install PyQt6 discord.py pynput requests pyinstaller

# 3. Build the EXE
build.bat
```

The output `DiscordOverlay.exe` will appear in the `dist/` folder.

---

## 📁 Project Structure

```
discord_overlay/
├── main.py              # Main overlay UI (PyQt6)
├── discord_bot.py       # Discord bot & webhook logic
├── config.example.json  # Template config (copy to config.json)
├── build.bat            # Script to build EXE with PyInstaller
└── .gitignore
```

---

## 📜 License

MIT — do whatever you want with it.
