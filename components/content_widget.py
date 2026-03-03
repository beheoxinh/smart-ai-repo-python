# File: components/content_widget.py
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSizePolicy

from .navigation_bar import NavigationBar
from .web_view import CustomWebView


class ContentWidget(QWidget):
    closeRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create WebView first
        self.web_view = CustomWebView()
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create Navigation Bar
        self.nav_bar = NavigationBar()

        # Add widgets to layout in order: WebView first, NavBar last
        layout.addWidget(self.web_view)
        layout.addWidget(self.nav_bar)

        self.setStyleSheet("""
            ContentWidget {
                background-color: #33322F;
            }
        """)

    def setup_connections(self):
        # Connect signals from navigation bar to web view
        self.nav_bar.refreshClicked.connect(self.web_view.reload)
        self.nav_bar.backClicked.connect(self.web_view.back)
        self.nav_bar.forwardClicked.connect(self.web_view.forward)
        self.nav_bar.navigationClicked.connect(self.handle_navigation_click)
        # FIX: Connect to the correctly renamed method 'clear_http_cache'
        self.nav_bar.clearCacheRequested.connect(self.web_view.clear_http_cache)
        self.nav_bar.closeClicked.connect(self.closeRequested.emit)

    def handle_navigation_click(self, url):
        self.web_view.setUrl(QUrl(url))
        self.web_view.save_last_url(url)
