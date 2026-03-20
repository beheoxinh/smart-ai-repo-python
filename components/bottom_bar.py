# File: components/bottom_bar.py
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QColor, QPainter

class BottomBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self.background_color = QColor("#1E1E1E")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.background_color)
