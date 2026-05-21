# File: components/sidebar.py (Cross-platform version)
import ctypes
import logging
import sys
import time

try:
    import win32gui
    import win32api
except ImportError:
    win32gui = None
    win32api = None

from PyQt6.QtCore import Qt, QTimer, QUrl, QEvent
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication
from PyQt6.QtGui import QShortcut, QKeySequence, QCursor

from components.resize_handle import ResizeHandle
from components.content_widget import ContentWidget
from components.bottom_bar import BottomBar


class Sidebar(QMainWindow):
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
        self.is_made_sticky = False
        self.manual_screen_index = -1
        self.last_mouse_screen = None
        self._last_processed_y = 0
        self._x11_display = None
        self._x11_lib = None
        self._last_focus_grab_time = 0
        self._last_sticky_id = None
        self.watchdog_timer = None
        self.resize_handle = None
        self.main_ui_container = None
        self.content_widget = None
        self.bottom_bar = None

        # Gesture State
        self.gesture_entry_y = None
        self.gesture_min_y = None
        self.gesture_max_y = None
        self.gesture_down_met = False
        self.gesture_up_met = False
        self.last_show_time = 0
        self.last_mouse_in_time = time.time()
        self.gesture_start_time = 0
        self._is_fullscreen_active = False

        self.watchdog_timer = QTimer(self)
        self.fullscreen_timer = QTimer(self)
        self.focus_watchdog_timer = QTimer(self)
        self.focus_watchdog_timer.timeout.connect(self._focus_watchdog_check)

        self.init_ui()
        self.setup_stability_watchdog()
        self.setup_fullscreen_watchdog()
        self.setup_shortcut()

        # Cài đặt bộ lọc sự kiện để bắt click chuột bên trong sidebar
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Bắt mọi cú click chuột bên trong Sidebar để tự động re-hook focus."""
        if self.is_visible and event.type() == QEvent.Type.MouseButtonPress:
            # Nếu click vào bất kỳ đâu trong sidebar, thực hiện re-hook focus ngay
            self._grab_focus_linux(forced=True)
        return super().eventFilter(obj, event)

    def setup_stability_watchdog(self):
        self.watchdog_timer.timeout.connect(self._stability_check)
        self.watchdog_timer.start(500)  # Giảm tần suất xuống 500ms để tránh lag

    def setup_fullscreen_watchdog(self):
        self.fullscreen_timer.timeout.connect(self._update_fullscreen_state)
        self.fullscreen_timer.start(3000)

    def _update_fullscreen_state(self):
        if sys.platform != "linux" or QApplication.platformName() == "wayland": return
        from PyQt6.QtCore import QProcess
        process = QProcess(self)

        def on_finished():
            try:
                output = process.readAllStandardOutput().data().decode().strip()
                self._is_fullscreen_active = '_NET_WM_STATE_FULLSCREEN' in output
            except Exception:
                pass
            process.deleteLater()

        process.finished.connect(on_finished)
        cmd = "id=$(xprop -root 32x '\t$0' _NET_ACTIVE_WINDOW | cut -f2); [ -n \"$id\" ] && [ \"$id\" != \"0x0\" ] && xprop -id \"$id\" _NET_WM_STATE"
        process.start("bash", ["-c", cmd])

    def _stability_check(self):
        if not self.is_visible or self.is_resizing: return
        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)
        margin = 100
        rect = self.rect().adjusted(-margin, -margin, margin, margin)
        now = time.time()
        if rect.contains(local_pos):
            self.last_mouse_in_time = now
            return
        time_away = now - self.last_mouse_in_time
        if time_away > 2.0 and not (self.has_active_popup or self.is_nav_menu_open or self.is_webview_menu_open):
            self.hide_sidebar(reason="watchdog")

    def calculate_width(self, screen_width):
        return int(screen_width * 0.5)

    def setup_shortcut(self):
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        shortcut.activated.connect(self.toggle_sidebar)

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.X11BypassWindowManagerHint |
            Qt.WindowType.WindowStaysOnTopHint
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

        self.content_widget.closeRequested.connect(lambda: self.hide_sidebar(reason="close_button"))
        self.content_widget.web_view.popupCreated.connect(self.handle_popup_created)
        self.content_widget.web_view.focusRequested.connect(lambda: self._grab_focus_linux(forced=True))
        self.content_widget.nav_bar.navigationClicked.connect(self.handle_navigation)
        self.content_widget.nav_bar.menu_state_changed.connect(self.on_nav_menu_state_changed)
        self.content_widget.context_menu_state_changed.connect(self.on_webview_menu_state_changed)

        container_layout.addWidget(main_widget)
        self.setCentralWidget(container)

        self.setMinimumWidth(0)
        self.main_ui_container.setMinimumWidth(0)

        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            self.last_width = self.calculate_width(primary_screen.geometry().width())

        self.active_screen = self.get_target_screen()
        self.setStyleSheet("QMainWindow { background-color: #33322F; }")
        self.hide_sidebar(initial=True, reason="initial")

    def _focus_watchdog_check(self):
        if not self.is_visible or self.is_resizing or self.has_active_popup or self.is_nav_menu_open or self.is_webview_menu_open:
            return

        # Check if the sidebar or its webview is actively focused
        web_view = self.content_widget.web_view if self.content_widget else None
        has_focus = False
        if web_view:
            has_focus = web_view.hasFocus() or self.isActiveWindow()
            proxy = web_view.focusProxy()
            if proxy and proxy.hasFocus():
                has_focus = True

        if not has_focus:
            logging.info("[FocusWatchdog] Focus lost, grabbing back...")
            self._grab_focus_linux(forced=True)

    def _grab_focus_linux(self, forced=False):
        if sys.platform != "linux" or QApplication.platformName() != 'xcb': return

        now = time.time()
        # Cooldown: Tránh spam X11 quá mức (tối thiểu 50ms giữa các lần)
        if not forced and (now - self._last_focus_grab_time) < 0.05: return
        self._last_focus_grab_time = now

        win_id = int(self.winId())
        if win_id == 0: return

        try:
            if self._x11_lib is None:
                self._x11_lib = ctypes.cdll.LoadLibrary("libX11.so.6")
                self._x11_lib.XOpenDisplay.restype = ctypes.c_void_p
                self._x11_lib.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
                self._x11_lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
                self._x11_lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]

            # Use a fresh transient connection to avoid X11 socket leaks or connection stales
            display = self._x11_lib.XOpenDisplay(None)
            if not display: return

            self.raise_()
            self.activateWindow()

            # Re-hook X11 Focus to the TOP-LEVEL window (Sidebar itself)
            # NEVER call winId() on child widgets like WebView to prevent Qt6 from creating
            # conflicting native child windows, which causes "QWidgetWindow must be a top level window" errors.
            self._x11_lib.XSetInputFocus(display, win_id, 1, 0)

            # Direct Qt internal focus to the web_view safely
            if self.content_widget and self.content_widget.web_view:
                self.content_widget.web_view.setFocus()

            self._x11_lib.XSync(display, 0)
            self._x11_lib.XCloseDisplay(display)
            logging.info(f"[FocusHook] Successfully grabbed X11 input focus for top-level Sidebar (win_id: {win_id})")
        except Exception as e:
            logging.error(f"X11 focus grab failed: {e}")

    def show_sidebar(self):
        if self.is_visible: return
        self.is_visible = True
        self.last_show_time = time.time()
        if hasattr(self, 'main_ui_container'):
            self.main_ui_container.show()
            self.main_ui_container.setMinimumWidth(200)
        if hasattr(self, 'resize_handle'): self.resize_handle.show()

        self.update_position()
        self.setWindowOpacity(1.0)
        self.raise_()
        self.activateWindow()

        # Start Focus Watchdog Loop (100ms) when visible
        self.focus_watchdog_timer.start(100)

        # Burst Focus: Lấy focus cực nhanh và liên tục khi vừa hiện ra
        self._grab_focus_linux(forced=True)
        QTimer.singleShot(10, lambda: self._grab_focus_linux(forced=True))
        QTimer.singleShot(100, lambda: self._grab_focus_linux(forced=True))
        QTimer.singleShot(250, lambda: self._grab_focus_linux(forced=True))
        QTimer.singleShot(500, lambda: self._grab_focus_linux(forced=True))

    def hide_sidebar(self, initial=False, reason="manual"):
        if not initial and (self.is_resizing or not self.is_visible): return
        if not initial and (time.time() - self.last_show_time) < 0.5: return

        # Stop Focus Watchdog Loop to avoid stealing focus when hidden
        self.focus_watchdog_timer.stop()

        self.setWindowOpacity(0.01)

        def finalize_hide():
            self.is_visible = False
            if hasattr(self, 'main_ui_container'):
                self.main_ui_container.hide()
                self.main_ui_container.setMinimumWidth(0)
            if hasattr(self, 'resize_handle'): self.resize_handle.hide()
            self.update_position()

        if not initial:
            QTimer.singleShot(50, finalize_hide)
        else:
            finalize_hide();
            self.show()

    def handle_popup_created(self, popup_window):
        self.popup_windows.append(popup_window)
        self.has_active_popup = True
        popup_window.raise_();
        popup_window.activateWindow()
        popup_window.popupClosed.connect(lambda: self.handle_popup_closed(popup_window))

    def handle_popup_closed(self, popup=None):
        if popup in self.popup_windows: self.popup_windows.remove(popup)
        if not self.popup_windows: self.has_active_popup = False
        self.raise_();
        self.activateWindow()

    def get_target_screen(self):
        screens = QApplication.screens()
        return max(screens, key=lambda s: s.geometry().x() + s.geometry().width()) if screens else QApplication.primaryScreen()

    def enterEvent(self, event):
        self.last_mouse_in_time = time.time()
        if not self.is_visible:
            curr_y = event.position().y()
            self.gesture_entry_y = curr_y;
            self.gesture_min_y = curr_y;
            self.gesture_max_y = curr_y
            self.gesture_down_met = False;
            self.gesture_up_met = False
            self.gesture_start_time = time.time()
        else:
            self._grab_focus_linux()
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self.last_mouse_in_time = time.time()
        if not self.is_visible and self.gesture_entry_y is not None:
            curr_y = event.position().y()
            self.gesture_min_y = min(self.gesture_min_y, curr_y)
            self.gesture_max_y = max(self.gesture_max_y, curr_y)
            if not self.gesture_down_met and (curr_y - self.gesture_min_y) > 200: self.gesture_down_met = True
            if not self.gesture_up_met and (self.gesture_max_y - curr_y) > 200: self.gesture_up_met = True
            if (time.time() - self.gesture_start_time) > 0.7:
                self.gesture_start_time = time.time();
                self.gesture_min_y = curr_y;
                self.gesture_max_y = curr_y
                self.gesture_down_met = False;
                self.gesture_up_met = False
            if self.gesture_down_met and self.gesture_up_met:
                self.gesture_entry_y = None
                if not self.has_active_popup and not self._is_fullscreen_active: self.show_sidebar()
        super().mouseMoveEvent(event)

    def toggle_sidebar(self):
        if self.is_visible:
            self.hide_sidebar(reason="toggle")
        else:
            self.show_sidebar()

    def update_position(self, _=None):
        screen = self.get_target_screen()
        if not screen: return
        geom = screen.geometry()
        target_w = self.last_width or int(geom.width() * 0.5) if self.is_visible else 5
        self.setGeometry(geom.x() + geom.width() - target_w, geom.y(), target_w, geom.height())

    def on_nav_menu_state_changed(self, is_open):
        self.is_nav_menu_open = is_open

    def on_webview_menu_state_changed(self, is_open):
        self.is_webview_menu_open = is_open

    def leaveEvent(self, event):
        super().leaveEvent(event)
        # Bỏ qua nếu người dùng đang nhấn giữ chuột (ví dụ khi resize)
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        if not self.is_visible or self.is_resizing:
            return
        if self.has_active_popup or self.is_nav_menu_open or self.is_webview_menu_open:
            return
        # Đợi 1 chút để tránh flickers nếu vừa hiện lên
        if (time.time() - self.last_show_time) < 0.5:
            return
        self.hide_sidebar(reason="leaveEvent")

    def handle_navigation(self, url):
        self.content_widget.web_view.setUrl(QUrl(url))
