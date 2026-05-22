import json
import logging
import os

from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush
from PyQt6.QtWidgets import QWidget, QApplication

from utils import AppPaths


class FloatingButton(QWidget):
    """Floating AI button -- entry point widget.

    Always-on-top, draggable, semi-transparent.
    Creates and manages the sidebar internally.

    Drag -> sets which monitor sidebar appears on.
    Click -> toggles sidebar visibility.
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
        self._potential_drag = False
        self._system_moving = False
        self._press_pos = QPoint()
        self._drag_offset = QPoint()
        self._hovered = False
        self._show_red_border = True

        # opacity via alpha paint (Wayland-safe)
        self._current_alpha = 160  # ~63 %
        self._target_alpha = 160

        self._move_to_center()

        center = self.geometry().center()
        screen = QApplication.screenAt(center)
        logging.info(
            f"[FloatingButton] Position at ({self.x()}, {self.y()}), "
            f"center ({center.x()}, {center.y()}), "
            f"screen: {screen.name() if screen else 'NONE'}"
        )

        # alpha animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_alpha)
        self._anim_timer.start(16)

        # listen for screen changes (fires on Wayland after system move)
        wh = self.windowHandle()
        if wh is not None:
            wh.screenChanged.connect(self._on_screen_changed)

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

    def _set_target_alpha(self, ratio):
        self._target_alpha = max(80, min(255, int(255 * ratio)))

    def _tick_alpha(self):
        cur = self._current_alpha
        diff = self._target_alpha - cur
        if abs(diff) > 1:
            self._current_alpha = cur + int(diff * 0.2)
            self.update()

    # -- paint -----------------------------------------------------------------

    def paintEvent(self, event):
        alpha = self._current_alpha
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(2, 2, -2, -2)

        if self._show_red_border:
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        # shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, min(alpha // 3, 60)))
        painter.drawEllipse(r.translated(0, 2))

        # bg
        if self._hovered or self._potential_drag or self._system_moving:
            base = QColor(60, 120, 240, min(alpha + 40, 255))
        else:
            base = QColor(45, 45, 52, alpha)
        painter.setBrush(QBrush(base))
        painter.setPen(QPen(QColor(255, 255, 255, min(alpha // 3, 80)), 1.5))
        painter.drawEllipse(r)

        # icon
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

    # -- mouse: Wayland-compatible drag using startSystemMove -------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.pos()
            self._potential_drag = True
            self._system_moving = False
            self._set_target_alpha(1.0)
            self.update()

    def mouseMoveEvent(self, event):
        if (
                event.buttons() & Qt.MouseButton.LeftButton
                and self._potential_drag
                and not self._system_moving
        ):
            delta = (
                    event.globalPosition().toPoint() - self._press_pos
            ).manhattanLength()
            if delta > 8:
                # Use compositor move (works on Wayland + X11 via xdg-shell)
                wh = self.windowHandle()
                if wh is not None:
                    wh.startSystemMove()
                    self._system_moving = True
                    self._potential_drag = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._potential_drag:
                # was a click, not a drag -- sync screen before showing sidebar
                self._potential_drag = False
                self._update_target_screen()
                self.sidebar.toggle_sidebar()
            elif self._system_moving:
                # system move just finished -- update target
                self._system_moving = False
                self._clamp_to_screen()
                self._update_target_screen()
                self._save_position()

        self._potential_drag = False
        self._system_moving = False
        self._set_target_alpha(0.85 if self._hovered else 0.63)
        self.update()

    def _on_screen_changed(self, screen):
        """Called by QWindow when the window moves to a different output."""
        if screen:
            logging.info(f"[FloatingButton] Screen changed to: {screen.name()}")
            # The move is in progress or just finished; update sidebar target
            if self._system_moving:
                self._update_target_screen()

    # -- hover -----------------------------------------------------------------

    def enterEvent(self, event):
        self._hovered = True
        self._set_target_alpha(1.0)
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        if not self._potential_drag and not self._system_moving:
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
            if any(
                    s.geometry().intersects(QRect(x, y, self.SIZE, self.SIZE))
                    for s in QApplication.screens()
            ):
                self.move(x, y)
            else:
                raise ValueError("off-screen")
        except Exception:
            self._move_to_center()
