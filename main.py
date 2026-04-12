# File: main.py
import os
import sys

# --- Platform Detection & Early Setup ---
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "wayland"

# --- Stable Chromium Flags ---
# These flags are chosen for broad compatibility and stability, avoiding experimental features
# that can cause rendering issues on some systems.
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox "
    # Performance & Stability
    "--enable-gpu-rasterization "
    "--ignore-gpu-blocklist "
    # Resource Management
    # "--disable-background-networking "
    # "--disable-background-timer-throttling "
    # "--disable-renderer-backgrounding "
    # Feature Reduction for Simplicity
    "--disable-component-update "
    "--disable-domain-reliability "
    "--disable-features=InterestCohort,RenderDocument,AudioServiceOutOfProcess "
    "--disable-sync "
    "--disable-translate "
    "--disable-breakpad "
    "--disable-dev-shm-usage "
)

# Commented out to allow error messages to be seen during debugging
# if sys.stderr is None:
#     sys.stderr = open(os.devnull, 'w')
# if sys.stdout is None:
#     sys.stdout = open(os.devnull, 'w')

import logging
from PyQt6.QtGui import QAction, QIcon
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
    # Ensure an app instance exists for the popup
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
        
        # Set the desktop file name for better integration with desktop environments (e.g., for location services)
        app.setDesktopFileName("smart-ai.desktop")

        paths = AppPaths()

        icon_path = paths.get_path('images', 'tray.svg')
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"Icon file not found: {icon_path}")

        icon = QIcon(icon_path)
        if icon.isNull():
            raise Exception("Failed to load icon, it might be corrupted.")

        tray_icon = QSystemTrayIcon(icon, parent=app)
        tray_menu = QMenu()

        # This is where the error occurs, so we wrap it
        try:
            sidebar = Sidebar()
        except Exception as e:
            # This provides a more specific error message
            error_info = f"Failed to create the main window (Sidebar).\n\nError: {e}\n\nTraceback:\n{traceback.format_exc()}"
            logging.error(error_info)
            raise RuntimeError(error_info) from e

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
        # This is the ultimate catch-all for any error during startup
        error_message = f"A fatal error occurred during application startup:\n\n{str(e)}"
        logging.critical(error_message, exc_info=True)
        show_critical_error(error_message)
        return 1

if __name__ == '__main__':
    sys.exit(main())
