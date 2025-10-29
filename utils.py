# File: utils.py
import os
import sys
from PyQt6.QtWidgets import QMessageBox

class AppPaths:
    def __init__(self, app_name="SmartAI", app_author="Hsx2"):
        self.app_name = app_name
        self.app_author = app_author
        self.root_path = self._determine_root_path()

    def _determine_root_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def get_root(self):
        return self.root_path

    def get_path(self, *paths):
        abs_path = os.path.join(self.root_path, *paths)
        return abs_path

    def get_data_dir(self, subfolder=None):
        base_path = os.path.join(self.root_path, "data")
        if subfolder:
            base_path = os.path.join(base_path, subfolder)
        os.makedirs(base_path, exist_ok=True)
        return base_path

    def get_appdata_dir(self, subfolder=None):
        if sys.platform == 'win32':
            base_path = os.path.join(
                os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local')),
                self.app_author,
                self.app_name
            )
        else:
            base_path = os.path.expanduser(f'~/.local/share/{self.app_name}')

        if subfolder:
            base_path = os.path.join(base_path, subfolder)
        os.makedirs(base_path, exist_ok=True)
        return base_path

    def ensure_dir(self, dir_path):
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        return dir_path

    def ensure_config_exists(self):
        config_dir = os.path.join(self.root_path, 'config')
        self.ensure_dir(config_dir)

    def join_path(self, *paths):
        return os.path.normpath(os.path.join(*paths))

def alert_popup(parent, title, message):
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setText(title)
    msg_box.setInformativeText(str(message))
    msg_box.setWindowTitle("Error")
    msg_box.setStyleSheet("""
        QMessageBox {
            background-color: #2b2b2b;
        }
        QMessageBox QLabel {
            color: white;
            background-color: transparent;
        }
        QPushButton {
            background-color: #3A3A3A;
            color: white;
            border: 1px solid #505050;
            padding: 5px;
            min-width: 70px;
        }
        QPushButton:hover {
            background-color: #505050;
        }
        QPushButton:pressed {
            background-color: #2D2D2D;
        }
    """)
    msg_box.exec()
