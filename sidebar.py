# File: components/sidebar.py (Cross-platform version)
import sys
import subprocess
import logging 
try:
    import win32gui
    import win32api
except ImportError:
    win32gui = None
    win32api = None

from PyQt6.QtCore import Qt, QTimer, QPoint, QEvent, QUrl, QRect
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication
from PyQt6.QtGui import QCursor, QShortcut, QKeySequence, QMouseEvent

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
        self.popup_windows = []
        self.last_width = None
        self.init_ui()
        self.setup_shortcut()

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
                Qt.WindowType.WindowStaysOnTopHint
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

            container_layout.addWidget(main_widget)
            self.setCentralWidget(container)

            primary_screen = QApplication.primaryScreen()
            if primary_screen:
                self.last_width = self.calculate_width(primary_screen.geometry().width())

            self.active_screen = QApplication.primaryScreen()

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

    def enterEvent(self, event):
        """Kích hoạt khi chuột đi vào vùng widget (kể cả vùng 1px)"""
        if not self.is_visible and not self.has_active_popup:
            screen = QApplication.screenAt(QCursor.pos())
            if screen and self.is_foreground_fullscreen(screen):
                return
            
            self.active_screen = screen
            self.show_sidebar()
        
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Kích hoạt khi chuột rời khỏi vùng widget"""
        if self.is_visible and not self.has_active_popup:
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
        # This function is platform-specific and complex, assuming it's correct for now.
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
            
            if not self.active_screen:
                self.active_screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()

            target_width = self.last_width or self.calculate_width(self.active_screen.geometry().width())
            
            self.setWindowOpacity(1.0)
            self.setFixedWidth(target_width)
            self.update_position()
            self.is_visible = True
            
            self.show()
            self.raise_()
            self.activateWindow()
            
        except Exception as e:
            logging.error(f"Error in show_sidebar: {e}", exc_info=True)
            alert_popup(self, "Show Sidebar Error", f"Error showing sidebar: {e}")

    def hide_sidebar(self, initial=False):
        try:
            if not initial and (self.is_resizing or not self.is_visible): return

            self.is_visible = False
            self.setWindowOpacity(0.01)
            self.setFixedWidth(1)

            if not initial:
                self.update_position()
            else:
                self.show()
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

    def update_position(self):
        try:
            if not self.active_screen:
                self.active_screen = self.get_screen_at_cursor() or QApplication.primaryScreen()

            screen_geometry = self.active_screen.geometry()
            bottom_margin = 64

            self.setGeometry(
                screen_geometry.x() + screen_geometry.width() - self.width(),
                screen_geometry.y(),
                self.width(),
                screen_geometry.height() - bottom_margin
            )
        except Exception as e:
            alert_popup(self, "Update Position Error", f"Error updating window position: {e}")
