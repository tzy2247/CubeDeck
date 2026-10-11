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

        self._pending_cmds = []
        self._cmd_index = 0
        self._render_timer = None

        self._level_boxes = {}
        self._level_overrides = {}
        self._bulk_state = None

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
        refresh_btn.clicked.connect(self._on_refresh_clicked)
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

        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        self._cmd_header = QLabel("允许的命令")
        self._cmd_header.setStyleSheet(
            f"color: {theme.c('text')}; font-weight: bold; "
            f"background: transparent;")
        header_row.addWidget(self._cmd_header)
        header_row.addStretch()

        self._select_all_btn = QPushButton("全选")
        self._select_all_btn.setObjectName("Ghost")
        self._select_all_btn.setFixedHeight(28)
        self._select_all_btn.setMinimumWidth(60)
        self._select_all_btn.setProperty("action", "select_all")
        self._select_all_btn.clicked.connect(self._on_action_button)
        header_row.addWidget(self._select_all_btn)

        self._unselect_all_btn = QPushButton("全不选")
        self._unselect_all_btn.setObjectName("Ghost")
        self._unselect_all_btn.setFixedHeight(28)
        self._unselect_all_btn.setMinimumWidth(70)
        self._unselect_all_btn.setProperty("action", "unselect_all")
        self._unselect_all_btn.clicked.connect(self._on_action_button)
        header_row.addWidget(self._unselect_all_btn)

        rl.addLayout(header_row)

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
    #  统一按钮事件
    # ========================================================
    def _on_action_button(self, checked=False):
        try:
            sender = self.sender()
            if sender is None:
                return

            action = sender.property("action")
            level = sender.property("level")

            if action == "select_all":
                self._select_all()
            elif action == "unselect_all":
                self._unselect_all()
            elif action == "level_select":
                self._select_level(level, True)
            elif action == "level_unselect":
                self._select_level(level, False)
        except Exception:
            import traceback
            QMessageBox.critical(
                self, "按钮事件出错", traceback.format_exc())

    def _on_refresh_clicked(self, checked=False):
        try:
            self._load_players()
        except Exception:
            import traceback
            QMessageBox.critical(self, "刷新出错",
                                 traceback.format_exc())

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

    def _save_policy(self, checked=False):
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
    #  玩家列表
    # ========================================================
    def _load_players(self):
        self._player_list.clear()
        shown = set()

        for name in self.state.perm_data.get("known_players", []):
            if name not in shown:
                self._add_player_item(name)
                shown.add(name)

        for name in self.state.perm_data.get("players", {}).keys():
            if name not in shown:
                self._add_player_item(name)
                shown.add(name)

        for name in self.state.perm_data.get("whitelist_players", []):
            if name not in shown:
                self._add_player_item(name)
                shown.add(name)

        if (self.state.rcon_client
                and self.state.rcon_client.connected):
            try:
                resp = self.state.rcon_client.command("list") or ""
                online_names = self._parse_list_response(resp)
                for name in online_names:
                    if name not in shown:
                        self._add_player_item(name)
                        shown.add(name)

                if online_names:
                    self.state.log(
                        f"RCON 在线玩家：{', '.join(online_names)}",
                        "info")
            except Exception as e:
                self.state.log(f"获取在线玩家失败：{e}", "warn")

    @staticmethod
    def _parse_list_response(resp: str):
        import re as _re
        clean = _re.sub(r"§.", "", resp)

        if ":" not in clean:
            return []
        tail = clean.split(":", 1)[1].strip()
        if not tail:
            return []

        names = []
        for n in tail.split(","):
            n = n.strip()
            if n:
                names.append(n)
        return names

    def _add_player_item(self, name):
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, name)
        item.setSizeHint(item.sizeHint().__class__(0, 32))
        self._player_list.addItem(item)

    # ========================================================
    #  选中玩家 → 渲染命令
    # ========================================================
    def _on_player_selected(self, item):
        self._selected_player = item.data(Qt.UserRole)
        self._start_render_commands()

    def _start_render_commands(self):
        if self._render_timer:
            try:
                self._render_timer.stop()
            except Exception:
                pass
            self._render_timer = None

        while self._cmd_body_layout.count():
            it = self._cmd_body_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        self._check_vars.clear()
        self._level_boxes.clear()
        self._level_overrides.clear()
        self._bulk_state = None

        player = self._selected_player
        if not player:
            return

        self._cmd_header.setText(f"允许 {player} 使用的命令")
        allowed = set(self.state.perm_data.get("players", {}).get(player, []))
        server_ver = self.state.server_info.version
        cmds_by_level = get_commands_for_version(server_ver)

        self._pending_cmds = []
        for level in sorted(cmds_by_level.keys()):
            # ★ 元组结构是 (name, desc, level)
            #    等级标记行：name="__level__", desc=None, level=真实等级
            self._pending_cmds.append(("__level__", None, level))
            for cmd_name, desc in cmds_by_level[level]:
                self._pending_cmds.append((cmd_name, desc, level))

        self._allowed = allowed
        self._cmd_index = 0
        self._render_chunk()

    def _render_chunk(self, batch=8):
        if self._cmd_index >= len(self._pending_cmds):
            self._cmd_body_layout.addStretch()
            self._render_timer = None
            self._bulk_state = None
            return

        end = min(self._cmd_index + batch, len(self._pending_cmds))
        for i in range(self._cmd_index, end):
            name, desc, level = self._pending_cmds[i]
            if name == "__level__":
                self._render_level_header(level)
            else:
                self._render_command(name, desc, level)

        self._cmd_index = end

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_chunk)
        self._render_timer.start(15)

    def _render_level_header(self, level):
        """渲染等级标题行 + 本等级全选/全不选按钮。"""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 8, 0, 2)
        row.setSpacing(6)

        lbl = QLabel(f"权限等级 {level}")
        lbl.setStyleSheet(
            f"color: {theme.c('accent')}; "
            f"font-size: 12px; font-weight: bold; "
            f"background: transparent;")
        row.addWidget(lbl)
        row.addStretch()

        btn_all = QPushButton("本等级全选")
        btn_all.setObjectName("Ghost")
        btn_all.setFixedHeight(26)
        btn_all.setMinimumWidth(
            btn_all.fontMetrics().horizontalAdvance("本等级全选") + 24)
        btn_all.setProperty("action", "level_select")
        btn_all.setProperty("level", str(level))
        btn_all.clicked.connect(self._on_action_button)
        row.addWidget(btn_all)

        btn_none = QPushButton("本等级全不选")
        btn_none.setObjectName("Ghost")
        btn_none.setFixedHeight(26)
        btn_none.setMinimumWidth(
            btn_none.fontMetrics().horizontalAdvance("本等级全不选") + 24)
        btn_none.setProperty("action", "level_unselect")
        btn_none.setProperty("level", str(level))
        btn_none.clicked.connect(self._on_action_button)
        row.addWidget(btn_none)

        self._cmd_body_layout.addWidget(container)

    def _render_command(self, name, desc, level):
        cb = QCheckBox(f"/{name}  ·  {desc}")
        cb.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 12px; "
            f"background: transparent;")

        level_key = str(level)
        cb.setProperty("cmd_name", name)
        cb.setProperty("cmd_level", level_key)

        if self._bulk_state is not None:
            cb.setChecked(self._bulk_state)
        elif level_key in self._level_overrides:
            cb.setChecked(self._level_overrides[level_key])
        else:
            cb.setChecked(name in self._allowed)

        self._check_vars[name] = cb
        self._level_boxes.setdefault(level_key, []).append(cb)
        self._cmd_body_layout.addWidget(cb)

    # ========================================================
    #  全选 / 全不选 / 按等级
    # ========================================================
    def _select_all(self):
        for cb in self._check_vars.values():
            cb.setChecked(True)
        if self._render_timer is not None:
            self._bulk_state = True
        self.state.log(
            f"[权限] 全选（{len(self._check_vars)} 条）", "info")

    def _unselect_all(self):
        for cb in self._check_vars.values():
            cb.setChecked(False)
        if self._render_timer is not None:
            self._bulk_state = False
        self.state.log(
            f"[权限] 全不选（{len(self._check_vars)} 条）", "info")

    def _select_level(self, level, checked):
        """切换指定等级下的所有命令。"""
        level_key = str(level)

        # 主路径：按 _level_boxes 字典匹配
        boxes = list(self._level_boxes.get(level_key, []))

        # 兜底：遍历所有 checkbox 的 cmd_level 属性
        if not boxes:
            for cb in self._check_vars.values():
                if str(cb.property("cmd_level")) == level_key:
                    boxes.append(cb)

        for cb in boxes:
            cb.setChecked(checked)

        self._level_overrides[level_key] = checked
        self.state.log(
            f"[权限] 等级 {level_key} → "
            f"{'全选' if checked else '全不选'}"
            f"（{len(boxes)} 条）", "info")

    # ========================================================
    #  保存玩家授权
    # ========================================================
    def _save_player_commands(self, checked=False):
        if not self._selected_player:
            QMessageBox.warning(self, "提示", "请先在左侧选择一位玩家。")
            return

        chosen = [k for k, cb in self._check_vars.items()
                  if cb.isChecked()]

        reply = QMessageBox.question(
            self, "保存授权确认",
            f"即将为玩家「{self._selected_player}」保存授权：\n\n"
            f"已勾选命令：{len(chosen)} 条\n"
            f"总命令数：{len(self._check_vars)} 条\n\n"
            f"是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes)
        if reply != QMessageBox.Yes:
            return

        self.state.perm_data.setdefault("players", {})[
            self._selected_player] = chosen

        if save_permissions(self.state.perm_data):
            self.state.perm_manager.update_data(self.state.perm_data)
            self.state.log(
                f"已保存 {self._selected_player} 的授权（{len(chosen)} 条）",
                "ok")

            QMessageBox.information(
                self, "保存成功",
                f"玩家「{self._selected_player}」的授权已保存。\n\n"
                f"共 {len(chosen)} 条命令已授权。")
        else:
            QMessageBox.critical(
                self, "保存失败",
                "无法写入权限文件，请检查数据目录的写入权限。")

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
        self._load_policy()
        QTimer.singleShot(30, self._load_players)