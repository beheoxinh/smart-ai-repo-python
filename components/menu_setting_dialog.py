# File: components/menu_setting_dialog.py (REFACTORED with all fields)

import os
import random
import shutil
import string

import requests
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout, QLineEdit, QPushButton, QMessageBox,
    QWidget, QHBoxLayout, QFileDialog, QDialog, QDialogButtonBox,
    QCheckBox, QSpinBox, QLabel, QSpacerItem, QSizePolicy
)

BASE_DIR = os.path.abspath(os.getcwd())
IMAGES_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


def random_filename(ext='png'):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=15)) + f'.{ext}'


class MenuSettingDialog(QDialog):
    def __init__(self, parent=None, mode="add"):
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle(f"{mode.capitalize()} Menu Item")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #2E2E2E; color: white;")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Tooltip
        layout.addWidget(QLabel("Tooltip:"))
        self.tooltip_input = QLineEdit()
        self.tooltip_input.setPlaceholderText("Text to show on hover")
        layout.addWidget(self.tooltip_input)

        # URL
        layout.addWidget(QLabel("URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        layout.addWidget(self.url_input)

        # Icon
        layout.addWidget(QLabel("Icon:"))
        icon_layout = QHBoxLayout()
        self.icon_input = QLineEdit()
        self.icon_input.setPlaceholderText("Icon filename (or URL to download)")
        icon_layout.addWidget(self.icon_input)
        upload_btn = QPushButton("📁")
        upload_btn.setFixedWidth(40)
        upload_btn.setToolTip("Select icon file")
        upload_btn.clicked.connect(self.choose_icon_file)
        icon_layout.addWidget(upload_btn)
        layout.addLayout(icon_layout)

        # Pinned and Order
        bottom_layout = QHBoxLayout()
        self.pinned_checkbox = QCheckBox("Pinned")
        self.pinned_checkbox.setToolTip("Pinned items are always visible")
        bottom_layout.addWidget(self.pinned_checkbox)

        bottom_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        bottom_layout.addWidget(QLabel("Order:"))
        self.order_spinbox = QSpinBox()
        self.order_spinbox.setRange(0, 999)
        self.order_spinbox.setToolTip("Lower numbers appear first")
        bottom_layout.addWidget(self.order_spinbox)
        layout.addLayout(bottom_layout)

        # Dialog Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.handle_submit)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def handle_submit(self):
        if not self.url_input.text().strip() or not self.icon_input.text().strip():
            QMessageBox.warning(self, "Error", "URL and Icon fields are required.")
            return
        self.accept()

    def get_data(self):
        tooltip = self.tooltip_input.text().strip()
        url = self.url_input.text().strip()
        icon = self.icon_input.text().strip()
        pinned = self.pinned_checkbox.isChecked()
        order = self.order_spinbox.value()

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        if icon.startswith("http://") or icon.startswith("https://"):
            try:
                response = requests.get(icon, timeout=5)
                content_type = response.headers.get("Content-Type", "")
                ext = "png"
                if "svg" in content_type: ext = "svg"
                elif "jpeg" in content_type or "jpg" in content_type: ext = "jpg"
                elif "webp" in content_type: ext = "webp"

                filename = random_filename(ext)
                save_path = os.path.join(IMAGES_DIR, filename)
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                icon = filename
            except Exception as e:
                QMessageBox.critical(self, "Download Failed", f"Cannot download icon from URL.\n{e}")
                return None

        return {
            "tooltip": tooltip,
            "url": url,
            "icon": icon,
            "pinned": pinned,
            "order": order
        }

    def prefill(self, data):
        self.tooltip_input.setText(data.get("tooltip", ""))
        self.url_input.setText(data.get("url", ""))
        self.icon_input.setText(data.get("icon", ""))
        self.pinned_checkbox.setChecked(data.get("pinned", True))
        self.order_spinbox.setValue(data.get("order", 99))

    def choose_icon_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn icon", "", "Image Files (*.png *.jpg *.jpeg *.svg)")
        if file_path:
            try:
                filename = os.path.basename(file_path)
                dest_path = os.path.join(IMAGES_DIR, filename)
                if not os.path.exists(dest_path):
                    shutil.copy(file_path, dest_path)
                self.icon_input.setText(filename)
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể chọn ảnh: {e}")
