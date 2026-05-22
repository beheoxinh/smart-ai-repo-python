import json
import logging
import os

from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush, QShortcut, QKeySequence
from PyQt6.QtWidgets import QWidget, QApplication, QHBoxLayout

from utils import AppPaths
from components.sidebar_panel import SidebarPanel


class FloatingButton(QWidget):
    """Single window containing floating icon (left) + optional sidebar (right).

    Collapsed: 64×64 window (button only).
    Expanded:  (64 + sidebar_w) × screen_height (button + sidebar at current pos).

    Sidebar is always on the same screen as the button because they share
    one window surface — no setScreen() needed on Wayland.
    """

    SIZE = 64
    MIN_SIDEBAR_WIDTH = 360

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._paths = AppPaths()

        # ── window flags ──────────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        # ── icon ──────────────────────────────────────────────────────────
        icon_path = self._paths.get_path('images', 'tray.svg')
        self._icon = QPixmap(icon_path)
        if self._icon.isNull():
            logging.error(f"[FloatingButton] Cannot load icon: {icon_path}")

        # ── sidebar panel (embedded child) ────────────────────────────────
        self._sidebar = SidebarPanel(self)
        self._sidebar.setVisible(False)
        self._sidebar_w = self.MIN_SIDEBAR_WIDTH
        self._sidebar_visible = False

        # Connect signals from sidebar
        self._sidebar.resizeRequested.connect(self._on_sidebar_resize)
        self._sidebar.closeRequested.connect(self._on_sidebar_close)

        # ── layout: sidebar takes remaining space after button area ────────
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Sidebar panel fills the layout; the button is painted in the
        # leading 64px which are transparent in the layout.
        self._layout.addWidget(self._sidebar)

        # ── drag / click state ────────────────────────────────────────────
        self._press_pos = QPoint()
        self._dragging = False
        self._hovered = False

        # ── alpha paint (Wayland-safe, no setWindowOpacity) ───────────────
        self._current_alpha = 160
        self._target_alpha = 160

        # ── keyboard shortcut ─────────────────────────────────────────────
        self._shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        self._shortcut.activated.connect(self._toggle_sidebar)

        # ── position from persistence ─────────────────────────────────────
        self._load_position()

        # ── alpha animation timer ─────────────────────────────────────────
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_alpha)
        self._anim_timer.start(16)

        # ── initial size (button only) ────────────────────────────────────
        self.setFixedSize(self.SIZE, self.SIZE)

        self.show()
        self.raise_()
        logging.info("[FloatingButton] Initialised (embedded sidebar)")

    # ── paint ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        """Paint the button circle at the left SIZE pixels of the window."""
        alpha = self._current_alpha
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Clip to button area (left SIZE × SIZE)
        button_rect = QRect(0, 0, self.SIZE, self.SIZE)
        painter.setClipRect(button_rect)
        r = button_rect.adjusted(2, 2, -2, -2)

        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, min(alpha // 3, 60)))
        painter.drawEllipse(r.translated(0, 2))

        # Background circle
        if self._hovered or self._dragging:
            base = QColor(60, 120, 240, min(alpha + 40, 255))
        else:
            base = QColor(45, 45, 52, alpha)
        painter.setBrush(QBrush(base))
        painter.setPen(QPen(QColor(255, 255, 255, min(alpha // 3, 80)), 1.5))
        painter.drawEllipse(r)

        # Icon
        if self._icon and not self._icon.isNull():
            icon_size = self.SIZE - 20
            scaled = self._icon.scaled(
                icon_size, icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            cx = (button_rect.width() - scaled.width()) // 2
            cy = (button_rect.height() - scaled.height()) // 2

            tinted = QPixmap(scaled.size())
            tinted.fill(Qt.GlobalColor.transparent)
            tp = QPainter(tinted)
            tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            tp.drawPixmap(0, 0, scaled)
            tp.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_DestinationIn
            )
            tp.fillRect(tinted.rect(), QColor(255, 255, 255, alpha))
            tp.end()

            painter.drawPixmap(cx, cy, tinted)

        painter.end()

    # ── alpha helpers ───────────────────────────────────────────────────────

    def _set_target_alpha(self, ratio):
        self._target_alpha = max(80, min(255, int(255 * ratio)))

    def _tick_alpha(self):
        cur = self._current_alpha
        diff = self._target_alpha - cur
        if abs(diff) > 1:
            self._current_alpha = cur + int(diff * 0.2)
            self.update()

    # ── mouse: drag (Wayland-safe startSystemMove) vs click ────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Only handle clicks in the button area (left SIZE px)
            if event.position().x() > self.SIZE:
                return
            self._press_pos = event.globalPosition().toPoint()
            self._dragging = False
            self._set_target_alpha(1.0)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and not self._dragging:
            delta = (
                    event.globalPosition().toPoint() - self._press_pos
            ).manhattanLength()
            if delta > 8:
                wh = self.windowHandle()
                if wh is not None:
                    wh.startSystemMove()
                    self._dragging = True

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self._dragging = False
                self._save_position()
            else:
                self._toggle_sidebar()

            self._set_target_alpha(0.70 if self._hovered else 0.50)
            self.update()

    # ── hover ───────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovered = True
        self._set_target_alpha(0.85)
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        if not self._dragging:
            self._set_target_alpha(0.50)
        self.update()

    # ── sidebar toggle ─────────────────────────────────────────────────────

    def _toggle_sidebar(self):
        if self._sidebar_visible:
            self._hide_sidebar()
        else:
            self._show_sidebar()

    def _show_sidebar(self):
        """Expand window width to show sidebar alongside the button."""
        self._sidebar_visible = True

        # Use screen height so the web view has room, but KEEP current position
        screen = QApplication.screenAt(self.geometry().center())
        if not screen:
            screen = QApplication.primaryScreen()
            if not screen:
                return

        window_w = self.SIZE + self._sidebar_w
        window_h = screen.geometry().height()

        self._sidebar.show_content()
        self._sidebar.setFixedWidth(self._sidebar_w)

        # Resize at current position — no forced screen-edge anchoring
        self.setFixedSize(window_w, window_h)

        logging.info(
            f"[FloatingButton] Sidebar shown: {window_w}x{window_h} @ "
            f"({self.x()},{self.y()}) on {screen.name()}"
        )

    def _hide_sidebar(self):
        """Shrink window back to button-only."""
        self._sidebar_visible = False
        self._sidebar.hide_content()
        self.setFixedSize(self.SIZE, self.SIZE)
        self.update()
        logging.info("[FloatingButton] Sidebar hidden")

    def _on_sidebar_close(self):
        """Called by sidebar watchdog or close button."""
        self._hide_sidebar()

    def _on_sidebar_resize(self, new_w):
        """Called during resize-handle drag — adjust window width only."""
        self._sidebar_w = new_w
        self._sidebar.setFixedWidth(new_w)

        window_w = self.SIZE + new_w
        self.setFixedSize(window_w, self.height())

    # ── position persistence ───────────────────────────────────────────────

    def _get_pos_file(self):
        return os.path.join(self._paths.get_data_dir(), 'button_pos.json')

    def _save_position(self):
        data = {'x': self.x(), 'y': self.y()}
        try:
            with open(self._get_pos_file(), 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logging.error(f"[FloatingButton] Save failed: {e}")

    def _load_position(self):
        path = self._get_pos_file()
        if not os.path.exists(path):
            self._place_default()
            return
        try:
            with open(path) as f:
                data = json.load(f)
            x, y = data.get('x', 0), data.get('y', 0)
            test_rect = QRect(x, y, self.SIZE, self.SIZE)
            on_screen = any(
                s.geometry().intersects(test_rect) for s in QApplication.screens()
            )
            if on_screen:
                self.move(x, y)
            else:
                raise ValueError("off-screen")
        except Exception:
            self._place_default()

    def _place_default(self):
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.geometry()
            self.move(
                g.x() + (g.width() - self.SIZE) // 2,
                g.y() + (g.height() - self.SIZE) // 2,
            )
