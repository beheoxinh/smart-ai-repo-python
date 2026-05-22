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

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QSlider, QWidgetAction,
    QWidget, QLabel, QHBoxLayout
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

        # ── opacity slider ────────────────────────────────────────────────
        opacity_widget = QWidget()
        opacity_layout = QHBoxLayout(opacity_widget)
        opacity_layout.setContentsMargins(10, 5, 10, 5)

        opacity_label = QLabel("Opacity:")
        opacity_layout.addWidget(opacity_label)

        opacity_slider = QSlider(Qt.Orientation.Horizontal)
        opacity_slider.setMinimum(10)
        opacity_slider.setMaximum(100)
        opacity_slider.setValue(50)
        opacity_slider.setFixedWidth(150)
        opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #ddd;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                border: 1px solid #005a9e;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #1e90ff;
            }
        """)
        opacity_slider.valueChanged.connect(btn.set_opacity)
        opacity_layout.addWidget(opacity_slider)

        opacity_action = QWidgetAction(tray_menu)
        opacity_action.setDefaultWidget(opacity_widget)
        tray_menu.addAction(opacity_action)

        # ── button size submenu ───────────────────────────────────────────
        size_menu = QMenu("Button Size", tray_menu)

        size_48 = QAction("Small (48px)")
        size_48.triggered.connect(lambda: btn.set_size(48))
        size_menu.addAction(size_48)

        size_64 = QAction("Medium (64px) ✓")
        size_64.triggered.connect(lambda: btn.set_size(64))
        size_menu.addAction(size_64)

        size_80 = QAction("Large (80px)")
        size_80.triggered.connect(lambda: btn.set_size(80))
        size_menu.addAction(size_80)

        size_96 = QAction("Extra Large (96px)")
        size_96.triggered.connect(lambda: btn.set_size(96))
        size_menu.addAction(size_96)

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
