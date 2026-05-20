# File: components/sidebar.py (Cross-platform version)
import ctypes
import logging
import shutil
import subprocess
import sys
import time

try:
    import win32gui
    import win32api
except ImportError:
    win32gui = None
    win32api = None

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication
from PyQt6.QtGui import QShortcut, QKeySequence, QCursor

from components.resize_handle import ResizeHandle
from components.content_widget import ContentWidget
from components.bottom_bar import BottomBar
from utils import alert_popup


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
        self.is_made_sticky = False  # Flag for workspace stickiness
        self.manual_screen_index = -1  # -1 means auto (rightmost)
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

        # Gesture Trigger State
        self.gesture_entry_y = None
        self.gesture_min_y = None
        self.gesture_max_y = None
        self.gesture_down_met = False
        self.gesture_up_met = False
        self._last_log_y = 0
        self.last_show_time = 0
        self.last_mouse_in_time = time.time()
        self.gesture_start_time = 0
        self._last_focus_grab_time = 0
        self._x11_display = None
        self._is_fullscreen_active = False

        self.watchdog_timer = QTimer(self)
        self.fullscreen_timer = QTimer(self)

        self.init_ui()
        self.setup_stability_watchdog()
        self.setup_fullscreen_watchdog()
        self.setup_shortcut()

    def setup_stability_watchdog(self):
        self.watchdog_timer.timeout.connect(self._stability_check)
        self.watchdog_timer.start(150)  # High-frequency watchdog: 150ms (0.15s)

    def setup_fullscreen_watchdog(self):
        self.fullscreen_timer.timeout.connect(self._update_fullscreen_state)
        self.fullscreen_timer.start(2000)  # Check every 2s

    def _update_fullscreen_state(self):
        """Update fullscreen state asynchronously to avoid blocking main thread."""
        if sys.platform == "win32":
            # Windows implementation is fast (win32gui calls)
            self._is_fullscreen_active = self.is_foreground_fullscreen(self.active_screen)
            return

        if sys.platform != "linux" or QApplication.platformName() == "wayland":
            return

        from PyQt6.QtCore import QProcess

        # We chain two xprop calls. First to get active window, then its state.
        # To keep it simple and truly non-blocking, we use a single QProcess with a shell command.
        process = QProcess(self)

        def on_finished():
            try:
                output = process.readAllStandardOutput().data().decode().strip()
                self._is_fullscreen_active = '_NET_WM_STATE_FULLSCREEN' in output
            except Exception:
                pass
            process.deleteLater()

        process.finished.connect(on_finished)
        # Get active window ID and then its state in one go
        cmd = "id=$(xprop -root 32x '\t$0' _NET_ACTIVE_WINDOW | cut -f2); [ -n \"$id\" ] && [ \"$id\" != \"0x0\" ] && xprop -id \"$id\" _NET_WM_STATE"
        process.start("bash", ["-c", cmd])

    def _stability_check(self):
        """Cleanup stuck states if sidebar is visible but mouse is away.
        Focus Watchdog part runs every 150ms for aggressive focus management.
        """
        if not self.is_visible:
            return

        # Don't hide if user is explicitly resizing
        if self.is_resizing:
            return

        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)

        # Margin to allow mouse to be slightly outside without hiding
        margin = 100
        rect = self.rect().adjusted(-margin, -margin, margin, margin)
        is_mouse_inside = rect.contains(local_pos)

        now = time.time()
        if is_mouse_inside:
            self.last_mouse_in_time = now
            # Focus Watchdog: if mouse is inside and visible but window doesn't have focus, grab it
            # Aggressively check every 150ms
            if not self.isActiveWindow():
                self._grab_focus_linux()
            return

        time_away = now - self.last_mouse_in_time

        # Force reset if away for > 20s (even if menus/popups are open)
        if time_away > 20.0:
            logging.info(f"Watchdog: Force reset after {time_away:.1f}s away")
            self.is_nav_menu_open = False
            self.is_webview_menu_open = False
            self.has_active_popup = False
            self.hide_sidebar(reason="watchdog_force")
            return

        # Normal hide if away for > 2.0s and no menus/popups are open
        if time_away > 2.0 and not (self.has_active_popup or self.is_nav_menu_open or self.is_webview_menu_open):
            logging.info(f"Watchdog: Hiding sidebar after {time_away:.1f}s away")
            self.hide_sidebar(reason="watchdog")

    def calculate_width(self, screen_width):
        return int(screen_width * 0.5)

    def setup_shortcut(self):
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        shortcut.activated.connect(self.toggle_sidebar)

    def init_ui(self):
        try:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.Tool |
                Qt.WindowType.X11BypassWindowManagerHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.NoDropShadowWindowHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setMouseTracking(True)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

            container = QWidget()
            container.setMouseTracking(True)  # QUAN TRỌNG: Phải bật ở đây thì QMainWindow mới nhận được move event
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)

            self.resize_handle = ResizeHandle(self)
            self.resize_handle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            container_layout.addWidget(self.resize_handle)

            main_widget = QWidget()
            main_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.main_ui_container = main_widget  # Lưu lại để ẩn/hiện
            main_widget.setMouseTracking(True)
            main_layout = QVBoxLayout(main_widget)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            self.content_widget = ContentWidget()
            main_layout.addWidget(self.content_widget)

            self.bottom_bar = BottomBar()
            self.bottom_bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            main_layout.addWidget(self.bottom_bar)

            self.content_widget.closeRequested.connect(lambda: self.hide_sidebar(reason="close_button"))
            self.content_widget.web_view.popupCreated.connect(self.handle_popup_created)
            self.content_widget.web_view.focusRequested.connect(lambda: self._grab_focus_linux(forced=True))
            self.content_widget.web_view.webviewRedirectCompleted.connect(self.handle_webview_redirect_completed)
            self.content_widget.nav_bar.navigationClicked.connect(self.handle_navigation)
            self.content_widget.nav_bar.menu_state_changed.connect(self.on_nav_menu_state_changed)
            self.content_widget.context_menu_state_changed.connect(self.on_webview_menu_state_changed)

            container_layout.addWidget(main_widget)
            self.setCentralWidget(container)

            # Diagnostics
            logging.info(f"UI Init: Sidebar WinID={hex(int(self.winId()))}")
            if self.content_widget is not None and self.content_widget.web_view is not None:
                logging.info(f"UI Init: WebView WinID={hex(int(self.content_widget.web_view.winId()))}")

            # Ép minimum width về 0 để có thể thu nhỏ cửa sổ về dải cảm ứng (sensor)
            # Nhưng CHỈ ép khi ở chế độ ẩn, khi hiện thì trả lại giá trị mặc định để tránh hỏng layout
            self.setMinimumWidth(0)
            self.main_ui_container.setMinimumWidth(0)
            if hasattr(self, 'resize_handle'):
                self.resize_handle.setMinimumWidth(0)

            primary_screen = QApplication.primaryScreen()
            if primary_screen:
                self.last_width = self.calculate_width(primary_screen.geometry().width())

            self.active_screen = self.get_target_screen()

            # Kết nối các tín hiệu khi thay đổi cấu hình màn hình
            app_instance = QApplication.instance()
            if app_instance:
                app_instance.screenAdded.connect(self.update_position)
                app_instance.screenRemoved.connect(self.update_position)

            self.setStyleSheet("""
                QMainWindow {
                    background-color: #33322F;
                }
            """)

            self.hide_sidebar(initial=True, reason="initial")

        except Exception as e:
            logging.error(f"Sidebar Initialization Error: {e}", exc_info=True)
            alert_popup(self, "Sidebar Initialization Error", f"Failed to initialize sidebar UI: {e}")
            raise

    def _make_sticky_linux(self):
        if sys.platform != "linux" or QApplication.platformName() != 'xcb':
            return

        win_id_ptr = self.winId()
        if not win_id_ptr:
            return
        hex_id = hex(int(win_id_ptr))

        # Check if ID changed since last sticky apply
        if self.is_made_sticky and hex_id == self._last_sticky_id:
            return

        logging.info(f"Linux Sticky Check: WinID={hex_id} (last={self._last_sticky_id})")

        wmctrl_path = shutil.which('wmctrl')
        if not wmctrl_path:
            logging.warning("wmctrl missing, cannot set sticky bit")
            self.is_made_sticky = True
            self._last_sticky_id = hex_id
            return

        try:
            # Standard sticky/skip flags
            subprocess.run(['wmctrl', '-i', '-r', hex_id, '-b', 'add,sticky,skip_taskbar,skip_pager'],
                           check=True, capture_output=True, text=True, timeout=1.0)

            logging.info(f"Linux window {hex_id} configured as sticky.")
            self.is_made_sticky = True
            self._last_sticky_id = hex_id
        except Exception as e:
            logging.error(f"Failed to configure Linux window: {e}")
            self.is_made_sticky = True
            self._last_sticky_id = hex_id

    def _grab_focus_linux(self, forced=False):
        """Force focus on X11 even with BypassWindowManagerHint.
        Corrects SIGSEGV on 64-bit Linux by explicitly defining ctypes argtypes/restype.
        """
        if sys.platform != "linux" or QApplication.platformName() != 'xcb':
            return

        # Let clicks pass through without immediate focus grab interference,
        # unless forced (e.g. from mousePressEvent)
        if not forced and QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return

        now = time.time()
        # Cooldown: Don't grab focus more than once every 100ms unless explicitly requested
        if not forced and (now - self._last_focus_grab_time) < 0.1:
            return
        self._last_focus_grab_time = now

        win_id = int(self.winId())
        if win_id == 0:
            return

        webview_win_id = 0
        if self.content_widget is not None and self.content_widget.web_view is not None:
            try:
                webview_win_id = int(self.content_widget.web_view.winId())
            except (AttributeError, RuntimeError):
                pass

        if forced:
            logging.info(f"X11 Focus Grab (forced={forced}): Sidebar={hex(win_id)}, WebView={hex(webview_win_id)}")

        try:
            # Cache the library handle and function signatures
            if self._x11_lib is None:
                lib = ctypes.cdll.LoadLibrary("libX11.so.6")

                lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
                lib.XOpenDisplay.restype = ctypes.c_void_p

                lib.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
                lib.XSetInputFocus.restype = ctypes.c_int

                lib.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                lib.XRaiseWindow.restype = ctypes.c_int

                lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
                lib.XSync.restype = ctypes.c_int

                lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
                lib.XCloseDisplay.restype = ctypes.c_int

                self._x11_lib = lib

            # Use cached display if available and not invalid
            if self._x11_display is None:
                display = self._x11_lib.XOpenDisplay(None)
                if not display:
                    logging.error("X11 Focus Grab: XOpenDisplay(None) failed (returned NULL)")
                    return
                self._x11_display = display

            # Ensure Qt knows it should have focus
            self.raise_()
            self.activateWindow()
            self.setFocus()

            # RevertToParent = 1, CurrentTime = 0
            # Grabbing focus on both windows to be safe
            if forced:
                self._x11_lib.XRaiseWindow(self._x11_display, win_id)
            self._x11_lib.XSetInputFocus(self._x11_display, win_id, 1, 0)

            if webview_win_id != 0:
                if forced:
                    self._x11_lib.XRaiseWindow(self._x11_display, webview_win_id)
                self._x11_lib.XSetInputFocus(self._x11_display, webview_win_id, 1, 0)

            self._x11_lib.XSync(self._x11_display, 0)

            # Explicitly set focus to web_view to ensure typing works
            if webview_win_id != 0:
                self.content_widget.web_view.setFocus()
                self.content_widget.web_view.activateWindow()

        except Exception as e:
            logging.error(f"X11 focus grab failed: {e}")
            self._x11_display = None  # Reset on failure

    def focusInEvent(self, event):
        logging.info(f"Qt Focus Event: {event.type().name}")
        super().focusInEvent(event)
        # When sidebar gets focus, ensure webview also has it
        if hasattr(self, 'content_widget') and self.content_widget.web_view:
            self.content_widget.web_view.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        if event.isAccepted():
            # Use a QTimer to ensure the window ID is valid
            QTimer.singleShot(100, self._make_sticky_linux)

    def on_nav_menu_state_changed(self, is_open):
        self.is_nav_menu_open = is_open

    def on_webview_menu_state_changed(self, is_open):
        self.is_webview_menu_open = is_open

    def get_target_screen(self):
        screens = QApplication.screens()
        if 0 <= self.manual_screen_index < len(screens):
            target = screens[self.manual_screen_index]
        else:
            target = self.get_rightmost_screen()

        if target:
            geom = target.geometry()
            # logging.info(f"Target screen: {target.name()} | Geometry: {geom.x()},{geom.y()} {geom.width()}x{geom.height()}")
        return target

    def set_manual_screen(self, index):
        self.manual_screen_index = index
        self.active_screen = self.get_target_screen()
        self.update_position()

    def get_rightmost_screen(self):
        screens = QApplication.screens()
        if not screens:
            return QApplication.primaryScreen()

        # Sắp xếp các màn hình theo tọa độ x + width để tìm màn hình ngoài cùng bên phải
        rightmost = max(screens, key=lambda s: s.geometry().x() + s.geometry().width())
        return rightmost

    def enterEvent(self, event):
        self.last_mouse_in_time = time.time()
        curr_y = event.position().y()

        # Khởi tạo tracking gesture nếu chưa có hoặc nếu đây là lần enter mới (không phải resume)
        if not self.is_visible:
            # Nếu đã có gesture dở dang, ta kiểm tra xem vị trí mới có "gần" vị trí cũ không
            # Nếu quá xa (ví dụ > 50px) thì coi như gesture mới hoàn toàn
            is_far = self.gesture_entry_y is not None and abs(curr_y - self.gesture_entry_y) > 10

            if self.gesture_entry_y is None or is_far:
                self.gesture_entry_y = curr_y
                self.gesture_min_y = curr_y
                self.gesture_max_y = curr_y
                self.gesture_down_met = False
                self.gesture_up_met = False
                self.gesture_start_time = time.time()
        else:
            self._grab_focus_linux()

        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self.last_mouse_in_time = time.time()
        # Chỉ xử lý gesture khi sidebar đang ở chế độ cảm ứng
        if not self.is_visible and self.gesture_entry_y is not None:
            curr_y = event.position().y()

            # Throttle processing to save CPU (e.g., only process if moved significantly or every N ms)
            if hasattr(self, '_last_processed_y') and abs(curr_y - self._last_processed_y) < 5:
                super().mouseMoveEvent(event)
                return
            self._last_processed_y = curr_y

            # Cập nhật min/max Y đã đi qua kể từ khi Enter
            if not hasattr(self, 'gesture_min_y'): self.gesture_min_y = curr_y
            if not hasattr(self, 'gesture_max_y'): self.gesture_max_y = curr_y

            self.gesture_min_y = min(self.gesture_min_y, curr_y)
            self.gesture_max_y = max(self.gesture_max_y, curr_y)

            # Check di xuống: Đã di chuyển xuống ít nhất 200px so với điểm cao nhất
            if not self.gesture_down_met and (curr_y - self.gesture_min_y) > 200:
                self.gesture_down_met = True

            # Check di lên: Đã di chuyển lên ít nhất 200px so với điểm thấp nhất
            if not self.gesture_up_met and (self.gesture_max_y - curr_y) > 200:
                self.gesture_up_met = True

            # Kiểm tra thời gian: Nếu quá 0.7s kể từ lúc bắt đầu thì reset
            gesture_duration = time.time() - self.gesture_start_time
            if gesture_duration > 0.7:
                # Reset để bắt đầu lại chu kỳ 0.7s mới nếu vẫn đang ở trong vùng cảm ứng
                self.gesture_start_time = time.time()
                self.gesture_min_y = curr_y
                self.gesture_max_y = curr_y
                self.gesture_down_met = False
                self.gesture_up_met = False

            # Nếu thỏa mãn cả 2 thì hiện sidebar
            if self.gesture_down_met and self.gesture_up_met:

                # Reset gesture ngay để tránh trigger liên tục
                self.gesture_entry_y = None

                if not self.has_active_popup and not self.is_nav_menu_open and not self.is_webview_menu_open:
                    screen = self.get_target_screen()
                    if screen and self._is_fullscreen_active:
                        return
                    self.active_screen = screen
                    self.show_sidebar()

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self.last_mouse_in_time = time.time()

        # Ý tưởng của user: "Self-healing" focus on click.
        # Kiểm tra xem sidebar đã thực sự gõ được chữ chưa (active window + webview focus)
        is_active = self.isActiveWindow()
        webview_has_focus = False
        if self.content_widget and self.content_widget.web_view:
            webview_has_focus = self.content_widget.web_view.hasFocus()

        if not is_active or not webview_has_focus:
            logging.info(f"MousePress Guard: Focus issue detected (Active={is_active}, WebView={webview_has_focus}). Re-hooking focus...")
            self.activateWindow()
            self._grab_focus_linux(forced=True)
        else:
            # Vẫn hook để đảm bảo X11 focus ổn định mà không cần log
            self._grab_focus_linux(forced=True)

        super().mousePressEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)

        # Ignore if mouse button is currently pressed (e.g. while resizing or dragging)
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return

        # Chỉ ẩn nếu nó đang hiện, không phải đang resize, popup, hoặc menu đang mở
        if not self.is_visible:
            return

        if self.is_resizing:
            return

        if self.has_active_popup or self.is_nav_menu_open or self.is_webview_menu_open:
            logging.info(f"Sidebar leaveEvent: Not hiding (popup={self.has_active_popup}, nav={self.is_nav_menu_open}, webview={self.is_webview_menu_open})")
            return

        now = time.time()
        # Đợi 1 tí để tránh flickers nếu vừa hiện lên
        if (now - self.last_show_time) < 0.5:
            return

        logging.info("Sidebar hide triggered by leaveEvent")
        self.hide_sidebar(reason="leaveEvent")

    def handle_navigation(self, url):
        try:
            self.content_widget.web_view.setUrl(QUrl(url))
            self.content_widget.web_view.save_last_url(url)
        except Exception as e:
            alert_popup(self, "Navigation Error", f"Failed to handle navigation to {url}: {e}")

    def handle_popup_created(self, popup_window):
        try:
            self.popup_windows.append(popup_window)
            self.has_active_popup = True

            flags = self.windowFlags()
            if flags & Qt.WindowType.WindowStaysOnTopHint:
                self.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
                self.show()

            popup_window.raise_()
            popup_window.activateWindow()
            popup_window.popupClosed.connect(lambda: self.handle_popup_closed(popup_window))
        except Exception as e:
            alert_popup(self, "Popup Error", f"Error handling popup creation: {e}")

    def handle_popup_closed(self, popup=None):
        try:
            if popup in self.popup_windows:
                self.popup_windows.remove(popup)

            if not self.popup_windows:
                self.has_active_popup = False

                flags = self.windowFlags()
                if not (flags & Qt.WindowType.WindowStaysOnTopHint):
                    self.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
                    self.show()

                self.raise_()
                self.activateWindow()
        except Exception as e:
            alert_popup(self, "Popup Error", f"Error handling popup closure: {e}")

    def handle_webview_redirect_completed(self, callback_url):
        try:
            for popup in self.popup_windows[:]:
                if popup:
                    popup.close()
        except Exception as e:
            alert_popup(self, "WebView Redirect Error", f"Error handling webview redirect: {e}")

    def is_foreground_fullscreen(self, screen):
        try:
            if sys.platform == "win32" and win32gui is not None:
                hwnd = win32gui.GetForegroundWindow()
                if not hwnd:
                    return False
                if hwnd == win32gui.GetDesktopWindow() or hwnd == win32gui.FindWindow("Progman", None) or hwnd == win32gui.FindWindow("WorkerW", None):
                    return False
                rect = win32gui.GetWindowRect(hwnd)
                win_width = rect[2] - rect[0]
                win_height = rect[3] - rect[1]
                screen_width = screen.geometry().width()
                screen_height = screen.geometry().height()
                return win_width >= screen_width and win_height >= screen_height

        except Exception as e:
            logging.error(f"Error checking fullscreen state: {e}")
        return False

    def toggle_sidebar(self):
        try:
            if self.is_visible:
                self.hide_sidebar(reason="toggle")
            else:
                self.show_sidebar()
        except Exception as e:
            alert_popup(self, "Toggle Sidebar Error", f"Error toggling sidebar visibility: {e}")

    def show_sidebar(self):
        try:
            if self.is_visible:
                return

            logging.info("Showing sidebar")
            self.is_visible = True
            self.last_show_time = time.time()

            # Hiện nội dung chính
            if hasattr(self, 'main_ui_container'):
                self.main_ui_container.show()
                self.main_ui_container.setMinimumWidth(200)  # Đảm bảo không bị bóp nghẹt

            if hasattr(self, 'resize_handle'):
                self.resize_handle.show()

            self.update_position()
            # Fight GNOME's automatic window placement
            QTimer.singleShot(50, self.update_position)
            QTimer.singleShot(200, self.update_position)
            QTimer.singleShot(500, self.update_position)

            def restore_opacity():
                self.setWindowOpacity(1.0)

            QTimer.singleShot(100, restore_opacity)
            self.setStyleSheet("QMainWindow { background-color: #33322F; }")
            self.raise_()
            self.activateWindow()
            self.setFocus()
            # Explicitly set focus to web_view to ensure typing works
            if self.content_widget is not None and self.content_widget.web_view is not None:
                self.content_widget.web_view.setFocus()

            # Multiple focus grabs to ensure focus is acquired
            QTimer.singleShot(0, lambda: self._grab_focus_linux(forced=True))
            QTimer.singleShot(50, lambda: self._grab_focus_linux(forced=True))
            QTimer.singleShot(200, self._grab_focus_linux)
            QTimer.singleShot(1000, lambda: self._grab_focus_linux(forced=True))

        except Exception as e:
            logging.error(f"Error in show_sidebar: {e}", exc_info=True)

    def hide_sidebar(self, initial=False, reason="manual"):
        try:
            if not initial:
                if self.is_resizing or not self.is_visible:
                    return
                # Debounce hide if just showed (tránh hiện tượng flickers/chớp tắt)
                if (time.time() - self.last_show_time) < 0.5:
                    return

            logging.info(f"Hiding sidebar (initial={initial}, reason={reason})")
            # Giảm opacity TRƯỚC khi thu nhỏ
            self.setWindowOpacity(0.01)

            def finalize_hide():
                self.is_visible = False
                if hasattr(self, 'main_ui_container'):
                    self.main_ui_container.hide()
                    self.main_ui_container.setMinimumWidth(0)
                if hasattr(self, 'resize_handle'):
                    self.resize_handle.hide()

                self.setStyleSheet("QMainWindow { background-color: transparent; }")
                self.update_position()

            if not initial:
                QTimer.singleShot(50, finalize_hide)
            else:
                finalize_hide()
                self.show()

        except Exception as e:
            logging.error(f"Error in hide_sidebar: {e}", exc_info=True)

    def closeEvent(self, event):
        try:
            if self._x11_display is not None:
                try:
                    self._x11_lib.XCloseDisplay(self._x11_display)
                    self._x11_display = None
                except Exception:
                    pass
            if self.content_widget is not None and self.content_widget.web_view is not None:
                self.content_widget.web_view.deleteLater()
            event.accept()
        except Exception as e:
            alert_popup(self, "Close Event Error", f"Error during close event: {e}")

    def get_current_screen_width(self):
        try:
            if self.active_screen:
                return self.active_screen.geometry().width()
            return QApplication.primaryScreen().geometry().width()
        except Exception as e:
            alert_popup(self, "Screen Width Error", f"Error getting current screen width: {e}")
            return 0

    def resizing_started(self):
        self.is_resizing = True

    def resizing_finished(self):
        self.is_resizing = False
        self.last_width = self.width()

    def update_position(self, _=None):
        try:
            # Always update target screen before calculating coordinates
            self.active_screen = self.get_target_screen()
            if not self.active_screen:
                return

            screen_geometry = self.active_screen.geometry()

            # Determine target width
            if self.is_visible:
                target_width = self.last_width or self.calculate_width(screen_geometry.width())
            else:
                target_width = 5

            # Absolute coordinates
            new_x = screen_geometry.x() + screen_geometry.width() - target_width
            new_y = screen_geometry.y()
            new_w = target_width
            new_h = screen_geometry.height()

            # logging.info(f"Geometry: {new_x},{new_y} {new_w}x{new_h} on {self.active_screen.name()}")
            self.setGeometry(new_x, new_y, new_w, new_h)

        except Exception as e:
            logging.error(f"Error in update_position: {e}", exc_info=True)

    def update_width_and_x_position(self):
        try:
            if not self.active_screen:
                self.active_screen = self.get_target_screen()

            screen_geometry = self.active_screen.geometry()

            current_y = self.y()
            current_height = self.height()

            new_x = screen_geometry.x() + screen_geometry.width() - self.width()

            self.move(new_x, current_y)

        except Exception as e:
            alert_popup(self, "Update Width Error", f"Error updating window width: {e}")
