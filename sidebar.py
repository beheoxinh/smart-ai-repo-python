# File: sidebar.py
import win32gui
import win32api
from PyQt6.QtCore import Qt, QTimer, QPoint, QEvent, QPropertyAnimation, QUrl
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication
from PyQt6.QtGui import QCursor, QShortcut, QKeySequence

from components.title_bar import TitleBar
from components.resize_handle import ResizeHandle
from components.content_widget import ContentWidget

class Sidebar(QMainWindow):
    def __init__(self):
        super().__init__()

        self.DEFAULT_WIDTH_RATIO = 0.55
        self.dialog_open = False
        self.setWindowTitle("sidebar")
        self.is_visible = False
        self.active_screen = None
        self.is_resizing = False
        self.has_active_popup = False
        self.popup_windows = []
        self.last_width = None  # Store the last manually resized width
        self.init_ui()
        self.setup_shortcut()

    def setup_shortcut(self):
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        shortcut.activated.connect(self.toggle_sidebar)

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        # QApplication.instance().installEventFilter(self)
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

        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)

        self.content_widget = ContentWidget()
        main_layout.addWidget(self.content_widget)

        self.content_widget.web_view.popupCreated.connect(self.handle_popup_created)
        self.content_widget.web_view.webviewRedirectCompleted.connect(self.handle_webview_redirect_completed)
        self.content_widget.nav_bar.navigationClicked.connect(self.handle_navigation)

        container_layout.addWidget(main_widget)

        self.setCentralWidget(container)

        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            self.setFixedWidth(int(primary_screen.geometry().width() * self.DEFAULT_WIDTH_RATIO))

        # Xác định màn hình ngoài cùng bên phải
        self.rightmost_screen = max(QApplication.screens(), key=lambda s: s.geometry().x() + s.geometry().width())

        self.mouse_timer = QTimer()
        self.mouse_timer.timeout.connect(self.check_mouse)
        self.mouse_timer.start(200)

        self.previous_state = win32api.GetKeyState(0x01)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #33322F;
            }
        """)

        self.hide()

    def handle_navigation(self, url):
        self.content_widget.web_view.setUrl(QUrl(url))
        self.content_widget.web_view.save_last_url(url)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if self.dialog_open:
                return False

            pos = event.globalPosition().toPoint()
            clicked_widget = QApplication.instance().widgetAt(pos)

            if clicked_widget:
                win = clicked_widget.window()
                if getattr(win, '__menu_setting_dialog__', False):
                    return False

            if clicked_widget and self.isAncestorOf(clicked_widget):
                return False

            if self.is_visible:
                print(f"Clicked outside Sidebar and popups at {pos}. Scheduling hide...")
                QTimer.singleShot(100, self.hide_sidebar_properly)
                return False

        return super().eventFilter(obj, event)

    def hide_sidebar_properly(self):
        if self.is_visible:
            self.hide_sidebar()

    def handle_popup_created(self, popup_window):
        print("Sidebar: Popup created")
        self.popup_windows.append(popup_window)  # Lưu đúng PopupWindow
        self.has_active_popup = True
        self.mouse_timer.stop()
        popup_window.popupClosed.connect(lambda: self.handle_popup_closed(popup_window))

    def handle_popup_closed(self, popup=None):
        print("Sidebar: Popup closed")
        if popup in self.popup_windows:
            self.popup_windows.remove(popup)

        if not self.popup_windows:
            self.has_active_popup = False
            self.mouse_timer.start(100)  # Restart the mouse timer
            # Removed gc.collect() as it's generally not needed and can cause performance issues

    def handle_webview_redirect_completed(self, callback_url):
        print(f"[Sidebar] Received webviewRedirectCompleted with URL: {callback_url}")

        for popup in self.popup_windows[:]:
            if popup:
                print(f"[Sidebar] Closing popup: {popup}")
                popup.close()

        self.popup_windows.clear()
        self.has_active_popup = False
        self.mouse_timer.start(100)

    def is_fullscreen_on_screen(self, screen):
        """Kiểm tra xem màn hình có ứng dụng toàn màn hình hay không."""

        def enum_windows_callback(hwnd, result):
            if not win32gui.IsWindowVisible(hwnd):
                return
            rect = win32gui.GetWindowRect(hwnd)
            screen_geometry = screen.geometry()
            if rect[0] == screen_geometry.left() and rect[1] == screen_geometry.top() and \
                    rect[2] == screen_geometry.right() and rect[3] == screen_geometry.bottom():
                result.append(hwnd)

        result = []
        win32gui.EnumWindows(enum_windows_callback, result)
        return len(result) > 0

    def check_mouse(self):
        try:
            if self.is_resizing or self.has_active_popup:
                return

            cursor_pos = win32gui.GetCursorPos()
            cursor_point = QPoint(cursor_pos[0], cursor_pos[1])
            screen = self.get_screen_at_cursor()

            if not screen or screen != self.rightmost_screen:
                return

            screen_geometry = self.rightmost_screen.geometry()

            is_near_edge = (cursor_pos[0] >= screen_geometry.x() + screen_geometry.width() - 5 and
                            cursor_pos[0] <= screen_geometry.x() + screen_geometry.width())

            if not self.is_visible:
                # Sidebar ẩn: chỉ cần kiểm tra dí mép màn hình
                if is_near_edge:
                    # Added fullscreen check here
                    if self.is_fullscreen_on_screen(screen):
                        return  # Don't show sidebar if a fullscreen app is active

                    self.active_screen = screen
                    if not self.is_resizing:
                        self.setFixedWidth(self.last_width or int(screen.geometry().width() * self.DEFAULT_WIDTH_RATIO))
                    self.update_position()
                    self.show_sidebar()
                    self.is_visible = True
                return

            # Nếu sidebar đang hiện thì kiểm tra click ra ngoài để ẩn
            if not self.geometry().contains(cursor_point):
                left_state = win32api.GetKeyState(0x01)  # Left Mouse
                right_state = win32api.GetKeyState(0x02)  # Right Mouse
                middle_state = win32api.GetKeyState(0x04)  # Middle Mouse

                if left_state < 0 or right_state < 0 or middle_state < 0:
                    print("Detected mouse click outside Sidebar. Hiding sidebar.")
                    self.hide_sidebar()
                    self.is_visible = False

        except Exception as e:
            print(f"Error in check_mouse: {e}")

    # Removed _delayed_hide as it was not used

    def toggle_sidebar(self):
        if self.is_visible:
            self.hide_sidebar()
        else:
            self.show_sidebar()

    def show_sidebar(self):
        screen = self.get_screen_at_cursor()
        if screen:
            self.active_screen = screen
            if not self.is_resizing:
                self.setFixedWidth(self.last_width or int(screen.geometry().width() * self.DEFAULT_WIDTH_RATIO))
            self.update_position()

            self.setWindowOpacity(0.0)  # Reset opacity trước khi show
            self.show()

            self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
            self.fade_animation.setDuration(150)  # ms
            self.fade_animation.setStartValue(0.0)
            self.fade_animation.setEndValue(1.0)
            self.fade_animation.start()

            self.is_visible = True

    def hide_sidebar(self):
        # CRASH FIX: Prevent hide animation during resize at all costs.
        if self.is_resizing or not self.isVisible():
            return

        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(350)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)

        def after_hide():
            self.hide()
            self.is_visible = False

        self.fade_animation.finished.connect(after_hide)
        self.fade_animation.start()

    def closeEvent(self, event):
        if self.parent:
            self.parent.popupClosed.emit()
        self.popupClosed.emit()
        self.content_widget.web_view.deleteLater()  # Giải phóng WebView manually
        event.accept()

    def get_current_screen_width(self):
        if self.active_screen:
            return self.active_screen.geometry().width()
        return QApplication.primaryScreen().geometry().width()

    def resizing_started(self):
        self.is_resizing = True

    def resizing_finished(self):
        self.is_resizing = False
        self.last_width = self.width()  # Save the last manually resized width

    def get_screen_at_cursor(self):
        cursor_pos = QCursor.pos()
        for screen in QApplication.screens():
            if screen.geometry().contains(cursor_pos):
                return screen
        return None

    def update_position(self):
        if not self.active_screen:
            return

        screen_geometry = self.active_screen.geometry()
        taskbar_height = self.get_taskbar_height()

        self.setGeometry(
            screen_geometry.x() + screen_geometry.width() - self.width(),
            screen_geometry.y(),
            self.width(),
            screen_geometry.height() - taskbar_height
        )

    def get_taskbar_height(self):
        taskbar = win32gui.FindWindow('Shell_TrayWnd', None)
        if taskbar:
            rect = win32gui.GetWindowRect(taskbar)
            return rect[3] - rect[1]
        return 0

    def moveEvent(self, event):
        if self.active_screen:
            self.update_position()

    def mousePressEvent(self, event):
        QTimer.singleShot(200, self.check_should_hide)
        super().mousePressEvent(event)

    def check_should_hide(self):
        if self.dialog_open:
            print("[DEBUG] Dialog is open, skip auto-hide")
            return
        cursor = QCursor.pos()
        clicked_widget = QApplication.instance().widgetAt(cursor)

        if not clicked_widget or not self.isAncestorOf(clicked_widget):
            print("Auto-hiding Sidebar due to click outside.")
            self.hide_sidebar()

    def dialog_open_set_false(self):
        self.dialog_open = False
        print("[DEBUG] Menu dialog closed, dialog_open = False")