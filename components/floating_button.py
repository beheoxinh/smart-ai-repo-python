import json
import logging
import os

from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush, QShortcut, QKeySequence
from PyQt6.QtWidgets import QWidget, QApplication

from components.sidebar_panel import SidebarPanel
from utils import AppPaths


class FloatingButton(QWidget):
    """Floating icon button — always 64×64, never resized.

    Sidebar is a separate window positioned at the button's right edge.
    Button position is NEVER affected by sidebar show/hide.
    """

    SIZE = 64

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
        self.setFixedSize(self.SIZE, self.SIZE)

        # ── icon ──────────────────────────────────────────────────────────
        icon_path = self._paths.get_path('images', 'tray.svg')
        self._icon = QPixmap(icon_path)
        if self._icon.isNull():
            logging.error(f"[FloatingButton] Cannot load icon: {icon_path}")

        # ── sidebar (separate window, no parent, not embedded) ────────────
        self._sidebar = None
        self._sidebar_w = 0
        self._sidebar_h = 0
        self._sidebar_visible = False

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

        # ── alpha animation timer ─────────────────────────────────────────
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_alpha)
        self._anim_timer.start(16)

        # ── force native window, position, then show ──────────────────
        self.winId()                # create native wl_surface + xdg-surface
        self._load_position()       # set geometry via QWindow.setGeometry
        self.show()
        self.raise_()
        logging.info("[FloatingButton] Initialised")

    # ── lazy sidebar ───────────────────────────────────────────────────────

    def _get_sidebar(self):
        if self._sidebar is None:
            self._sidebar = SidebarPanel(self)
            self._sidebar.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Window
            )
            self._sidebar.resizeRequested.connect(self._on_sidebar_resize)
            self._sidebar.resizeHeightRequested.connect(self._on_sidebar_height_resize)
            self._sidebar.closeRequested.connect(self._on_sidebar_close)
            # Direct bypass: nav_bar close button → FloatingButton
            self._sidebar.content_widget.nav_bar.closeClicked.connect(
                self._on_sidebar_close
            )
        return self._sidebar

    # ── paint ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        alpha = self._current_alpha
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(2, 2, -2, -2)

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
            cx = (self.width() - scaled.width()) // 2
            cy = (self.height() - scaled.height()) // 2

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

    def toggle_sidebar(self):
        """Public entry point for tray / keyboard shortcut."""
        self._toggle_sidebar()

    def _show_sidebar(self):
        """Show sidebar as an independent window — button position NEVER changes.

        Like CSS position: absolute — sidebar appears at the button's right
        edge (same Y) but does NOT push or move the button.
        Default size: 1/2 screen width × 2/3 screen height on first show.
        """
        self._sidebar_visible = True
        sidebar = self._get_sidebar()

        screen = QApplication.screenAt(self.geometry().center())
        if screen:
            sg = screen.geometry()
            sidebar_w = self._sidebar_w or sg.width() // 2
            sidebar_h = self._sidebar_h or int(sg.height() * 2 / 3)

            # Position: right of button, same Y
            sx = self.x() + self.SIZE
            sy = self.y()
            # Clamp horizontal so sidebar stays on-screen
            min_sx = sg.x()
            max_sx = sg.x() + sg.width() - sidebar_w
            sx = max(min_sx, min(sx, max_sx))
            # Vertical center on button (clamped to screen)
            btn_center_y = self.y() + self.SIZE // 2
            sy = btn_center_y - sidebar_h // 2
            sy = max(sg.y(), min(sy, sg.y() + sg.height() - sidebar_h))
        else:
            sidebar_w = self._sidebar_w or 500
            sidebar_h = self._sidebar_h or 500
            sx = self.x() + self.SIZE
            sy = self.y()

        # Force native handle + transient parent for positioning
        sidebar.winId()
        sidebar_wh = sidebar.windowHandle()
        btn_wh = self.windowHandle()
        if sidebar_wh and btn_wh:
            sidebar_wh.setTransientParent(btn_wh)

        sidebar.setGeometry(sx, sy, sidebar_w, sidebar_h)
        sidebar.show_content()
        sidebar.show()
        sidebar.raise_()

        logging.info(
            f"[FloatingButton] Sidebar {sidebar_w}x{sidebar_h} "
            f"at ({sx},{sy}) — button UNCHANGED at ({self.x()},{self.y()})"
        )

    def _hide_sidebar(self):
        """Hide sidebar window — button position is untouched."""
        self._sidebar_visible = False
        if self._sidebar is not None:
            self._sidebar.hide_content()
            self._sidebar.hide()
        logging.info("[FloatingButton] Sidebar hidden")

    def _on_sidebar_close(self):
        logging.info("[FloatingButton] closeRequested received — hiding sidebar")
        self._hide_sidebar()

    def _on_sidebar_resize(self, new_w):
        self._sidebar_w = new_w
        if self._sidebar is not None:
            self._sidebar.setFixedWidth(new_w)

    def _on_sidebar_height_resize(self, new_h):
        self._sidebar_h = new_h

    def _move_to(self, x, y):
        """Move window using native QWindow API (reliable on Wayland pre-map)."""
        wh = self.windowHandle()
        if wh is not None:
            wh.setGeometry(QRect(x, y, self.width(), self.height()))
        else:
            self.move(x, y)

    # ── position persistence ───────────────────────────────────────────────

    def _get_pos_file(self):
        return os.path.join(self._paths.get_data_dir(), 'button_pos.json')

    def _save_position(self):
        data = {
            'x': self.x(),
            'y': self.y(),
            'sidebar_w': self._sidebar_w,
            'sidebar_h': self._sidebar_h,
        }
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
                self._move_to(x, y)
            else:
                raise ValueError("off-screen")
            # Restore sidebar dimensions (0 = use defaults on first show)
            self._sidebar_w = data.get('sidebar_w', 0)
            self._sidebar_h = data.get('sidebar_h', 0)
        except Exception:
            self._place_default()

    def _place_default(self):
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.geometry()
            self._move_to(
                g.x() + g.width() - self.SIZE - 20,
                g.y() + g.height() // 2 - self.SIZE // 2,
            )
