import os
import sys

# --- Stable Chromium Flags (before any Qt import) ---
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
from PyQt6.QtGui import QAction, QIcon, QActionGroup
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from utils import AppPaths
from components.floating_button import FloatingButton
import faulthandler

faulthandler.enable()

log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stdout)


# --- Error handler ---
def show_critical_error(message):
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
        app.setDesktopFileName("smart-ai")

        paths = AppPaths()
        icon_path = paths.get_path('images', 'tray.svg')
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"Icon file not found: {icon_path}")

        icon = QIcon(icon_path)
        if icon.isNull():
            raise Exception("Failed to load icon.")

        # ── Entry: Floating AI Button ──────────────────────
        # Creates the sidebar internally on first click.
        floating_btn = FloatingButton(app)

        # ── System tray (secondary) ────────────────────────
        tray_icon = QSystemTrayIcon(icon, parent=app)
        tray_menu = QMenu()

        show_action = QAction("Show / Hide Sidebar")
        show_action.triggered.connect(lambda *a: (floating_btn._update_target_screen(), floating_btn.sidebar.toggle_sidebar()))
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        screen_menu = tray_menu.addMenu("Display Screen")

        def refresh_screen_menu():
            screen_menu.clear()
            screen_group = QActionGroup(screen_menu)

            auto_action = QAction("Auto (Rightmost)", screen_menu, checkable=True)
            auto_action.setChecked(
                floating_btn._sidebar is None
                or floating_btn._sidebar.manual_screen_index == -1
            )
            auto_action.triggered.connect(
                lambda: floating_btn._sidebar
                        and floating_btn._sidebar.set_manual_screen(-1)
            )
            screen_menu.addAction(auto_action)
            screen_group.addAction(auto_action)
            screen_menu.addSeparator()

            for i, screen in enumerate(QApplication.screens()):
                screen_name = (
                    f"Screen {i + 1}: {screen.name()}"
                    f" ({screen.geometry().width()}x{screen.geometry().height()})"
                )
                action = QAction(screen_name, screen_menu, checkable=True)
                action.setChecked(
                    floating_btn._sidebar is not None
                    and floating_btn._sidebar.manual_screen_index == i
                )
                action.triggered.connect(
                    lambda checked, idx=i: floating_btn._sidebar
                                           and floating_btn._sidebar.set_manual_screen(idx)
                )
                screen_menu.addAction(action)
                screen_group.addAction(action)

        refresh_screen_menu()
        app.screenAdded.connect(lambda _: refresh_screen_menu())
        app.screenRemoved.connect(lambda _: refresh_screen_menu())

        tray_menu.addSeparator()
        exit_action = QAction("Quit")
        exit_action.triggered.connect(app.quit)
        tray_menu.addAction(exit_action)

        tray_icon.setContextMenu(tray_menu)
        tray_icon.show()

        return app.exec()

    except Exception as e:
        error_message = f"A fatal error occurred during startup:\n\n{str(e)}"
        logging.critical(error_message, exc_info=True)
        show_critical_error(error_message)
        return 1


if __name__ == '__main__':
    sys.exit(main())
