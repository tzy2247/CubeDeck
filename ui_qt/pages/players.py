"""玩家管理：在线列表 + 快捷操作。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QMessageBox, QFrame,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage
from ui_qt.widgets.card import Card
from ui_qt.dialogs.player_detail import PlayerDetailDialog


class PlayersPage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self._build()
        state.rcon_connected.connect(self.refresh)
        state.server_stopped.connect(self._on_server_stopped)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ---- 顶部 ----
        top = QHBoxLayout()
        title = QLabel("在线玩家")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 16px; font-weight: bold;")
        top.addWidget(title)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px;")
        top.addWidget(self._count_label)
        top.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("Ghost")
        refresh_btn.setFixedHeight(36)
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(refresh_btn)
        root.addLayout(top)

        # ---- 列表 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, 1)

        self._show_empty("点击「刷新」加载在线玩家")

    def _clear_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_empty(self, text):
        self._clear_list()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 13px; "
            f"padding: 40px;")
        self._list_layout.addWidget(lbl)
        self._list_layout.addStretch()

    # ========================================================
    #  数据
    # ========================================================
    def refresh(self):
        if not (self.state.rcon_client and self.state.rcon_client.connected):
            self._show_empty("RCON 未连接")
            return
        self._count_label.setText("读取中…")
        self.state.quick_rcon("list", on_done=self._on_list_result)

    def _on_list_result(self, resp):
        names = []
        if resp and ":" in resp:
            tail = resp.split(":", 1)[1].strip()
            if tail:
                names = [n.strip() for n in tail.split(",") if n.strip()]

        self._clear_list()
        if not names:
            self._show_empty("当前没有在线玩家")
            self._count_label.setText("")
            return

        self._count_label.setText(f"共 {len(names)} 人")
        for name in names:
            self._list_layout.addWidget(self._make_player_row(name))
        self._list_layout.addStretch()

    def _make_player_row(self, name):
        row = QFrame()
        row.setObjectName("Card")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(16, 10, 16, 10)
        rl.setSpacing(10)

        icon = QLabel("🎮")
        icon.setStyleSheet(
            f"color: {theme.c('accent')}; font-size: 18px;")
        rl.addWidget(icon)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        rl.addWidget(name_lbl)
        rl.addStretch()

        def qc(cmd, refresh_after=True):
            self.state.quick_rcon(cmd)
            if refresh_after:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(800, self.refresh)

        for label, obj_name, cmd in (
            ("击杀", "Danger", f"kill {name}"),
            ("踢出", "Orange", f"kick {name}"),
            ("封禁", "Red", f"ban {name}"),
            ("OP", "Green", f"op {name}"),
        ):
            btn = QPushButton(label)
            btn.setObjectName(obj_name)
            btn.setFixedSize(60, 30)
            btn.clicked.connect(lambda _=False, c=cmd: qc(c))
            rl.addWidget(btn)

        detail_btn = QPushButton("详情")
        detail_btn.setObjectName("Accent")
        detail_btn.setFixedSize(96, 30)
        detail_btn.clicked.connect(lambda: self._open_detail(name))
        rl.addWidget(detail_btn)

        return row

    def _open_detail(self, name):
        dlg = PlayerDetailDialog(self.state, name, self)
        dlg.exec()

    def _on_server_stopped(self):
        self._show_empty("服务器未运行")

    def on_show(self):
        self.refresh()

    def on_rcon_connected(self):
        self.refresh()