import logging
import time

from PyQt6.QtCore import Qt, QTimer, QUrl, QEvent
from PyQt6.QtGui import QShortcut, QKeySequence, QCursor
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication

from components.bottom_bar import BottomBar
from components.content_widget import ContentWidget
from components.resize_handle import ResizeHandle


class Sidebar(QMainWindow):
    """Floating sidebar panel.

    Designed for Wayland-native operation:
    - No X11 / wmctrl / ctypes hacks
    - Screen selection driven by the FloatingButton
    - Positioning via setGeometry (best-effort on Wayland)
    - Auto-hide when mouse leaves for >2 s
    """

    def __init__(self):
        super().__init__()

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
        self.manual_screen_index = -1
        self.last_mouse_screen = None
        self._last_processed_y = 0
        self.watchdog_timer = None
        self.resize_handle = None
        self.main_ui_container = None
        self.content_widget = None
        self.bottom_bar = None

        # Gesture state
        self.gesture_entry_y = None
        self.gesture_min_y = None
        self.gesture_max_y = None
        self.gesture_down_met = False
        self.gesture_up_met = False
        self.last_show_time = 0
        self.last_mouse_in_time = time.time()
        self.gesture_start_time = 0

        self.watchdog_timer = QTimer(self)

        self.init_ui()
        self.setup_stability_watchdog()
        self.setup_shortcut()
        self.installEventFilter(self)

    # ── event filter ───────────────────────────────────────
    def eventFilter(self, obj, event):
        if self.is_visible and event.type() == QEvent.Type.MouseButtonPress:
            self.raise_()
            self.activateWindow()
            if self.content_widget and self.content_widget.web_view:
                self.content_widget.web_view.setFocus()
        return super().eventFilter(obj, event)

    # ── watchdogs ──────────────────────────────────────────
    def setup_stability_watchdog(self):
        self.watchdog_timer.timeout.connect(self._stability_check)
        self.watchdog_timer.start(500)

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
            self.hide_sidebar(reason="watchdog")

    # ── convenience ────────────────────────────────────────
    def calculate_width(self, screen_width):
        return int(screen_width * 0.5)

    def setup_shortcut(self):
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        shortcut.activated.connect(self.toggle_sidebar)

    # ── UI ──────────────────────────────────────────────────
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

        self.content_widget.closeRequested.connect(
            lambda: self.hide_sidebar(reason="close_button")
        )
        self.content_widget.web_view.popupCreated.connect(self.handle_popup_created)
        self.content_widget.nav_bar.navigationClicked.connect(self.handle_navigation)
        self.content_widget.nav_bar.menu_state_changed.connect(
            self.on_nav_menu_state_changed
        )
        self.content_widget.context_menu_state_changed.connect(
            self.on_webview_menu_state_changed
        )

        container_layout.addWidget(main_widget)
        self.setCentralWidget(container)

        self.setMinimumWidth(0)
        self.main_ui_container.setMinimumWidth(0)

        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            self.last_width = self.calculate_width(
                primary_screen.geometry().width()
            )

        self.active_screen = self.get_target_screen()
        self.setStyleSheet("QMainWindow { background-color: #33322F; }")

        self.hide_sidebar(initial=True, reason="initial")

    # ── show / hide ─────────────────────────────────────────
    def show_sidebar(self):
        if self.is_visible:
            return
        self.is_visible = True
        self.last_show_time = time.time()

        # Always re-sync screen from the floating button's last known index
        if self.manual_screen_index >= 0:
            screens = QApplication.screens()
            if 0 <= self.manual_screen_index < len(screens):
                self.active_screen = screens[self.manual_screen_index]
                logging.info(
                    f"[Sidebar] Resynced to manual screen {self.manual_screen_index}: "
                    f"{self.active_screen.name()}"
                )

        self.update_position()

        if hasattr(self, "main_ui_container"):
            self.main_ui_container.show()
        if hasattr(self, "resize_handle"):
            self.resize_handle.show()

        self.raise_()
        self.activateWindow()

        # On Wayland, activateWindow may cause compositor to move the
        # window to the active/pointer screen.  Re-assert screen after
        # the compositor has processed the focus request.
        QTimer.singleShot(50, self._reassert_screen)

        if self.content_widget and self.content_widget.web_view:
            self.content_widget.web_view.setFocus()

    def hide_sidebar(self, initial=False, reason="manual"):
        if not initial and not self.is_visible:
            return
        if not initial and (time.time() - self.last_show_time) < 0.3:
            return

        self.is_visible = False

        if hasattr(self, "main_ui_container"):
            self.main_ui_container.hide()
        if hasattr(self, "resize_handle"):
            self.resize_handle.hide()

        self.update_position()

        if initial:
            self.show()  # first map

    def toggle_sidebar(self):
        if self.is_visible:
            self.hide_sidebar(reason="toggle")
        else:
            self.show_sidebar()

    # ── popups ──────────────────────────────────────────────
    def handle_popup_created(self, popup_window):
        self.popup_windows.append(popup_window)
        self.has_active_popup = True
        popup_window.raise_()
        popup_window.activateWindow()
        popup_window.popupClosed.connect(
            lambda: self.handle_popup_closed(popup_window)
        )

    def handle_popup_closed(self, popup=None):
        if popup in self.popup_windows:
            self.popup_windows.remove(popup)
        if not self.popup_windows:
            self.has_active_popup = False
        self.raise_()
        self.activateWindow()

    # ── screen target ───────────────────────────────────────
    def get_target_screen(self):
        screens = QApplication.screens()
        return (
            max(screens, key=lambda s: s.geometry().x() + s.geometry().width())
            if screens
            else QApplication.primaryScreen()
        )

    def set_manual_screen(self, index):
        screens = QApplication.screens()
        if 0 <= index < len(screens):
            self.manual_screen_index = index
            self.active_screen = screens[index]
            logging.info(
                f"[Screen] Manually set to screen {index}: {self.active_screen.name()}"
            )
            self.update_position()

    # ── mouse events ───────────────────────────────────────
    def enterEvent(self, event):
        self.last_mouse_in_time = time.time()

        if not self.is_visible:
            # Only auto-detect when no manual screen is set
            if self.manual_screen_index < 0:
                cursor_pos = QCursor.pos()
                screen_with_mouse = QApplication.screenAt(cursor_pos)
                if screen_with_mouse and screen_with_mouse != self.active_screen:
                    self.active_screen = screen_with_mouse
                    self.update_position()
                    logging.info(
                        f"[Screen] Jumped to screen: {screen_with_mouse.name()}"
                    )

            curr_y = event.position().y()
            self.gesture_entry_y = curr_y
            self.gesture_min_y = curr_y
            self.gesture_max_y = curr_y
            self.gesture_down_met = False
            self.gesture_up_met = False
            self.gesture_start_time = time.time()

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
                if not self.has_active_popup:
                    self.show_sidebar()

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

        self.hide_sidebar(reason="leaveEvent")

    # ── positioning ─────────────────────────────────────────
    def update_position(self, _=None):
        """Place sidebar at right edge of active screen.

        On Wayland, setGeometry is a hint — the compositor may
        override position, but screen association (via setScreen)
        is honoured.
        """
        screen = self.active_screen or self.get_target_screen()
        if not screen:
            return

        geom = screen.geometry()
        target_w = self.last_width if self.is_visible else 1

        new_x = geom.x() + geom.width() - target_w
        new_y = geom.y()

        # Request placement via setGeometry + setScreen
        self.setGeometry(new_x, new_y, target_w, geom.height())
        wh = self.windowHandle()
        if wh:
            wh.setScreen(screen)

        logging.info(
            f"[Pos] Screen '{screen.name()}': {geom.x()},{geom.y()} "
            f"{geom.width()}x{geom.height()} -> X:{new_x} W:{target_w}"
        )

    def _reassert_screen(self):
        """Re-apply active_screen after compositor may have moved window."""
        if not self.active_screen:
            return
        wh = self.windowHandle()
        if wh:
            wh.setScreen(self.active_screen)
            logging.info(
                f"[Sidebar] Re-asserted screen: {self.active_screen.name()}"
            )

    # ── resize ──────────────────────────────────────────────
    def resizing_started(self):
        self.is_resizing = True

    def resizing_finished(self):
        self.is_resizing = False
        self.last_width = self.width()

    def get_current_screen_width(self):
        if self.active_screen:
            return self.active_screen.geometry().width()
        return QApplication.primaryScreen().geometry().width()

    def update_width_and_x_position(self):
        screen = self.get_target_screen()
        if not screen:
            return
        geom = screen.geometry()
        new_x = geom.x() + geom.width() - self.width()
        self.move(new_x, self.y())

    # ── menu / nav state ────────────────────────────────────
    def on_nav_menu_state_changed(self, is_open):
        self.is_nav_menu_open = is_open

    def on_webview_menu_state_changed(self, is_open):
        self.is_webview_menu_open = is_open

    # ── navigation ──────────────────────────────────────────
    def handle_navigation(self, url):
        self.content_widget.web_view.setUrl(QUrl(url))
