"""带彩色圆点的状态指示器。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from ui_qt.theme import theme


class StatusDot(QWidget):
    def __init__(self, text="", color_key="text_faint", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {theme.c(color_key)}; font-size: 12px;")
        layout.addWidget(self._dot)

        self._label = QLabel(text)
        self._label.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px;")
        layout.addWidget(self._label)

    def set_state(self, text, color_key):
        self._dot.setStyleSheet(
            f"color: {theme.c(color_key)}; font-size: 12px;")
        self._label.setText(text)