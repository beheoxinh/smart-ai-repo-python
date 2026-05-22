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
        else:
            logging.info(f"[FloatingButton] Icon loaded: {icon_path} ({self._icon.width()}x{self._icon.height()})")

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
        self._current_alpha = 0.5  # Default 50% opacity
        self._target_alpha = 0.5

        # ── keyboard shortcut ─────────────────────────────────────────────
        self._shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        self._shortcut.activated.connect(self._toggle_sidebar)

        # ── alpha animation timer ─────────────────────────────────────────
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_alpha)
        self._anim_timer.start(16)

        # ── force native window, then show (loads settings + position) ────
        self.winId()  # create native wl_surface + xdg-surface
        self._show_button()

        # ── workspace tracking ─────────────────────────────────────────────
        # Every 3 s, if sidebar is closed, force hide/show to re-map the
        # window onto the current GNOME workspace (Window type is workspace-
        # bound; the timer ensures the button follows the active workspace).
        self._ws_timer = QTimer(self)
        self._ws_timer.timeout.connect(self._reapply_workspace)
        self._ws_timer.start(3000)

        logging.info("[FloatingButton] Initialised")

    # ── unified show method (always respects saved settings) ───────────────

    def _show_button(self):
        """Show the button icon with saved opacity, size, and position from settings.

        This is the ONE place that controls how the button appears.
        Every code path that needs to show the button MUST call this method
        to guarantee opacity / size / position are always loaded from config.
        """
        self._load_position()  # restore saved position (x, y)
        self._load_settings()  # restore opacity + size from settings
        self.show()
        self.raise_()
        logging.info(
            f"[FloatingButton] Button shown: opacity={self._current_alpha:.0%}, "
            f"size={self.SIZE}px, pos=({self.x()},{self.y()})"
        )

    # ── workspace re-apply ──────────────────────────────────────────────────

    def _reapply_workspace(self):
        """Force re-map on the current GNOME workspace.

        hide() + show() triggers a full xdg-toplevel map cycle, which
        makes the compositor place the Window on the current (active)
        workspace.  Uses _show_button() to ensure opacity/size stay correct
        after the compositor resets window state.
        """
        if not self.isVisible() or self._sidebar_visible:
            return
        self._hovered = False
        self.hide()
        self._show_button()

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
        alpha = int(self._current_alpha * 255)
        if self._hovered:
            logging.debug(f"[FloatingButton] paintEvent: hovered=True, alpha={alpha}, _current_alpha={self._current_alpha}")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(2, 2, -2, -2)

        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, min(alpha // 3, 60)))
        painter.drawEllipse(r.translated(0, 2))

        # Background circle
        if self._hovered or self._dragging:
            base = QColor(70, 70, 78, min(alpha + 40, 255))  # Lighter gray on hover
        else:
            base = QColor(45, 45, 52, alpha)
        painter.setBrush(QBrush(base))
        painter.setPen(QPen(QColor(255, 255, 255, min(alpha // 3, 80)), 1.5))
        painter.drawEllipse(r)

        # Icon
        if self._icon and not self._icon.isNull():
            icon_size = max(self.SIZE - 20, 32)  # minimum 32px
            scaled = self._icon.scaled(
                icon_size, icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            cx = (self.width() - scaled.width()) // 2
            cy = (self.height() - scaled.height()) // 2

            # Simple opacity via painter
            painter.setOpacity(self._current_alpha)
            painter.drawPixmap(cx, cy, scaled)
            painter.setOpacity(1.0)  # restore

        painter.end()

    # ── alpha helpers ───────────────────────────────────────────────────────

    def _set_target_alpha(self, ratio):
        """Set target alpha (0.0 = transparent, 1.0 = opaque)."""
        self._target_alpha = max(0.0, min(1.0, ratio))

    def _tick_alpha(self):
        """Animate _current_alpha toward _target_alpha (both 0.0–1.0)."""
        cur = self._current_alpha
        diff = self._target_alpha - cur
        if abs(diff) > 0.005:
            self._current_alpha = cur + diff * 0.2
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
        self._save_settings({'sidebar_w': new_w})

    def _on_sidebar_height_resize(self, new_h):
        self._sidebar_h = new_h
        if self._sidebar is not None:
            self._sidebar.setFixedHeight(new_h)
        self._save_settings({'sidebar_h': new_h})

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

    def set_opacity(self, alpha_percent):
        """Set button opacity (0-100).

        Args:
            alpha_percent: Opacity percentage (0 = fully transparent, 100 = opaque)
        """
        alpha = alpha_percent / 100.0
        # Set both current and target for immediate effect
        self._current_alpha = alpha
        self._target_alpha = alpha
        self.update()
        self._save_settings({'opacity': alpha_percent})
        logging.info(f"[FloatingButton] Opacity set to {alpha_percent}%")

    def set_size(self, size):
        """Change button size.

        Args:
            size: New size in pixels (e.g., 48, 64, 96)
        """
        if size < 32 or size > 128:
            logging.warning(f"[FloatingButton] Invalid size {size} (valid: 32-128)")
            return

        # Update SIZE constant
        self.SIZE = size
        self.setFixedSize(size, size)

        # Reload and reposition to ensure proper placement
        self._load_position()
        self.update()

        self._save_settings({'size': size})
        logging.info(f"[FloatingButton] Size changed to {size}px")

    def toggle_button(self):
        """Toggle the FloatingButton window itself (show/hide).

        When hiding, also hides the sidebar and saves position.
        When showing, uses _show_button() to reload saved settings
        (opacity, size, position) instead of hardcoding defaults.
        Use this from tray icon menu.
        """
        if self.isVisible():
            logging.info("[FloatingButton] Hiding button (tray toggle)")
            self._save_position()
            if self._sidebar_visible:
                self._hide_sidebar()
            self.hide()
        else:
            logging.info("[FloatingButton] Showing button (tray toggle)")
            self._show_button()

    def _save_settings(self, updates):
        """Update settings in button_pos.json (merge with existing data)."""
        try:
            existing = json.loads(self._paths.read('button_pos.json'))
        except Exception:
            existing = {}

        existing.update(updates)
        self._paths.write('button_pos.json', json.dumps(existing, indent=2))
        logging.info(f"[FloatingButton] Settings saved: {updates}")

    def _load_settings(self):
        """Load opacity and size from button_pos.json."""
        try:
            data = json.loads(self._paths.read('button_pos.json'))

            # Load opacity (default 50%)
            opacity = data.get('opacity', 50)
            alpha = opacity / 100.0
            self._current_alpha = alpha
            self._target_alpha = alpha

            # Load size (default 64)
            size = data.get('size', 64)
            if size != self.SIZE:
                self.SIZE = size
                self.setFixedSize(size, size)

            logging.info(f"[FloatingButton] Settings loaded: opacity={opacity}%, size={size}px")
            return opacity, size
        except Exception as e:
            logging.warning(f"[FloatingButton] Failed to load settings: {e}")
            return 50, 64

    def get_opacity(self):
        """Get current opacity as percentage (0-100)."""
        try:
            data = json.loads(self._paths.read('button_pos.json'))
            return data.get('opacity', 50)
        except Exception:
            return 50

    def get_size(self):
        """Get current button size in pixels."""
        return self.SIZE

    def _save_position(self):
        # Merge with existing settings to preserve opacity/size
        try:
            existing = json.loads(self._paths.read('button_pos.json'))
        except Exception:
            existing = {}

        existing.update({
            'x': self.x(),
            'y': self.y(),
            'sidebar_w': self._sidebar_w,
            'sidebar_h': self._sidebar_h,
        })

        try:
            self._paths.write('button_pos.json', json.dumps(existing, indent=2))
        except Exception as e:
            logging.error(f"[FloatingButton] Save position failed: {e}")

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
