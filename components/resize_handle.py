from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtWidgets import QFrame


class ResizeHandle(QFrame):
    """10px drag handle on the LEFT edge of the sidebar window.

    Emits dragResized(new_width) during drag.
    SidebarPanel handles its own window repositioning (moving left when
    expanding) so the icon button is never affected.
    """

    dragStarted = pyqtSignal()
    dragResized = pyqtSignal(int)   # new sidebar window width
    dragFinished = pyqtSignal()

    MIN_WIDTH = 360
    MAX_WIDTH = 1200

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
            self._start_x = int(event.globalPosition().x())
            self._start_width = self.parent.width()
            self._start_win_x = self.parent.x()
            self.dragStarted.emit()

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            dx = int(event.globalPosition().x()) - self._start_x
            # Drag LEFT (dx < 0) → wider window; drag RIGHT (dx > 0) → narrower
            new_width = self._start_width - dx
            new_width = max(self.MIN_WIDTH, min(self.MAX_WIDTH, new_width))

            if new_width != self.parent.width():
                # Move the window left-right so the RIGHT edge stays anchored
                delta = new_width - self._start_width
                new_x = self._start_win_x - delta
                self.parent.setFixedWidth(new_width)
                wh = self.parent.windowHandle()
                if wh is not None:
                    wh.setGeometry(QRect(new_x, self.parent.y(), new_width, self.parent.height()))
                else:
                    self.parent.move(new_x, self.parent.y())
                self.dragResized.emit(new_width)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_resizing:
            self.is_resizing = False
            self.dragFinished.emit()
