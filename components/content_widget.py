# File: components/content_widget.py
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy

from .navigation_bar import NavigationBar
from .web_view import CustomWebView
from .title_bar import TitleBar


class ContentWidget(QWidget):
    closeRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = TitleBar()
        main_layout.addWidget(self.title_bar)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Create WebView first
        self.web_view = CustomWebView()
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create Navigation Bar
        self.nav_bar = NavigationBar()

        # Add widgets to layout in order: WebView first, NavBar last
        content_layout.addWidget(self.web_view)
        content_layout.addWidget(self.nav_bar)

        main_layout.addLayout(content_layout)

        self.setStyleSheet("""
            ContentWidget {
                background-color: #33322F;
                border-bottom: 1px solid #444;
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
        self.web_view.titleChanged.connect(self.title_bar.set_title)

    def handle_navigation_click(self, url):
        self.web_view.setUrl(QUrl(url))
        self.web_view.save_last_url(url)
