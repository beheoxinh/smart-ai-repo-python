"""
sidebar.py — AI Sidebar main window.

Key differences from the original (pre-rework):
  - ALL X11-specific ctypes / wmctrl / _NET_WM_WINDOW_TYPE_DOCK code is removed.
    Under Wayland these hacks were fighting Mutter and causing focus issues.
  - ALL focus-stealing machinery is removed (XSetInputFocus, fake key events,
    focus watchdog timer).  The Python daemon still runs on XWayland via
    QT_QPA_PLATFORM=xcb, so move() / setGeometry() still work.  But instead
    of grabbing focus via X11, we trust the GNOME extension to handle window
    management via Mutter's native APIs.
  - D-Bus signals (stateChanged, widthChanged, popupStateChanged) allow the
    GNOME Shell extension to track sidebar state.
  - show_on_screen(index) lets the extension tell us which monitor to appear on.

Everything else (WebView, nav, resize, gesture detection, menus, popups)
is preserved verbatim.
"""

import logging
import sys
import time

from PyQt6.QtCore import Qt, QTimer, QUrl, QEvent, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication
from PyQt6.QtGui import QShortcut, QKeySequence, QCursor

from components.resize_handle import ResizeHandle
from components.content_widget import ContentWidget
from components.bottom_bar import BottomBar


class Sidebar(QMainWindow):
    """The sidebar main window.  Manages its own geometry (XWayland),
    but defers screen-selection decisions to the D-Bus layer / extension."""

    # ── D-Bus facing signals ──────────────────────────────────────────
    stateChanged = pyqtSignal(bool, arguments=['visible'])
    widthChanged = pyqtSignal(int,   arguments=['width'])
    popupStateChanged = pyqtSignal(bool, arguments=['open'])

    def __init__(self):
        super().__init__()

        # ── State ──────────────────────────────────────────────────────
        self.dialog_open = False
        self.setWindowTitle("sidebar")
        self.is_visible = False
        self.active_screen = None
        self.is_resizing = False
        self.has_active_popup = False
        self.is_nav_menu_open = False
        self.is_webview_menu_open = False
        self.popup_windows = []
        self.last_width = None
        self.is_made_sticky = False
        self.manual_screen_index = -1
        self.last_mouse_screen = None
        self._last_processed_y = 0
        self.gesture_entry_y = None
        self.gesture_min_y = None
        self.gesture_max_y = None
        self.gesture_down_met = False
        self.gesture_up_met = False
        self.last_show_time = 0
        self.last_mouse_in_time = time.time()
        self.gesture_start_time = 0
        self._is_fullscreen_active = False

        # ── Timers ─────────────────────────────────────────────────────
        self.watchdog_timer = QTimer(self)
        self.fullscreen_timer = QTimer(self)

        self.watchdog_timer.timeout.connect(self._stability_check)
        self.fullscreen_timer.timeout.connect(self._update_fullscreen_state)

        # ── Build ──────────────────────────────────────────────────────
        self.init_ui()
        self.watchdog_timer.start(500)
        self.fullscreen_timer.start(3000)
        self.setup_shortcut()

        # Global event filter for click re-focus
        self.installEventFilter(self)

    # ── Event filter ───────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if self.is_visible and event.type() == QEvent.Type.MouseButtonPress:
            self.raise_()
            self.activateWindow()
        return super().eventFilter(obj, event)

    # ── Fullscreen detection (X11-only; silently no-ops on Wayland) ───

    def _update_fullscreen_state(self):
        if sys.platform != "linux" or QApplication.platformName() == "wayland":
            return
        from PyQt6.QtCore import QProcess
        process = QProcess(self)

        def on_finished():
            try:
                out = process.readAllStandardOutput().data().decode().strip()
                self._is_fullscreen_active = '_NET_WM_STATE_FULLSCREEN' in out
            except Exception:
                pass
            process.deleteLater()

        process.finished.connect(on_finished)
        cmd = (
            "id=$(xprop -root 32x '\t$0' _NET_ACTIVE_WINDOW | cut -f2); "
            '[ -n "$id" ] && [ "$id" != "0x0" ] && xprop -id "$id" _NET_WM_STATE'
        )
        process.start("bash", ["-c", cmd])

    # ── Stability watchdog (auto-hide when mouse leaves for 2+ s) ─────

    def _stability_check(self):
        if not self.is_visible or self.is_resizing:
            return
        pos = QCursor.pos()
        local = self.mapFromGlobal(pos)
        margin = 100
        rect = self.rect().adjusted(-margin, -margin, margin, margin)
        now = time.time()
        if rect.contains(local):
            self.last_mouse_in_time = now
            return
        away = now - self.last_mouse_in_time
        if away > 2.0 and not (
            self.has_active_popup
            or self.is_nav_menu_open
            or self.is_webview_menu_open
        ):
            self.hide_sidebar(reason="watchdog")

    # ── Geometry helpers ──────────────────────────────────────────────

    def calculate_width(self, screen_width):
        return int(screen_width * 0.5)

    def get_current_screen_width(self):
        if self.active_screen:
            return self.active_screen.geometry().width()
        return QApplication.primaryScreen().geometry().width()

    def get_target_screen(self):
        screens = QApplication.screens()
        return (
            max(screens, key=lambda s: s.geometry().x() + s.geometry().width())
            if screens
            else QApplication.primaryScreen()
        )

    # ── Hot-key ───────────────────────────────────────────────────────

    def setup_shortcut(self):
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        shortcut.activated.connect(self.toggle_sidebar)

    # ── UI construction ───────────────────────────────────────────────

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        container = QWidget()
        container.setMouseTracking(True)
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.resize_handle = ResizeHandle(self)
        container_layout.addWidget(self.resize_handle)

        main_widget = QWidget()
        self.main_ui_container = main_widget
        main_widget.setMouseTracking(True)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.content_widget = ContentWidget()
        main_layout.addWidget(self.content_widget)

        self.bottom_bar = BottomBar()
        main_layout.addWidget(self.bottom_bar)

        # ── Signal wiring ──
        self.content_widget.closeRequested.connect(
            lambda: self.hide_sidebar(reason="close_button")
        )
        wv = self.content_widget.web_view
        wv.popupCreated.connect(self._on_popup_created)
        wv.popupClosed.connect(self._on_popup_closed)
        wv.focusRequested.connect(lambda: (self.raise_(), self.activateWindow()))
        nav = self.content_widget.nav_bar
        nav.navigationClicked.connect(self._on_navigate)
        nav.menu_state_changed.connect(self._on_nav_menu_state)
        self.content_widget.context_menu_state_changed.connect(
            self._on_webview_menu_state
        )

        container_layout.addWidget(main_widget)
        self.setCentralWidget(container)

        self.setMinimumWidth(0)
        self.main_ui_container.setMinimumWidth(0)

        primary = QApplication.primaryScreen()
        if primary:
            self.last_width = self.calculate_width(primary.geometry().width())

        self.active_screen = self.get_target_screen()
        self.setStyleSheet("QMainWindow { background-color: #33322F; }")
        self.hide_sidebar(initial=True, reason="initial")

    # ── Show / Hide ───────────────────────────────────────────────────

    def show_sidebar(self):
        if self.is_visible:
            return
        self.is_visible = True
        self.last_show_time = time.time()
        self.update_position()
        if self.main_ui_container:
            self.main_ui_container.show()
        if self.resize_handle:
            self.resize_handle.show()
        self.raise_()
        self.activateWindow()
        self.stateChanged.emit(True)
        logging.info("[Sidebar] Shown")

    def hide_sidebar(self, initial=False, reason="manual"):
        if not initial and not self.is_visible:
            return
        if not initial and (time.time() - self.last_show_time) < 0.3:
            return

        self.is_visible = False
        if self.main_ui_container:
            self.main_ui_container.hide()
        if self.resize_handle:
            self.resize_handle.hide()
        self.update_position()

        if initial:
            self.show()  # map the window once so we can toggle visibility

        self.stateChanged.emit(False)
        logging.info(f"[Sidebar] Hidden (reason={reason})")

    def toggle_sidebar(self):
        if self.is_visible:
            self.hide_sidebar(reason="toggle")
        else:
            self.show_sidebar()

    # ── Public: called by D-Bus service ───────────────────────────────

    def show_on_screen(self, screen_index):
        """Show the sidebar on a specific monitor index.
        screen_index = -1 means auto (rightmost)."""
        screens = QApplication.screens()
        if 0 <= screen_index < len(screens):
            self.manual_screen_index = screen_index
            self.active_screen = screens[screen_index]
            logging.info(
                f"[Sidebar] D-Bus show on screen {screen_index}: "
                f"{self.active_screen.name()}"
            )
        else:
            self.manual_screen_index = -1
            self.active_screen = self.get_target_screen()
        self.show_sidebar()

    # ── Position management ───────────────────────────────────────────

    def update_position(self, _=None):
        screen = self.active_screen or self.get_target_screen()
        if not screen:
            return
        geom = screen.geometry()
        target_w = self.last_width if self.is_visible else 1
        new_x = geom.x() + geom.width() - target_w
        new_y = geom.y()
        new_h = geom.height()
        self.setGeometry(new_x, new_y, target_w, new_h)
        logging.info(
            f"[Pos] {screen.name()}: geom {geom.x()},{geom.y()} "
            f"{geom.width()}x{geom.height()} -> "
            f"sidebar X={new_x} W={target_w}"
        )

    def update_width_and_x_position(self):
        screen = self.get_target_screen()
        if not screen:
            return
        geom = screen.geometry()
        new_x = geom.x() + geom.width() - self.width()
        self.move(new_x, self.y())

    def set_manual_screen(self, index):
        """Override from tray menu (fallback when extension is absent)."""
        screens = QApplication.screens()
        if 0 <= index < len(screens):
            self.manual_screen_index = index
            self.active_screen = screens[index]
            logging.info(
                f"[Screen] Manually set to {index}: {self.active_screen.name()}"
            )
            self.update_position()
        else:
            self.manual_screen_index = -1
            self.active_screen = self.get_target_screen()
            self.update_position()

    # ── Resize callbacks ──────────────────────────────────────────────

    def resizing_started(self):
        self.is_resizing = True

    def resizing_finished(self):
        self.is_resizing = False
        self.last_width = self.width()
        self.widthChanged.emit(self.last_width)

    # ── Mouse enter / leave / gesture ─────────────────────────────────

    def enterEvent(self, event):
        self.last_mouse_in_time = time.time()

        # Auto-jump to the screen the mouse is on (only when hidden)
        if not self.is_visible:
            cursor_pos = QCursor.pos()
            screen = QApplication.screenAt(cursor_pos)
            if screen and screen != self.active_screen:
                self.active_screen = screen
                self.update_position()
                logging.info(f"[Screen] Jumped to {screen.name()}")

            curr_y = event.position().y()
            self.gesture_entry_y = curr_y
            self.gesture_min_y = curr_y
            self.gesture_max_y = curr_y
            self.gesture_down_met = False
            self.gesture_up_met = False
            self.gesture_start_time = time.time()
        else:
            self.raise_()
            self.activateWindow()

        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self.last_mouse_in_time = time.time()
        if not self.is_visible and self.gesture_entry_y is not None:
            curr_y = event.position().y()
            self.gesture_min_y = min(self.gesture_min_y, curr_y)
            self.gesture_max_y = max(self.gesture_max_y, curr_y)
            if not self.gesture_down_met and (curr_y - self.gesture_min_y) > 200:
                self.gesture_down_met = True
            if not self.gesture_up_met and (self.gesture_max_y - curr_y) > 200:
                self.gesture_up_met = True
            if (time.time() - self.gesture_start_time) > 0.7:
                self.gesture_start_time = time.time()
                self.gesture_min_y = curr_y
                self.gesture_max_y = curr_y
                self.gesture_down_met = False
                self.gesture_up_met = False
            if self.gesture_down_met and self.gesture_up_met:
                self.gesture_entry_y = None
                if not self.has_active_popup and not self._is_fullscreen_active:
                    self.show_sidebar()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        if not self.is_visible or self.is_resizing:
            return
        if self.has_active_popup or self.is_nav_menu_open or self.is_webview_menu_open:
            return
        if (time.time() - self.last_show_time) < 0.5:
            return
        self.hide_sidebar(reason="leaveEvent")

    # ── Popups ────────────────────────────────────────────────────────

    def _on_popup_created(self, popup_win):
        self.popup_windows.append(popup_win)
        self.has_active_popup = True
        popup_win.raise_()
        popup_win.activateWindow()
        self.popupStateChanged.emit(True)

        # Wire close signal (disconnect old connections to avoid leaks)
        try:
            popup_win.popupClosed.disconnect()
        except TypeError:
            pass
        popup_win.popupClosed.connect(
            lambda w=popup_win: self._on_popup_closed(w)
        )

    def _on_popup_closed(self, popup=None):
        if popup in self.popup_windows:
            self.popup_windows.remove(popup)
        if not self.popup_windows:
            self.has_active_popup = False
            self.popupStateChanged.emit(False)
        self.raise_()
        self.activateWindow()

    # ── Navigation / menu state ───────────────────────────────────────

    def _on_navigate(self, url):
        self.content_widget.web_view.setUrl(QUrl(url))

    def _on_nav_menu_state(self, is_open):
        self.is_nav_menu_open = is_open

    def _on_webview_menu_state(self, is_open):
        self.is_webview_menu_open = is_open
