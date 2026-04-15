# File: components/web_view.py
import ctypes
import os
import sys
import traceback
from urllib.parse import urlparse
from uuid import UUID

from PyQt6.QtCore import QUrl, Qt, pyqtSignal, QStandardPaths, QTimer
from PyQt6.QtGui import QGuiApplication, QDesktopServices, QAction, QCursor
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestInfo,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMenu, QDialog, QVBoxLayout

from utils import AppPaths


class PopupWindow(QDialog):
    popupClosed = pyqtSignal()

    def __init__(self, profile):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        
        # Use a layout for QDialog
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.web_view = QWebEngineView(self)
        self.page = CustomWebEnginePage(profile, self)
        self.web_view.setPage(self.page)
        layout.addWidget(self.web_view)

        self.setWindowTitle("Loading...")
        self.setMinimumSize(800, 650)
        
        # Set flags to be a Tool window, like the sidebar, to ensure consistent window manager behavior
        self.setWindowFlags(
            Qt.WindowType.Tool | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        # Center the window on the active screen
        screen = QGuiApplication.screenAt(QCursor.pos())
        if not screen:
            screen = QGuiApplication.primaryScreen()
        
        screen_geo = screen.geometry()
        window_width = int(screen_geo.width() * 0.75)
        window_height = int(screen_geo.height() * 0.75)
        center_x = screen_geo.x() + (screen_geo.width() - window_width) // 2
        center_y = screen_geo.y() + (screen_geo.height() - window_height) // 2
        self.setGeometry(center_x, center_y, window_width, window_height)

        self.page.authFinished.connect(self.close)
        self.page.titleChanged.connect(self.setWindowTitle)

    def closeEvent(self, event):
        print("PopupWindow: Closing")
        self.popupClosed.emit()
        event.accept()


class CustomWebEnginePage(QWebEnginePage):
    popupCreated = pyqtSignal(object)
    authCallback = pyqtSignal(str)
    authFinished = pyqtSignal(str)

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self._profile = profile
        self.auth_in_progress = False
        self.current_url = None

        actions_to_hide = [
            QWebEnginePage.WebAction.Back,
            QWebEnginePage.WebAction.Forward,
            QWebEnginePage.WebAction.Reload,
            QWebEnginePage.WebAction.ViewSource,
            QWebEnginePage.WebAction.SavePage,
            QWebEnginePage.WebAction.InspectElement,
            QWebEnginePage.WebAction.OpenLinkInNewWindow,
            QWebEnginePage.WebAction.OpenLinkInNewTab,
            QWebEnginePage.WebAction.OpenLinkInNewBackgroundTab,
            QWebEnginePage.WebAction.DownloadLinkToDisk,
            QWebEnginePage.WebAction.DownloadMediaToDisk,
        ]
        for action in actions_to_hide:
            self.action(action).setVisible(False)

    def javaScriptCanAccessClipboard(self):
        return True

    def javaScriptConsoleMessage(self, level, message, line, sourceid):
        pass

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        url_str = url.toString()
        parsed_url = urlparse(url_str)

        if "claude.ai" in parsed_url.netloc and self.auth_in_progress:
            print("Auth completed, returning to app")
            self.auth_in_progress = False
            self.authFinished.emit(url_str)
            return True

        return super().acceptNavigationRequest(url, _type, isMainFrame)

    def createWindow(self, window_type):
        try:
            popup = PopupWindow(self._profile)
            popup.page.auth_in_progress = True
            popup.show()
            self.popupCreated.emit(popup)
            return popup.page
        except Exception as e:
            print(f"Error creating popup window: {e}")
            return None

    def createStandardContextMenu(self):
        try:
            custom_menu = QMenu(self.view())
            custom_menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

            hit_test_data = self.contextMenuData()
            link_url = hit_test_data.linkUrl()
            is_link_present = bool(link_url.url())
            is_image = hit_test_data.mediaType() == hit_test_data.MediaType.MediaTypeImage
            is_text_selected = bool(hit_test_data.selectedText())
            is_editable = hit_test_data.isContentEditable()

            if is_link_present:
                open_action = QAction("Open in default browser", custom_menu)
                open_action.triggered.connect(lambda: QDesktopServices.openUrl(link_url))
                custom_menu.addAction(open_action)
                if link_url.isValid():
                    custom_menu.addAction(self.action(QWebEnginePage.WebAction.CopyLinkToClipboard))
                custom_menu.addSeparator()

            if is_image:
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.CopyImageToClipboard))
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.CopyImageUrlToClipboard))
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.DownloadImageToDisk))
                custom_menu.addSeparator()

            if is_text_selected:
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.Copy))

            if is_editable:
                if not is_text_selected:
                    custom_menu.addAction(self.action(QWebEnginePage.WebAction.Copy))
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.Cut))
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.Paste))
                custom_menu.addSeparator()
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.SelectAll))

            if not custom_menu.actions() or (not is_link_present and not is_image and not is_text_selected and not is_editable):
                if custom_menu.actions():
                    custom_menu.addSeparator()
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.Reload))

            actions = custom_menu.actions()
            if actions and actions[-1].isSeparator():
                custom_menu.removeAction(actions[-1])

            return custom_menu if custom_menu.actions() else None
        except Exception as e:
            print(f"ERROR in createStandardContextMenu: {e}")
            traceback.print_exc()
            return QMenu(self.view())


class CustomWebView(QWebEngineView):
    popupCreated = pyqtSignal(object)
    popupClosed = pyqtSignal()
    webviewRedirectCompleted = pyqtSignal(str)
    clearCacheRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("customWebView")
        self.app_paths = AppPaths()
        self.active_popups = []
        self.loaded = False

        self.setStyleSheet("""
            #customWebView { background-color: white; }
            QMenu { background-color: #2C2C29; border: 1px solid transparent; border-radius: 5px; padding: 0; margin: 0; }
            QMenu::item { padding: 6px 25px 6px 15px; color: #c0c0c0; font-size: 13px; font-weight: 600; font-family: "Segoe UI", "Segoe UI Emoji", "Segoe UI Symbol"; background-color: transparent; }
            QMenu::item:selected { background-color: #333333; font-weight: 800; padding-left: 18px; }
            QMenu::separator { height: 1px; background-color: #4D4D4D; margin: 4px 0; }
            QMenu::item:disabled { color: #6d6d6d; }
        """)

        self.profile = QWebEngineProfile("secure_browser_profile", self)
        self.setup_profile()

        self.custom_page = CustomWebEnginePage(self.profile, self)
        self.setPage(self.custom_page)

        self.custom_page.urlChanged.connect(self.check_main_url_change)
        self.custom_page.urlChanged.connect(lambda url: self.save_last_url(url.toString()))
        self.custom_page.popupCreated.connect(self.add_popup_window)
        self.custom_page.authCallback.connect(self.handle_auth_callback)
        self.custom_page.loadFinished.connect(self.on_load_finished)
        self.custom_page.featurePermissionRequested.connect(self.on_feature_permission_requested)
        self.custom_page.renderProcessTerminated.connect(self.on_render_process_terminated)

        self.setup_settings()
        self.setMouseTracking(True)

    def on_render_process_terminated(self, termination_status, exit_code):
        status_str = str(termination_status)
        print(f"[CRITICAL] Render process terminated! Status: {status_str}, Exit Code: {exit_code}")
        if termination_status != QWebEnginePage.RenderProcessTerminationStatus.NormalTermination:
            print("Attempting to reload page after crash...")
            QTimer.singleShot(1000, self.reload)

    def on_feature_permission_requested(self, url, feature):
        QTimer.singleShot(0, lambda: self._grant_permission(url, feature))

    def _grant_permission(self, url, feature):
        try:
            self.custom_page.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
        except Exception as e:
            print(f"Error granting permission: {e}")

    def add_popup_window(self, popup_window_instance):
        self.active_popups.append(popup_window_instance)
        popup_window_instance.popupClosed.connect(lambda: self.remove_popup_window(popup_window_instance))
        self.popupCreated.emit(popup_window_instance)

    def remove_popup_window(self, popup_window_instance):
        if popup_window_instance in self.active_popups:
            self.active_popups.remove(popup_window_instance)
        self.popupClosed.emit()

    def clear_http_cache(self):
        try:
            self.page().profile().clearHttpCache()
            print("HTTP cache cleared (cookies preserved).")
        except Exception as e:
            print(f"Error clearing HTTP cache: {e}")

    def setup_profile(self):
        cache_path = self.app_paths.get_data_dir("cache")
        self.profile.setCachePath(cache_path)
        self.profile.setPersistentStoragePath(cache_path)
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        self.profile.downloadRequested.connect(self.handle_download_requested)
        self.profile.setSpellCheckEnabled(False) # Disabled spell checking
        self.profile.setSpellCheckLanguages(['en-US'])
        self.profile.setUrlRequestInterceptor(EnhancedBrowserInterceptor())

    def setup_settings(self):
        settings = self.settings()
        attributes_to_enable = [
            QWebEngineSettings.WebAttribute.JavascriptEnabled,
            QWebEngineSettings.WebAttribute.LocalStorageEnabled,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.AutoLoadImages,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.DnsPrefetchEnabled,
            QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly,
            QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled,
            QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript,
            QWebEngineSettings.WebAttribute.WebGLEnabled,
            QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled,
            QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled,
        ]
        for attr in attributes_to_enable:
            settings.setAttribute(attr, True)

        # CRITICAL FIX: Allow loading local HTTP content like Open WebUI.
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
        settings.setDefaultTextEncoding('UTF-8')

    def on_load_finished(self, ok):
        if ok:
            try:
                self.inject_chrome_compatibility_script()
            except Exception as e:
                print(f"Inject JS failed: {e}")
        else:
            print("Page load failed")
        for popup in list(self.active_popups):
            popup.close()

    def inject_chrome_compatibility_script(self):
        script = """
        (function() {
            'use strict';
            if ('webdriver' in navigator) {
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
            }
            window.chrome = window.chrome || {};
        })();
        """
        self.page().runJavaScript(script)

    def save_last_url(self, url):
        try:
            last_url_path = os.path.join(self.app_paths.get_data_dir(), 'lasturl')
            with open(last_url_path, "w", encoding="utf-8") as file:
                file.write(url)
        except Exception as e:
            print(f"Error saving URL: {e}")

    def load_last_url(self):
        try:
            last_url_path = os.path.join(self.app_paths.get_data_dir(), 'lasturl')
            if os.path.exists(last_url_path):
                with open(last_url_path, "r", encoding="utf-8") as file:
                    url = file.read().strip()
                    if url:
                        return url
        except Exception as e:
            print(f"Error loading URL: {e}")
        return "https://chatgpt.com/"

    def get_download_folder(self):
        path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if path:
            return path
        if sys.platform == "win32":
            try:
                FOLDERID_Downloads = UUID('{374DE290-123F-4565-9164-39C4925E467B}').bytes_le
                path_ptr = ctypes.c_wchar_p()
                ctypes.windll.shell32.SHGetKnownFolderPath(FOLDERID_Downloads, 0, None, ctypes.byref(path_ptr))
                return path_ptr.value
            except Exception:
                pass
        return os.path.join(os.path.expanduser("~"), "Downloads")

    def handle_download_requested(self, download_item):
        try:
            downloads_dir = self.get_download_folder()
            os.makedirs(downloads_dir, exist_ok=True)
            download_item.setDownloadDirectory(downloads_dir)
            download_item.accept()
        except Exception as e:
            print(f"Error handling download: {e}")

    def check_main_url_change(self, url):
        self.webviewRedirectCompleted.emit(url.toString().lower())

    def handle_auth_callback(self, callback_url):
        self.webviewRedirectCompleted.emit(callback_url)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded:
            try:
                last_url = self.load_last_url()
                if last_url:
                    self.setUrl(QUrl(last_url))
                self.loaded = True
            except Exception as e:
                print(f"Error loading initial URL: {e}")

    def enterEvent(self, event):
        self.setFocus()
        super().enterEvent(event)


class EnhancedBrowserInterceptor(QWebEngineUrlRequestInterceptor):
    """
    A more intelligent interceptor that only modifies the initial main frame request
    to look like a standard browser, and leaves all other requests (e.g., API calls,
    data streams, images) untouched to ensure stability and performance.
    """
    def interceptRequest(self, info):
        try:
            # Only modify the main frame request to set the User-Agent and initial headers.
            if info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame:
                info.setHttpHeader(b"User-Agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
                info.setHttpHeader(b"Accept-Language", b"en-US,en;q=0.9,vi;q=0.8")
                info.setHttpHeader(b"Accept", b"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
            
            # For all other request types (like XHR, Fetch, scripts, images), we do not
            # interfere. This is critical for stable streaming of AI responses.
        except Exception as e:
            print(f"Interceptor error: {e}")