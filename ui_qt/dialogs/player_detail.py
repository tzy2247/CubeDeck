"""玩家详情对话框：背包 / 传送 / Buff / 操作。"""
import re
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QScrollArea, QLineEdit, QComboBox,
    QMessageBox, QFrame,
)

from ui_qt.theme import theme


# 槽位列表（0-8 快捷栏 / 9-35 背包 / 36-39 装备 / 40 副手）
SLOT_NAMES = (
    [f"hotbar.{i}" for i in range(9)]
    + [f"inventory.{i}" for i in range(27)]
    + ["armor.head", "armor.chest", "armor.legs", "armor.feet"]
    + ["weapon.offhand"]
)
SLOT_LABELS = (
    [f"快捷栏 {i+1}" for i in range(9)]
    + [f"背包 {i+1}" for i in range(27)]
    + ["头盔", "胸甲", "护腿", "靴子", "副手"]
)

EFFECTS = [
    ("speed", "速度"), ("slowness", "缓慢"),
    ("haste", "急迫"), ("strength", "力量"),
    ("jump_boost", "跳跃提升"), ("regeneration", "生命恢复"),
    ("resistance", "抗性提升"), ("fire_resistance", "防火"),
    ("water_breathing", "水下呼吸"), ("invisibility", "隐身"),
    ("night_vision", "夜视"), ("hunger", "饥饿"),
    ("weakness", "虚弱"), ("poison", "中毒"),
    ("wither", "凋零"), ("health_boost", "生命提升"),
    ("absorption", "伤害吸收"), ("saturation", "饱和"),
    ("glowing", "发光"), ("levitation", "漂浮"),
    ("slow_falling", "缓降"), ("darkness", "黑暗"),
]

DIMENSIONS = [
    ("minecraft:overworld", "主世界"),
    ("minecraft:the_nether", "下界"),
    ("minecraft:the_end", "末地"),
]


class PlayerDetailDialog(QDialog):
    def __init__(self, state, player, parent=None):
        super().__init__(parent)
        self.state = state
        self.player = player
        self._slot_items = {}
        self._slot_labels = {}
        self._inv_merged = {}

        self.setWindowTitle(f"玩家详情 · {player}")
        self.resize(920, 720)
        self._build()

        QTimer.singleShot(150, self._reload_inventory)
        QTimer.singleShot(200, self._load_online_players)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # 头部
        header = QHBoxLayout()
        title = QLabel(f"🎮   {self.player}")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("Ghost")
        close_btn.setFixedSize(36, 36)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        root.addLayout(header)

        # Tab
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_inventory_tab(), "🎒  背包")
        self.tabs.addTab(self._build_teleport_tab(), "🧭  传送")
        self.tabs.addTab(self._build_buff_tab(), "✨  Buff")
        self.tabs.addTab(self._build_actions_tab(), "⚡  操作")
        root.addWidget(self.tabs, 1)

    # ========================================================
    #  背包 Tab
    # ========================================================
    def _build_inventory_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self._inv_status = QLabel("点击「刷新」读取背包")
        self._inv_status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px;")
        top.addWidget(self._inv_status)
        top.addStretch()

        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.setObjectName("Accent")
        refresh_btn.setFixedHeight(34)
        refresh_btn.clicked.connect(self._reload_inventory)
        top.addWidget(refresh_btn)

        clear_btn = QPushButton("🧹  清空背包")
        clear_btn.setObjectName("Danger")
        clear_btn.setFixedHeight(34)
        clear_btn.clicked.connect(self._clear_whole_inventory)
        top.addWidget(clear_btn)

        layout.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)

        for i, (slot_name, label) in enumerate(zip(SLOT_NAMES, SLOT_LABELS)):
            if i in (0, 9, 36, 40):
                titles = {0: "快捷栏", 9: "背包", 36: "装备", 40: "副手"}
                title_lbl = QLabel(titles[i])
                title_lbl.setStyleSheet(
                    f"color: {theme.c('accent')}; "
                    f"font-size: 12px; font-weight: bold; "
                    f"padding: 6px 4px 2px 4px;")
                bl.addWidget(title_lbl)

            bl.addWidget(self._make_slot_row(slot_name, label))

        bl.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        return w

    def _make_slot_row(self, slot_name, label):
        row = QFrame()
        row.setObjectName("Card")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 8, 12, 8)
        rl.setSpacing(10)

        name_lbl = QLabel(label)
        name_lbl.setFixedWidth(90)
        name_lbl.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px;")
        rl.addWidget(name_lbl)

        value_lbl = QLabel("— 空 —")
        value_lbl.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 13px;")
        rl.addWidget(value_lbl, 1)
        self._slot_labels[slot_name] = value_lbl

        edit_btn = QPushButton("编辑")
        edit_btn.setObjectName("Accent")
        edit_btn.setFixedSize(60, 28)
        edit_btn.clicked.connect(lambda: self._edit_slot(slot_name, label))
        rl.addWidget(edit_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("Ghost")
        clear_btn.setFixedSize(60, 28)
        clear_btn.clicked.connect(
            lambda: self._write_slot(slot_name, label, "", 0))
        rl.addWidget(clear_btn)

        return row

    def _edit_slot(self, slot_name, label):
        from ui_qt.dialogs.item_edit import ItemEditDialog
        cur = self._slot_items.get(slot_name, ("", 1))
        dlg = ItemEditDialog(self, label, cur[0], cur[1])
        if dlg.exec() == QDialog.Accepted:
            item_id, count = dlg.result_item()
            self._write_slot(slot_name, label, item_id, count)

    def _write_slot(self, slot_name, label, item_id, count):
        if item_id:
            cmd = (f"item replace entity {self.player} {slot_name} "
                   f"with {item_id} {count}")
        else:
            cmd = f"item replace entity {self.player} {slot_name} with air 1"
        self.state.quick_rcon(cmd,
                              on_done=lambda _: self._reload_inventory())

    def _clear_whole_inventory(self):
        reply = QMessageBox.question(
            self, "清空背包", f"确定要清空 {self.player} 的全部物品吗？")
        if reply != QMessageBox.Yes:
            return
        self.state.quick_rcon(f"clear {self.player}",
                              on_done=lambda _: self._reload_inventory())

    def _reload_inventory(self):
        self._inv_status.setText("读取中…")
        self._inv_merged = {}

        def cb_inv(resp):
            self._inv_merged.update(self._parse_inventory(resp))
            if self.state.server_info.has("equipment_field"):
                self.state.quick_rcon(
                    f"data get entity {self.player} equipment",
                    on_done=cb_equip)
            else:
                self._finish_inventory()

        def cb_equip(resp):
            self._inv_merged.update(self._parse_equipment(resp))
            self._finish_inventory()

        self.state.quick_rcon(
            f"data get entity {self.player} Inventory",
            on_done=cb_inv)

    def _finish_inventory(self):
        self._slot_items = dict(self._inv_merged)
        for slot_name, lbl in self._slot_labels.items():
            entry = self._slot_items.get(slot_name)
            if entry:
                iid, cnt = entry
                short = iid.replace("minecraft:", "")
                lbl.setText(f"{short}   ×{cnt}")
                lbl.setStyleSheet(
                    f"color: {theme.c('text')}; font-size: 13px;")
            else:
                lbl.setText("— 空 —")
                lbl.setStyleSheet(
                    f"color: {theme.c('text_faint')}; font-size: 13px;")
        self._inv_status.setText(
            f"✔ 已读取 {len(self._slot_items)} 个物品")

    @staticmethod
    def _parse_inventory(resp):
        result = {}
        if not resp:
            return result
        start = resp.find("[")
        end = resp.rfind("]")
        if start == -1 or end == -1:
            return result
        body = resp[start + 1:end]

        # 顶层切分
        depth = 0
        in_quote = False
        buf = []
        parts = []
        for i, ch in enumerate(body):
            if ch == '"' and (i == 0 or body[i - 1] != "\\"):
                in_quote = not in_quote
            if in_quote:
                buf.append(ch)
                continue
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        if buf:
            parts.append("".join(buf))

        # 槽位映射
        idx_map = {i: i for i in range(36)}
        idx_map.update({100: 39, 101: 38, 102: 37, 103: 36, -106: 40})

        for item_str in parts:
            slot_m = re.search(r'\bSlot:\s*(-?\d+)b', item_str)
            if not slot_m:
                continue
            after = item_str[slot_m.end():]
            id_m = re.search(r'\bid:\s*"([^"]+)"', after)
            if not id_m:
                continue
            before = item_str[:slot_m.start()]
            counts = re.findall(r'\bcount:\s*(\d+)', before)
            cnt = int(counts[-1]) if counts else 1
            try:
                nbt_slot = int(slot_m.group(1))
            except ValueError:
                continue
            idx = idx_map.get(nbt_slot)
            if idx is None:
                continue
            result[SLOT_NAMES[idx]] = (id_m.group(1), cnt)
        return result

    @staticmethod
    def _parse_equipment(resp):
        result = {}
        if not resp or "entity data" not in resp:
            return result
        for field, slot in (
            ("head", "armor.head"), ("chest", "armor.chest"),
            ("legs", "armor.legs"), ("feet", "armor.feet"),
            ("offhand", "weapon.offhand"),
        ):
            m = re.search(rf'\b{field}:\s*\{{', resp)
            if not m:
                continue
            sub = resp[m.end():m.end() + 500]
            id_m = re.search(r'\bid:\s*"([^"]+)"', sub)
            if not id_m:
                continue
            cnt_m = re.search(r'\bcount:\s*(\d+)', sub)
            result[slot] = (id_m.group(1),
                            int(cnt_m.group(1)) if cnt_m else 1)
        return result

    # ========================================================
    #  传送 Tab
    # ========================================================
    def _build_teleport_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # 随机传送
        c1 = QFrame()
        c1.setObjectName("Card")
        l1 = QVBoxLayout(c1)
        title1 = QLabel("🎲  随机安全传送")
        title1.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        l1.addWidget(title1)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("最小半径"))
        self._tp_min = QLineEdit("100")
        self._tp_min.setFixedWidth(80)
        row1.addWidget(self._tp_min)
        row1.addWidget(QLabel("最大半径"))
        self._tp_max = QLineEdit("2000")
        self._tp_max.setFixedWidth(80)
        row1.addWidget(self._tp_max)
        row1.addStretch()
        l1.addLayout(row1)

        btn1 = QPushButton("传送到随机安全点")
        btn1.setObjectName("Accent")
        btn1.setFixedHeight(38)
        btn1.clicked.connect(self._tp_random)
        l1.addWidget(btn1)
        layout.addWidget(c1)

        # 玩家互传
        c2 = QFrame()
        c2.setObjectName("Card")
        l2 = QVBoxLayout(c2)
        title2 = QLabel("👥  传送到其他玩家")
        title2.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        l2.addWidget(title2)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("目标玩家"))
        self._tp_target = QComboBox()
        self._tp_target.addItem("加载中…")
        row2.addWidget(self._tp_target, 1)
        l2.addLayout(row2)

        btn2 = QPushButton(f"把 {self.player} 传送到目标玩家")
        btn2.setObjectName("Accent")
        btn2.setFixedHeight(38)
        btn2.clicked.connect(self._tp_to_player)
        l2.addWidget(btn2)
        layout.addWidget(c2)

        # 定点
        c3 = QFrame()
        c3.setObjectName("Card")
        l3 = QVBoxLayout(c3)
        title3 = QLabel("📍  多维度定点传送")
        title3.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        l3.addWidget(title3)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("维度"))
        self._tp_dim = QComboBox()
        for dim, cn in DIMENSIONS:
            self._tp_dim.addItem(cn, dim)
        row3.addWidget(self._tp_dim, 1)
        l3.addLayout(row3)

        row4 = QHBoxLayout()
        for label, attr, default in (("X", "_tp_x", "0"),
                                      ("Y", "_tp_y", "64"),
                                      ("Z", "_tp_z", "0")):
            row4.addWidget(QLabel(label))
            e = QLineEdit(default)
            e.setFixedWidth(80)
            setattr(self, attr, e)
            row4.addWidget(e)
        row4.addStretch()
        l3.addLayout(row4)

        btn3 = QPushButton("传送到指定坐标")
        btn3.setObjectName("Accent")
        btn3.setFixedHeight(38)
        btn3.clicked.connect(self._tp_coords)
        l3.addWidget(btn3)
        layout.addWidget(c3)

        layout.addStretch()
        return w

    def _tp_random(self):
        try:
            rmin = int(self._tp_min.text())
            rmax = int(self._tp_max.text())
            if rmax <= rmin:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "参数错误",
                                "半径必须是整数，最大值 > 最小值")
            return
        cmd = f"spreadplayers ~ ~ {rmin} {rmax} under 320 false {self.player}"
        self.state.quick_rcon(cmd)

    def _tp_to_player(self):
        target = self._tp_target.currentText()
        if not target or target.startswith("（"):
            QMessageBox.warning(self, "提示", "没有可用的目标玩家")
            return
        self.state.quick_rcon(f"tp {self.player} {target}")

    def _tp_coords(self):
        dim = self._tp_dim.currentData() or "minecraft:overworld"
        try:
            x = self._tp_x.text().strip() or "0"
            y = self._tp_y.text().strip() or "64"
            z = self._tp_z.text().strip() or "0"
            float(x); float(y); float(z)
        except ValueError:
            QMessageBox.warning(self, "参数错误", "坐标必须是数字")
            return
        cmd = f"execute in {dim} run tp {self.player} {x} {y} {z}"
        self.state.quick_rcon(cmd)

    def _load_online_players(self):
        def cb(resp):
            self._tp_target.clear()
            names = []
            if resp and ":" in resp:
                tail = resp.split(":", 1)[1].strip()
                if tail:
                    names = [n.strip() for n in tail.split(",")
                             if n.strip() and n.strip() != self.player]
            if not names:
                self._tp_target.addItem("（无其他在线玩家）")
            else:
                for n in names:
                    self._tp_target.addItem(n)
        self.state.quick_rcon("list", on_done=cb)

    # ========================================================
    #  Buff Tab
    # ========================================================
    def _build_buff_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setSpacing(10)

        title = QLabel("✨  给予效果")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        cl.addWidget(title)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("效果"))
        self._eff_combo = QComboBox()
        for key, cn in EFFECTS:
            self._eff_combo.addItem(f"{cn}  ({key})", key)
        row1.addWidget(self._eff_combo, 1)
        cl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("时长(秒)"))
        self._eff_dur = QLineEdit("30")
        self._eff_dur.setFixedWidth(80)
        row2.addWidget(self._eff_dur)
        row2.addWidget(QLabel("倍率"))
        self._eff_amp = QLineEdit("0")
        self._eff_amp.setFixedWidth(80)
        row2.addWidget(self._eff_amp)
        row2.addStretch()
        cl.addLayout(row2)

        btn_row = QHBoxLayout()
        apply_btn = QPushButton("✨  施加效果")
        apply_btn.setObjectName("Green")
        apply_btn.setFixedHeight(42)
        apply_btn.clicked.connect(self._apply_effect)
        btn_row.addWidget(apply_btn, 1)

        clear_btn = QPushButton("🚫  清除全部效果")
        clear_btn.setObjectName("Red")
        clear_btn.setFixedHeight(42)
        clear_btn.clicked.connect(
            lambda: self.state.quick_rcon(f"effect clear {self.player}"))
        btn_row.addWidget(clear_btn, 1)
        cl.addLayout(btn_row)

        layout.addWidget(card)
        layout.addStretch()
        return w

    def _apply_effect(self):
        effect = self._eff_combo.currentData()
        if not effect:
            return
        try:
            dur = int(self._eff_dur.text())
            amp = int(self._eff_amp.text())
            if dur < 1 or amp < 0 or amp > 255:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "参数错误", "时长/倍率无效")
            return
        self.state.quick_rcon(
            f"effect give {self.player} {effect} {dur} {amp}")

    # ========================================================
    #  操作 Tab
    # ========================================================
    def _build_actions_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # 私信
        c1 = QFrame()
        c1.setObjectName("Card")
        l1 = QVBoxLayout(c1)
        t1 = QLabel("💬  服务器私信")
        t1.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        l1.addWidget(t1)

        row = QHBoxLayout()
        self._msg_entry = QLineEdit()
        self._msg_entry.setPlaceholderText("输入消息…")
        self._msg_entry.setFixedHeight(38)
        self._msg_entry.returnPressed.connect(self._send_msg)
        row.addWidget(self._msg_entry, 1)

        send_btn = QPushButton("发送")
        send_btn.setObjectName("Accent")
        send_btn.setFixedSize(80, 38)
        send_btn.clicked.connect(self._send_msg)
        row.addWidget(send_btn)
        l1.addLayout(row)
        layout.addWidget(c1)

        # 游戏模式
        c2 = QFrame()
        c2.setObjectName("Card")
        l2 = QVBoxLayout(c2)
        t2 = QLabel("🎮  游戏模式")
        t2.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        l2.addWidget(t2)

        gm_row = QHBoxLayout()
        for gm, cn in (("survival", "生存"), ("creative", "创造"),
                       ("adventure", "冒险"), ("spectator", "观察")):
            btn = QPushButton(cn)
            btn.setObjectName("Ghost")
            btn.setFixedHeight(40)
            btn.clicked.connect(
                lambda _=False, g=gm:
                self.state.quick_rcon(f"gamemode {g} {self.player}"))
            gm_row.addWidget(btn)
        l2.addLayout(gm_row)
        layout.addWidget(c2)

        # 管理操作
        c3 = QFrame()
        c3.setObjectName("Card")
        l3 = QVBoxLayout(c3)
        t3 = QLabel("⚡  管理操作")
        t3.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        l3.addWidget(t3)

        act_row = QHBoxLayout()
        actions = [
            ("🎁  OP", "Green", f"op {self.player}"),
            ("⛔ 取消OP", "Orange", f"deop {self.player}"),
            ("👢 踢出", "Orange", f"kick {self.player}"),
            ("☠ 击杀", "Red", f"kill {self.player}"),
            ("🚫 封禁", "Red", f"ban {self.player}"),
            ("🏠 出生点", "Accent",
             f"execute in minecraft:overworld run tp {self.player} 0 100 0"),
        ]
        for label, obj, cmd in actions:
            btn = QPushButton(label)
            btn.setObjectName(obj)
            btn.setFixedHeight(42)
            btn.clicked.connect(
                lambda _=False, c=cmd: self.state.quick_rcon(c))
            act_row.addWidget(btn)
        l3.addLayout(act_row)
        layout.addWidget(c3)

        layout.addStretch()
        return w

    def _send_msg(self):
        msg = self._msg_entry.text().strip()
        if not msg:
            return
        safe = msg.replace('"', '\\"')
        self.state.quick_rcon(f"tell {self.player} {safe}")
        self._msg_entry.clear()