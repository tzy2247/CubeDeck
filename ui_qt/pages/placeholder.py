"""占位页：尚未迁移的页面用它保持 UI 完整。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ui_qt.pages.base import BasePage


class PlaceholderPage(BasePage):
    def __init__(self, state, title="页面", parent=None):
        super().__init__(state, parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        lbl = QLabel(f"「{title}」正在迁移中…")
        lbl.setStyleSheet("font-size: 18px; color: #8b93a7;")
        layout.addWidget(lbl)

        sub = QLabel("已备份，下一轮补齐")
        sub.setStyleSheet("font-size: 13px; color: #5d6577;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)