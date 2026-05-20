# File: components/sidebar.py (Cross-platform version)
import logging
import os
import shutil
import subprocess
import sys

try:
    import win32gui
    import win32api
except ImportError:
    win32gui = None
    win32api = None

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication
from PyQt6.QtGui import QCursor, QShortcut, QKeySequence

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

        self.init_ui()
        self.setup_shortcut()

        # Timer debug tọa độ chuột và màn hình
        self.debug_timer = QTimer(self)
        self.debug_timer.timeout.connect(self.debug_mouse_position)
        self.debug_timer.start(1000)  # Mỗi 1 giây log một lần

    def debug_mouse_position(self):
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)

        # Log trạng thái thực tế của window
        window_screen = "None"
        if self.windowHandle() and self.windowHandle().screen():
            window_screen = self.windowHandle().screen().name()

        if screen:
            screen_name = screen.name()
            if screen_name != self.last_mouse_screen or window_screen != getattr(self, 'last_window_screen', ''):
                logging.info(
                    f"STATUS: Mouse on {screen_name} | Window ACTUALLY on {window_screen} | Target Screen: {self.active_screen.name() if self.active_screen else 'None'}")
                self.last_mouse_screen = screen_name
                self.last_window_screen = window_screen

    def calculate_width(self, screen_width):
        return int(screen_width * 0.5)

    def setup_shortcut(self):
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        shortcut.activated.connect(self.toggle_sidebar)

    def init_ui(self):
        try:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.ToolTip |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.NoDropShadowWindowHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)

            self.resize_handle = ResizeHandle(self)
            container_layout.addWidget(self.resize_handle)

            main_widget = QWidget()
            main_layout = QVBoxLayout(main_widget)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            self.content_widget = ContentWidget()
            main_layout.addWidget(self.content_widget)

            self.bottom_bar = BottomBar()
            main_layout.addWidget(self.bottom_bar)

            self.content_widget.closeRequested.connect(self.hide_sidebar)
            self.content_widget.web_view.popupCreated.connect(self.handle_popup_created)
            self.content_widget.web_view.webviewRedirectCompleted.connect(self.handle_webview_redirect_completed)
            self.content_widget.nav_bar.navigationClicked.connect(self.handle_navigation)
            self.content_widget.nav_bar.menu_state_changed.connect(self.on_nav_menu_state_changed)
            self.content_widget.context_menu_state_changed.connect(self.on_webview_menu_state_changed)

            container_layout.addWidget(main_widget)
            self.setCentralWidget(container)

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

            self.hide_sidebar(initial=True)

        except Exception as e:
            logging.error(f"Sidebar Initialization Error: {e}", exc_info=True)
            alert_popup(self, "Sidebar Initialization Error", f"Failed to initialize sidebar UI: {e}")
            raise

    def _make_sticky_linux(self):
        if self.is_made_sticky or sys.platform != "linux" or QApplication.platformName() != 'xcb':
            return

        if not shutil.which('wmctrl'):
            logging.warning("`wmctrl` not found. Cannot make the window sticky across workspaces. Please install it (e.g., 'sudo apt-get install wmctrl').")
            self.is_made_sticky = True  # Don't try again
            return

        try:
            win_id_ptr = self.winId()
            if not win_id_ptr:
                return  # Window not ready yet

            win_id = int(win_id_ptr)
            hex_id = hex(win_id)

            subprocess.run(
                ['wmctrl', '-i', '-r', hex_id, '-b', 'add,sticky'],
                check=True,
                capture_output=True,
                text=True
            )
            logging.info(f"Made window {hex_id} sticky for all workspaces.")
            self.is_made_sticky = True
        except (subprocess.CalledProcessError, FileNotFoundError, TypeError) as e:
            logging.error(f"Failed to make window sticky using wmctrl: {e}")
            self.is_made_sticky = True  # Don't try again

    def showEvent(self, event):
        super().showEvent(event)
        if event.isAccepted():
            # Use a QTimer to ensure the window ID is valid
            QTimer.singleShot(100, self._make_sticky_linux)

    def on_nav_menu_state_changed(self, is_open):
        self.is_nav_menu_open = is_open
        logging.info(f"Nav menu state changed: {'Open' if is_open else 'Closed'}")

    def on_webview_menu_state_changed(self, is_open):
        self.is_webview_menu_open = is_open
        logging.info(f"Webview context menu state changed: {'Open' if is_open else 'Closed'}")

    def get_target_screen(self):
        screens = QApplication.screens()
        if 0 <= self.manual_screen_index < len(screens):
            return screens[self.manual_screen_index]
        return self.get_rightmost_screen()

    def set_manual_screen(self, index):
        self.manual_screen_index = index
        self.active_screen = self.get_target_screen()
        self.update_position()
        logging.info(f"Manual screen set to index: {index}")

    def get_rightmost_screen(self):
        screens = QApplication.screens()
        if not screens:
            return QApplication.primaryScreen()

        # In ra list màn hình để kiểm tra thứ tự
        for i, s in enumerate(screens):
            logging.info(f"Screen Check [{i}]: {s.name()} | Geometry: {s.geometry()}")

        # Sắp xếp các màn hình theo tọa độ x + width để tìm màn hình ngoài cùng bên phải
        rightmost = max(screens, key=lambda s: s.geometry().x() + s.geometry().width())
        logging.info(f"Detected RIGHTMOST Screen: {rightmost.name()} | Geometry: {rightmost.geometry()}")
        return rightmost

    def enterEvent(self, event):
        # Log tọa độ chuột để debug
        cursor_pos = QCursor.pos()
        logging.info(f"Mouse EnterEvent tại: x={cursor_pos.x()}, y={cursor_pos.y()}")

        if not self.is_visible and not self.has_active_popup and not self.is_nav_menu_open and not self.is_webview_menu_open:
            # Sử dụng màn hình mục tiêu (auto hoặc manual)
            screen = self.get_target_screen()
            if screen and self.is_foreground_fullscreen(screen):
                return

            self.active_screen = screen
            self.show_sidebar()

        super().enterEvent(event)

    def leaveEvent(self, event):
        if QApplication.mouseButtons() == Qt.MouseButton.LeftButton:
            return
        if self.is_visible and not self.has_active_popup and not self.is_nav_menu_open and not self.is_webview_menu_open:
            self.hide_sidebar()

        super().leaveEvent(event)

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
                # ... (giữ nguyên code win32)
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

            elif sys.platform == "linux":
                if QApplication.platformName() == "wayland":
                    # Trên Wayland native, không có cách chuẩn để check fullscreen của app khác
                    # Ta tạm thời trả về False để tránh block sidebar vô lý
                    return False

                import subprocess
                try:
                    # Logic xprop chỉ dành cho X11
                    active_win_out = subprocess.check_output(['xprop', '-root', '32x', '\t$0', '_NET_ACTIVE_WINDOW'], stderr=subprocess.DEVNULL).decode().strip()
                    # ...
                    win_id = active_win_out.split('\t')[-1].strip()
                    if win_id and win_id != "0x0":
                        win_props = subprocess.check_output(['xprop', '-id', win_id, '_NET_WM_STATE'], stderr=subprocess.DEVNULL).decode()
                        if '_NET_WM_STATE_FULLSCREEN' in win_props:
                            return True
                except Exception:
                    pass

        except Exception as e:
            logging.error(f"Error checking fullscreen state: {e}")
        return False

    def toggle_sidebar(self):
        try:
            if self.is_visible:
                self.hide_sidebar()
            else:
                self.show_sidebar()
        except Exception as e:
            alert_popup(self, "Toggle Sidebar Error", f"Error toggling sidebar visibility: {e}")

    def show_sidebar(self):
        try:
            if self.is_visible: return

            # Luôn cập nhật màn hình mục tiêu trước khi hiển thị
            self.active_screen = self.get_target_screen()
            if not self.active_screen:
                self.active_screen = QApplication.primaryScreen()

            # BẮT BUỘC: Ép screen trước khi gọi show()
            # winId() đảm bảo windowHandle() được tạo ra
            self.winId()
            if self.windowHandle():
                logging.info(f"PRE-SHOW: Setting screen to {self.active_screen.name()}")
                self.windowHandle().setScreen(self.active_screen)

            # Reset style về bình thường khi hiện
            self.setStyleSheet("QMainWindow { background-color: #33322F; }")
            if hasattr(self, 'centralWidget') and self.centralWidget():
                self.centralWidget().setStyleSheet("background-color: transparent;")

            target_width = self.last_width or self.calculate_width(self.active_screen.geometry().width())

            self.setWindowOpacity(1.0)
            self.setFixedWidth(target_width)
            self.is_visible = True

            # Cập nhật tọa độ lần cuối
            self.update_position()

            self.show()
            self.raise_()
            self.activateWindow()

        except Exception as e:
            logging.error(f"Error in show_sidebar: {e}", exc_info=True)
            alert_popup(self, "Show Sidebar Error", f"Error showing sidebar: {e}")

    def hide_sidebar(self, initial=False):
        try:
            if not initial and (self.is_resizing or not self.is_visible): return

            # Make sensor area transparent
            transparent_style = "background-color: transparent;"
            self.setStyleSheet(f"QMainWindow {{ {transparent_style} }}")
            if hasattr(self, 'centralWidget') and self.centralWidget():
                self.centralWidget().setStyleSheet(transparent_style)

            # Set a very low opacity for the sensor area so it's invisible but still catches mouse events
            self.setWindowOpacity(0.01)

            self.is_visible = False
            # Width 5px for the sensor
            self.setFixedWidth(5)

            if not initial:
                self.update_position()
            else:
                self.show()
                # Use a small delay to ensure coordinates are correct after initialization
                QTimer.singleShot(50, self.update_position)

        except Exception as e:
            logging.error(f"Error in hide_sidebar: {e}", exc_info=True)
            alert_popup(self, "Hide Sidebar Error", f"Error hiding sidebar: {e}")

    def closeEvent(self, event):
        try:
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

    def get_screen_at_cursor(self):
        cursor_pos = QCursor.pos()
        return QApplication.screenAt(cursor_pos)

    def update_position(self, _=None):
        try:
            # Luôn cập nhật màn hình mục tiêu trước khi tính toán tọa độ
            self.active_screen = self.get_target_screen()
            if not self.active_screen:
                logging.warning("update_position: No active screen found.")
                return

            screen_geometry = self.active_screen.geometry()
            dpr = self.devicePixelRatioF()
            logging.info(f"Device Pixel Ratio (DPR): {dpr}")
            platform = QApplication.platformName()
            is_wayland_session = os.environ.get("XDG_SESSION_TYPE") == "wayland"

            # QUAN TRỌNG: Trên Wayland/XWayland, windowHandle().screen() cập nhật rất chậm
            # dẫn đến loop vô tận. Ta sẽ dựa vào tọa độ thực tế để quyết định có cần ép screen không.
            actual_x = self.x()
            screen_geo = self.active_screen.geometry()
            is_outside_target = (actual_x < screen_geo.x() or actual_x > (screen_geo.x() + screen_geo.width()))

            if self.windowHandle() and is_outside_target:
                logging.info(
                    f"SCREEN MISMATCH: Actual X {actual_x} is outside {self.active_screen.name()} ({screen_geo.x()} to {screen_geo.x() + screen_geo.width()}). Forcing...")
                # Ép screen và tọa độ cùng lúc để phá clamping
                self.windowHandle().setScreen(self.active_screen)

            # Sử dụng chiều rộng mục tiêu: 
            # Nếu đang hiện thì là last_width, nếu đang ẩn thì là 5px
            target_width = self.width()
            if not self.is_visible:
                target_width = 5

            # Đảm bảo chiều rộng sidebar không vượt quá 90% chiều rộng màn hình hiện tại
            max_allowed_width = int(screen_geometry.width() * 0.9)
            if target_width > max_allowed_width:
                logging.info(f"Clamping width from {target_width} to {max_allowed_width}")
                target_width = max_allowed_width

            bottom_margin = 0
            # Tọa độ X tuyệt đối trên toàn bộ không gian desktop
            new_x = screen_geometry.x() + screen_geometry.width() - target_width
            new_y = screen_geometry.y()
            new_w = target_width
            new_h = screen_geometry.height() - bottom_margin

            logging.info(
                f"MOVING WINDOW to: Screen={self.active_screen.name()} (Global X: {screen_geometry.x()}) | Target Rect: x={new_x}, y={new_y}, w={new_w}, h={new_h} | Platform: {platform} | WaylandSession: {is_wayland_session}")

            # Trên XWayland, di chuyển cửa sổ xuyên màn hình đôi khi bị "clamped".
            # Ta sẽ thử combo setGeometry + move để ép nó.
            if is_wayland_session or platform == "wayland":
                self.setGeometry(new_x, new_y, new_w, new_h)
                # Gọi thêm move để chắc chắn trên XWayland
                QTimer.singleShot(50, lambda: self.move(new_x, new_y))
            else:
                self.move(new_x, new_y)
                self.resize(new_w, new_h)

            # Log kết quả thực tế sau khi đặt
            actual_geo = self.geometry()
            logging.info(f"ACTUAL GEOMETRY after move: x={actual_geo.x()}, y={actual_geo.y()}, w={actual_geo.width()}, h={actual_geo.height()}")

            if actual_geo.x() != new_x and not is_wayland_session:
                logging.warning(f"POSITION MISMATCH! Expected x={new_x}, got x={actual_geo.x()}. OS or Window Manager might be clamping the window.")

        except Exception as e:
            logging.error(f"Error in update_position: {e}", exc_info=True)
            alert_popup(self, "Update Position Error", f"Error updating window position: {e}")

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
