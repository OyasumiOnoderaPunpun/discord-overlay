@echo off
echo Building Discord Overlay Executable...
call venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconsole --onefile --name "DiscordOverlay" main.py
echo Build complete! Check the "dist" folder for DiscordOverlay.exe
pause
