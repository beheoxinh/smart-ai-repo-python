# File: components/resize_handle.py
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame


class ResizeHandle(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedWidth(10)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.is_resizing = False
        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.15);
                border-left: 1px solid rgba(255, 255, 255, 0.3);
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
                # SỬA LỖI: Gọi hàm mới chỉ để cập nhật chiều rộng và vị trí X
                self.parent.update_width_and_x_position()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_resizing:
            self.is_resizing = False
            self.parent.resizing_finished()
