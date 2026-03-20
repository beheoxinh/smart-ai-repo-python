# File: components/sidebar.py (Original version, before show/hide modifications)
import win32gui
import win32api
from PyQt6.QtCore import Qt, QTimer, QPoint, QEvent, QPropertyAnimation, QUrl
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication
from PyQt6.QtGui import QCursor, QShortcut, QKeySequence

from components.resize_handle import ResizeHandle
from components.content_widget import ContentWidget
from utils import alert_popup # Import alert_popup

class Sidebar(QMainWindow):
    def __init__(self):
        super().__init__()

        self.dialog_open = False
        self.setWindowTitle("sidebar")
        self.is_visible = False
        self.active_screen = None
        self.is_resizing = False
        self.has_active_popup = False
        self.popup_windows = []
        self.last_width = None
        self.init_ui()
        self.setup_shortcut()

    def calculate_width(self, screen_width):
        return int(screen_width * 0.6)

    def setup_shortcut(self):
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        shortcut.activated.connect(self.toggle_sidebar)

    def init_ui(self):
        try:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.Tool |
                Qt.WindowType.WindowStaysOnTopHint
            )
            self.installEventFilter(self)
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

            self.content_widget.closeRequested.connect(self.hide_sidebar)
            self.content_widget.web_view.popupCreated.connect(self.handle_popup_created)
            self.content_widget.web_view.webviewRedirectCompleted.connect(self.handle_webview_redirect_completed)
            self.content_widget.nav_bar.navigationClicked.connect(self.handle_navigation)

            container_layout.addWidget(main_widget)
            self.setCentralWidget(container)

            primary_screen = QApplication.primaryScreen()
            if primary_screen:
                self.setFixedWidth(self.calculate_width(primary_screen.geometry().width()))

            self.update_rightmost_screen()

            self.mouse_timer = QTimer()
            self.mouse_timer.timeout.connect(self.check_mouse)
            self.mouse_timer.start(100) # Original interval

            self.setStyleSheet("""
                QMainWindow {
                    background-color: #33322F;
                }
            """)
            self.hide()
        except Exception as e:
            alert_popup(self, "Sidebar Initialization Error", f"Failed to initialize sidebar UI: {e}")
            raise # Re-raise to propagate to main.py

    def update_rightmost_screen(self):
        try:
            screens = QApplication.screens()
            if screens:
                self.rightmost_screen = max(screens, key=lambda s: s.geometry().x() + s.geometry().width())
            else:
                self.rightmost_screen = None
        except Exception as e:
            alert_popup(self, "Screen Update Error", f"Failed to update rightmost screen: {e}")

    def handle_navigation(self, url):
        try:
            self.content_widget.web_view.setUrl(QUrl(url))
            self.content_widget.web_view.save_last_url(url)
        except Exception as e:
            alert_popup(self, "Navigation Error", f"Failed to handle navigation to {url}: {e}")

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.Type.MouseButtonPress:
                if self.dialog_open:
                    return False
                pass
            return super().eventFilter(obj, event)
        except Exception as e:
            alert_popup(self, "Event Filter Error", f"Error in event filter: {e}")
            return False # Prevent event from being processed further

    def handle_popup_created(self, popup_window):
        try:
            self.popup_windows.append(popup_window)
            self.has_active_popup = True
            self.mouse_timer.stop()
            popup_window.popupClosed.connect(lambda: self.handle_popup_closed(popup_window))
        except Exception as e:
            alert_popup(self, "Popup Error", f"Error handling popup creation: {e}")

    def handle_popup_closed(self, popup=None):
        try:
            if popup in self.popup_windows:
                self.popup_windows.remove(popup)
            if not self.popup_windows:
                self.has_active_popup = False
                self.mouse_timer.start(100) # Original interval
        except Exception as e:
            alert_popup(self, "Popup Error", f"Error handling popup closure: {e}")

    def handle_webview_redirect_completed(self, callback_url):
        try:
            for popup in self.popup_windows[:]:
                if popup:
                    popup.close()
            self.popup_windows.clear()
            self.has_active_popup = False
            self.mouse_timer.start(100) # Original interval
        except Exception as e:
            alert_popup(self, "WebView Redirect Error", f"Error handling webview redirect: {e}")

    def is_foreground_fullscreen(self, screen):
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd: return False
            class_name = win32gui.GetClassName(hwnd)
            if class_name in ["Progman", "WorkerW"]: return False
            if not win32gui.IsWindowVisible(hwnd): return False
            rect = win32gui.GetWindowRect(hwnd)
            screen_geo = screen.geometry()
            return (abs(rect[0] - screen_geo.x()) <= 1 and
                    abs(rect[1] - screen_geo.y()) <= 1 and
                    abs(rect[2] - rect[0] - screen_geo.width()) <= 1 and
                    abs(rect[3] - rect[1] - screen_geo.height()) <= 1)
        except Exception as e:
            # This function is called frequently, so just log and return False
            # print(f"Error checking fullscreen: {e}")
            return False

    def check_mouse(self):
        try:
            if self.is_resizing or self.has_active_popup:
                return

            cursor_pos = QCursor.pos()

            self.update_rightmost_screen() # Original logic
            if not self.rightmost_screen:
                return

            screen = self.rightmost_screen
            screen_geo = screen.geometry()

            if not self.is_visible:
                right_edge = screen_geo.x() + screen_geo.width()
                is_at_edge = (cursor_pos.x() >= right_edge - 2)
                is_vertically_inside = (screen_geo.y() <= cursor_pos.y() <= screen_geo.y() + screen_geo.height())

                if is_at_edge and is_vertically_inside:
                    if self.is_foreground_fullscreen(screen):
                        return

                    self.active_screen = screen
                    if not self.is_resizing:
                        self.setFixedWidth(self.last_width or self.calculate_width(screen_geo.width()))
                    self.update_position()
                    self.show_sidebar()
                    return

            else:
                if not self.frameGeometry().contains(cursor_pos):
                    left_state = win32api.GetKeyState(0x01)
                    right_state = win32api.GetKeyState(0x02)
                    middle_state = win32api.GetKeyState(0x04)

                    if left_state < 0 or right_state < 0 or middle_state < 0:
                        self.hide_sidebar()
        except Exception as e:
            # This function is called frequently, so just log and return silently
            # alert_popup(self, "Mouse Check Error", f"Error in check_mouse: {e}")
            pass

    def toggle_sidebar(self):
        try:
            if self.is_visible:
                self.hide_sidebar()
            else:
                screen = self.get_screen_at_cursor()
                if screen:
                    self.active_screen = screen
                    self.update_position()
                    self.show_sidebar()
        except Exception as e:
            alert_popup(self, "Toggle Sidebar Error", f"Error toggling sidebar visibility: {e}")

    def show_sidebar(self):
        try:
            if self.is_visible: return
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()
            self.activateWindow()

            self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
            self.fade_animation.setDuration(100)
            self.fade_animation.setStartValue(0.0)
            self.fade_animation.setEndValue(1.0)
            self.fade_animation.start()
            self.is_visible = True
        except Exception as e:
            alert_popup(self, "Show Sidebar Error", f"Error showing sidebar: {e}")

    def hide_sidebar(self):
        try:
            if self.is_resizing or not self.isVisible(): return
            self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
            self.fade_animation.setDuration(100)
            self.fade_animation.setStartValue(1.0)
            self.fade_animation.setEndValue(0.0)

            def after_hide():
                self.hide()
                self.is_visible = False
                try:
                    self.fade_animation.finished.disconnect(after_hide)
                except TypeError:
                    pass # Already disconnected

            self.fade_animation.finished.connect(after_hide)
            self.fade_animation.start()
        except Exception as e:
            alert_popup(self, "Hide Sidebar Error", f"Error hiding sidebar: {e}")

    def closeEvent(self, event):
        try:
            # Original code had self.parent, but Sidebar is QMainWindow, not a child.
            # Removed self.parent check.
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
            return 0 # Return a safe default

    def resizing_started(self):
        try:
            self.is_resizing = True
            # Original code did not stop timer here.
            # For stability, it's safer to stop the timer during resize.
            # However, user explicitly asked not to change show/hide logic.
            # So, reverting to original behavior for this part.
        except Exception as e:
            alert_popup(self, "Resize Error", f"Error starting resize: {e}")

    def resizing_finished(self):
        try:
            self.is_resizing = False
            self.last_width = self.width()
            # Original code did not restart timer here.
            # For stability, it's safer to restart the timer after resize.
            # However, user explicitly asked not to change show/hide logic.
            # So, reverting to original behavior for this part.
        except Exception as e:
            alert_popup(self, "Resize Error", f"Error finishing resize: {e}")

    def get_screen_at_cursor(self):
        try:
            cursor_pos = QCursor.pos()
            for screen in QApplication.screens():
                if screen.geometry().contains(cursor_pos):
                    return screen
            return None
        except Exception as e:
            alert_popup(self, "Screen Detection Error", f"Error getting screen at cursor: {e}")
            return None

    def update_position(self):
        try:
            if not self.active_screen: return
            screen_geometry = self.active_screen.geometry()
            # Original code did not calculate taskbar height here.
            # Reverting to original behavior.
            self.setGeometry(
                screen_geometry.x() + screen_geometry.width() - self.width(),
                screen_geometry.y(),
                self.width(),
                screen_geometry.height()
            )
        except Exception as e:
            alert_popup(self, "Update Position Error", f"Error updating window position: {e}")

    # Original get_taskbar_height was not present in the initial version.
    # Removed it to fully rollback.
    # def get_taskbar_height(self):
    #     try:
    #         taskbar = win32gui.FindWindow('Shell_TrayWnd', None)
    #         if taskbar:
    #             rect = win32gui.GetWindowRect(taskbar)
    #             return rect[3] - rect[1]
    #     except:
    #         pass
    #     return 0

    def moveEvent(self, event):
        try:
            if self.active_screen:
                self.update_position()
        except Exception as e:
            alert_popup(self, "Move Event Error", f"Error during move event: {e}")

    def dialog_open_set_false(self):
        try:
            self.dialog_open = False
        except Exception as e:
            alert_popup(self, "Dialog State Error", f"Error setting dialog_open to false: {e}")
