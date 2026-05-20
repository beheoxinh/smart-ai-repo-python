# File: main.py
import os
import sys

# --- Platform Detection & Early Setup ---
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    # GNOME Wayland (Mutter) không cho phép ứng dụng tự do đặt vị trí cửa sổ (absolute positioning).
    # Để sidebar có thể neo sát mép phải màn hình, chúng ta buộc Qt phải sử dụng XWayland (backend 'xcb')
    # thay vì native 'wayland'.
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# --- Stable Chromium Flags ---
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox "
    # Performance & Stability
    "--enable-gpu-rasterization "
    "--ignore-gpu-blocklist "
    # Feature Reduction for Simplicity
    "--disable-component-update "
    "--disable-domain-reliability "
    "--disable-features=InterestCohort,RenderDocument,AudioServiceOutOfProcess "
    "--disable-sync "
    "--disable-translate "
    "--disable-breakpad "
    "--disable-dev-shm-usage "
)

import logging
from PyQt6.QtGui import QAction, QIcon, QActionGroup
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from utils import AppPaths
from sidebar import Sidebar
import traceback
import faulthandler

faulthandler.enable()

# Cấu hình logging
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stdout)


# --- Centralized Error Handling ---
def show_critical_error(message):
    """A simple, dependency-free error popup for critical failures."""
    from PyQt6.QtWidgets import QMessageBox, QApplication
    if not QApplication.instance():
        _ = QApplication(sys.argv)
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setText("Critical Application Error")
    msg_box.setInformativeText(str(message))
    msg_box.setWindowTitle("Error")
    msg_box.exec()


def main():
    try:
        app = QApplication(sys.argv)

        # Sửa lỗi: Bỏ ".desktop" ở cuối tên file
        app.setDesktopFileName("smart-ai")

        paths = AppPaths()

        icon_path = paths.get_path('images', 'tray.svg')
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"Icon file not found: {icon_path}")

        icon = QIcon(icon_path)
        if icon.isNull():
            raise Exception("Failed to load icon, it might be corrupted.")

        tray_icon = QSystemTrayIcon(icon, parent=app)
        tray_menu = QMenu()

        try:
            sidebar = Sidebar()
        except Exception as e:
            error_info = f"Failed to create the main window (Sidebar).\n\nError: {e}\n\nTraceback:\n{traceback.format_exc()}"
            logging.error(error_info)
            raise RuntimeError(error_info) from e

        # --- Screen Selection Menu ---
        screen_menu = tray_menu.addMenu("Display Screen")
        screen_group = QActionGroup(screen_menu)

        def refresh_screen_menu():
            screen_menu.clear()

            # Auto (Rightmost) option
            auto_action = QAction("Auto (Rightmost)", screen_menu, checkable=True)
            auto_action.setChecked(sidebar.manual_screen_index == -1)
            auto_action.triggered.connect(lambda: sidebar.set_manual_screen(-1))
            screen_menu.addAction(auto_action)
            screen_group.addAction(auto_action)

            screen_menu.addSeparator()

            # Individual screens
            screens = QApplication.screens()
            for i, screen in enumerate(screens):
                screen_name = f"Screen {i + 1}: {screen.name()} ({screen.geometry().width()}x{screen.geometry().height()})"
                action = QAction(screen_name, screen_menu, checkable=True)
                action.setChecked(sidebar.manual_screen_index == i)
                # Sử dụng lambda với capture giá trị hiện tại của i
                action.triggered.connect(lambda checked, idx=i: sidebar.set_manual_screen(idx))
                screen_menu.addAction(action)
                screen_group.addAction(action)

        refresh_screen_menu()

        # Cập nhật menu khi cắm/rút màn hình
        app.screenAdded.connect(lambda _: refresh_screen_menu())
        app.screenRemoved.connect(lambda _: refresh_screen_menu())

        show_action = QAction("Show")
        show_action.triggered.connect(sidebar.show_sidebar)
        tray_menu.addAction(show_action)

        exit_action = QAction("Quit")
        exit_action.triggered.connect(app.quit)
        tray_menu.addAction(exit_action)

        tray_icon.setContextMenu(tray_menu)
        tray_icon.show()

        return app.exec()

    except Exception as e:
        error_message = f"A fatal error occurred during application startup:\n\n{str(e)}"
        logging.critical(error_message, exc_info=True)
        show_critical_error(error_message)
        return 1


if __name__ == '__main__':
    sys.exit(main())
