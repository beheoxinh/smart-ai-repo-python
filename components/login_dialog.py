"""
Login dialog for SmartAI - allows users to save and manage login credentials
for their AI service accounts.
"""
import os
import json
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QGroupBox, QMessageBox, QTabWidget,
    QWidget, QSpinBox
)
from PyQt6.QtGui import QPixmap, QIcon
from utils import AppPaths


class LoginDialog(QDialog):
    """Login dialog for managing AI service credentials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app_paths = AppPaths()
        self.setWindowTitle("SmartAI Login")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #2E2E2E;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit {
                background-color: #3A3A3A;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #0078D4;
            }
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1084D8;
            }
            QPushButton:pressed {
                background-color: #006CBE;
            }
            QPushButton#cancelBtn {
                background-color: #3A3A3A;
                color: #ffffff;
            }
            QPushButton#cancelBtn:hover {
                background-color: #505050;
            }
            QGroupBox {
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QTabWidget::pane {
                border: 1px solid #505050;
                background-color: #2E2E2E;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #3A3A3A;
                color: #ffffff;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0078D4;
            }
            QCheckBox {
                color: #ffffff;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)
        self._init_ui()
        self._load_credentials()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("SmartAI Login")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0078D4; margin-bottom: 10px;")
        layout.addWidget(title)

        # Tab widget
        tabs = QTabWidget()

        # Login tab
        login_tab = self._create_login_tab()
        tabs.addTab(login_tab, "Login")

        # Saved accounts tab
        accounts_tab = self._create_accounts_tab()
        tabs.addTab(accounts_tab, "Saved Accounts")

        layout.addWidget(tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self._handle_login)
        btn_layout.addWidget(self.login_btn)

        layout.addLayout(btn_layout)

    def _create_login_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # Service selection
        layout.addWidget(QLabel("Service:"))
        self.service_combo = QComboBox()
        self.service_combo.addItems([
            "ChatGPT",
            "Claude AI",
            "Google Gemini",
            "Ollama (Local)",
            "Custom URL"
        ])
        self.service_combo.currentTextChanged.connect(self._on_service_changed)
        layout.addWidget(self.service_combo)

        # URL display
        layout.addWidget(QLabel("Login URL:"))
        self.url_label = QLabel("https://chat.openai.com")
        self.url_label.setStyleSheet("color: #888888; font-size: 12px;")
        layout.addWidget(self.url_label)

        # Custom URL input
        layout.addWidget(QLabel("Custom URL (optional):"))
        self.custom_url_input = QLineEdit()
        self.custom_url_input.setPlaceholderText("https://example.com")
        self.custom_url_input.setVisible(False)
        layout.addWidget(self.custom_url_input)

        layout.addSpacing(10)

        # Credentials group
        creds_group = QGroupBox("Credentials")
        creds_layout = QVBoxLayout()

        # Email/Username
        creds_layout.addWidget(QLabel("Email or Username:"))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your@email.com or username")
        creds_layout.addWidget(self.email_input)

        # Password
        creds_layout.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter your password")
        creds_layout.addWidget(self.password_input)

        # Remember checkbox
        self.remember_check = QCheckBox("Remember me")
        creds_layout.addWidget(self.remember_check)

        creds_group.setLayout(creds_layout)
        layout.addWidget(creds_group)

        layout.addStretch()
        return widget

    def _create_accounts_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(QLabel("Saved Accounts:"))

        # List of saved accounts
        self.accounts_list = QListWidget()
        self.accounts_list.setStyleSheet("""
            QListWidget {
                background-color: #3A3A3A;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
            }
            QListWidget::item:selected {
                background-color: #0078D4;
            }
        """)
        layout.addWidget(self.accounts_list)

        # Buttons
        btn_layout = QHBoxLayout()

        delete_btn = QPushButton("Delete Selected")
        delete_btn.setObjectName("cancelBtn")
        delete_btn.clicked.connect(self._delete_account)
        btn_layout.addWidget(delete_btn)

        use_btn = QPushButton("Use This Account")
        use_btn.clicked.connect(self._use_selected_account)
        btn_layout.addWidget(use_btn)

        layout.addLayout(btn_layout)
        return widget

    def _on_service_changed(self, service):
        urls = {
            "ChatGPT": "https://chat.openai.com",
            "Claude AI": "https://claude.ai/",
            "Google Gemini": "https://gemini.google.com",
            "Ollama (Local)": "http://127.0.0.1:7001",
            "Custom URL": ""
        }
        self.url_label.setText(urls.get(service, ""))
        self.custom_url_input.setVisible(service == "Custom URL")

    def _load_credentials(self):
        """Load saved credentials from disk."""
        try:
            path = os.path.join(self.app_paths.get_data_dir(), 'credentials.json')
            if os.path.exists(path):
                with open(path, 'r') as f:
                    self._credentials = json.load(f)
            else:
                self._credentials = {}
        except Exception:
            self._credentials = {}

        self._refresh_accounts_list()

    def _save_credentials(self):
        """Save credentials to disk."""
        try:
            path = os.path.join(self.app_paths.get_data_dir(), 'credentials.json')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump(self._credentials, f, indent=2)
        except Exception as e:
            print(f"Error saving credentials: {e}")

    def _refresh_accounts_list(self):
        """Refresh the accounts list display."""
        self.accounts_list.clear()
        for service, accounts in self._credentials.items():
            for email in accounts:
                self.accounts_list.addItem(f"{service}: {email}")

    def _handle_login(self):
        """Handle login button click."""
        service = self.service_combo.currentText()
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email:
            QMessageBox.warning(self, "Error", "Please enter your email or username.")
            return

        if not password:
            QMessageBox.warning(self, "Error", "Please enter your password.")
            return

        # For local Ollama, no login needed
        if service == "Ollama (Local)":
            self.accept()
            return

        # Save credentials if remember is checked
        if self.remember_check.isChecked():
            if service not in self._credentials:
                self._credentials[service] = []
            if email not in self._credentials[service]:
                self._credentials[service].append(email)
                self._save_credentials()
                self._refresh_accounts_list()

        # Open the login URL in the browser
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        # Just accept - the parent will handle navigation
        self.accept()

    def _delete_account(self):
        """Delete selected account from saved list."""
        current_item = self.accounts_list.currentItem()
        if not current_item:
            return

        text = current_item.text()
        parts = text.split(": ", 1)
        if len(parts) == 2:
            service, email = parts
            if service in self._credentials and email in self._credentials[service]:
                self._credentials[service].remove(email)
                if not self._credentials[service]:
                    del self._credentials[service]
                self._save_credentials()
                self._refresh_accounts_list()

    def _use_selected_account(self):
        """Use the selected account - fills in the login form."""
        current_item = self.accounts_list.currentItem()
        if not current_item:
            return

        text = current_item.text()
        parts = text.split(": ", 1)
        if len(parts) == 2:
            service, email = parts
            self.service_combo.setCurrentText(service)
            self.email_input.setText(email)
            # Switch to login tab
            self.service_combo.parent().parent().setCurrentIndex(0)

    def get_login_data(self):
        """Get the login data entered by the user."""
        return {
            'service': self.service_combo.currentText(),
            'email': self.email_input.text().strip(),
            'password': self.password_input.text(),
            'url': self.custom_url_input.text().strip() or self.url_label.text(),
            'remember': self.remember_check.isChecked()
        }

    def get_selected_account(self):
        """Get the selected account from the list."""
        current_item = self.accounts_list.currentItem()
        if current_item:
            text = current_item.text()
            parts = text.split(": ", 1)
            if len(parts) == 2:
                return {'service': parts[0], 'email': parts[1]}
        return None


# Need to import QComboBox and QListWidget
from PyQt6.QtWidgets import QComboBox, QListWidget
