import json
import logging
import os

from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush
from PyQt6.QtWidgets import QWidget, QApplication

from utils import AppPaths


class FloatingButton(QWidget):
    """Floating AI button — entry point widget.

    Always-on-top, draggable, semi-transparent.
    Creates and manages the sidebar internally.

    Drag -> sets which monitor sidebar appears on.
    Click -> toggles sidebar visibility.

    Uses WA_TranslucentBackground + alpha colours for transparency,
    because setWindowOpacity is not supported on Wayland.
    """

    SIZE = 64
    MARGIN = 16

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._paths = AppPaths()
        self._sidebar = None  # created lazily

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.SIZE, self.SIZE)

        # icon
        icon_path = self._paths.get_path('images', 'tray.svg')
        self._icon = QPixmap(icon_path)
        if self._icon.isNull():
            logging.error(f"[FloatingButton] Cannot load icon: {icon_path}")

        # state
        self._dragging = False
        self._drag_start = QPoint()
        self._drag_offset = QPoint()
        self._hovered = False
        self._show_red_border = True  # remove once user confirms visibility

        # overlay opacity is done via alpha in paintEvent, NOT setWindowOpacity
        # (Wayland does not support setWindowOpacity)
        self._current_alpha = 160  # ~63 % opacity (0-255)

        self._move_to_center()

        center = self.geometry().center()
        screen = QApplication.screenAt(center)
        logging.info(
            f"[FloatingButton] Position at ({self.x()}, {self.y()}), "
            f"center ({center.x()}, {center.y()}), "
            f"screen: {screen.name() if screen else 'NONE'}"
        )

        # repaint timer for smooth alpha transitions (instead of opacity animation)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_alpha)
        self._anim_timer.start(16)

        self.show()
        self.raise_()
        logging.info("[FloatingButton] Shown and raised")

    # -- lazy sidebar ----------------------------------------------------------

    @property
    def sidebar(self):
        if self._sidebar is None:
            logging.info("[FloatingButton] First use - creating sidebar lazily")
            from sidebar import Sidebar
            self._sidebar = Sidebar()
        return self._sidebar

    # -- alpha helpers ---------------------------------------------------------

    def _set_target_alpha(self, visible_ratio):
        """visible_ratio: 0.0 (fully invisible) .. 1.0 (fully opaque)"""
        self._target_alpha = max(80, min(255, int(255 * visible_ratio)))

    def _tick_alpha(self):
        cur = self._current_alpha
        target = getattr(self, '_target_alpha', cur)
        diff = target - cur
        if abs(diff) > 1:
            self._current_alpha = cur + int(diff * 0.2)
            self.update()  # triggers repaint with new alpha

    # -- paint -----------------------------------------------------------------

    def paintEvent(self, event):
        alpha = self._current_alpha

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(2, 2, -2, -2)

        # debug red border
        if self._show_red_border:
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        # subtle shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, min(alpha // 3, 60)))
        painter.drawEllipse(r.translated(0, 2))

        # background circle (alpha-driven)
        if self._hovered or self._dragging:
            base = QColor(60, 120, 240, min(alpha + 40, 255))
        else:
            base = QColor(45, 45, 52, alpha)
        painter.setBrush(QBrush(base))
        painter.setPen(QPen(QColor(255, 255, 255, min(alpha // 3, 80)), 1.5))
        painter.drawEllipse(r)

        # icon (semi-transparent as well)
        if self._icon and not self._icon.isNull():
            icon_size = self.SIZE - 20
            scaled = self._icon.scaled(
                icon_size, icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2

            # draw icon with alpha by painting onto a temporary transparent pixmap
            tinted = QPixmap(scaled.size())
            tinted.fill(Qt.GlobalColor.transparent)
            tp = QPainter(tinted)
            tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            tp.drawPixmap(0, 0, scaled)
            tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            tp.fillRect(tinted.rect(), QColor(255, 255, 255, alpha))
            tp.end()

            painter.drawPixmap(x, y, tinted)

        painter.end()

    # -- mouse -----------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_offset = self._drag_start - self.pos()
            self._set_target_alpha(1.0)
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = (event.globalPosition().toPoint() -
                     self._drag_start).manhattanLength()
            if delta > 8:
                self._dragging = True
            if self._dragging:
                self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self._dragging = False
                self._clamp_to_screen()
                self._update_target_screen()
                self._save_position()
            else:
                self.sidebar.toggle_sidebar()
            self._set_target_alpha(0.85 if self._hovered else 0.63)
            self.update()

    # -- hover -----------------------------------------------------------------

    def enterEvent(self, event):
        self._hovered = True
        self._set_target_alpha(1.0)
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        if not self._dragging:
            self._set_target_alpha(0.63)
        self.update()

    # -- screen logic ----------------------------------------------------------

    def _update_target_screen(self):
        center = self.geometry().center()
        screen = QApplication.screenAt(center)
        if not screen:
            logging.warning("[FloatingButton] No screen found at centre")
            return
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            if s.name() == screen.name():
                self.sidebar.set_manual_screen(i)
                geo = screen.geometry()
                logging.info(
                    f"[FloatingButton] -> Screen {i}: {screen.name()} "
                    f"({geo.width()}x{geo.height()} @ {geo.x()},{geo.y()})"
                )
                break

    def _clamp_to_screen(self):
        center = self.geometry().center()
        screen = QApplication.screenAt(center)
        if not screen:
            return
        g = screen.geometry()
        x = max(g.x(), min(self.x(), g.x() + g.width() - self.SIZE))
        y = max(g.y(), min(self.y(), g.y() + g.height() - self.SIZE))
        self.move(x, y)

    # -- position --------------------------------------------------------------

    def _move_to_center(self):
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
        try:
            with open(self._get_pos_file(), 'w') as f:
                json.dump({'x': self.x(), 'y': self.y()}, f)
        except Exception as e:
            logging.error(f"[FloatingButton] Save failed: {e}")

    def _load_position(self):
        path = self._get_pos_file()
        if not os.path.exists(path):
            self._move_to_center()
            return
        try:
            with open(path) as f:
                data = json.load(f)
            x, y = data.get('x', 0), data.get('y', 0)
            if any(s.geometry().intersects(QRect(x, y, self.SIZE, self.SIZE))
                   for s in QApplication.screens()):
                self.move(x, y)
            else:
                raise ValueError("off-screen")
        except Exception:
            self._move_to_center()
