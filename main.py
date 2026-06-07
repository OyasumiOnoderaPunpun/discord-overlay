import sys
import json
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                             QPushButton, QFrame, QSizeGrip, QSlider)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QCursor
from pynput import keyboard


# ---------------------------------------------------------------------------
# Signal bridge  (pynput lives in its own thread → Qt signals are thread-safe)
# ---------------------------------------------------------------------------
class HotkeySignals(QObject):
    toggle_chat    = pyqtSignal()
    key_recorded   = pyqtSignal(str)   # emitted when user finishes binding a key


# ---------------------------------------------------------------------------
# Dedicated drag-handle widget
# ---------------------------------------------------------------------------
class DragHandle(QFrame):
    """A grip strip the user grabs to move the parent window."""

    def __init__(self, parent_window, parent=None):
        super().__init__(parent)
        self._win    = parent_window
        self._origin = QPoint()

        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        self.setFixedHeight(22)
        self.setObjectName("drag_handle")
        self.setToolTip("Drag to move")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        dots = QLabel("· · · · · · · · · · · ·")
        dots.setStyleSheet("color: rgba(255,255,255,40); font-size: 10px; letter-spacing: 2px;")
        lay.addWidget(dots, alignment=Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._origin = ev.globalPosition().toPoint()

    def mouseMoveEvent(self, ev):
        if not self._origin.isNull():
            delta = ev.globalPosition().toPoint() - self._origin
            self._win.move(self._win.pos() + delta)
            self._origin = ev.globalPosition().toPoint()

    def mouseReleaseEvent(self, ev):
        self._origin = QPoint()


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------
class SettingsPanel(QFrame):
    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.setObjectName("settings_panel")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # ── Always on Top ────────────────────────────────────────────────────
        aot_row = QHBoxLayout()
        aot_icon = QLabel("📌")
        aot_label = QLabel("Always on Top")
        aot_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        aot_row.addWidget(aot_icon)
        aot_row.addWidget(aot_label)
        aot_row.addStretch()

        self.aot_btn = QPushButton()
        self.aot_btn.setCheckable(True)
        self.aot_btn.setChecked(self.overlay.always_on_top)
        self.aot_btn.setFixedSize(54, 22)
        self.aot_btn.setObjectName("toggle_btn")
        self.aot_btn.clicked.connect(self._on_aot_toggled)
        self._refresh_aot_label()
        aot_row.addWidget(self.aot_btn)
        layout.addLayout(aot_row)

        # ── Chat Hotkey ──────────────────────────────────────────────────────
        key_row = QHBoxLayout()
        key_icon = QLabel("💬")
        key_label = QLabel("Chat Key")
        key_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        key_row.addWidget(key_icon)
        key_row.addWidget(key_label)
        key_row.addStretch()

        self.key_display = QLabel()
        self.key_display.setObjectName("key_display")
        self.key_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.key_display.setFixedSize(30, 22)
        self._refresh_key_display()
        key_row.addWidget(self.key_display)

        self.set_key_btn = QPushButton("Set")
        self.set_key_btn.setObjectName("set_key_btn")
        self.set_key_btn.setFixedSize(38, 22)
        self.set_key_btn.clicked.connect(self.overlay._start_key_recording)
        key_row.addWidget(self.set_key_btn)
        layout.addLayout(key_row)

        # ── Opacity ──────────────────────────────────────────────────────────
        op_row = QHBoxLayout()
        op_icon = QLabel("💡")
        op_label = QLabel("Opacity")
        op_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        op_row.addWidget(op_icon)
        op_row.addWidget(op_label)
        op_row.addStretch()

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(int(self.overlay.opacity_value * 100))
        self.opacity_slider.setFixedWidth(100)
        self.opacity_slider.valueChanged.connect(self.overlay._update_opacity)
        op_row.addWidget(self.opacity_slider)
        layout.addLayout(op_row)

    # helpers
    def _on_aot_toggled(self, checked):
        self.overlay.always_on_top = checked
        self.overlay._apply_window_flags()
        self.overlay._save_config()
        self._refresh_aot_label()

    def _refresh_aot_label(self):
        on = self.aot_btn.isChecked()
        self.aot_btn.setText("ON" if on else "OFF")

    def _refresh_key_display(self):
        k = self.overlay.chat_hotkey
        self.key_display.setText(f"`{k}`" if len(k) == 1 else k)

    def set_recording_state(self, recording: bool):
        if recording:
            self.set_key_btn.setText("…")
            self.set_key_btn.setEnabled(False)
            self.key_display.setText("?")
        else:
            self.set_key_btn.setText("Set")
            self.set_key_btn.setEnabled(True)
            self._refresh_key_display()


# ---------------------------------------------------------------------------
# Main overlay window
# ---------------------------------------------------------------------------
class ChatOverlay(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config       = config
        self.chat_open    = False
        self.always_on_top = bool(config.get("always_on_top", True))
        self.chat_hotkey  = config.get("chat_hotkey", "`")
        self.opacity_value = float(config.get("opacity", 0.8))
        self.text_color   = config.get("text_color", "#ffffff")
        self.accent_color = config.get("accent_color", "#7289da")
        self._recording   = False

        self._hotkey_signals = HotkeySignals()
        self._hotkey_signals.toggle_chat.connect(self._toggle_chat)
        self._hotkey_signals.key_recorded.connect(self._finish_key_recording)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()
        self._apply_window_flags()
        self._apply_styles()
        self._start_listener()

        from discord_bot import DiscordManager
        self.discord_mgr = DiscordManager(self.config)
        self.discord_mgr.start_bot()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._drain_queue)
        self._poll_timer.start(50)

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)

        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("bg_frame")
        bg = QVBoxLayout(self.bg_frame)
        bg.setContentsMargins(0, 0, 0, 6)
        bg.setSpacing(0)
        root.addWidget(self.bg_frame)

        # ── Drag handle (top strip) ──────────────────────────────────────────
        self.drag_handle = DragHandle(self)
        bg.addWidget(self.drag_handle)

        # ── Title bar (title + settings + close) ────────────────────────────
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(10, 2, 8, 2)

        self.title_label = QLabel("Discord Overlay")
        self.title_label.setStyleSheet("color: #888888; font-size: 11px;")
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(22, 22)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self._toggle_settings)
        title_bar.addWidget(self.settings_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setObjectName("close_btn")
        close_btn.clicked.connect(self.close)
        title_bar.addWidget(close_btn)

        bg.addLayout(title_bar)

        # ── Settings panel (hidden by default) ──────────────────────────────
        self.settings_panel = SettingsPanel(self)
        self.settings_panel.setVisible(False)
        bg.addWidget(self.settings_panel)

        # ── Separator ────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: rgba(255,255,255,18); max-height:1px;")
        bg.addWidget(sep)

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
        self.chat_layout.setSpacing(3)
        self.scroll_area.setWidget(self.chat_widget)
        bg.addWidget(self.scroll_area, 1)

        # ── Input + resize grip ──────────────────────────────────────────────
        input_row = QHBoxLayout()
        input_row.setContentsMargins(8, 0, 4, 0)

        self.input_box = QLineEdit()
        self._refresh_placeholder()
        self.input_box.returnPressed.connect(self._send_message)
        input_row.addWidget(self.input_box)

        grip = QSizeGrip(self)
        grip.setFixedSize(14, 14)
        input_row.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        bg.addLayout(input_row)

        self.resize(400, 460)

    def _toggle_settings(self):
        self.settings_panel.setVisible(not self.settings_panel.isVisible())
        self.adjustSize()

    # -----------------------------------------------------------------------
    # Window flags (always-on-top + click-through logic)
    # -----------------------------------------------------------------------
    def _apply_window_flags(self):
        flags = Qt.WindowType.FramelessWindowHint
        if self.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
            if not self.chat_open:
                flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.show()

    # -----------------------------------------------------------------------
    # Styles
    # -----------------------------------------------------------------------
    def _apply_styles(self):
        a = int(self.opacity_value * 255)
        ac = self.accent_color
        self.setStyleSheet(f"""
            #bg_frame {{
                background-color: rgba(18, 18, 26, {a});
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,20);
            }}
            #drag_handle {{
                background: rgba(255,255,255,6);
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid rgba(255,255,255,10);
            }}
            #settings_panel {{
                background: rgba(0,0,0,60);
                border-bottom: 1px solid rgba(255,255,255,12);
            }}
            QLabel {{
                color: {self.text_color};
            }}
            QLineEdit {{
                background: rgba(0,0,0,130);
                color: {self.text_color};
                border: 1px solid rgba(255,255,255,20);
                border-radius: 5px;
                padding: 5px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ac};
            }}
            QPushButton {{
                background: transparent;
                border: none;
                color: #888888;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,18);
                border-radius: 4px;
                color: #ffffff;
            }}
            #close_btn:hover {{
                background: rgba(220,50,50,180);
                border-radius: 4px;
                color: white;
            }}
            #toggle_btn {{
                border-radius: 11px;
                font-size: 11px;
                font-weight: bold;
                color: white;
            }}
            #toggle_btn[checked="true"], #toggle_btn:checked {{
                background: {ac};
            }}
            #toggle_btn:!checked {{
                background: rgba(255,255,255,20);
                color: #888888;
            }}
            #key_display {{
                background: rgba(255,255,255,12);
                color: #cccccc;
                border-radius: 4px;
                font-size: 11px;
                font-family: monospace;
            }}
            #set_key_btn {{
                background: rgba(255,255,255,12);
                border-radius: 4px;
                color: #aaaaaa;
                font-size: 11px;
            }}
            #set_key_btn:hover {{
                background: {ac};
                color: white;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,35);
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QSlider::groove:horizontal {{
                background: rgba(255,255,255,25);
                height: 3px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {ac};
                width: 12px;
                height: 12px;
                border-radius: 6px;
                margin: -5px 0;
            }}
        """)

    def _update_opacity(self, value):
        self.opacity_value = value / 100.0
        self._apply_styles()
        self._save_config()

    # -----------------------------------------------------------------------
    # Message queue polling
    # -----------------------------------------------------------------------
    def _drain_queue(self):
        q = self.discord_mgr.message_queue
        for _ in range(10):
            if q.empty():
                break
            item = q.get_nowait()
            if item[0] == "msg":
                self._add_message(item[1], item[2])
            elif item[0] == "status":
                self._add_status(item[1])

    def _add_message(self, author, content):
        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setText(
            f'<span style="color:{self.accent_color};font-weight:bold;">{author}</span>'
            f'<span style="color:#cccccc;">: {content}</span>'
        )
        lbl.setStyleSheet("padding: 1px 8px;")
        self.chat_layout.addWidget(lbl)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _add_status(self, text):
        lbl = QLabel(f"<i>{text}</i>")
        lbl.setStyleSheet("color: #555555; padding: 1px 8px; font-size: 11px;")
        self.chat_layout.addWidget(lbl)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    # -----------------------------------------------------------------------
    # Send message
    # -----------------------------------------------------------------------
    def _send_message(self):
        content = self.input_box.text().strip()
        if content:
            self.discord_mgr.send_webhook_message(content)
            self.input_box.clear()
        self._close_chat()

    # -----------------------------------------------------------------------
    # Chat open / close
    # -----------------------------------------------------------------------
    def _open_chat(self):
        self.chat_open = True
        self._apply_window_flags()
        self.input_box.setFocus()
        self.activateWindow()
        self.title_label.setText("Discord Overlay  💬")

    def _close_chat(self):
        self.chat_open = False
        self.input_box.clearFocus()
        self._apply_window_flags()
        self.title_label.setText("Discord Overlay")

    def _toggle_chat(self):
        if self.chat_open:
            self._close_chat()
        else:
            self._open_chat()

    def _refresh_placeholder(self):
        k = self.chat_hotkey
        self.input_box.setPlaceholderText(
            f"Press {k!r} to chat  •  Enter to send  •  Esc to dismiss"
        )

    # -----------------------------------------------------------------------
    # Hotkey listener
    # -----------------------------------------------------------------------
    def _start_listener(self):
        self._listener = keyboard.Listener(on_press=self._on_key)
        self._listener.daemon = True
        self._listener.start()

    def _restart_listener(self):
        if hasattr(self, "_listener"):
            self._listener.stop()
        self._start_listener()

    def _on_key(self, key):
        # ── Recording mode: capture next key ────────────────────────────────
        if self._recording:
            # Ignore pure modifier presses
            if isinstance(key, keyboard.Key) and key in (
                keyboard.Key.shift, keyboard.Key.shift_r,
                keyboard.Key.ctrl, keyboard.Key.ctrl_r,
                keyboard.Key.alt, keyboard.Key.alt_r,
                keyboard.Key.cmd, keyboard.Key.cmd_r,
            ):
                return
            try:
                char = key.char
                if char:
                    self._hotkey_signals.key_recorded.emit(char)
            except AttributeError:
                # Special key (F1, Tab, etc.) — use its name
                name = key.name
                self._hotkey_signals.key_recorded.emit(f"<{name}>")
            return

        # ── Normal mode ──────────────────────────────────────────────────────
        # Escape → close chat
        if key == keyboard.Key.esc and self.chat_open:
            self._hotkey_signals.toggle_chat.emit()
            return

        # Chat hotkey
        try:
            char = key.char
        except AttributeError:
            char = None

        hk = self.chat_hotkey
        if hk.startswith("<") and hk.endswith(">"):
            # Special key binding
            try:
                if key.name == hk[1:-1]:
                    self._hotkey_signals.toggle_chat.emit()
            except AttributeError:
                pass
        elif char == hk:
            self._hotkey_signals.toggle_chat.emit()

    # -----------------------------------------------------------------------
    # Key recording flow
    # -----------------------------------------------------------------------
    def _start_key_recording(self):
        self._recording = True
        self.settings_panel.set_recording_state(True)

    def _finish_key_recording(self, key_str: str):
        self._recording = False
        self.chat_hotkey = key_str
        self.config["chat_hotkey"] = key_str
        self._save_config()
        self.settings_panel.set_recording_state(False)
        self._refresh_placeholder()
        # Listener doesn't need restart — it reads self.chat_hotkey dynamically

    # -----------------------------------------------------------------------
    # Config persistence
    # -----------------------------------------------------------------------
    def _save_config(self):
        self.config["opacity"]      = self.opacity_value
        self.config["chat_hotkey"]  = self.chat_hotkey
        self.config["always_on_top"] = self.always_on_top
        try:
            if getattr(sys, 'frozen', False):
                base = os.path.dirname(sys.executable)
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(base, "config.json"), "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Could not save config: {e}")

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------
    def closeEvent(self, event):
        self._poll_timer.stop()
        if hasattr(self, "_listener"):
            self._listener.stop()
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

    path = os.path.join(base, "config.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)

    default = {
        "username":     "Player1",
        "bot_token":    "YOUR_BOT_TOKEN_HERE",
        "webhook_url":  "YOUR_WEBHOOK_URL_HERE",
        "channel_id":   "123456789012345678",
        "chat_hotkey":  "`",
        "always_on_top": True,
        "opacity":      0.8,
        "text_color":   "#ffffff",
        "accent_color": "#7289da"
    }
    try:
        with open(path, "w") as f:
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
