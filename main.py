import sys
import json
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QLineEdit,
                             QScrollArea, QPushButton, QFrame, QSizeGrip, QSlider,
                             QColorDialog, QFileDialog, QDialog)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QCursor, QColor, QKeySequence, QPixmap
from pynput import keyboard


# ---------------------------------------------------------------------------
# Theme & accent presets
# ---------------------------------------------------------------------------
THEMES = {
    "Discord":  {"bg": (20,  20,  28),  "accent": "#7289da", "text": "#ffffff"},
    "Midnight": {"bg": (8,   8,   18),  "accent": "#5865f2", "text": "#d0d0ff"},
    "Amoled":   {"bg": (0,   0,   0),   "accent": "#00b4d8", "text": "#ffffff"},
    "Sakura":   {"bg": (28,  14,  22),  "accent": "#f472b6", "text": "#ffe4f0"},
    "Forest":   {"bg": (10,  22,  12),  "accent": "#4ade80", "text": "#e0ffe8"},
    "Sunset":   {"bg": (28,  14,  6),   "accent": "#fb923c", "text": "#fff0e0"},
}

ACCENT_PRESETS = [
    "#7289da", "#5865f2", "#00b4d8", "#4ade80",
    "#fb923c", "#f472b6", "#f87171", "#a78bfa",
]

FONT_SIZES = {"S": 11, "M": 13, "L": 16}

# Keys that should be applied to config.json if missing (backward compat)
CONFIG_DEFAULTS = {
    "chat_hotkey":   "`",
    "always_on_top": True,
    "theme":         "Discord",
    "accent_color":  "#7289da",
    "text_color":    "#ffffff",
    "bg_rgb":        [20, 20, 28],
    "opacity":       0.8,
    "font_size":     13,
    "corner_radius": 10,
    "show_scrollbar": False,
}


# ---------------------------------------------------------------------------
# Signal bridge  (pynput → Qt, thread-safe)
# ---------------------------------------------------------------------------
class HotkeySignals(QObject):
    toggle_chat  = pyqtSignal()
    key_recorded = pyqtSignal(str)


# ---------------------------------------------------------------------------
# Title bar  (also acts as drag handle — no separate grey strip)
# ---------------------------------------------------------------------------
class TitleBar(QFrame):
    """Transparent title bar that the user can drag to move the window."""

    def __init__(self, parent_window, parent=None):
        super().__init__(parent)
        self._win    = parent_window
        self._origin = QPoint()
        self.setObjectName("title_bar")
        # Use move-cursor everywhere EXCEPT over the buttons
        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 8, 5)
        lay.setSpacing(4)

        self.title_label = QLabel("Discord Overlay")
        self.title_label.setObjectName("title_label")
        lay.addWidget(self.title_label)
        lay.addStretch()

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(22, 22)
        self.settings_btn.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.settings_btn.setToolTip("Settings")
        lay.addWidget(self.settings_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setObjectName("close_btn")
        self.close_btn.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        lay.addWidget(self.close_btn)

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
# Helper widgets
# ---------------------------------------------------------------------------
def _separator(obj_name=None):
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    if obj_name:
        sep.setObjectName(obj_name)
    else:
        sep.setStyleSheet("background: rgba(255,255,255,12); max-height: 1px;")
    return sep

def _section_header(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: rgba(255,255,255,30); font-size: 9px; font-weight: bold; "
        "letter-spacing: 2px; padding: 6px 0 2px 0;"
    )
    return lbl

class ChatInput(QLineEdit):
    image_pasted = pyqtSignal(bytes, str)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData()
            if mime.hasImage():
                img = clipboard.image()
                ba = QByteArray()
                buffer = QBuffer(ba)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buffer, "PNG")
                self.image_pasted.emit(ba.data(), "pasted_image.png")
                return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------
class SettingsPanel(QFrame):
    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.setObjectName("settings_panel")
        self._theme_btns  = {}
        self._accent_btns = {}
        self._size_btns   = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 4, 10, 10)
        root.setSpacing(0)

        # ══════════════════════════ SYSTEM ════════════════════════════════
        root.addWidget(_section_header("SYSTEM"))

        # Always on Top
        aot_row = QHBoxLayout()
        aot_row.addWidget(QLabel("📌"))
        aot_lbl = QLabel("Always on Top")
        aot_lbl.setStyleSheet("color:#cccccc; font-size:12px;")
        aot_row.addWidget(aot_lbl)
        aot_row.addStretch()
        self.aot_btn = QPushButton()
        self.aot_btn.setCheckable(True)
        self.aot_btn.setChecked(self.overlay.always_on_top)
        self.aot_btn.setFixedSize(48, 20)
        self.aot_btn.setObjectName("toggle_btn")
        self.aot_btn.clicked.connect(self._on_aot)
        self._refresh_aot()
        aot_row.addWidget(self.aot_btn)
        root.addLayout(aot_row)

        # Chat hotkey
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("💬"))
        key_lbl = QLabel("Chat Key")
        key_lbl.setStyleSheet("color:#cccccc; font-size:12px;")
        key_row.addWidget(key_lbl)
        key_row.addStretch()
        self.key_display = QLabel()
        self.key_display.setObjectName("key_display")
        self.key_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.key_display.setFixedSize(28, 20)
        self._refresh_key()
        key_row.addWidget(self.key_display)
        self.set_key_btn = QPushButton("Set")
        self.set_key_btn.setObjectName("set_key_btn")
        self.set_key_btn.setFixedSize(34, 20)
        self.set_key_btn.clicked.connect(self.overlay._start_key_recording)
        key_row.addWidget(self.set_key_btn)
        root.addLayout(key_row)

        # Opacity
        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("💡"))
        op_lbl = QLabel("Opacity")
        op_lbl.setStyleSheet("color:#cccccc; font-size:12px;")
        op_row.addWidget(op_lbl)
        op_row.addStretch()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(int(self.overlay.opacity_value * 100))
        self.opacity_slider.setFixedWidth(90)
        self.opacity_slider.valueChanged.connect(self.overlay._set_opacity)
        op_row.addWidget(self.opacity_slider)
        root.addLayout(op_row)

        root.addSpacing(4)
        root.addWidget(_separator())

        # ══════════════════════ APPEARANCE ════════════════════════════════
        root.addWidget(_section_header("APPEARANCE"))

        # Themes
        root.addWidget(QLabel("🎨  Theme", styleSheet="color:#cccccc;font-size:12px;"))
        theme_grid = QGridLayout()
        theme_grid.setSpacing(4)
        for i, (name, t) in enumerate(THEMES.items()):
            btn = QPushButton(name)
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda _, n=name: self.overlay._apply_theme(n))
            self._theme_btns[name] = btn
            theme_grid.addWidget(btn, i // 3, i % 3)
        root.addLayout(theme_grid)
        self._refresh_theme_btns()

        root.addSpacing(6)

        # Accent swatches
        root.addWidget(QLabel("🖌  Accent", styleSheet="color:#cccccc;font-size:12px;"))
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(4)
        for color in ACCENT_PRESETS:
            sw = QPushButton()
            sw.setFixedSize(20, 20)
            sw.clicked.connect(lambda _, c=color: self.overlay._set_accent(c))
            self._accent_btns[color] = sw
            swatch_row.addWidget(sw)
        self.custom_color_btn = QPushButton("+")
        self.custom_color_btn.setFixedSize(20, 20)
        self.custom_color_btn.setObjectName("custom_color_btn")
        self.custom_color_btn.clicked.connect(self.overlay._pick_custom_accent)
        swatch_row.addWidget(self.custom_color_btn)
        swatch_row.addStretch()
        root.addLayout(swatch_row)
        self._refresh_accent_btns()

        root.addSpacing(6)

        # Font size
        root.addWidget(QLabel("🔤  Text Size", styleSheet="color:#cccccc;font-size:12px;"))
        size_row = QHBoxLayout()
        size_row.setSpacing(4)
        for label, size in FONT_SIZES.items():
            btn = QPushButton(label)
            btn.setFixedSize(30, 22)
            btn.clicked.connect(lambda _, s=size: self.overlay._set_font_size(s))
            self._size_btns[size] = btn
            size_row.addWidget(btn)
        size_row.addStretch()
        root.addLayout(size_row)
        self._refresh_size_btns()

        root.addSpacing(6)

        # Corner radius
        radius_row = QHBoxLayout()
        radius_row.addWidget(QLabel("⬛", styleSheet="color:#cccccc;font-size:12px;"))
        radius_row.addWidget(QLabel("Corners", styleSheet="color:#cccccc;font-size:12px;"))
        radius_row.addStretch()
        self.radius_slider = QSlider(Qt.Orientation.Horizontal)
        self.radius_slider.setRange(0, 20)
        self.radius_slider.setValue(self.overlay.corner_radius)
        self.radius_slider.setFixedWidth(90)
        self.radius_slider.valueChanged.connect(self.overlay._set_corner_radius)
        radius_row.addWidget(self.radius_slider)
        root.addLayout(radius_row)

        root.addSpacing(6)

        # Show Scrollbar
        sb_row = QHBoxLayout()
        sb_row.addWidget(QLabel("↕", styleSheet="color:#cccccc;font-size:12px;"))
        sb_row.addWidget(QLabel("Scrollbar", styleSheet="color:#cccccc;font-size:12px;"))
        sb_row.addStretch()
        self.sb_btn = QPushButton()
        self.sb_btn.setCheckable(True)
        self.sb_btn.setChecked(self.overlay.show_scrollbar)
        self.sb_btn.setFixedSize(48, 20)
        self.sb_btn.setObjectName("toggle_btn")
        self.sb_btn.clicked.connect(self._on_sb)
        self._refresh_sb()
        sb_row.addWidget(self.sb_btn)
        root.addLayout(sb_row)

    # ── refresh helpers ──────────────────────────────────────────────────────
    def _on_sb(self, checked):
        self.overlay._set_show_scrollbar(checked)
        self._refresh_sb()

    def _refresh_sb(self):
        self.sb_btn.setText("ON" if self.sb_btn.isChecked() else "OFF")

    def _on_aot(self, checked):
        self.overlay.always_on_top = checked
        self.overlay._apply_window_flags()
        self.overlay._save_config()
        self._refresh_aot()

    def _refresh_aot(self):
        self.aot_btn.setText("ON" if self.aot_btn.isChecked() else "OFF")

    def _refresh_key(self):
        k = self.overlay.chat_hotkey
        display = k if len(k) <= 3 else k[1:-1][:4]
        self.key_display.setText(display)

    def _refresh_theme_btns(self):
        current = self.overlay.current_theme
        for name, t in THEMES.items():
            r, g, b = t["bg"]
            selected = (name == current)
            border = f"2px solid {t['accent']}" if selected else "1px solid rgba(255,255,255,18)"
            self._theme_btns[name].setStyleSheet(f"""
                QPushButton {{
                    background: rgb({r},{g},{b});
                    color: {t['text']};
                    border: {border};
                    border-radius: 5px;
                    font-size: 10px;
                    font-weight: {'bold' if selected else 'normal'};
                    padding: 0 4px;
                }}
                QPushButton:hover {{ border: 2px solid {t['accent']}; }}
            """)

    def _refresh_accent_btns(self):
        current = self.overlay.accent_color.lower()
        for color, btn in self._accent_btns.items():
            selected = color.lower() == current
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    border-radius: 4px;
                    border: {'2px solid white' if selected else '1px solid rgba(255,255,255,20)'};
                }}
                QPushButton:hover {{ border: 2px solid white; }}
            """)

    def _refresh_size_btns(self):
        current = self.overlay.font_size
        ac = self.overlay.accent_color
        for size, btn in self._size_btns.items():
            selected = (size == current)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {ac if selected else 'rgba(255,255,255,10)'};
                    border-radius: 4px;
                    color: {'white' if selected else '#777'};
                    font-size: 11px;
                    font-weight: {'bold' if selected else 'normal'};
                    border: none;
                }}
                QPushButton:hover {{ background: {ac}; color: white; }}
            """)

    def set_recording_state(self, recording: bool):
        if recording:
            self.set_key_btn.setText("…")
            self.set_key_btn.setEnabled(False)
            self.key_display.setText("?")
        else:
            self.set_key_btn.setText("Set")
            self.set_key_btn.setEnabled(True)
            self._refresh_key()


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------
class ImageDialog(QDialog):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Viewer")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background: rgba(0, 0, 0, 210);")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Scale to screen if too large
        screen = QApplication.primaryScreen().geometry()
        max_w, max_h = screen.width() * 0.8, screen.height() * 0.8
        
        if pixmap.width() > max_w or pixmap.height() > max_h:
            pixmap = pixmap.scaled(int(max_w), int(max_h), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
        self.img_label.setPixmap(pixmap)
        layout.addWidget(self.img_label)
        
    def mousePressEvent(self, event):
        self.close()

class ImageLabel(QLabel):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.original_pixmap = QPixmap(file_path)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")
        
        max_w = 200
        if self.original_pixmap.width() > max_w:
            scaled = self.original_pixmap.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
        else:
            scaled = self.original_pixmap
        self.setPixmap(scaled)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dialog = ImageDialog(self.original_pixmap, self.window())
            self.dialog.show()

# ---------------------------------------------------------------------------
# Main overlay
# ---------------------------------------------------------------------------
class ChatOverlay(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config        = config

        # State
        self.chat_open     = False
        self.always_on_top = bool(config.get("always_on_top", True))
        self.chat_hotkey   = config.get("chat_hotkey",   "`")
        self.opacity_value = float(config.get("opacity", 0.8))
        self.text_color    = config.get("text_color",    "#ffffff")
        self.accent_color  = config.get("accent_color",  "#7289da")
        self.current_theme = config.get("theme",         "Discord")
        self.font_size     = int(config.get("font_size",     13))
        self.corner_radius = int(config.get("corner_radius", 10))
        self.show_scrollbar= bool(config.get("show_scrollbar", False))
        self.bg_rgb        = tuple(config.get("bg_rgb", [20, 20, 28]))
        self._recording    = False
        self.current_attachment = None

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
    # UI construction
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

        # ── Title bar (doubles as drag handle — no separate strip) ───────────
        self.title_bar = TitleBar(self)
        self.title_bar.settings_btn.clicked.connect(self._toggle_settings)
        self.title_bar.close_btn.clicked.connect(self.close)
        bg.addWidget(self.title_bar)

        # ── Settings panel (hidden by default) ───────────────────────────────
        self.settings_panel = SettingsPanel(self)
        self.settings_panel.setVisible(False)
        bg.addWidget(self.settings_panel)

        # ── Thin separator ────────────────────────────────────────────────────
        bg.addWidget(_separator("title_separator"))

        # ── Chat scroll area ──────────────────────────────────────────────────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        self._apply_scrollbar_policy()
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.chat_widget = QWidget()
        self.chat_widget.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setSpacing(2)
        self.scroll_area.setWidget(self.chat_widget)
        bg.addWidget(self.scroll_area, 1)

        # ── Attachment preview row ────────────────────────────────────────────
        self.attachment_widget = QWidget()
        self.attachment_widget.setVisible(False)
        self.attachment_layout = QHBoxLayout(self.attachment_widget)
        self.attachment_layout.setContentsMargins(8, 0, 4, 0)
        
        self.attachment_label = QLabel()
        self.attachment_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.attachment_layout.addWidget(self.attachment_label)
        
        self.remove_attachment_btn = QPushButton("✕")
        self.remove_attachment_btn.setFixedSize(18, 18)
        self.remove_attachment_btn.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        self.remove_attachment_btn.clicked.connect(self._clear_attachment)
        self.attachment_layout.addWidget(self.remove_attachment_btn)
        self.attachment_layout.addStretch()
        bg.addWidget(self.attachment_widget)

        # ── Input row + resize grip ───────────────────────────────────────────
        input_row = QHBoxLayout()
        input_row.setContentsMargins(8, 0, 4, 0)
        
        self.attach_btn = QPushButton("📎")
        self.attach_btn.setFixedSize(22, 22)
        self.attach_btn.setToolTip("Attach File")
        self.attach_btn.clicked.connect(self._open_file_dialog)
        input_row.addWidget(self.attach_btn)

        self.input_box = ChatInput()
        self._refresh_placeholder()
        self.input_box.returnPressed.connect(self._send_message)
        self.input_box.image_pasted.connect(self._on_image_pasted)
        input_row.addWidget(self.input_box)

        grip = QSizeGrip(self)
        grip.setFixedSize(14, 14)
        input_row.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        bg.addLayout(input_row)

        self.resize(400, 480)

    def _toggle_settings(self):
        self.settings_panel.setVisible(not self.settings_panel.isVisible())

    # -----------------------------------------------------------------------
    # Window flags (always-on-top + click-through)
    # -----------------------------------------------------------------------
    def _apply_window_flags(self):
        flags = Qt.WindowType.FramelessWindowHint
        if self.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
            if not self.chat_open:
                flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.show()

    def _apply_scrollbar_policy(self):
        if self.show_scrollbar:
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # -----------------------------------------------------------------------
    # Stylesheet (all dynamic values go through here)
    # -----------------------------------------------------------------------
    def _apply_styles(self):
        r, g, b = self.bg_rgb
        a  = int(self.opacity_value * 255)
        cr = self.corner_radius
        ac = self.accent_color
        tc = self.text_color

        self.setStyleSheet(f"""
            #bg_frame {{
                background-color: rgba({r},{g},{b},{a});
                border-radius: {cr}px;
                border: 1px solid rgba(255,255,255,15);
            }}
            #title_bar {{
                background: transparent;
                border-top-left-radius: {cr}px;
                border-top-right-radius: {cr}px;
            }}
            #title_label {{
                color: rgba(255,255,255,35);
                font-size: 11px;
                background: transparent;
            }}
            #title_separator {{
                background: {ac};
                max-height: 1px;
            }}
            #settings_panel {{
                background: rgba(0,0,0,45);
                border-bottom: 1px solid rgba(255,255,255,10);
            }}
            QLabel {{ color: {tc}; background: transparent; }}
            QLineEdit {{
                background: rgba(0,0,0,110);
                color: {tc};
                border: 1px solid rgba(255,255,255,15);
                border-radius: 5px;
                padding: 5px 8px;
                font-size: {self.font_size}px;
            }}
            QLineEdit:focus {{ border: 1px solid {ac}; }}
            QPushButton {{
                background: transparent;
                border: none;
                color: rgba(255,255,255,40);
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,12);
                border-radius: 4px;
                color: white;
            }}
            #close_btn:hover {{
                background: rgba(220,50,50,150);
                border-radius: 4px;
                color: white;
            }}
            #toggle_btn {{
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
                color: white;
            }}
            #toggle_btn:checked  {{ background: {ac}; }}
            #toggle_btn:!checked {{ background: rgba(255,255,255,15); color: #555; }}
            #key_display {{
                background: rgba(255,255,255,8);
                color: #aaaaaa;
                border-radius: 4px;
                font-size: 11px;
                font-family: monospace;
            }}
            #set_key_btn {{
                background: rgba(255,255,255,8);
                border-radius: 4px;
                color: #888888;
                font-size: 11px;
            }}
            #set_key_btn:hover {{ background: {ac}; color: white; }}
            #custom_color_btn {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #f87171, stop:0.25 #fb923c,
                    stop:0.5  #4ade80, stop:0.75 #60a5fa, stop:1 #a78bfa);
                border-radius: 4px;
                color: white;
                font-size: 13px;
                font-weight: bold;
            }}
            QSlider::groove:horizontal {{
                background: rgba(255,255,255,18);
                height: 3px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {ac};
                width: 12px; height: 12px;
                border-radius: 6px; margin: -5px 0;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 2px 2px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 30);
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {ac};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        """)

    # -----------------------------------------------------------------------
    # Appearance setters
    # -----------------------------------------------------------------------
    def _apply_theme(self, name: str):
        if name not in THEMES:
            return
        t = THEMES[name]
        self.current_theme = name
        self.bg_rgb        = t["bg"]
        self.accent_color  = t["accent"]
        self.text_color    = t["text"]
        self._apply_styles()
        self.settings_panel._refresh_theme_btns()
        self.settings_panel._refresh_accent_btns()
        self.settings_panel._refresh_size_btns()
        self._save_config()

    def _set_accent(self, color: str):
        self.accent_color  = color
        self.current_theme = ""
        self._apply_styles()
        self.settings_panel._refresh_theme_btns()
        self.settings_panel._refresh_accent_btns()
        self.settings_panel._refresh_size_btns()
        self._save_config()

    def _pick_custom_accent(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self, "Pick accent colour")
        if color.isValid():
            self._set_accent(color.name())

    def _set_font_size(self, size: int):
        self.font_size = size
        self._apply_styles()
        self.settings_panel._refresh_size_btns()
        self._save_config()

    def _set_corner_radius(self, value: int):
        self.corner_radius = value
        self._apply_styles()
        self._save_config()

    def _set_show_scrollbar(self, checked: bool):
        self.show_scrollbar = checked
        self._apply_scrollbar_policy()
        self._save_config()

    def _set_opacity(self, value: int):
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
                if len(item) == 4:
                    self._add_message(item[1], item[2], item[3])
                else:
                    self._add_message(item[1], item[2])
            elif item[0] == "status":
                self._add_status(item[1])

    def _add_message(self, author, content, image_paths=None):
        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setText(
            f'<span style="color:{self.accent_color};font-weight:bold;'
            f'font-size:{self.font_size}px;">{author}</span>'
            f'<span style="color:{self.text_color};font-size:{self.font_size}px;">: {content}</span>'
        )
        lbl.setStyleSheet("padding: 1px 8px;")
        self.chat_layout.addWidget(lbl)
        
        if image_paths:
            for path in image_paths:
                img_lbl = ImageLabel(path)
                img_lbl.setStyleSheet("padding: 2px 8px;")
                self.chat_layout.addWidget(img_lbl)

        # Always snap to latest — regardless of typing state
        QTimer.singleShot(0,  self._scroll_to_bottom)
        QTimer.singleShot(50, self._scroll_to_bottom)   # second pass after layout settles

    def _add_status(self, text):
        lbl = QLabel(f"<i>{text}</i>")
        lbl.setStyleSheet("color: #444444; padding: 1px 8px; font-size: 11px;")
        self.chat_layout.addWidget(lbl)
        QTimer.singleShot(0,  self._scroll_to_bottom)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    # -----------------------------------------------------------------------
    # Attachments
    # -----------------------------------------------------------------------
    def _open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Attach File")
        if file_path:
            self.current_attachment = {"path": file_path}
            import os
            self.attachment_label.setText(f"📎 {os.path.basename(file_path)}")
            self.attachment_widget.setVisible(True)

    def _on_image_pasted(self, img_bytes, filename):
        self.current_attachment = {"bytes": img_bytes, "filename": filename}
        self.attachment_label.setText(f"📎 {filename}")
        self.attachment_widget.setVisible(True)

    def _clear_attachment(self):
        self.current_attachment = None
        self.attachment_widget.setVisible(False)

    # -----------------------------------------------------------------------
    # Sending  — NO auto-close after Enter; user controls when to close chat
    # -----------------------------------------------------------------------
    def _send_message(self):
        content = self.input_box.text().strip()
        if content or self.current_attachment:
            self.discord_mgr.send_webhook_message(content, self.current_attachment)
            self.input_box.clear()
            self._clear_attachment()
        # ↑ Intentionally NOT calling _close_chat() here.
        # User presses Esc or the chat hotkey again to dismiss.

    # -----------------------------------------------------------------------
    # Chat open / close
    # -----------------------------------------------------------------------
    def _open_chat(self):
        self.chat_open = True
        self._apply_window_flags()   # removes click-through, calls show()
        self.title_bar.title_label.setText("Discord Overlay  💬")
        # Scroll to latest so user sees newest messages when they open chat
        QTimer.singleShot(0,   self._scroll_to_bottom)
        # Grab focus reliably: defer until after window is fully shown & painted
        QTimer.singleShot(80,  self._grab_focus)

    def _close_chat(self):
        self.chat_open = False
        self.input_box.clearFocus()
        self._apply_window_flags()   # re-applies click-through
        self.title_bar.title_label.setText("Discord Overlay")

    def _toggle_chat(self):
        if self.chat_open:
            self._close_chat()
        else:
            self._open_chat()

    def _grab_focus(self):
        """Force keyboard focus into the input box — works even from a game."""
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 9)          # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)    # steal foreground
        except Exception:
            pass
        self.raise_()
        self.activateWindow()
        self.input_box.setFocus()

    def _refresh_placeholder(self):
        k = self.chat_hotkey
        self.input_box.setPlaceholderText(
            f"Press {k!r} to open  •  Enter sends  •  Esc or {k!r} to close"
        )

    # -----------------------------------------------------------------------
    # Hotkey listener  (pynput, background thread)
    # -----------------------------------------------------------------------
    def _start_listener(self):
        self._listener = keyboard.Listener(on_press=self._on_key)
        self._listener.daemon = True
        self._listener.start()

    def _on_key(self, key):
        # ── Key-recording mode ───────────────────────────────────────────────
        if self._recording:
            if isinstance(key, keyboard.Key) and key in (
                keyboard.Key.shift,   keyboard.Key.shift_r,
                keyboard.Key.ctrl,    keyboard.Key.ctrl_r,
                keyboard.Key.alt,     keyboard.Key.alt_r,
                keyboard.Key.cmd,     keyboard.Key.cmd_r,
            ):
                return
            try:
                char = key.char
                if char:
                    self._hotkey_signals.key_recorded.emit(char)
            except AttributeError:
                self._hotkey_signals.key_recorded.emit(f"<{key.name}>")
            return

        # ── Normal mode ──────────────────────────────────────────────────────
        if key == keyboard.Key.esc and self.chat_open:
            self._hotkey_signals.toggle_chat.emit()
            return

        hk = self.chat_hotkey
        try:
            char = key.char
        except AttributeError:
            char = None

        if hk.startswith("<") and hk.endswith(">"):
            try:
                if key.name == hk[1:-1]:
                    self._hotkey_signals.toggle_chat.emit()
            except AttributeError:
                pass
        elif char == hk:
            self._hotkey_signals.toggle_chat.emit()

    def _start_key_recording(self):
        self._recording = True
        self.settings_panel.set_recording_state(True)

    def _finish_key_recording(self, key_str: str):
        self._recording  = False
        self.chat_hotkey = key_str
        self.config["chat_hotkey"] = key_str
        self.settings_panel.set_recording_state(False)
        self._refresh_placeholder()
        self._save_config()

    # -----------------------------------------------------------------------
    # Config persistence
    # -----------------------------------------------------------------------
    def _save_config(self):
        self.config.update({
            "opacity":       self.opacity_value,
            "chat_hotkey":   self.chat_hotkey,
            "always_on_top": self.always_on_top,
            "theme":         self.current_theme,
            "accent_color":  self.accent_color,
            "text_color":    self.text_color,
            "font_size":     self.font_size,
            "corner_radius": self.corner_radius,
            "show_scrollbar": self.show_scrollbar,
            "bg_rgb":        list(self.bg_rgb),
        })
        try:
            base = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                    else os.path.dirname(os.path.abspath(__file__)))
            with open(os.path.join(base, "config.json"), "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Config save error: {e}")

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
# Config loader  (with migration for older config.json versions)
# ---------------------------------------------------------------------------
def load_config():
    base = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
            else os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "config.json")

    config = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                config = json.load(f)
        except Exception:
            config = {}

    # Apply defaults for any missing keys (handles old config.json versions)
    changed = False
    for key, val in CONFIG_DEFAULTS.items():
        if key not in config:
            config[key] = val
            changed = True

    # Bootstrap required Discord fields if totally missing
    for key, placeholder in [
        ("username",    "Player1"),
        ("bot_token",   "YOUR_BOT_TOKEN_HERE"),
        ("webhook_url", "YOUR_WEBHOOK_URL_HERE"),
        ("channel_id",  "123456789012345678"),
    ]:
        if key not in config:
            config[key] = placeholder
            changed = True

    if changed:
        try:
            with open(path, "w") as f:
                json.dump(config, f, indent=4)
        except Exception:
            pass

    return config


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
