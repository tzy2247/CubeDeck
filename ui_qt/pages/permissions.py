"""权限管理：策略 + 玩家列表 + 命令勾选 + 违规显示。"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QCheckBox, QScrollArea, QWidget,
    QMessageBox, QFrame, QComboBox, QTextEdit, QSplitter,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage
from core.commands import get_commands_for_version
from core.permissions import save_permissions


MODES = [
    ("关闭审计", "off"), ("仅记录", "log"), ("警告玩家", "warn"),
    ("警告+踢出", "kick"), ("警告+封禁", "ban"),
]


class PermissionsPage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self._selected_player = None
        self._check_vars = {}

        # 分帧渲染状态
        self._pending_cmds = []       # [(name, desc, level), ...]
        self._cmd_index = 0
        self._render_timer = None

        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ---- 顶部策略 ----
        top = QFrame()
        top.setObjectName("Card")
        tl = QVBoxLayout(top)
        tl.setContentsMargins(20, 16, 20, 16)
        tl.setSpacing(10)

        title = QLabel("权限审计策略")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 13px; font-weight: bold; "
            f"background: transparent;")
        tl.addWidget(title)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(self._make_label("执法模式", 90))
        self._mode_combo = QComboBox()
        for label, key in MODES:
            self._mode_combo.addItem(label, key)
        self._mode_combo.setFixedHeight(34)
        self._mode_combo.setFixedWidth(120)
        row1.addWidget(self._mode_combo)

        row1.addWidget(self._make_label("窗口(秒)", 70))
        self._window_edit = QLineEdit("300")
        self._window_edit.setFixedWidth(70)
        self._window_edit.setFixedHeight(34)
        row1.addWidget(self._window_edit)

        row1.addWidget(self._make_label("踢出阈值", 70))
        self._kick_edit = QLineEdit("3")
        self._kick_edit.setFixedWidth(60)
        self._kick_edit.setFixedHeight(34)
        row1.addWidget(self._kick_edit)

        row1.addWidget(self._make_label("封禁阈值", 70))
        self._ban_edit = QLineEdit("10")
        self._ban_edit.setFixedWidth(60)
        self._ban_edit.setFixedHeight(34)
        row1.addWidget(self._ban_edit)
        row1.addStretch()
        tl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        save_btn = QPushButton("保存策略")
        save_btn.setObjectName("Accent")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save_policy)
        row2.addWidget(save_btn)

        refresh_btn = QPushButton("刷新玩家")
        refresh_btn.setObjectName("Ghost")
        refresh_btn.setFixedHeight(36)
        refresh_btn.clicked.connect(self._load_players)
        row2.addWidget(refresh_btn)
        row2.addStretch()

        self._policy_status = QLabel("")
        self._policy_status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px; "
            f"background: transparent;")
        row2.addWidget(self._policy_status)
        tl.addLayout(row2)
        root.addWidget(top)

        # ---- 中部：玩家 + 命令 ----
        splitter = QSplitter(Qt.Horizontal)

        left = QFrame()
        left.setObjectName("Card")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 14, 16, 14)
        ctk_lbl = QLabel("玩家")
        ctk_lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-weight: bold; "
            f"background: transparent;")
        ll.addWidget(ctk_lbl)

        self._player_list = QListWidget()
        self._player_list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; }}")
        self._player_list.itemClicked.connect(self._on_player_selected)
        ll.addWidget(self._player_list, 1)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("Card")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 14, 16, 14)

        self._cmd_header = QLabel("允许的命令")
        self._cmd_header.setStyleSheet(
            f"color: {theme.c('text')}; font-weight: bold; "
            f"background: transparent;")
        rl.addWidget(self._cmd_header)

        cmd_scroll = QScrollArea()
        cmd_scroll.setWidgetResizable(True)
        cmd_scroll.setFrameShape(QScrollArea.NoFrame)

        self._cmd_body = QWidget()
        self._cmd_body_layout = QVBoxLayout(self._cmd_body)
        self._cmd_body_layout.setContentsMargins(0, 0, 0, 0)
        self._cmd_body_layout.setSpacing(2)
        self._cmd_body_layout.addStretch()

        cmd_scroll.setWidget(self._cmd_body)
        rl.addWidget(cmd_scroll, 1)

        save_player_btn = QPushButton("保存该玩家的授权")
        save_player_btn.setObjectName("Green")
        save_player_btn.setFixedHeight(38)
        save_player_btn.clicked.connect(self._save_player_commands)
        rl.addWidget(save_player_btn)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        # ---- 底部违规 ----
        bottom = QFrame()
        bottom.setObjectName("Card")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(16, 12, 16, 12)

        btitle = QLabel("实时违规记录")
        btitle.setStyleSheet(
            f"color: {theme.c('text')}; font-weight: bold; "
            f"background: transparent;")
        bl.addWidget(btitle)

        self._violation_box = QTextEdit()
        self._violation_box.setReadOnly(True)
        self._violation_box.setFixedHeight(100)
        bl.addWidget(self._violation_box)
        root.addWidget(bottom)

        self._load_policy()

    def _make_label(self, text, width):
        lbl = QLabel(text)
        lbl.setFixedWidth(width)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 13px; "
            f"background: transparent;")
        return lbl

    # ========================================================
    #  策略
    # ========================================================
    def _load_policy(self):
        d = self.state.perm_data
        mode_key = d.get("enforcement_mode", "log")
        for i, (_, key) in enumerate(MODES):
            if key == mode_key:
                self._mode_combo.setCurrentIndex(i)
                break
        self._window_edit.setText(str(d.get("check_window_seconds", 300)))
        self._kick_edit.setText(str(d.get("violations_to_kick", 3)))
        self._ban_edit.setText(str(d.get("violations_to_ban", 10)))

    def _save_policy(self):
        try:
            window = int(self._window_edit.text())
            kick = int(self._kick_edit.text())
            ban = int(self._ban_edit.text())
        except ValueError:
            QMessageBox.critical(self, "参数错误", "必须是正整数")
            return

        self.state.perm_data.update({
            "enforcement_mode": self._mode_combo.currentData(),
            "check_window_seconds": window,
            "violations_to_kick": kick,
            "violations_to_ban": ban,
        })
        if save_permissions(self.state.perm_data):
            self.state.perm_manager.update_data(self.state.perm_data)
            self.state.log("权限策略已保存", "ok")
            self._policy_status.setText("已保存")

    # ========================================================
    #  玩家列表（异步加载 RCON）
    # ========================================================
    def _load_players(self):
        """先显示本地已授权的玩家，RCON 列表在后台获取。"""
        self._player_list.clear()

        # 1. 立即显示本地缓存的玩家
        local_names = set(self.state.perm_data.get("players", {}).keys())
        for name in sorted(local_names):
            self._add_player_item(name)

        # 2. 后台拉取在线玩家
        if (self.state.rcon_client
                and self.state.rcon_client.connected):
            self._fetch_online_players_async()

    def _fetch_online_players_async(self):
        def worker():
            try:
                resp = self.state.rcon_client.command("list") or ""
                names = []
                if ":" in resp:
                    tail = resp.split(":", 1)[1].strip()
                    if tail:
                        for n in tail.split(","):
                            n = n.strip()
                            if n:
                                names.append(n)
            except Exception:
                names = []

            # 回主线程合并
            QTimer.singleShot(0, lambda: self._merge_online_players(names))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _merge_online_players(self, online_names):
        """把 RCON 返回的玩家合并到现有列表（不重复）。"""
        existing = set()
        for i in range(self._player_list.count()):
            item = self._player_list.item(i)
            existing.add(item.data(Qt.UserRole))

        for name in sorted(online_names):
            if name not in existing:
                self._add_player_item(name)

    def _add_player_item(self, name):
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, name)
        item.setSizeHint(item.sizeHint().__class__(0, 32))
        self._player_list.addItem(item)

    # ========================================================
    #  选中玩家 → 渲染命令列表
    # ========================================================
    def _on_player_selected(self, item):
        self._selected_player = item.data(Qt.UserRole)
        self._start_render_commands()

    def _start_render_commands(self):
        """清空旧控件 + 分帧渲染新控件。"""
        # 停掉上一次的分帧渲染
        if self._render_timer:
            try:
                self._render_timer.stop()
            except Exception:
                pass
            self._render_timer = None

        # 清空
        while self._cmd_body_layout.count():
            it = self._cmd_body_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        self._check_vars.clear()

        player = self._selected_player
        if not player:
            return

        self._cmd_header.setText(f"允许 {player} 使用的命令")
        allowed = set(self.state.perm_data.get("players", {}).get(player, []))
        server_ver = self.state.server_info.version
        cmds_by_level = get_commands_for_version(server_ver)

        # 铺平所有命令，带上等级
        self._pending_cmds = []
        for level in sorted(cmds_by_level.keys()):
            self._pending_cmds.append(("__level__", level, None))
            for cmd_name, desc in cmds_by_level[level]:
                self._pending_cmds.append((cmd_name, desc, level))

        self._allowed = allowed
        self._cmd_index = 0

        # 分帧渲染：每次 8 个
        self._render_chunk()

    def _render_chunk(self, batch=8):
        if self._cmd_index >= len(self._pending_cmds):
            self._cmd_body_layout.addStretch()
            self._render_timer = None
            return

        end = min(self._cmd_index + batch, len(self._pending_cmds))
        for i in range(self._cmd_index, end):
            name, desc, level = self._pending_cmds[i]
            if name == "__level__":
                title = QLabel(f"权限等级 {desc}")
                title.setStyleSheet(
                    f"color: {theme.c('accent')}; "
                    f"font-size: 12px; font-weight: bold; "
                    f"padding: 8px 0 2px 0; background: transparent;")
                self._cmd_body_layout.addWidget(title)
            else:
                cb = QCheckBox(f"/{name}  ·  {desc}")
                cb.setChecked(name in self._allowed)
                cb.setStyleSheet(
                    f"color: {theme.c('text')}; font-size: 12px; "
                    f"background: transparent;")
                self._check_vars[name] = cb
                self._cmd_body_layout.addWidget(cb)

        self._cmd_index = end

        # 下一批延迟 15ms，让 UI 处理事件
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_chunk)
        self._render_timer.start(15)

    # ========================================================
    #  保存
    # ========================================================
    def _save_player_commands(self):
        if not self._selected_player:
            return
        chosen = [k for k, cb in self._check_vars.items() if cb.isChecked()]
        self.state.perm_data.setdefault("players", {})[
            self._selected_player] = chosen
        if save_permissions(self.state.perm_data):
            self.state.perm_manager.update_data(self.state.perm_data)
            self.state.log(
                f"已保存 {self._selected_player} 的授权（{len(chosen)} 条）",
                "ok")

    # ========================================================
    #  违规
    # ========================================================
    def append_violation(self, line):
        import time
        ts = time.strftime("%H:%M:%S")
        self._violation_box.append(f"[{ts}] {line}")

    # ========================================================
    #  生命周期
    # ========================================================
    def on_show(self):
        # 策略读取很快，直接同步
        self._load_policy()
        # 玩家列表异步加载，不阻塞 UI
        QTimer.singleShot(30, self._load_players)