from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor


class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet("TitleBar { border-bottom: 1px solid #444; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.title_label = QLabel("New Tab")
        self.title_label.setStyleSheet("color: #fff; background-color: transparent;")
        layout.addWidget(self.title_label)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_title(self, title):
        self.title_label.setText(title)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setBrush(QColor("#2E2E2E"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
