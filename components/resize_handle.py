from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtWidgets import QFrame


class ResizeHandle(QFrame):
    """Drag handle supporting horizontal (left edge) and vertical (bottom edge) resize.

    Horizontal mode:
      - Fixed 10px wide, cursor SizeHorCursor
      - Drag left → wider, window moves left; drag right → narrower, window moves right
      - Right edge of window stays anchored

    Vertical mode:
      - Fixed 10px tall, cursor SizeVerCursor
      - Drag down → taller, no window movement; drag up → shorter
      - Top edge of window stays anchored
    """

    dragStarted = pyqtSignal()
    dragResized = pyqtSignal(int)   # new width (horizontal) or new height (vertical)
    dragFinished = pyqtSignal()

    MIN_WIDTH = 360
    MAX_WIDTH = 1200
    MIN_HEIGHT = 300
    MAX_HEIGHT = 1200

    def __init__(self, parent, mode='horizontal'):
        super().__init__(parent)
        self.parent = parent
        self.mode = mode
        self.is_resizing = False

        if mode == 'horizontal':
            self.setFixedWidth(10)
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            self.setStyleSheet("""
                QFrame { background-color: transparent; }
                QFrame:hover {
                    background-color: rgba(255, 255, 255, 0.15);
                    border-left: 1px solid rgba(255, 255, 255, 0.3);
                }
            """)
        else:
            self.setFixedHeight(10)
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            self.setStyleSheet("""
                QFrame { background-color: transparent; }
                QFrame:hover {
                    background-color: rgba(255, 255, 255, 0.15);
                    border-top: 1px solid rgba(255, 255, 255, 0.3);
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_resizing = True
            if self.mode == 'horizontal':
                self._start_pos = int(event.globalPosition().x())
                self._start_size = self.parent.width()
                self._start_win_x = self.parent.x()
            else:
                self._start_pos = int(event.globalPosition().y())
                self._start_size = self.parent.height()
            self.dragStarted.emit()

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            if self.mode == 'horizontal':
                d = int(event.globalPosition().x()) - self._start_pos
                new_size = self._start_size - d
                new_size = max(self.MIN_WIDTH, min(self.MAX_WIDTH, new_size))
                if new_size != self.parent.width():
                    delta = new_size - self._start_size
                    new_x = self._start_win_x - delta
                    self.parent.setFixedWidth(new_size)
                    wh = self.parent.windowHandle()
                    if wh is not None:
                        wh.setGeometry(QRect(new_x, self.parent.y(), new_size, self.parent.height()))
                    else:
                        self.parent.move(new_x, self.parent.y())
                    self.dragResized.emit(new_size)
            else:  # vertical
                d = int(event.globalPosition().y()) - self._start_pos
                new_size = self._start_size + d  # drag down → taller
                new_size = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, new_size))
                if new_size != self.parent.height():
                    self.parent.setFixedHeight(new_size)
                    self.dragResized.emit(new_size)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_resizing:
            self.is_resizing = False
            self.dragFinished.emit()
