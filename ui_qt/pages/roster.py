"""名单管理：白名单 / 封禁玩家 / 封禁 IP。"""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QTabWidget, QWidget, QMessageBox,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage


class RosterPage(BasePage):
    CONFIGS = [
        ("whitelist",  "whitelist.json",      "whitelist add",
         "whitelist remove", "白名单"),
        ("ban",        "banned-players.json", "ban",
         "pardon",          "封禁玩家"),
        ("banip",      "banned-ips.json",     "ban-ip",
         "pardon-ip",       "封禁 IP"),
    ]

    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self._tabs_data = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        for key, jf, add_cmd, rm_cmd, title in self.CONFIGS:
            w = self._make_tab(key, jf, add_cmd, rm_cmd)
            tabs.addTab(w, title)
        root.addWidget(tabs)

    def _make_tab(self, key, json_file, add_cmd, rm_cmd):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        row = QHBoxLayout()
        entry = QLineEdit()
        entry.setPlaceholderText("输入玩家名或 IP…")
        entry.setFixedHeight(38)
        entry.returnPressed.connect(
            lambda: self._add(key, entry, add_cmd))
        row.addWidget(entry, 1)

        add_btn = QPushButton("添加")
        add_btn.setObjectName("Accent")
        add_btn.setFixedHeight(38)
        add_btn.clicked.connect(lambda: self._add(key, entry, add_cmd))
        row.addWidget(add_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("Ghost")
        refresh_btn.setFixedHeight(38)
        refresh_btn.clicked.connect(self.refresh)
        row.addWidget(refresh_btn)
        layout.addLayout(row)

        lst = QListWidget()
        layout.addWidget(lst, 1)

        self._tabs_data[key] = {
            "json_file": json_file,
            "remove_cmd": rm_cmd,
            "list": lst,
        }
        return w

    def _add(self, key, entry, add_cmd):
        name = entry.text().strip()
        if not name:
            return
        entry.clear()
        self.state.quick_rcon(f"{add_cmd} {name}",
                              on_done=lambda _: self._delay_refresh())
        self.state.log(f"添加 {name} 到 {add_cmd}", "ok")

    def _delay_refresh(self):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(800, self.refresh)

    def refresh(self):
        for key, info in self._tabs_data.items():
            jf = info["json_file"]
            lst = info["list"]
            lst.clear()

            path = self.state.server_path / jf
            if not path.exists():
                lst.addItem(f"（{jf} 不存在）")
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                lst.addItem(f"读取失败：{e}")
                continue

            if not data:
                lst.addItem("（空）")
                continue

            for entry in data:
                name = entry.get("name") or entry.get("ip") or "?"
                reason = entry.get("reason", "")
                text = f"{name}"
                if reason:
                    text += f"   ·   {reason}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, name)
                lst.addItem(item)

            # 双击移除
            lst.itemDoubleClicked.connect(
                lambda item, k=key: self._remove(k, item))

    def _remove(self, key, item):
        name = item.data(Qt.UserRole)
        if not name:
            return
        info = self._tabs_data[key]
        reply = QMessageBox.question(
            self, "移除", f"确定要移除 {name} 吗？")
        if reply != QMessageBox.Yes:
            return
        self.state.quick_rcon(f"{info['remove_cmd']} {name}",
                              on_done=lambda _: self._delay_refresh())

    def on_show(self):
        self.refresh()

    def on_rcon_connected(self):
        self.refresh()