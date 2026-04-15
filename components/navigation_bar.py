import json
import os
import shutil

from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QPushButton, QSpacerItem,
    QSizePolicy, QMenu, QApplication, QMessageBox
)

from components.menu_setting_dialog import MenuSettingDialog
from utils import AppPaths  # Import AppPaths


class NavigationBar(QFrame):
    refreshClicked = pyqtSignal()
    backClicked = pyqtSignal()
    forwardClicked = pyqtSignal()
    clearCacheRequested = pyqtSignal()
    navigationClicked = pyqtSignal(str)
    closeClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app_paths = AppPaths() # Initialize AppPaths
        self.buttons = []
        self.button_data = []
        self.drag_start_pos = None
        # Use the correct path for user-specific config data
        self.config_path = os.path.join(self.app_paths.get_data_dir('config'), 'nav_config.json')
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        self.setFixedWidth(70)
        self.setStyleSheet("""
            NavigationBar {
                background-color: #1E1E1E;
                border: none;
            }
        """)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 0, 5, 0)
        self.main_layout.setSpacing(20)

        # Close button at the top
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(50, 40)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.closeClicked.emit)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                font-size: 24px;
                font-weight: bold;
                padding: 0;
                margin: 0;
            }
            QPushButton:hover {
                color: white;
                background-color: #3A3A3A;
                border-radius: 5px;
            }
        """)
        self.main_layout.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.center_layout = QVBoxLayout()
        self.center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.main_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        self.main_layout.addLayout(self.center_layout)
        self.main_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Add buttons
        self.add_button_btn = QPushButton()
        self.add_button_btn.setFixedSize(50, 34)
        self.add_button_btn.setText("+")
        self.add_button_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button_btn.setStyleSheet("""
            QPushButton {
                background-color: #3A3A3A;
                color: white;
                font-size: 20px;
                font-weight: bold;
                padding: -5px 0 0 0;
                margin: 0;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        self.add_button_btn.clicked.connect(self.open_add_button_dialog)
        self.main_layout.addWidget(self.add_button_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def add_button(self, icon_path, tooltip, url):
        btn = QPushButton()
        btn.setFixedSize(60, 90)
        btn.setToolTip(tooltip)
        btn.url = url
        btn.clicked.connect(self.handle_navigation_click)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        icon = QIcon(icon_path)
        btn.setIcon(icon)
        btn.setIconSize(btn.size() * 0.8)

        btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                color: white;
                border: none;
                font-size: 20px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #3D3D3D;
            }
            QPushButton:pressed {
                background-color: #404040;
            }
        """)

        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(self.show_context_menu)

        return btn

    def handle_navigation_click(self):
        btn = self.sender()
        if btn not in self.buttons:
            print("Clicked button not in buttons list! Possibly deleted.")
            return
        self.navigationClicked.emit(btn.url)

    def show_context_menu(self, pos):
        button = self.sender()
        if not button or button not in self.buttons:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E1E1E;
                color: white;
                border: 1px solid #505050;
            }
            QMenu::item {
                padding: 5px 20px;
            }
            QMenu::item:selected {
                background-color: #3D3D3D;
            }
        """)
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")
        clear_cache_action = menu.addAction("Clear Cache")

        action = menu.exec(button.mapToGlobal(QPoint(0, button.height())))

        if action == edit_action:
            self.edit_button(button)
        elif action == delete_action:
            self.delete_button(button)
        elif action == clear_cache_action:
            self.clearCacheRequested.emit()

    def edit_button(self, button):
        self.parent().dialog_open = True
        idx = self.buttons.index(button)
        current_data = self.button_data[idx]

        def update_callback(new_data):
            old_icon = self.button_data[idx]['icon']
            self.button_data[idx] = new_data
            self.save_config()
            self.load_config()

            # Nếu icon đã đổi, check xóa icon cũ nếu không xài
            if old_icon != new_data['icon']:
                self.cleanup_unused_icon(old_icon)

        self.dialog = MenuSettingDialog(callback=update_callback, parent=self, mode="edit")
        self.dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.dialog.__menu_setting_dialog__ = True
        self.dialog.prefill(current_data, idx)
        self.dialog.show()

    def open_add_button_dialog(self):
        self.parent().dialog_open = True

        def add_new_button(new_data):
            self.button_data.append(new_data)
            self.save_config()
            self.load_config()

        self.dialog = MenuSettingDialog(callback=add_new_button, parent=self, mode="add")
        self.dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.dialog.__menu_setting_dialog__ = True
        self.dialog.show()

    def delete_button(self, button):
        reply = QMessageBox.question(
            self,
            "Delete",
            "Are you sure?!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self.buttons.index(button)
        icon_to_check = self.button_data[idx]['icon']

        btn = self.buttons.pop(idx)
        self.button_data.pop(idx)

        btn.clicked.disconnect()
        btn.customContextMenuRequested.disconnect()

        self.center_layout.removeWidget(btn)
        btn.deleteLater()

        self.save_config()
        self.cleanup_unused_icon(icon_to_check)
        self.rebuild_layout()

    def mousePressEvent(self, event):
        self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not self.drag_start_pos:
            return

        if (event.pos() - self.drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
            for btn in self.buttons:
                if btn.geometry().contains(self.mapFromGlobal(event.globalPosition().toPoint())):
                    idx = self.buttons.index(btn)
                    if idx > 0:
                        self.buttons.insert(idx - 1, self.buttons.pop(idx))
                        self.button_data.insert(idx - 1, self.button_data.pop(idx))
                        self.rebuild_layout()
                        self.save_config()
                    break

    def rebuild_layout(self):
        # Added a comment to force a file change
        for i in reversed(range(self.center_layout.count())):
            item = self.center_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        for btn in self.buttons:
            self.center_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

    def load_config(self):
        self.app_paths.ensure_config_exists()

        if not os.path.exists(self.config_path):
            default_config_path = self.app_paths.get_path('config', 'nav_config.json')
            if os.path.exists(default_config_path):
                try:
                    shutil.copy2(default_config_path, self.config_path)
                except Exception as e:
                    print(f"Could not copy default config: {e}")
                    self.button_data = []
                    self.rebuild_layout_from_config()
                    return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.button_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.button_data = []

        # --- Add Ollama button if it doesn't exist ---
        ollama_exists = any(btn.get('tooltip') == 'Ollama' for btn in self.button_data)
        if not ollama_exists:
            ollama_button = {
                "icon": "ollama.svg",
                "tooltip": "Ollama",
                "url": "http://127.0.0.1:7001"
            }
            self.button_data.insert(0, ollama_button) # Add to the beginning
            self.save_config() # Save the updated config

        self.rebuild_layout_from_config()

    def rebuild_layout_from_config(self):
        # Clear existing buttons
        for btn in self.buttons:
            self.center_layout.removeWidget(btn)
            btn.deleteLater()
        self.buttons.clear()

        # Add new buttons from config
        for data in self.button_data:
            # Icons for nav buttons should always come from the bundled resources
            icon_full_path = self.app_paths.get_path('images', data['icon'])
            # Fallback icon if the specified one doesn't exist
            if not os.path.exists(icon_full_path):
                icon_full_path = self.app_paths.get_path('images', 'default.svg') # Assuming you have a default.svg

            btn = self.add_button(icon_full_path, data['tooltip'], data['url'])
            self.center_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self.buttons.append(btn)
        
        self.rebuild_layout()

    def save_config(self):
        self.app_paths.ensure_config_exists()
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.button_data, f, indent=4)

    def cleanup_unused_icon(self, icon_filename):
        # Check if the icon is still used by any button
        is_used = any(data['icon'] == icon_filename for data in self.button_data)
        if not is_used:
            try:
                # Icons are part of the bundled app, so we don't delete them from the user's data dir
                # Instead, we check the source images folder if needed, but cleanup is tricky
                # For now, we just don't delete them to be safe
                pass
            except Exception as e:
                print(f"Error during icon cleanup check: {e}")
