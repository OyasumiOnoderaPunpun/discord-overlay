import sys
import json
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QScrollArea, 
                             QPushButton, QFrame, QSizePolicy, QColorDialog, QSlider, QSizeGrip)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QPalette
from pynput import keyboard
from discord_bot import DiscordManager

class HotkeySignals(QObject):
    toggle_mode = pyqtSignal()

class ChatOverlay(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.interactive_mode = True
        self.drag_pos = QPoint()
        
        # Load config values
        self.bg_color = self.config.get("bg_color", "rgba(30, 30, 30, 200)")
        self.text_color = self.config.get("text_color", "#ffffff")
        self.accent_color = self.config.get("accent_color", "#7289da")
        
        self.init_ui()
        self.setup_discord()
        self.setup_hotkey()
        
    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main Widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.central_layout = QVBoxLayout(self.central_widget)
        self.central_layout.setContentsMargins(10, 10, 10, 10)
        
        # Background Frame (for translucency and styling)
        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("bg_frame")
        self.bg_layout = QVBoxLayout(self.bg_frame)
        self.bg_layout.setContentsMargins(5, 5, 5, 5)
        self.central_layout.addWidget(self.bg_frame)
        
        # Header (Drag handle & Settings)
        self.header_layout = QHBoxLayout()
        
        self.title_label = QLabel("Discord Overlay (Press Insert to Lock)\n[DRAG ME]")
        self.title_label.setStyleSheet("color: white; font-weight: bold; background: rgba(0,0,0,100); padding: 5px;")
        self.header_layout.addWidget(self.title_label)
        
        self.header_layout.addStretch()
        
        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.clicked.connect(self.toggle_settings)
        self.header_layout.addWidget(self.settings_btn)
        
        self.close_btn = QPushButton("❌")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.close)
        self.header_layout.addWidget(self.close_btn)
        
        self.bg_layout.addLayout(self.header_layout)
        
        # Settings Panel (Hidden by default)
        self.settings_panel = QFrame()
        self.settings_panel.setVisible(False)
        self.settings_layout = QVBoxLayout(self.settings_panel)
        
        # Opacity Slider
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:", styleSheet="color: white;"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.config.get("opacity", 0.8) * 100))
        self.opacity_slider.valueChanged.connect(self.update_opacity)
        opacity_layout.addWidget(self.opacity_slider)
        self.settings_layout.addLayout(opacity_layout)
        
        self.bg_layout.addWidget(self.settings_panel)
        
        # Chat History
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        
        self.chat_widget = QWidget()
        self.chat_widget.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.chat_widget)
        
        self.bg_layout.addWidget(self.scroll_area)
        
        # Input Box and Size Grip
        self.input_layout = QHBoxLayout()
        self.input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type a message...")
        self.input_box.returnPressed.connect(self.send_message)
        self.input_layout.addWidget(self.input_box)
        
        self.size_grip = QSizeGrip(self)
        self.input_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        
        self.bg_layout.addLayout(self.input_layout)
        
        self.update_styles()
        self.resize(400, 500)
        
    def update_styles(self):
        opacity = self.opacity_slider.value() / 100.0
        # Parse rgba and inject new opacity if it's rgba
        # For simplicity, we just use a generic dark theme with dynamic opacity
        r, g, b = 25, 25, 25
        a = int(opacity * 255)
        
        style = f"""
            #bg_frame {{
                background-color: rgba({r}, {g}, {b}, {a});
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 50);
            }}
            QLabel {{
                color: {self.text_color};
            }}
            QLineEdit {{
                background-color: rgba(0, 0, 0, 150);
                color: {self.text_color};
                border: 1px solid {self.accent_color};
                border-radius: 5px;
                padding: 5px;
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                color: white;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 30);
                border-radius: 5px;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 8px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 50);
                border-radius: 4px;
            }}
        """
        self.setStyleSheet(style)
        
    def update_opacity(self):
        self.update_styles()

    def toggle_settings(self):
        self.settings_panel.setVisible(not self.settings_panel.isVisible())

    def setup_discord(self):
        self.discord_mgr = DiscordManager(self.config)
        self.discord_mgr.signals.message_received.connect(self.add_message)
        self.discord_mgr.signals.status_changed.connect(self.add_status)
        self.discord_mgr.start_bot()

    def add_message(self, author, content):
        msg_label = QLabel(f"<b>{author}:</b> {content}")
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("padding: 2px;")
        self.chat_layout.addWidget(msg_label)
        
        # Scroll to bottom
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    def add_status(self, status):
        status_label = QLabel(f"<i>{status}</i>")
        status_label.setStyleSheet("color: #888888;")
        self.chat_layout.addWidget(status_label)

    def send_message(self):
        content = self.input_box.text().strip()
        if content:
            self.discord_mgr.send_webhook_message(content)
            self.input_box.clear()

    # --- Click-Through and Hotkey Logic ---
    def setup_hotkey(self):
        self.hotkey_signals = HotkeySignals()
        self.hotkey_signals.toggle_mode.connect(self.toggle_interactive_mode)
        
        # Read hotkey from config, default to insert
        key_str = self.config.get("hotkey", "insert").lower()
        key_obj = keyboard.Key.insert if key_str == "insert" else keyboard.Key.insert
        # Pynput can handle more keys but we'll stick to insert as requested
        
        def on_press(key):
            if key == key_obj:
                self.hotkey_signals.toggle_mode.emit()

        self.keyboard_listener = keyboard.Listener(on_press=on_press)
        self.keyboard_listener.start()

    def toggle_interactive_mode(self):
        self.interactive_mode = not self.interactive_mode
        if self.interactive_mode:
            # Make window interactive
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | 
                Qt.WindowType.WindowStaysOnTopHint
            )
            self.title_label.setText("Discord Overlay (Press Insert to Lock)")
            self.bg_frame.setStyleSheet(self.bg_frame.styleSheet() + "border: 1px solid rgba(255, 255, 255, 50);")
            self.show()
            self.input_box.setFocus()
            self.activateWindow()
        else:
            # Make window click-through
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | 
                Qt.WindowType.WindowStaysOnTopHint | 
                Qt.WindowType.WindowTransparentForInput
            )
            self.title_label.setText("Discord Overlay (LOCKED - Press Insert)")
            self.bg_frame.setStyleSheet(self.bg_frame.styleSheet() + "border: 1px solid transparent;")
            self.show()
            
    # Auto unfocus when clicking outside: 
    # Standard behavior is that clicking outside an interactive window takes focus away.
    # To switch to click-through when losing focus entirely, we could override changeEvent.
    def changeEvent(self, event):
        if event.type() == event.Type.ActivationChange:
            if not self.isActiveWindow() and self.interactive_mode:
                # Optionally auto-lock when losing focus
                self.toggle_interactive_mode()
        super().changeEvent(event)

    # --- Dragging Logic ---
    def mousePressEvent(self, event):
        # Only allow dragging if they click within the top 40 pixels (the header area)
        if event.button() == Qt.MouseButton.LeftButton and self.interactive_mode and event.position().y() < 40:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if not self.drag_pos.isNull() and self.interactive_mode:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.drag_pos = QPoint()

    def closeEvent(self, event):
        self.discord_mgr.stop_bot()
        super().closeEvent(event)

def load_config():
    # If running as an EXE via PyInstaller, use the exe folder. Otherwise use script folder.
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
        
    config_path = os.path.join(application_path, "config.json")
    
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return json.load(f)
            
    # Create default config next to the exe if it doesn't exist
    default_config = {
        "username": "Player1",
        "bot_token": "YOUR_BOT_TOKEN_HERE",
        "webhook_url": "YOUR_WEBHOOK_URL_HERE",
        "channel_id": "123456789012345678",
        "hotkey": "insert",
        "opacity": 0.8,
        "bg_color": "rgba(30, 30, 30, 200)",
        "text_color": "#ffffff",
        "accent_color": "#7289da"
    }
    try:
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=4)
    except:
        pass
    return default_config

if __name__ == "__main__":
    app = QApplication(sys.argv)
    config = load_config()
    overlay = ChatOverlay(config)
    overlay.show()
    sys.exit(app.exec())
