# File: components/resize_handle.py
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame


class ResizeHandle(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedWidth(5)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.is_resizing = False
        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_resizing = True
            self.start_x = int(event.globalPosition().x())
            self.start_width = self.parent.width()
            self.parent.resizing_started()

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            dx = int(event.globalPosition().x()) - self.start_x
            screen_width = self.parent.get_current_screen_width()
            min_width = int(screen_width * 0.2)
            max_width = int(screen_width * 0.8)
            new_width = max(min_width, min(max_width, self.start_width - dx))
            if new_width != self.parent.width():
                self.parent.setFixedWidth(new_width)
                self.parent.update_position()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_resizing:
            self.is_resizing = False
            self.parent.resizing_finished()