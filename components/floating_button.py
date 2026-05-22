import json
import logging
import os

from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush
from PyQt6.QtWidgets import QWidget, QApplication

from utils import AppPaths


class FloatingButton(QWidget):
    """Floating AI button — entry point widget.

    Always-on-top, draggable, semi-transparent circle.
    Creates and manages the sidebar lazily.

    Click → toggle sidebar.
    Drag → choose which monitor sidebar appears on (via _update_target_screen).

    On Wayland, sets sidebar as transient parent so compositor keeps
    both windows on the same output.
    """

    SIZE = 64

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._paths = AppPaths()
        self._sidebar = None
        self._ready = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.SIZE, self.SIZE)

        # Icon
        icon_path = self._paths.get_path('images', 'tray.svg')
        self._icon = QPixmap(icon_path)
        if self._icon.isNull():
            logging.error(f"[FloatingButton] Cannot load icon: {icon_path}")

        # State
        self._press_pos = QPoint()
        self._dragging = False
        self._hovered = False
        self._show_red_border = True

        # Opacity (alpha paint — Wayland-safe)
        self._current_alpha = 160
        self._target_alpha = 160

        self._load_position()

        wh = self.windowHandle()
        logging.info(
            f"[FloatingButton] Initial pos ({self.x()}, {self.y()}), "
            f"screen: {wh.screen().name() if wh and wh.screen() else 'NONE'}"
        )

        # Alpha animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_alpha)
        self._anim_timer.start(16)

        self.show()
        self.raise_()
        self._ready = True

        # Listen for compositor-initiated screen changes
        if wh is not None:
            wh.screenChanged.connect(self._on_screen_changed)

        logging.info("[FloatingButton] Shown and raised")

    # ── helpers ─────────────────────────────────────────────────────────────────

    @property
    def _current_screen(self):
        wh = self.windowHandle()
        return wh.screen() if wh else None

    def _set_target_alpha(self, ratio):
        self._target_alpha = max(80, min(255, int(255 * ratio)))

    def _tick_alpha(self):
        cur = self._current_alpha
        diff = self._target_alpha - cur
        if abs(diff) > 1:
            self._current_alpha = cur + int(diff * 0.2)
            self.update()

    # ── lazy sidebar ────────────────────────────────────────────────────────────

    @property
    def sidebar(self):
        if self._sidebar is None:
            logging.info("[FloatingButton] First use — creating sidebar lazily")
            from sidebar import Sidebar
            self._sidebar = Sidebar()
        return self._sidebar

    def _set_sidebar_transient_parent(self):
        """On Wayland, tell compositor sidebar belongs to button's output."""
        btn_wh = self.windowHandle()
        if btn_wh is None:
            return
        sidebar_wh = self.sidebar.windowHandle()
        if sidebar_wh is None:
            return
        sidebar_wh.setTransientParent(btn_wh)
        logging.info("[FloatingButton] Sidebar transient parent set")

    # ── paint ───────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        alpha = self._current_alpha
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(2, 2, -2, -2)

        # Debug red border
        if self._show_red_border:
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

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

        # Icon with alpha
        if self._icon and not self._icon.isNull():
            icon_size = self.SIZE - 20
            scaled = self._icon.scaled(
                icon_size, icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2

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

            painter.drawPixmap(x, y, tinted)

        painter.end()

    # ── mouse: Wayland-compatible drag with startSystemMove ─────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
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
                self._clamp_to_screen()
                self._update_target_screen()
                self._save_position()
            else:
                # Click — toggle sidebar
                self._update_target_screen()
                self.sidebar.toggle_sidebar()
                self._set_sidebar_transient_parent()

            self._target_alpha = 0.70 if self._hovered else 0.50
            self.update()

    # ── screen change ───────────────────────────────────────────────────────────

    def _on_screen_changed(self, screen):
        if not self._ready or not screen:
            return
        logging.info(f"[FloatingButton] Screen changed to: {screen.name()}")
        self._update_target_screen()

    # ── hover ───────────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovered = True
        self._target_alpha = 0.85
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        if not self._dragging:
            self._target_alpha = 0.50
        self.update()

    # ── screen logic ────────────────────────────────────────────────────────────

    def _update_target_screen(self):
        screen = self._current_screen
        if not screen:
            return
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            if s.name() == screen.name():
                self.sidebar.set_manual_screen(i)
                geo = screen.geometry()
                logging.info(
                    f"[FloatingButton] → Screen {i}: {screen.name()} "
                    f"({geo.width()}x{geo.height()} @ {geo.x()},{geo.y()})"
                )
                break

    def _clamp_to_screen(self):
        screen = self._current_screen
        if not screen:
            return
        g = screen.geometry()
        x = max(g.x(), min(self.x(), g.x() + g.width() - self.SIZE))
        y = max(g.y(), min(self.y(), g.y() + g.height() - self.SIZE))
        self.move(x, y)

    # ── position persistence ────────────────────────────────────────────────────

    def _place_default(self):
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.geometry()
            self.move(
                g.x() + (g.width() - self.SIZE) // 2,
                g.y() + (g.height() - self.SIZE) // 2,
            )

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

            # Validate: ensure at least partially visible on some screen
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
