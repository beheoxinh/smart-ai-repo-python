# File: main.py
import os
import sys

# --- Stable Chromium Flags ---
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox "
    "--enable-gpu-rasterization "
    "--ignore-gpu-blocklist "
    "--disable-component-update "
    "--disable-domain-reliability "
    "--disable-features=InterestCohort,RenderDocument,AudioServiceOutOfProcess "
    "--disable-sync "
    "--disable-translate "
    "--disable-breakpad "
    "--disable-dev-shm-usage "
)

import logging

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from utils import AppPaths
from components.floating_button import FloatingButton
import faulthandler

faulthandler.enable()

log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stdout)


def show_critical_error(message):
    """A simple, dependency-free error popup for critical failures."""
    from PyQt6.QtWidgets import QMessageBox
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
        app.setDesktopFileName("smart-ai")

        paths = AppPaths()
        icon_path = paths.get_path('images', 'tray.svg')
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"Icon file not found: {icon_path}")

        icon = QIcon(icon_path)
        if icon.isNull():
            raise Exception("Failed to load icon, it might be corrupted.")

        # ── Entry point: floating button owns the sidebar internally ──
        floating_btn = FloatingButton(app)

        # ── System tray ──────────────────────────────────────────────
        tray_icon = QSystemTrayIcon(icon, parent=app)
        tray_menu = QMenu()

        show_action = QAction("Show / Hide Sidebar")
        show_action.triggered.connect(floating_btn._toggle_sidebar)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

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
