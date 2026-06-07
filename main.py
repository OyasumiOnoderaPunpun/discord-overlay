import sys
import json
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                             QPushButton, QFrame, QSizeGrip, QSlider)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject
from pynput import keyboard
from discord_bot import DiscordManager


# ---------------------------------------------------------------------------
# Global hotkey signal bridge (pynput runs in its own thread)
# ---------------------------------------------------------------------------
class HotkeySignals(QObject):
    lock_position   = pyqtSignal()   # Insert  → toggle position lock
    toggle_chat     = pyqtSignal()   # chat_hotkey → focus / unfocus input


# ---------------------------------------------------------------------------
# Main overlay window
# ---------------------------------------------------------------------------
class ChatOverlay(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config

        # State flags
        self.position_locked  = False   # Insert locks dragging; window stays interactive
        self.chat_open        = False   # chat_hotkey toggles typing focus
        self.drag_pos         = QPoint()

        # Appearance
        self.opacity_value  = float(self.config.get("opacity", 0.8))
        self.text_color     = self.config.get("text_color",   "#ffffff")
        self.accent_color   = self.config.get("accent_color", "#7289da")

        self._init_ui()
        self._setup_discord()
        self._setup_hotkeys()
        self._setup_message_poll()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------
    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput   # start click-through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # Background frame
        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("bg_frame")
        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(6, 6, 6, 6)
        bg_layout.setSpacing(4)
        root_layout.addWidget(self.bg_frame)

        # ── Header (drag handle + controls) ─────────────────────────────────
        header = QHBoxLayout()

        self.drag_icon = QLabel("⠿")
        self.drag_icon.setToolTip("Drag to move  |  Insert = lock position")
        self.drag_icon.setStyleSheet("color: #aaaaaa; font-size: 16px; padding: 2px 6px;")
        header.addWidget(self.drag_icon)

        self.title_label = QLabel("Discord Overlay")
        self.title_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        header.addWidget(self.title_label)

        header.addStretch()

        # Opacity slider inline in header
        header.addWidget(QLabel("💡", styleSheet="color:#aaa;"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(int(self.opacity_value * 100))
        self.opacity_slider.setFixedWidth(80)
        self.opacity_slider.valueChanged.connect(self._update_opacity)
        header.addWidget(self.opacity_slider)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setObjectName("close_btn")
        self.close_btn.clicked.connect(self.close)
        header.addWidget(self.close_btn)

        bg_layout.addLayout(header)

        # ── Thin separator ───────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,30);")
        bg_layout.addWidget(sep)

        # ── Chat scroll area ─────────────────────────────────────────────────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.chat_widget = QWidget()
        self.chat_widget.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setSpacing(2)
        self.scroll_area.setWidget(self.chat_widget)

        bg_layout.addWidget(self.scroll_area, 1)

        # ── Input row ────────────────────────────────────────────────────────
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Press ` to chat  •  Enter to send  •  Esc to close")
        self.input_box.returnPressed.connect(self._send_message)
        input_row.addWidget(self.input_box)

        size_grip = QSizeGrip(self)
        input_row.addWidget(size_grip, 0,
                            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        bg_layout.addLayout(input_row)

        self._apply_styles()
        self.resize(420, 480)

    # -----------------------------------------------------------------------
    # Styling
    # -----------------------------------------------------------------------
    def _apply_styles(self):
        a = int(self.opacity_value * 255)
        self.setStyleSheet(f"""
            #bg_frame {{
                background-color: rgba(20, 20, 28, {a});
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,25);
            }}
            QLabel {{
                color: {self.text_color};
            }}
            QLineEdit {{
                background-color: rgba(0,0,0,140);
                color: {self.text_color};
                border: 1px solid {self.accent_color};
                border-radius: 5px;
                padding: 5px 8px;
                font-size: 13px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                color: #aaaaaa;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,25);
                border-radius: 4px;
                color: white;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,45);
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QSlider::groove:horizontal {{
                background: rgba(255,255,255,30);
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {self.accent_color};
                width: 12px;
                height: 12px;
                border-radius: 6px;
                margin: -4px 0;
            }}
        """)

    def _update_opacity(self, value):
        self.opacity_value = value / 100.0
        self._apply_styles()

    # -----------------------------------------------------------------------
    # Discord setup + message polling
    # -----------------------------------------------------------------------
    def _setup_discord(self):
        self.discord_mgr = DiscordManager(self.config)
        self.discord_mgr.start_bot()

    def _setup_message_poll(self):
        """Poll the thread-safe queue every 50 ms — eliminates cross-thread signal lag."""
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._drain_queue)
        self._poll_timer.start(50)   # 50 ms = 20 updates/sec, very responsive

    def _drain_queue(self):
        q = self.discord_mgr.message_queue
        # Process up to 10 messages per tick to avoid UI stutter on burst
        for _ in range(10):
            if q.empty():
                break
            item = q.get_nowait()
            if item[0] == "msg":
                _, author, content = item
                self._add_message(author, content)
            elif item[0] == "status":
                _, text = item
                self._add_status(text)

    # -----------------------------------------------------------------------
    # Chat message rendering
    # -----------------------------------------------------------------------
    def _add_message(self, author, content):
        bubble = QLabel()
        bubble.setWordWrap(True)
        bubble.setTextFormat(Qt.TextFormat.RichText)
        bubble.setText(
            f'<span style="color:{self.accent_color};font-weight:bold;">{author}</span>'
            f'<span style="color:#cccccc;">: {content}</span>'
        )
        bubble.setStyleSheet("padding: 1px 4px;")
        self.chat_layout.addWidget(bubble)

        # Scroll to bottom AFTER the layout has updated
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _add_status(self, text):
        lbl = QLabel(f"<i>{text}</i>")
        lbl.setStyleSheet("color: #666666; padding: 1px 4px; font-size: 11px;")
        self.chat_layout.addWidget(lbl)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    # -----------------------------------------------------------------------
    # Sending
    # -----------------------------------------------------------------------
    def _send_message(self):
        content = self.input_box.text().strip()
        if content:
            self.discord_mgr.send_webhook_message(content)
            self.input_box.clear()
        # Auto-close chat after sending (feels natural for gaming)
        self._close_chat()

    # -----------------------------------------------------------------------
    # Hotkey setup
    # -----------------------------------------------------------------------
    def _setup_hotkeys(self):
        self._hotkey_signals = HotkeySignals()
        self._hotkey_signals.lock_position.connect(self._toggle_position_lock)
        self._hotkey_signals.toggle_chat.connect(self._toggle_chat)

        chat_key_str = self.config.get("chat_hotkey", "`").lower()

        def on_press(key):
            # Insert → lock/unlock position
            if key == keyboard.Key.insert:
                self._hotkey_signals.lock_position.emit()
                return

            # Escape → close chat if open
            if key == keyboard.Key.esc:
                if self.chat_open:
                    self._hotkey_signals.toggle_chat.emit()
                return

            # Chat hotkey (backtick / configurable)
            try:
                char = key.char
            except AttributeError:
                char = None

            if char == chat_key_str:
                self._hotkey_signals.toggle_chat.emit()

        self._keyboard_listener = keyboard.Listener(on_press=on_press)
        self._keyboard_listener.start()

    # -----------------------------------------------------------------------
    # Hotkey actions
    # -----------------------------------------------------------------------
    def _toggle_position_lock(self):
        """Insert — lock/unlock dragging. Window stays interactive regardless."""
        self.position_locked = not self.position_locked
        if self.position_locked:
            self.title_label.setText("Discord Overlay  🔒")
            self.drag_icon.setStyleSheet("color: #555555; font-size: 16px; padding: 2px 6px;")
        else:
            self.title_label.setText("Discord Overlay")
            self.drag_icon.setStyleSheet("color: #aaaaaa; font-size: 16px; padding: 2px 6px;")

    def _open_chat(self):
        """Make window interactive + focus input box for typing."""
        self.chat_open = True
        # Remove click-through flag
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.show()
        self.input_box.setFocus()
        self.activateWindow()
        self.input_box.setStyleSheet(
            self.input_box.styleSheet() +
            f"; border: 1px solid {self.accent_color};"
        )
        self.title_label.setText("Discord Overlay  💬")

    def _close_chat(self):
        """Unfocus input, restore click-through."""
        self.chat_open = False
        self.input_box.clearFocus()
        # Re-apply click-through
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput
        )
        self.show()
        lock_icon = "  🔒" if self.position_locked else ""
        self.title_label.setText(f"Discord Overlay{lock_icon}")

    def _toggle_chat(self):
        if self.chat_open:
            self._close_chat()
        else:
            self._open_chat()

    # -----------------------------------------------------------------------
    # Dragging (header area only, respects position lock)
    # -----------------------------------------------------------------------
    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and not self.position_locked
                and event.position().y() < 40):
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if not self.drag_pos.isNull() and not self.position_locked:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.drag_pos = QPoint()

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------
    def closeEvent(self, event):
        self._poll_timer.stop()
        self._keyboard_listener.stop()
        self.discord_mgr.stop_bot()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_config():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    config_path = os.path.join(base, "config.json")

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return json.load(f)

    # Generate default config next to exe if missing
    default = {
        "username":    "Player1",
        "bot_token":   "YOUR_BOT_TOKEN_HERE",
        "webhook_url": "YOUR_WEBHOOK_URL_HERE",
        "channel_id":  "123456789012345678",
        "hotkey":      "insert",
        "chat_hotkey": "`",
        "opacity":     0.8,
        "text_color":  "#ffffff",
        "accent_color":"#7289da"
    }
    try:
        with open(config_path, "w") as f:
            json.dump(default, f, indent=4)
    except Exception:
        pass
    return default


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    config = load_config()
    overlay = ChatOverlay(config)
    overlay.show()
    sys.exit(app.exec())
