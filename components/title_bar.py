# File: components/title_bar.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor # Import các class cần thiết

class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        
        # Giữ lại stylesheet cho đường viền dưới
        self.setStyleSheet("""
            TitleBar {
                border-bottom: 1px solid #444;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.title_label = QLabel("New Tab")
        # Đảm bảo label cũng có nền trong suốt để không che mất màu đen của chúng ta
        self.title_label.setStyleSheet("color: #fff; background-color: transparent;")
        layout.addWidget(self.title_label)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_title(self, title):
        self.title_label.setText(title)

    # GIẢI PHÁP TRIỆT ĐỂ: Tự vẽ màu nền bằng paintEvent
    def paintEvent(self, event):
        # Tạo một "cọ vẽ" cho widget này
        painter = QPainter(self)
        # Đặt màu tô là màu đen
        painter.setBrush(QColor("#2E2E2E"))
        # Không vẽ viền (vì đã có trong stylesheet)
        painter.setPen(Qt.PenStyle.NoPen)
        # Vẽ một hình chữ nhật lấp đầy toàn bộ không gian của TitleBar
        painter.drawRect(self.rect())
