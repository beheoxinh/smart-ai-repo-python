import logging
import time

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QApplication

from components.resize_handle import ResizeHandle
from components.content_widget import ContentWidget
from components.bottom_bar import BottomBar


class SidebarPanel(QWidget):
    """Embedded sidebar panel — child of FloatingButton's window.

    No window flags, no screen detection, no X11.
    Pure content widget that the parent FloatingButton resizes/positions.
    """

    resizeRequested = pyqtSignal(int)   # new sidebar width from drag handle
    closeRequested = pyqtSignal()        # from watchdog or close button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)

        # ── state ─────────────────────────────────────────────────────
        self._sidebar_w = 400            # current sidebar width
        self.is_visible = False
        self.is_resizing = False
        self.has_active_popup = False
        self.is_nav_menu_open = False
        self.is_webview_menu_open = False
        self.popup_windows = []
        self.last_mouse_in_time = time.time()
        self.last_show_time = time.time()

        # ── watchdog timer ────────────────────────────────────────────
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.timeout.connect(self._stability_check)
        self._watchdog_timer.start(500)

        # ── build UI ──────────────────────────────────────────────────
        self.setMouseTracking(True)
        self._init_ui()

        logging.info("[SidebarPanel] Initialized")

    # ── UI ─────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Resize handle on the LEFT (between button and sidebar content)
        self.resize_handle = ResizeHandle(self)
        self.resize_handle.dragResized.connect(self._on_resize_drag)
        layout.addWidget(self.resize_handle)

        # Main content area
        main_widget = QWidget()
        main_widget.setMouseTracking(True)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.content_widget = ContentWidget()
        main_layout.addWidget(self.content_widget)

        self.bottom_bar = BottomBar()
        main_layout.addWidget(self.bottom_bar)

        # ── signal wiring ─────────────────────────────────────────────
        self.content_widget.closeRequested.connect(
            lambda: self.closeRequested.emit()
        )
        self.content_widget.web_view.popupCreated.connect(
            self.handle_popup_created
        )
        self.content_widget.nav_bar.navigationClicked.connect(
            self.handle_navigation
        )
        self.content_widget.nav_bar.menu_state_changed.connect(
            self.on_nav_menu_state_changed
        )
        self.content_widget.context_menu_state_changed.connect(
            self.on_webview_menu_state_changed
        )

        layout.addWidget(main_widget)
        self.setStyleSheet("background-color: #33322F;")

    # ── show / hide (called by FloatingButton) ─────────────────────────

    def show_content(self):
        """Make content visible (parent also resizes window)."""
        self.is_visible = True
        self.last_show_time = time.time()
        self.setVisible(True)
        if self.content_widget and self.content_widget.web_view:
            self.content_widget.web_view.setFocus()

    def hide_content(self):
        """Hide content (parent also shrinks window)."""
        self.is_visible = False
        self.setVisible(False)

    # ── resize handle support ──────────────────────────────────────────

    def _on_resize_drag(self, new_w):
        """Forward width change from ResizeHandle to parent."""
        self._sidebar_w = new_w
        self.resizeRequested.emit(new_w)

    def get_sidebar_width(self):
        return self._sidebar_w

    def set_sidebar_width(self, w):
        self._sidebar_w = w

    # ── watchdog: auto-hide when mouse leaves for 2 s ──────────────────

    def _stability_check(self):
        if not self.is_visible or self.is_resizing:
            return
        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)
        margin = 100
        rect = self.rect().adjusted(-margin, -margin, margin, margin)
        now = time.time()
        if rect.contains(local_pos):
            self.last_mouse_in_time = now
            return
        time_away = now - self.last_mouse_in_time
        if time_away > 2.0 and not (
            self.has_active_popup
            or self.is_nav_menu_open
            or self.is_webview_menu_open
        ):
            self.closeRequested.emit()

    # ── mouse events for auto-hide tracking ────────────────────────────

    def enterEvent(self, event):
        self.last_mouse_in_time = time.time()
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self.last_mouse_in_time = time.time()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        if not self.is_visible or self.is_resizing:
            return
        if (
            self.has_active_popup
            or self.is_nav_menu_open
            or self.is_webview_menu_open
        ):
            return
        if (time.time() - self.last_show_time) < 0.5:
            return
        self.closeRequested.emit()

    # ── popup tracking ─────────────────────────────────────────────────

    def handle_popup_created(self, popup_window):
        self.popup_windows.append(popup_window)
        self.has_active_popup = True
        popup_window.popupClosed.connect(
            lambda: self.handle_popup_closed(popup_window)
        )

    def handle_popup_closed(self, popup=None):
        if popup in self.popup_windows:
            self.popup_windows.remove(popup)
        if not self.popup_windows:
            self.has_active_popup = False

    # ── menu state ─────────────────────────────────────────────────────

    def on_nav_menu_state_changed(self, is_open):
        self.is_nav_menu_open = is_open

    def on_webview_menu_state_changed(self, is_open):
        self.is_webview_menu_open = is_open

    # ── navigation ─────────────────────────────────────────────────────

    def handle_navigation(self, url):
        self.content_widget.web_view.setUrl(QUrl(url))
