import json
import logging
import os

from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush, QLinearGradient
from PyQt6.QtWidgets import QWidget, QApplication

from utils import AppPaths


class FloatingButton(QWidget):
    """Floating AI button -- drag to select monitor, click to toggle sidebar.

    Semi-transparent always-on-top widget that acts as a visual anchor
    for the sidebar.  Wherever you drag this button, *that* monitor becomes
    the sidebar's display target (calls ``sidebar.set_manual_screen()``).
    The existing edge-hover reveal logic is preserved.
    """

    SIZE = 56
    MARGIN = 20

    def __init__(self, sidebar, parent=None):
        super().__init__(parent)
        self.sidebar = sidebar
        self._paths = AppPaths()

        # --- window flags ---
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.setFixedSize(self.SIZE, self.SIZE)

        # --- icon ---
        icon_path = self._paths.get_path('images', 'tray.svg')
        self._icon = QPixmap(icon_path)
        if self._icon.isNull():
            logging.error(f"[FloatingButton] Cannot load icon: {icon_path}")

        # --- drag state ---
        self._dragging = False
        self._drag_start = QPoint()
        self._drag_offset = QPoint()
        self._hovered = False

        self._target_opacity = 0.50
        self.setWindowOpacity(0.50)

        # --- initial position ---
        self._load_position()

        # --- opacity animation timer ---
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate_opacity)
        self._anim_timer.start(16)  # ~60 fps

        self.show()
        logging.info("[FloatingButton] Initialized")

    # ── paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(2, 2, -2, -2)

        # subtle shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50))
        painter.drawEllipse(r.translated(0, 2))

        # background gradient
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        if self._hovered or self._dragging:
            grad.setColorAt(0, QColor(70, 140, 255, 230))
            grad.setColorAt(1, QColor(110, 80, 230, 230))
        else:
            grad.setColorAt(0, QColor(50, 50, 55, 200))
            grad.setColorAt(1, QColor(35, 35, 40, 220))

        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.2))
        painter.drawEllipse(r)

        # icon centered
        if self._icon and not self._icon.isNull():
            icon_size = self.SIZE - 16
            scaled = self._icon.scaled(
                icon_size, icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        painter.end()

    # ── mouse ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_offset = self._drag_start - self.pos()
            self._target_opacity = 0.85
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = (event.globalPosition().toPoint() - self._drag_start).manhattanLength()
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
                # Click (no meaningful drag) → toggle sidebar
                self.sidebar.toggle_sidebar()

            self._target_opacity = 0.70 if self._hovered else 0.50
            self.update()

    # ── hover ──────────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovered = True
        self._target_opacity = 0.85
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        if not self._dragging:
            self._target_opacity = 0.50
        self.update()

    # ── screen logic ───────────────────────────────────────────────────────────

    def _update_target_screen(self):
        """Determine which monitor the button centre is on; set sidebar target."""
        center = self.geometry().center()
        screen = QApplication.screenAt(center)
        if not screen:
            logging.warning("[FloatingButton] No screen found at centre position")
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
        """Keep button fully visible inside whichever monitor it landed on."""
        center = self.geometry().center()
        screen = QApplication.screenAt(center)
        if not screen:
            return

        g = screen.geometry()
        x = max(g.x(), min(self.x(), g.x() + g.width() - self.SIZE))
        y = max(g.y(), min(self.y(), g.y() + g.height() - self.SIZE))
        self.move(x, y)

    # ── opacity animation ──────────────────────────────────────────────────────

    def _animate_opacity(self):
        cur = self.windowOpacity()
        diff = self._target_opacity - cur
        if abs(diff) > 0.005:
            self.setWindowOpacity(cur + diff * 0.18)

    # ── position persistence ───────────────────────────────────────────────────

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
                logging.info(f"[FloatingButton] Restored position ({x}, {y})")
            else:
                raise ValueError("off-screen")
        except Exception as e:
            logging.warning(f"[FloatingButton] Position invalid ({e}), using default")
            self._place_default()

    def _place_default(self):
        """Bottom-left corner of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.geometry()
            self.move(g.x() + self.MARGIN, g.y() + g.height() - self.SIZE - self.MARGIN)
