import os
import sys
from PyQt6.QtWidgets import QMessageBox


class AppPaths:
    def __init__(self, app_name=".smartAI"):
        self.app_data_root = os.path.join(os.path.expanduser('~'), app_name)
        self.root_path = self._determine_root_path()

    def _determine_root_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def get_root(self):
        return self.root_path

    def get_path(self, *paths):
        return os.path.join(self.root_path, *paths)

    def get_data_dir(self, subfolder=None):
        base_path = self.app_data_root
        if subfolder:
            base_path = os.path.join(base_path, subfolder)
        os.makedirs(base_path, exist_ok=True)
        return base_path

    def get_appdata_dir(self, subfolder=None):
        return self.get_data_dir(subfolder)

    def ensure_dir(self, dir_path):
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        return dir_path

    def ensure_config_exists(self):
        config_dir = self.get_data_dir('config')
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
        QMessageBox { background-color: #2b2b2b; }
        QMessageBox QLabel { color: white; background-color: transparent; }
        QPushButton {
            background-color: #3A3A3A; color: white;
            border: 1px solid #505050; padding: 5px; min-width: 70px;
        }
        QPushButton:hover { background-color: #505050; }
        QPushButton:pressed { background-color: #2D2D2D; }
    """)
    msg_box.exec()
