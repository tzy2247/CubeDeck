"""卡片容器。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel

from ui_qt.theme import theme


class Card(QFrame):
    """带标题的卡片。

    布局：上下左右统一 20px 内边距，标题与正文间距 6px。
    """

    def __init__(self, parent=None, title=None, subtitle=None):
        super().__init__(parent)
        self.setObjectName("Card")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(10)

        if title is not None:
            header = QHBoxLayout()
            header.setSpacing(8)
            header.setContentsMargins(0, 0, 0, 0)

            t = QLabel(title)
            t.setObjectName("CardTitle")
            t.setStyleSheet(
                f"font-size: 13px; font-weight: bold; "
                f"background: transparent; color: {theme.c('text')};")
            header.addWidget(t)

            if subtitle:
                s = QLabel(subtitle)
                s.setStyleSheet(
                    f"font-size: 11px; background: transparent; "
                    f"color: {theme.c('text_faint')};")
                header.addWidget(s)

            header.addStretch()
            self._header_layout = header
            self._layout.addLayout(header)
        else:
            self._header_layout = None

    def body(self):
        return self._layout

    def add_header_widget(self, widget):
        if self._header_layout:
            # 插在 stretch 之前
            count = self._header_layout.count()
            self._header_layout.insertWidget(count - 1, widget)


class SectionLabel(QLabel):
    """分区标题（用于表单分组）。"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("SectionTitle")
        self.setStyleSheet(
            f"font-size: 12px; font-weight: bold; "
            f"color: {theme.c('text_dim')}; "
            f"letter-spacing: 0.5px; background: transparent;")