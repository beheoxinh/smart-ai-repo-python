# File: components/title_bar.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt

class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet("""
            background-color: #2a2a2a;
            border-bottom: 1px solid #444;
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.title_label = QLabel("New Tab")
        self.title_label.setStyleSheet("color: #fff;")
        layout.addWidget(self.title_label)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_title(self, title):
        self.title_label.setText(title)
