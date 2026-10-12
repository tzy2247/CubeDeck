"""侧边栏的服务器切换选择器。"""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
)

from ui_qt.theme import theme
from core import server_registry as registry


class ServerSelector(QWidget):
    """服务器切换下拉框。"""

    server_changed = Signal(str)   # server_id

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._build()
        self.reload()

        # ★ 注册到 theme，主题切换时自动刷新内联样式
        theme.register(self.apply_theme)
        # 首次应用
        self.apply_theme()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 标签
        self._label = QLabel("当前服务器")
        layout.addWidget(self._label)

        # 下拉框
        self._combo = QComboBox()
        self._combo.setFixedHeight(36)
        self._combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self._combo)

    # ========================================================
    def apply_theme(self):
        """刷新内联样式（主题切换时调用）。"""
        try:
            self._label.setStyleSheet(
                f"color: {theme.c('text_faint')}; font-size: 11px; "
                f"background: transparent;")
        except Exception:
            pass

        try:
            self._combo.setStyleSheet(
                f"QComboBox {{ "
                f"background-color: {theme.c('input_bg')}; "
                f"color: {theme.c('input_text')}; "
                f"border: 1px solid {theme.c('border')}; "
                f"border-radius: 8px; padding: 4px 10px; font-size: 13px; }}"
                f"QComboBox:hover {{ border-color: {theme.c('accent')}; }}"
                f"QComboBox::drop-down {{ border: none; width: 22px; }}"
                f"QComboBox QAbstractItemView {{ "
                f"background-color: {theme.c('card')}; "
                f"color: {theme.c('text')}; "
                f"border: 1px solid {theme.c('border')}; "
                f"selection-background-color: {theme.c('accent')}; }}")
        except Exception:
            pass

    # ========================================================
    def reload(self):
        """从注册表重新加载服务器列表。"""
        self._combo.blockSignals(True)
        self._combo.clear()

        servers = registry.list_servers()
        active_id = self.state.server_id

        if not servers:
            self._combo.addItem("（无服务器）", "")
            self._combo.setEnabled(False)
            self._combo.blockSignals(False)
            return

        self._combo.setEnabled(True)
        for s in servers:
            name = s.get("name", s["id"])
            self._combo.addItem(name, s["id"])

        for i in range(self._combo.count()):
            if self._combo.itemData(i) == active_id:
                self._combo.setCurrentIndex(i)
                break

        self._combo.blockSignals(False)

    def _on_changed(self, idx):
        server_id = self._combo.itemData(idx)
        if not server_id or server_id == self.state.server_id:
            return
        self.server_changed.emit(server_id)