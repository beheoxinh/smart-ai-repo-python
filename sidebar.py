# File: components/sidebar.py (Cross-platform version)
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

        # Gesture Trigger State
        self.gesture_entry_y = None
        self.gesture_min_y = None
        self.gesture_max_y = None
        self.gesture_down_met = False
        self.gesture_up_met = False
        self._last_log_y = 0
        self.last_show_time = 0
        self.gesture_start_time = 0

        # Timer kiểm tra chuột rời khỏi sidebar (Auto-hide)
        self.leave_check_timer = QTimer(self)
        self.leave_check_timer.timeout.connect(self.check_auto_hide)

        self.init_ui()
        self.setup_shortcut()

    def check_auto_hide(self):
        if not self.is_visible or self.is_resizing or self.has_active_popup or self.is_nav_menu_open or self.is_webview_menu_open:
            return

        now = time.time()
        if (now - self.last_show_time) < 0.5:
            return

        cursor_pos = QCursor.pos()
        cursor_x = cursor_pos.x()
        cursor_y = cursor_pos.y()

        geo = self.geometry()

        # Di chuyển ra ngoài phía trái sidebar (cộng thêm 5px an toàn), hoặc sang phải (nếu có màn hình khác)
        # hoặc di chuyển ra khỏi top/bottom
        is_outside_x = cursor_x < (geo.left() - 5) or cursor_x > (geo.right() + 5)
        is_outside_y = cursor_y < geo.top() or cursor_y > geo.bottom()

        if is_outside_x or is_outside_y:
            logging.info(f"   [AUTO HIDE] Mouse moved outside! Pos=({cursor_x},{cursor_y}) Geo=[L:{geo.left()}, R:{geo.right()}]")
            self.hide_sidebar()

    def debug_mouse_position(self):
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)

        # Log trạng thái thực tế của window
        window_screen = "None"
        if self.windowHandle() and self.windowHandle().screen():
            window_screen = self.windowHandle().screen().name()

        if screen:
            screen_name = screen.name()
            if screen_name != getattr(self, 'last_mouse_screen', None) or window_screen != getattr(self, 'last_window_screen', ''):
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
            self.setMouseTracking(True)

            container = QWidget()
            container.setMouseTracking(True)  # QUAN TRỌNG: Phải bật ở đây thì QMainWindow mới nhận được move event
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)

            self.resize_handle = ResizeHandle(self)
            container_layout.addWidget(self.resize_handle)

            main_widget = QWidget()
            self.main_ui_container = main_widget  # Lưu lại để ẩn/hiện
            main_widget.setMouseTracking(True)
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
        curr_y = cursor_pos.y()
        logging.info(f"==> MẮT THẦN: Mouse ENTER at x={cursor_pos.x()}, y={curr_y} | Current Visible={self.is_visible}")

        # Khởi tạo tracking gesture nếu chưa có hoặc nếu đây là lần enter mới (không phải resume)
        if not self.is_visible:
            # Nếu đã có gesture dở dang, ta kiểm tra xem vị trí mới có "gần" vị trí cũ không
            # Nếu quá xa (ví dụ > 50px) thì coi như gesture mới hoàn toàn
            is_far = self.gesture_entry_y is not None and abs(curr_y - self.gesture_entry_y) > 100

            if self.gesture_entry_y is None or is_far:
                self.gesture_entry_y = curr_y
                self.gesture_min_y = curr_y
                self.gesture_max_y = curr_y
                self.gesture_down_met = False
                self.gesture_up_met = False
                self.gesture_start_time = time.time()
                logging.info(f"   [GESTURE START] Initial Y={self.gesture_entry_y} at {self.gesture_start_time}")
            else:
                logging.info(
                    f"   [GESTURE RESUME] Continuing from Y={self.gesture_entry_y} (Min={getattr(self, 'gesture_min_y', 0)}, Max={getattr(self, 'gesture_max_y', 0)})")

        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        # Chỉ xử lý gesture khi sidebar đang ở chế độ cảm ứng
        if not self.is_visible and self.gesture_entry_y is not None:
            curr_pos = QCursor.pos()
            curr_y = curr_pos.y()

            # Cập nhật min/max Y đã đi qua kể từ khi Enter
            if not hasattr(self, 'gesture_min_y'): self.gesture_min_y = curr_y
            if not hasattr(self, 'gesture_max_y'): self.gesture_max_y = curr_y

            self.gesture_min_y = min(self.gesture_min_y, curr_y)
            self.gesture_max_y = max(self.gesture_max_y, curr_y)

            # Check di xuống: Đã di chuyển xuống ít nhất 100px so với điểm cao nhất
            if not self.gesture_down_met and (curr_y - self.gesture_min_y) > 100:
                self.gesture_down_met = True
                logging.info(f"   [GESTURE STEP] Step: Down > 100px OK (Current={curr_y}, Min={self.gesture_min_y})")

            # Check di lên: Đã di chuyển lên ít nhất 100px so với điểm thấp nhất
            if not self.gesture_up_met and (self.gesture_max_y - curr_y) > 100:
                self.gesture_up_met = True

            # Kiểm tra thời gian: Nếu quá 1s kể từ lúc bắt đầu thì reset
            gesture_duration = time.time() - self.gesture_start_time
            if gesture_duration > 1.0:
                # Reset để bắt đầu lại chu kỳ 1s mới nếu vẫn đang ở trong vùng cảm ứng
                self.gesture_start_time = time.time()
                self.gesture_min_y = curr_y
                self.gesture_max_y = curr_y
                self.gesture_down_met = False
                self.gesture_up_met = False

            # Nếu thỏa mãn cả 2 thì hiện sidebar
            if self.gesture_down_met and self.gesture_up_met:
                logging.info(f"   [GESTURE COMPLETE] Thresholds met in {gesture_duration:.2f}s. Triggering show_sidebar()")

                # Reset gesture ngay để tránh trigger liên tục
                self.gesture_entry_y = None

                if not self.has_active_popup and not self.is_nav_menu_open and not self.is_webview_menu_open:
                    screen = self.get_target_screen()
                    if screen and self.is_foreground_fullscreen(screen):
                        logging.info("   [SHOW BLOCKED] Fullscreen app detected.")
                        return
                    self.active_screen = screen
                    self.show_sidebar()
                else:
                    logging.info(f"   [SHOW BLOCKED] UI busy: popup={self.has_active_popup}, nav={self.is_nav_menu_open}, webview={self.is_webview_menu_open}")

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        # Chúng ta dùng check_auto_hide timer để xử lý việc ẩn chính xác hơn
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
            logging.info(f"==> MẮT THẦN: [SHOW] Starting show_sidebar. is_visible was {self.is_visible}")
            if self.is_visible:
                return

            self.is_visible = True
            self.last_show_time = time.time()

            # Hiện nội dung chính
            if hasattr(self, 'main_ui_container'):
                self.main_ui_container.show()
                self.main_ui_container.setMinimumWidth(200)  # Đảm bảo không bị bóp nghẹt

            if hasattr(self, 'resize_handle'):
                self.resize_handle.show()

            self.update_position()
            self.leave_check_timer.start(200)  # Kiểm tra mỗi 200ms

            def restore_opacity():
                logging.info("   [SHOW OPACITY] Setting opacity to 1.0")
                self.setWindowOpacity(1.0)

            QTimer.singleShot(100, restore_opacity)
            self.setStyleSheet("QMainWindow { background-color: #33322F; }")
            self.raise_()
            self.activateWindow()

        except Exception as e:
            logging.error(f"Error in show_sidebar: {e}", exc_info=True)

    def hide_sidebar(self, initial=False):
        try:
            if not initial:
                if self.is_resizing or not self.is_visible:
                    return
                # Debounce hide if just showed (tránh hiện tượng flickers/chớp tắt)
                if (time.time() - self.last_show_time) < 0.5:
                    logging.info(f"   [HIDE IGNORED] Too soon after show ({(time.time() - self.last_show_time) * 1000:.0f}ms)")
                    return

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
                self.leave_check_timer.stop()
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
                return

            screen_geometry = self.active_screen.geometry()

            # Xác định chiều rộng mục tiêu
            if self.is_visible:
                target_width = self.last_width or self.calculate_width(screen_geometry.width())
            else:
                target_width = 20

            # Tọa độ X tuyệt đối
            new_x = screen_geometry.x() + screen_geometry.width() - target_width
            new_y = screen_geometry.y()
            new_w = target_width
            new_h = screen_geometry.height()

            logging.info(f"==> MẮT THẦN: [MOVE] Target: x={new_x}, y={new_y}, w={new_w}, h={new_h} | Visible={self.is_visible}")

            # Ép window handle sang đúng screen nếu cần (chỉ làm khi thực sự lệch màn hình)
            if self.windowHandle() and self.windowHandle().screen() != self.active_screen:
                self.windowHandle().setScreen(self.active_screen)

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
