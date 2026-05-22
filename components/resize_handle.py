from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QApplication


class ResizeHandle(QFrame):
    """10px drag handle between button area and sidebar content.

    Emits ``dragResized(new_width)`` during drag and
    ``dragFinished(new_width)`` on release.
    """

    dragResized = pyqtSignal(int)
    dragFinished = pyqtSignal(int)

    def __init__(self, sidebar_panel):
        super().__init__(sidebar_panel)
        self._panel = sidebar_panel
        self.setFixedWidth(10)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self._resizing = False
        self._start_x = 0
        self._start_w = 0
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
            self._resizing = True
            self._start_x = int(event.globalPosition().x())
            self._start_w = self._panel.get_sidebar_width()

    def mouseMoveEvent(self, event):
        if self._resizing:
            dx = int(event.globalPosition().x()) - self._start_x
            screens = QApplication.screens()
            screen = QApplication.screenAt(
                self._panel.mapToGlobal(self._panel.rect().center())
            )
            if not screen:
                screen = QApplication.primaryScreen()
            screen_w = screen.geometry().width()
            min_w = int(screen_w * 0.2)
            max_w = int(screen_w * 0.8)
            # Negative dx (drag left) = wider sidebar
            new_w = max(min_w, min(max_w, self._start_w - dx))
            self.dragResized.emit(new_w)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._resizing:
            self._resizing = False
            self.dragFinished.emit(self._panel.get_sidebar_width())
