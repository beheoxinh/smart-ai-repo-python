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
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)

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
        app.aboutToQuit.connect(btn._save_position)

        # ── manual refresh button ───────────────────────────────────────────
        refresh_action = QAction("Refresh")
        refresh_action.triggered.connect(btn.refresh_button)
        tray_menu.addAction(refresh_action)

        tray_menu.addSeparator()

        show_action = QAction("Hide Float Button")

        def update_show_action_text():
            if btn.isVisible():
                show_action.setText("Hide Float Button")
            else:
                show_action.setText("Show Float Button")

        def toggle_and_update():
            btn.toggle_button()
            update_show_action_text()

        show_action.triggered.connect(toggle_and_update)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        # ── opacity submenu ───────────────────────────────────────────────
        opacity_menu = QMenu("Opacity", tray_menu)

        for value in [20, 40, 60, 80, 100]:
            action = QAction(f"{value}%", tray_menu)
            action.setCheckable(True)
            action.triggered.connect((lambda v: lambda: btn.set_opacity(v))(value))
            opacity_menu.addAction(action)

        def update_opacity_checks():
            current = btn.get_opacity()
            for action in opacity_menu.actions():
                text = action.text().rstrip("%")
                value = int(text)
                action.setChecked(abs(current - value) < 5)

        opacity_menu.aboutToShow.connect(update_opacity_checks)

        tray_menu.addMenu(opacity_menu)

        # ── button size submenu ───────────────────────────────────────────
        size_menu = QMenu("Button Size", tray_menu)

        for size, label in [(48, "Small"), (64, "Medium"), (80, "Large"), (96, "Extra Large")]:
            action = QAction(f"{label} ({size}px)", tray_menu)
            action.setCheckable(True)
            action.triggered.connect((lambda s: lambda: btn.set_size(s))(size))
            size_menu.addAction(action)

        def update_size_checks():
            current = btn.get_size()
            for action in size_menu.actions():
                # Extract size from "Label (XXpx)" format
                text = action.text()
                size = int(text.split("(")[1].split("px")[0])
                action.setChecked(current == size)

        size_menu.aboutToShow.connect(update_size_checks)

        tray_menu.addMenu(size_menu)

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
