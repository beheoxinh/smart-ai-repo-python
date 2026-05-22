# File: main.py
import os
import sys

# --- XWayland (XCB) override ---
# GNOME Mutter (Wayland compositor) controls window positioning absolutely.
# The application CANNOT set its own window position on native Wayland.
# XCB backend forces Qt to use XWayland, where X11 window management
# (move(), setGeometry()) works as the application intends.
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

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
import faulthandler

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from utils import AppPaths
from components.floating_button import FloatingButton

faulthandler.enable()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)


def show_critical_error(message):
    from PyQt6.QtWidgets import QMessageBox
    if not QApplication.instance():
        _ = QApplication(sys.argv)
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setText("Critical Application Error")
    msg.setInformativeText(str(message))
    msg.setWindowTitle("Error")
    msg.exec()


def main():
    try:
        app = QApplication(sys.argv)
        app.setDesktopFileName("smart-ai")
        paths = AppPaths()

        # ── tray icon ─────────────────────────────────────────────────────
        icon_path = paths.get_path('images', 'tray.svg')
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"Icon file not found: {icon_path}")
        icon = QIcon(icon_path)
        if icon.isNull():
            raise Exception("Failed to load icon")

        tray_icon = QSystemTrayIcon(icon, parent=app)
        tray_menu = QMenu()

        # ── floating button (creates its own window + lazy sidebar) ────────
        btn = FloatingButton(app)

        show_action = QAction("Show/Hide")
        show_action.triggered.connect(btn.toggle_sidebar)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit")
        quit_action.triggered.connect(app.quit)
        tray_menu.addAction(quit_action)

        tray_icon.setContextMenu(tray_menu)
        tray_icon.show()

        return app.exec()

    except Exception as e:
        error_msg = (
            f"A fatal error occurred during startup:\n\n{str(e)}"
        )
        logging.critical(error_msg, exc_info=True)
        show_critical_error(error_msg)
        return 1


if __name__ == '__main__':
    sys.exit(main())
