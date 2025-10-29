# File: components/web_view.py
import ctypes
import os
import subprocess
import sys
import traceback
from urllib.parse import urlparse
from uuid import UUID

from PyQt6.QtCore import QUrl, Qt, pyqtSignal, QTimer, QPropertyAnimation
from PyQt6.QtGui import QGuiApplication, QClipboard, QPainter, QColor, QDesktopServices, QAction
from PyQt6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
                                   QWebEngineSettings, QWebEngineUrlRequestInterceptor, QWebEngineDownloadRequest)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow, QLabel, QApplication, QMenu

from utils import AppPaths, alert_popup

class PopupWindow(QMainWindow):
    popupClosed = pyqtSignal()

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.parent = parent

        self.web_view = QWebEngineView(self)
        self.page = CustomWebEnginePage(profile, self)
        self.web_view.setPage(self.page)
        self.setCentralWidget(self.web_view)
        self.setWindowTitle("Loading...")
        self.setMinimumSize(800, 650)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        screen = QGuiApplication.primaryScreen().geometry()
        window_width = int(screen.width() * 0.75)
        window_height = int(screen.height() * 0.75)
        center_x = screen.x() + (screen.width() - window_width) // 2
        center_y = screen.y() + (screen.height() - window_height) // 2
        self.setGeometry(center_x, center_y, window_width, window_height)

        self.page.authFinished.connect(self.close)
        self.page.titleChanged.connect(self.setWindowTitle)

    def closeEvent(self, event):
        print("PopupWindow: Closing")
        if self.parent:
            self.parent.popupClosed.emit()
        self.popupClosed.emit()
        event.accept()


class CustomWebEnginePage(QWebEnginePage):
    popupCreated = pyqtSignal(object)
    authCallback = pyqtSignal(str)
    authFinished = pyqtSignal(str)

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self._profile = profile
        self.parent = parent # This parent is CustomWebView
        self.auth_in_progress = False
        self.current_url = None

        # Override các actions mặc định để vô hiệu hóa chúng
        self.action(QWebEnginePage.WebAction.Back).setVisible(False)
        self.action(QWebEnginePage.WebAction.Forward).setVisible(False)
        self.action(QWebEnginePage.WebAction.Reload).setVisible(False)
        self.action(QWebEnginePage.WebAction.ViewSource).setVisible(False)
        self.action(QWebEnginePage.WebAction.SavePage).setVisible(False)
        # self.action(QWebEnginePage.WebAction.SelectAll).setVisible(False) # Keep SelectAll for editable content
        self.action(QWebEnginePage.WebAction.InspectElement).setVisible(False)
        self.action(QWebEnginePage.WebAction.DownloadLinkToDisk).setVisible(False)
        self.action(QWebEnginePage.WebAction.DownloadImageToDisk).setVisible(False)
        self.action(QWebEnginePage.WebAction.DownloadMediaToDisk).setVisible(False)
        self.action(QWebEnginePage.WebAction.OpenLinkInNewWindow).setVisible(False) # Ensure this is hidden
        self.action(QWebEnginePage.WebAction.OpenLinkInNewTab).setVisible(False)
        self.action(QWebEnginePage.WebAction.OpenLinkInNewBackgroundTab).setVisible(False)

    def javaScriptCanAccessClipboard(self):
        return True

    def javaScriptConsoleMessage(self, level, message, line, sourceid):
        print(f"JS [{level}] {message} (line {line})")

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        url_str = url.toString()
        parsed_url = urlparse(url_str)

        if "claude.ai" in parsed_url.netloc:
            if self.auth_in_progress:
                print("Auth completed, returning to app")
                self.auth_in_progress = False
                self.authFinished.emit(url_str)
                return True
        return True

    def createWindow(self, window_type):
        try:
            popup = PopupWindow(self._profile, self.parent)
            popup.show()
            self.popupCreated.emit(popup)
            return popup.page
        except Exception as e:
            print(f"Error creating popup window: {e}")
            return None

    def createStandardContextMenu(self):
        try:
            # Create a new QMenu. Styling is handled by the parent CustomWebView.
            custom_menu = QMenu(self.view())
            custom_menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

            # Get context data to decide which actions to show.
            hit_test_data = self.contextMenuData()
            link_url = hit_test_data.linkUrl()
            is_link_present = bool(link_url.url()) # Check if URL string is not empty
            is_image = hit_test_data.mediaType() == QWebEnginePage.MediaType.MediaTypeImage
            is_text_selected = bool(hit_test_data.selectedText())
            is_editable = hit_test_data.isContentEditable()

            # --- DEBUGGING PRINTS ---
            print(f"Context Menu Debug: link_url.url() = {link_url.url()}")
            print(f"Context Menu Debug: image_url.url() = {hit_test_data.imageUrl().url()}")
            print(f"Context Menu Debug: media_url.url() = {hit_test_data.mediaUrl().url()}")
            print(f"Context Menu Debug: is_link_present = {is_link_present}")
            print(f"Context Menu Debug: is_image = {is_image}")
            print(f"Context Menu Debug: is_text_selected = {is_text_selected}")
            print(f"Context Menu Debug: is_editable = {is_editable}")
            print(f"Context Menu Debug: mediaType = {hit_test_data.mediaType()}")
            # ------------------------

            # Build the menu from scratch based on context.
            if is_link_present:
                open_action = QAction("Open in default browser", custom_menu)
                open_action.triggered.connect(lambda: QDesktopServices.openUrl(link_url))
                custom_menu.addAction(open_action)
                
                # Only add CopyLinkToClipboard if the link is actually valid
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
            
            # Add general actions if the menu is still empty or for general clicks
            # Ensure Reload is always available if no other specific actions are added
            if not custom_menu.actions() or (not is_link_present and not is_image and not is_text_selected and not is_editable):
                 # Add a separator if there are already items before adding Reload
                if custom_menu.actions():
                    custom_menu.addSeparator()
                custom_menu.addAction(self.action(QWebEnginePage.WebAction.Reload))

            # Clean up trailing separator if any
            actions = custom_menu.actions()
            if actions and actions[-1].isSeparator():
                custom_menu.removeAction(actions[-1])
            
            # Don't show an empty menu
            if not custom_menu.actions():
                return None

            return custom_menu
        except Exception as e:
            print(f"ERROR in createStandardContextMenu: {e}")
            traceback.print_exc()
            return QMenu(self.view()) # Return an empty menu to prevent crash

class CustomWebView(QWebEngineView):
    popupCreated = pyqtSignal(object)
    popupClosed = pyqtSignal()
    webviewRedirectCompleted = pyqtSignal(str)
    clearCacheRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app_paths = AppPaths() # Initialize AppPaths
        self.active_toasts = []
        self.active_popups = [] # List to keep track of open popup windows
        
        # Apply stylesheet for the webview and its child QMenu
        self.setStyleSheet("""
            CustomWebView {
                background-color: white;
            }
            QMenu {
                background-color: #2C2C29;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 0;
                margin: 0;
            }
            QMenu::item {
                padding: 6px 25px 6px 15px;
                color: #c0c0c0;
                font-size: 13px;
                font-weight: 600;
                font-family: "Segoe UI", "Segoe UI Emoji", "Segoe UI Symbol";
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #333333;
                font-weight: 800;
                padding-left: 18px;
            }
            QMenu::separator {
                height: 1px;
                background-color: #4D4D4D;
                margin: 4px 0;
            }
            QMenu::item:disabled {
                color: #6d6d6d;
            }
        """)
        
        self.profile = QWebEngineProfile("secure_browser_profile", self)
        self.setup_profile()

        self.custom_page = CustomWebEnginePage(self.profile, self)
        self.setPage(self.custom_page)

        self.custom_page.urlChanged.connect(self.check_main_url_change)
        # self.custom_page.popupCreated.connect(self.handle_popup_created) # Removed, handled by add_popup_window
        self.custom_page.authCallback.connect(self.handle_auth_callback)
        self.custom_page.loadFinished.connect(self.on_load_finished)

        self.setup_settings()
        self.setMouseTracking(True)
        self.loaded = False

    def add_popup_window(self, popup_window_instance):
        print(f"CustomWebView: Adding popup window {popup_window_instance}")
        self.active_popups.append(popup_window_instance)
        popup_window_instance.popupClosed.connect(lambda: self.remove_popup_window(popup_window_instance))

    def remove_popup_window(self, popup_window_instance):
        print(f"CustomWebView: Removing popup window {popup_window_instance}")
        if popup_window_instance in self.active_popups:
            self.active_popups.remove(popup_window_instance)
        # Emit CustomWebView's own popupClosed signal if its parent needs to know
        self.popupClosed.emit()

    def clear_cache(self):
        self.page().profile().clearHttpCache()
        print("HTTP cache cleared")
        cookie_store = self.page().profile().cookieStore()
        cookie_store.deleteAllCookies()
        print("Cookies cleared")

    def setup_profile(self):
        cache_path = self.app_paths.get_appdata_dir("cache")
        self.profile.setCachePath(cache_path)
        self.profile.setPersistentStoragePath(cache_path)
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        self.profile.downloadRequested.connect(self.handle_download_requested)
        self.profile.setSpellCheckEnabled(True)
        self.profile.setSpellCheckLanguages(['en-US'])
        self.profile.setUrlRequestInterceptor(EnhancedBrowserInterceptor())

    def setup_settings(self):
        settings = self.settings()
        for attr in [
            QWebEngineSettings.WebAttribute.JavascriptEnabled,
            QWebEngineSettings.WebAttribute.LocalStorageEnabled,
            QWebEngineSettings.WebAttribute.WebGLEnabled,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript,
            QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled,
            QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled,
            QWebEngineSettings.WebAttribute.AutoLoadImages,
            QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.XSSAuditingEnabled,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.ScreenCaptureEnabled,
            QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,
            QWebEngineSettings.WebAttribute.DnsPrefetchEnabled,
            QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled,
        ]:
            settings.setAttribute(attr, True)
        
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
        settings.setDefaultTextEncoding('UTF-8')

    def on_load_finished(self, ok):
        if ok:
            try:
                self.inject_chrome_compatibility_script()
                print("Chrome compatibility script injected successfully.")
            except Exception as e:
                print(f"Inject JS failed: {e}")
        else:
            print("Page load failed")
        
        # Close all active popups when the main webview reloads
        for popup in list(self.active_popups): # Iterate over a copy to allow modification during iteration
            print(f"CustomWebView: Closing popup {popup} due to main webview reload.")
            popup.close()

    def inject_chrome_compatibility_script(self):
        master_script = '''
        (function() {
            'use strict';
            if (navigator.webdriver) {
                try {
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                } catch (e) {
                    console.error('Failed to spoof webdriver:', e);
                }
            }
            window.chrome = window.chrome || {};
            window.chrome.runtime = window.chrome.runtime || { id: 'your-extension-id' };
            if (!navigator.permissions) {
                navigator.permissions = {
                    query: async (descriptor) => {
                        const state = (descriptor.name === 'notifications') ? 'granted' : 'prompt';
                        return { name: descriptor.name, state: state, onchange: null };
                    }
                };
            }
            window.addEventListener('error', function(e) {
                console.log('JS Error:', {
                    message: e.message,
                    filename: e.filename,
                    line: e.lineno,
                    col: e.colno,
                    error: e.error ? e.error.stack : 'N/A'
                });
            });
            window.addEventListener('unhandledrejection', function(e) {
                console.log('JS Unhandled Rejection:', e.reason ? (e.reason.stack || e.reason) : 'N/A');
            });
            console.log('Chrome compatibility script injected and executed.');
        })();
        '''
        self.page().runJavaScript(master_script)

    def save_last_url(self, url):
        try:
            last_url_path = os.path.join(self.app_paths.get_data_dir(), 'lasturl.txt')
            with open(last_url_path, "w") as file:
                file.write(url)
            print(f"URL saved to: {last_url_path}")
        except Exception as e:
            print(f"Error saving URL: {e}")

    def load_last_url(self):
        try:
            last_url_path = os.path.join(self.app_paths.get_data_dir(), 'lasturl.txt')
            if os.path.exists(last_url_path):
                with open(last_url_path, "r") as file:
                    url = file.read().strip()
                    if url:
                        print(f"URL loaded from: {last_url_path}")
                        return url
        except Exception as e:
            print(f"Error loading URL: {e}")
        return "https://chatgpt.com/"

    def get_download_folder(self):
        FOLDERID_Downloads = UUID('{374DE290-123F-4565-9164-39C4925E467B}').bytes_le
        path_ptr = ctypes.c_wchar_p()
        ctypes.windll.shell32.SHGetKnownFolderPath(FOLDERID_Downloads, 0, None, ctypes.byref(path_ptr))
        return path_ptr.value

    def handle_download_requested(self, download_item):
        try:
            downloads_dir = self.get_download_folder()
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)

            save_path = os.path.join(downloads_dir, download_item.downloadFileName())
            download_item.setDownloadDirectory(downloads_dir)
            download_item.accept()
            print(f"Downloading file to: {save_path}")
        except Exception as e:
            print(f"Error handling download: {e}")

    def check_main_url_change(self, url):
        url_str = url.toString().lower()
        print(f"Main WebView URL changed: {url_str}")
        self.webviewRedirectCompleted.emit(url_str)

    def handle_auth_callback(self, callback_url):
        print(f"WebView: Auth callback received: {callback_url}")
        self.webviewRedirectCompleted.emit(callback_url)

    def handle_popup_created(self, popup):
        print("CustomWebView: New popup created")
        self.popupCreated.emit(popup)

    def createWindow(self, window_type):
        try:
            popup_window = PopupWindow(self.profile(), self)
            popup_window.show()
            self.popupCreated.emit(popup_window)
            return popup_window.web_view.page()
        except Exception as e:
            print(f"Error creating popup window: {e}")
            return None

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded:
            try:
                print("Loading initial URL...")
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
    def interceptRequest(self, info):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }
        for name, value in headers.items():
            info.setHttpHeader(name.encode(), value.encode())
