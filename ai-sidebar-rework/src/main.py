"""
main.py — AI Sidebar Daemon (entry point).

Architecture (hybrid GNOME Extension + Python daemon):

  GNOME Shell Extension (cursor hot-zone)        Python side (this file)
  ┌──────────────────────────────┐               ┌────────────────────┐
  │  cursor-moved → detect       │  D-Bus call   │  SidebarService    │
  │  right-edge hot-zone         │ ──────────►   │  ShowOnScreen(i)   │
  │                              │               │  Hide()            │
  │  listens to signals          │ ◄──────────── │  StateChanged      │
  │  from daemon                 │  D-Bus signal │  WidthChanged      │
  └──────────────────────────────┘               │  PopupState        │
                                                 │                    │
                          QApplication + QWebEngineView (XWayland)
                          (WebView, NavBar, Menus, Resize, Gesture...)

Environment:
  QT_QPA_PLATFORM=xcb  — forced below so move()/setGeometry() work.
  The GNOME extension provides the screen index; we handle the UI.

Fallback mode (no GNOME extension):
  If the extension is absent, the tray- icon "Display Screen" submenu
  provides manual override, and auto-detection (rightmost) works as before.
"""

import os
import sys

# ── Platform: force XWayland so we can position the window ────────────
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# ── Stable Chromium flags ─────────────────────────────────────────────
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
import traceback

import faulthandler

faulthandler.enable()

from PyQt6.QtGui import QAction, QIcon, QActionGroup
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QTimer

from utils import AppPaths
from sidebar import Sidebar

# ── Logging ────────────────────────────────────────────────────────────
log_fmt = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_fmt, stream=sys.stdout)

# ── D-Bus availability check ──────────────────────────────────────────
HAS_DBUS = False
try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    import threading as _threading

    HAS_DBUS = True
except ImportError:
    logging.warning(
        "python3-dbus / PyGObject not available. "
        "GNOME Shell extension integration disabled."
    )


# ═══════════════════════════════════════════════════════════════════════
# D-Bus Service (runs in a background thread with its own GLib loop)
# ═══════════════════════════════════════════════════════════════════════

class SidebarService:
    """Exposes the sidebar over the session D-Bus so the GNOME Shell
    extension can show/hide/query it."""

    if HAS_DBUS:

        class _SidebarAdaptor(dbus.service.Object):
            def __init__(self, bus, path, sidebar_ref):
                self._sidebar_ref = sidebar_ref
                super().__init__(bus, path)

            # ── Methods called BY the extension ───────────────────────

            @dbus.service.method(
                "com.smartai.Sidebar", in_signature="i", out_signature=""
            )
            def ShowOnScreen(self, screen_index):
                sidebar = self._sidebar_ref()
                if sidebar:
                    QTimer.singleShot(0, lambda: sidebar.show_on_screen(screen_index))

            @dbus.service.method(
                "com.smartai.Sidebar", in_signature="", out_signature=""
            )
            def Hide(self):
                sidebar = self._sidebar_ref()
                if sidebar:
                    QTimer.singleShot(0, lambda: sidebar.hide_sidebar(reason="dbus"))

            @dbus.service.method(
                "com.smartai.Sidebar", in_signature="", out_signature=""
            )
            def Toggle(self):
                sidebar = self._sidebar_ref()
                if sidebar:
                    QTimer.singleShot(0, lambda: sidebar.toggle_sidebar())

            @dbus.service.method(
                "com.smartai.Sidebar", in_signature="", out_signature="b"
            )
            def IsVisible(self):
                sidebar = self._sidebar_ref()
                return sidebar.is_visible if sidebar else False

            @dbus.service.method(
                "com.smartai.Sidebar", in_signature="", out_signature=""
            )
            def Ping(self):
                pass

            # ── Signals emitted TO the extension ──────────────────────

            @dbus.service.signal("com.smartai.Sidebar", signature="b")
            def StateChanged(self, visible):
                pass

            @dbus.service.signal("com.smartai.Sidebar", signature="i")
            def WidthChanged(self, width):
                pass

            @dbus.service.signal("com.smartai.Sidebar", signature="b")
            def PopupState(self, open):
                pass

    # ───────────────────────────────────────────────────────────────────

    def __init__(self, sidebar):
        self._sidebar = sidebar
        self._thread = None
        self._adaptor = None

        if not HAS_DBUS:
            logging.info("D-Bus disabled — running in standalone mode")
            return

        self._thread = _threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """GLib main-loop in a background thread."""
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        loop = GLib.MainLoop()

        try:
            bus = dbus.SessionBus()
            bus.request_name("com.smartai.Sidebar")
            self._adaptor = self._SidebarAdaptor(
                bus, "/com/smartai/Sidebar", lambda: self._sidebar
            )
            logging.info("D-Bus service registered: com.smartai.Sidebar")
            loop.run()
        except Exception as e:
            logging.error(f"D-Bus service thread failed: {e}")

    def emit_state_changed(self, visible):
        if self._adaptor:
            self._adaptor.StateChanged(visible)

    def emit_width_changed(self, width):
        if self._adaptor:
            self._adaptor.WidthChanged(width)

    def emit_popup_state(self, open):
        if self._adaptor:
            self._adaptor.PopupState(open)


# ═══════════════════════════════════════════════════════════════════════
# Error popup helper
# ═══════════════════════════════════════════════════════════════════════

def show_critical_error(message):
    from PyQt6.QtWidgets import QMessageBox

    if not QApplication.instance():
        _ = QApplication(sys.argv)
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setText("Critical Application Error")
    box.setInformativeText(str(message))
    box.setWindowTitle("Error")
    box.exec()


# ═══════════════════════════════════════════════════════════════════════
# Application entry
# ═══════════════════════════════════════════════════════════════════════

def main():
    try:
        app = QApplication(sys.argv)
        app.setDesktopFileName("smart-ai")

        paths = AppPaths()

        # ── Icon ───────────────────────────────────────────────────────
        icon_path = paths.get_path("images", "tray.svg")
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"Icon not found: {icon_path}")
        icon = QIcon(icon_path)
        if icon.isNull():
            raise Exception("Failed to load icon")

        # ── Tray ───────────────────────────────────────────────────────
        tray_icon = QSystemTrayIcon(icon, parent=app)
        tray_menu = QMenu()

        # ── Sidebar ────────────────────────────────────────────────────
        try:
            sidebar = Sidebar()
        except Exception as e:
            raise RuntimeError(
                f"Failed to create Sidebar.\nError: {e}\n{traceback.format_exc()}"
            ) from e

        # ── D-Bus service ──────────────────────────────────────────────
        dbus_svc = SidebarService(sidebar)

        # Wire sidebar signals → D-Bus
        def on_state(visible):
            dbus_svc.emit_state_changed(visible)

        def on_width(w):
            dbus_svc.emit_width_changed(w)

        def on_popup(open):
            dbus_svc.emit_popup_state(open)

        sidebar.stateChanged.connect(on_state)
        sidebar.widthChanged.connect(on_width)
        sidebar.popupStateChanged.connect(on_popup)

        # ── Tray: Display Screen submenu ───────────────────────────────
        screen_menu = tray_menu.addMenu("Display Screen")

        def refresh_screen_menu():
            screen_menu.clear()
            group = QActionGroup(screen_menu)

            auto_act = QAction("Auto (Rightmost)", screen_menu, checkable=True)
            auto_act.setChecked(sidebar.manual_screen_index == -1)
            auto_act.triggered.connect(lambda: sidebar.set_manual_screen(-1))
            screen_menu.addAction(auto_act)
            group.addAction(auto_act)
            screen_menu.addSeparator()

            for i, sc in enumerate(QApplication.screens()):
                name = (
                    f"Screen {i + 1}: {sc.name()} "
                    f"({sc.geometry().width()}x{sc.geometry().height()})"
                )
                act = QAction(name, screen_menu, checkable=True)
                act.setChecked(sidebar.manual_screen_index == i)
                act.triggered.connect(lambda checked, idx=i: sidebar.set_manual_screen(idx))
                screen_menu.addAction(act)
                group.addAction(act)

        refresh_screen_menu()
        app.screenAdded.connect(lambda _: refresh_screen_menu())
        app.screenRemoved.connect(lambda _: refresh_screen_menu())

        # ── Tray: Show / Quit ──────────────────────────────────────────
        show_act = QAction("Show")
        show_act.triggered.connect(sidebar.show_sidebar)
        tray_menu.addAction(show_act)

        quit_act = QAction("Quit")
        quit_act.triggered.connect(app.quit)
        tray_menu.addAction(quit_act)

        tray_icon.setContextMenu(tray_menu)
        tray_icon.show()

        logging.info("AI Sidebar daemon started")
        return app.exec()

    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        show_critical_error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
