# File: components/menu_setting_dialog.py

import os
import shutil
import random
import string
import requests

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout, QLineEdit, QPushButton, QMessageBox,
    QWidget, QHBoxLayout, QFileDialog
)

BASE_DIR = os.path.abspath(os.getcwd())
IMAGES_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


def random_filename(ext='png'):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=15)) + f'.{ext}'


class MenuSettingDialog(QWidget):
    def __init__(self, callback, existing_items=None, parent=None, mode="add"):
        super().__init__(parent)
        self.callback = callback
        self.mode = mode
        self.existing_items = existing_items or []
        self.setWindowTitle("Settings Menu Item")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #2E2E2E; color: white;")
        self.setFixedSize(350, 300)

        layout = QVBoxLayout(self)

        self.tooltip_input = QLineEdit()
        self.tooltip_input.setPlaceholderText("Tooltip")
        layout.addWidget(self.tooltip_input)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("URL")
        layout.addWidget(self.url_input)

        icon_layout = QHBoxLayout()
        self.icon_input = QLineEdit()
        self.icon_input.setPlaceholderText("Icon filename (or URL)")
        icon_layout.addWidget(self.icon_input)

        upload_btn = QPushButton("📁")
        upload_btn.setFixedWidth(40)
        upload_btn.setToolTip("Select icon file")
        upload_btn.clicked.connect(self.choose_icon_file)
        icon_layout.addWidget(upload_btn)

        layout.addLayout(icon_layout)

        submit_btn = QPushButton("Add" if self.mode == "add" else "Save")
        submit_btn.clicked.connect(self.handle_submit)
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(submit_btn)

    def handle_submit(self):
        tooltip = self.tooltip_input.text().strip()
        url = self.url_input.text().strip()
        icon = self.icon_input.text().strip()

        if not url or not icon:
            QMessageBox.warning(self, "Error", "All fields are required.")
            return

        # Thêm https nếu thiếu
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        # Nếu icon là link thì tải về rồi random tên
        if icon.startswith("http://") or icon.startswith("https://"):
            try:
                response = requests.get(icon, timeout=5)
                content_type = response.headers.get("Content-Type", "")
                ext = "png"
                if "svg" in content_type:
                    ext = "svg"
                elif "jpeg" in content_type:
                    ext = "jpg"
                elif "jpg" in content_type:
                    ext = "jpg"
                elif "webp" in content_type:
                    ext = "webp"

                filename = random_filename(ext)
                save_path = os.path.join(IMAGES_DIR, filename)

                with open(save_path, 'wb') as f:
                    f.write(response.content)

                icon = filename
                print(f"[ICON DOWNLOADED] Saved to {save_path}")
            except Exception as e:
                QMessageBox.critical(self, "Download Failed", f"Cannot download icon from URL.\n{e}")
                return

        data = {
            "tooltip": tooltip,
            "url": url,
            "icon": icon,
            "pinned": True,
            "order": len(self.existing_items) + 1
        }

        self.callback(data)
        self.close()

    def prefill(self, data, index):
        self.index = index
        self.tooltip_input.setText(data.get("tooltip", ""))
        self.url_input.setText(data.get("url", ""))
        self.icon_input.setText(data.get("icon", ""))

    def choose_icon_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn icon",
            "",
            "Image Files (*.png *.jpg *.jpeg *.svg)"
        )

        if file_path:
            try:
                filename = os.path.basename(file_path)
                dest_path = os.path.join(IMAGES_DIR, filename)

                if not os.path.exists(dest_path):
                    shutil.copy(file_path, dest_path)

                self.icon_input.setText(filename)
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể chọn ảnh: {e}")
