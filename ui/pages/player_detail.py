"""玩家详情窗口：背包编辑 / 传送 / Buff / 操作。"""
import re
import threading
from tkinter import messagebox
import customtkinter as ctk

from core.theme import C
from core.item_names import get_all_item_ids, get_item_name, get_item_id
from ui.widgets.search_dropdown import SearchDropdown


# ============================================================
#  常量
# ============================================================
EFFECTS = [
    ("speed",              "速度"),
    ("slowness",           "缓慢"),
    ("haste",              "急迫"),
    ("mining_fatigue",     "挖掘疲劳"),
    ("strength",           "力量"),
    ("instant_health",     "瞬间治疗"),
    ("instant_damage",     "瞬间伤害"),
    ("jump_boost",         "跳跃提升"),
    ("nausea",             "反胃"),
    ("regeneration",       "生命恢复"),
    ("resistance",         "抗性提升"),
    ("fire_resistance",    "防火"),
    ("water_breathing",    "水下呼吸"),
    ("invisibility",       "隐身"),
    ("blindness",          "失明"),
    ("night_vision",       "夜视"),
    ("hunger",             "饥饿"),
    ("weakness",           "虚弱"),
    ("poison",             "中毒"),
    ("wither",             "凋零"),
    ("health_boost",       "生命提升"),
    ("absorption",         "伤害吸收"),
    ("saturation",         "饱和"),
    ("glowing",            "发光"),
    ("levitation",         "漂浮"),
    ("luck",               "幸运"),
    ("unluck",             "霉运"),
    ("slow_falling",       "缓降"),
    ("conduit_power",      "潮涌能量"),
    ("dolphins_grace",     "海豚的恩惠"),
    ("bad_omen",           "不祥之兆"),
    ("hero_of_the_village","村庄英雄"),
    ("darkness",           "黑暗"),
]
EFFECT_OPTIONS = [f"{name}  ({key})" for key, name in EFFECTS]

DIMENSIONS = [
    ("minecraft:overworld", "主世界"),
    ("minecraft:the_nether", "下界"),
    ("minecraft:the_end",    "末地"),
]
DIMENSION_OPTIONS = [f"{name}  ({key})" for key, name in DIMENSIONS]

GAMEMODES = ["survival", "creative", "adventure", "spectator"]
GAMEMODE_CN = {
    "survival":  "生存",
    "creative":  "创造",
    "adventure": "冒险",
    "spectator": "观察者",
}

# 槽位名（0-8 快捷栏 / 9-35 背包 / 36-39 装备 / 40 副手）
SLOT_NAMES = (
    [f"hotbar.{i}" for i in range(9)] +
    [f"inventory.{i}" for i in range(27)] +
    ["armor.head", "armor.chest", "armor.legs", "armor.feet"] +
    ["weapon.offhand"]
)
SLOT_LABELS = (
    [f"快捷栏 {i+1}" for i in range(9)] +
    [f"背包 {i+1}" for i in range(27)] +
    ["头盔", "胸甲", "护腿", "靴子"] +
    ["副手"]
)

# NBT 数字槽位 -> SLOT_NAMES 索引
NBT_SLOT_TO_IDX = {i: i for i in range(36)}
NBT_SLOT_TO_IDX.update({
    100: 39,   # 靴子
    101: 38,   # 护腿
    102: 37,   # 胸甲
    103: 36,   # 头盔
    -106: 40,  # 副手
})


# ============================================================
#  解析工具
# ============================================================
def _split_top_level(s):
    """按顶层逗号切分字符串，忽略括号/花括号/方括号内的逗号。"""
    parts = []
    depth = 0
    in_quote = False
    buf = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            in_quote = not in_quote
        if in_quote:
            buf.append(ch)
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return parts


def _extract_brace(s, start):
    """从 s[start]（应为 '{'）开始，返回匹配完整的 {...} 子串。"""
    depth = 0
    in_quote = False
    i = start
    while i < len(s):
        ch = s[i]
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            in_quote = not in_quote
        if not in_quote:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        i += 1
    return ""


def parse_inventory(resp):
    """
    解析 data get entity <player> Inventory。
    只识别顶层物品（大写 Slot + b 后缀），潜影盒内部的小写 slot 不误匹配。
    """
    result = {}
    if not resp:
        return result

    start = resp.find("[")
    end = resp.rfind("]")
    if start == -1 or end == -1:
        return result

    body = resp[start + 1:end]

    for item_str in _split_top_level(body):
        slot_m = re.search(r'\bSlot:\s*(-?\d+)b', item_str)
        if not slot_m:
            continue

        after = item_str[slot_m.end():]
        id_m = re.search(r'\bid:\s*"([^"]+)"', after)
        if not id_m:
            continue

        before = item_str[:slot_m.start()]
        counts = re.findall(r'\bcount:\s*(\d+)', before)
        count = int(counts[-1]) if counts else 1

        try:
            nbt_slot = int(slot_m.group(1))
        except ValueError:
            continue

        idx = NBT_SLOT_TO_IDX.get(nbt_slot)
        if idx is None:
            continue

        result[SLOT_NAMES[idx]] = (id_m.group(1), count)

    return result


def parse_equipment(resp):
    """
    解析 data get entity <player> equipment（1.20.5+ 独立字段）。
    """
    result = {}
    if not resp or "entity data" not in resp:
        return result

    for field, slot_name in (
        ("head",    "armor.head"),
        ("chest",   "armor.chest"),
        ("legs",    "armor.legs"),
        ("feet",    "armor.feet"),
        ("offhand", "weapon.offhand"),
    ):
        m = re.search(rf'\b{field}:\s*\{{', resp)
        if not m:
            continue
        brace_start = m.end() - 1
        inner = _extract_brace(resp, brace_start)
        if not inner:
            continue
        id_m = re.search(r'\bid:\s*"([^"]+)"', inner)
        if not id_m:
            continue
        cnt_m = re.search(r'\bcount:\s*(\d+)', inner)
        result[slot_name] = (
            id_m.group(1),
            int(cnt_m.group(1)) if cnt_m else 1,
        )

    return result


# ============================================================
#  物品编辑对话框
# ============================================================
class ItemEditDialog(ctk.CTkToplevel):
    def __init__(self, parent, slot_label, current_id, current_count,
                 on_save, on_clear):
        super().__init__(parent)
        self.on_save = on_save
        self.on_clear = on_clear
        self.f = parent.f

        self._dropdown = None
        self._selected_item_id = current_id or ""
        self._searching = False

        self.title(f"编辑 · {slot_label}")
        self.geometry("520x460")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.transient(parent)
        self.after(60, self.focus_force)

        f = self.f
        frame = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=16,
                             border_width=1, border_color=C["border"])
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(frame, text=slot_label, font=f["h1"],
                     text_color=C["text"]).pack(anchor="w", padx=18, pady=(16, 12))

        # ---- 搜索行 ----
        row1 = ctk.CTkFrame(frame, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(row1, text="物品", font=f["body"], text_color=C["text"],
                     width=60, anchor="w").pack(side="left")

        self.search_entry = ctk.CTkEntry(
            row1, height=38, corner_radius=9, font=f["body"],
            fg_color=C["console_bg"], border_color=C["border"],
            border_width=1, placeholder_text="输入中文名或英文 ID 搜索…",
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))

        self.search_entry.bind("<KeyRelease>", self._on_key)
        self.search_entry.bind("<Escape>", lambda e: self._close_dropdown())
        self.search_entry.bind("<Return>", lambda e: self._close_dropdown())

        # 已选提示
        self.selected_label = ctk.CTkLabel(
            frame, text="", font=f["small"], text_color=C["accent"], anchor="w")
        self.selected_label.pack(fill="x", padx=18, pady=(2, 6))

        # 预构建搜索索引
        self._search_index = []
        for iid, name in get_all_item_ids():
            display = f"{name}  ({iid})"
            self._search_index.append((name.lower(), iid.lower(), display))

        # 回填当前物品
        if current_id:
            cn = get_item_name(current_id)
            self.search_entry.insert(0, cn)
            self.selected_label.configure(text=f"已选：{cn}  ({current_id})")

        # 内嵌下拉（挂在 frame 上）
        self._dropdown = SearchDropdown(
            frame, self.search_entry,
            command=self._on_pick,
            width=420, height=160,
        )

        # 点击外部关闭下拉
        self.bind("<Button-1>", self._on_click_outside, add="+")

        # ---- 数量 ----
        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(row2, text="数量", font=f["body"], text_color=C["text"],
                     width=60, anchor="w").pack(side="left")
        self.count_entry = ctk.CTkEntry(row2, height=38, corner_radius=9,
                                        font=f["body"], fg_color=C["console_bg"],
                                        border_color=C["border"], border_width=1)
        self.count_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.count_entry.insert(0, str(current_count or 1))

        # ---- 常用物品 ----
        quick = ctk.CTkFrame(frame, fg_color="transparent")
        quick.pack(fill="x", padx=18, pady=(10, 6))
        ctk.CTkLabel(quick, text="常用", font=f["small"],
                     text_color=C["text_dim"], width=60, anchor="w"
                     ).pack(side="left")

        common_row = ctk.CTkFrame(quick, fg_color="transparent")
        common_row.pack(side="left", fill="x", expand=True)

        common_items = [
            ("钻石",     "minecraft:diamond"),
            ("下界合金", "minecraft:netherite_ingot"),
            ("金苹果",   "minecraft:golden_apple"),
            ("鞘翅",     "minecraft:elytra"),
            ("图腾",     "minecraft:totem_of_undying"),
        ]
        for i, (cn, iid) in enumerate(common_items):
            common_row.grid_columnconfigure(i, weight=1, uniform="cm")
            ctk.CTkButton(common_row, text=cn, height=30, corner_radius=7,
                          font=f["small"], fg_color="transparent",
                          hover_color=C["card_hover"], border_width=1,
                          border_color=C["border"], text_color=C["text_dim"],
                          command=lambda d=iid: self._quick_pick(d)
                          ).grid(row=0, column=i, sticky="ew", padx=3)

        # ---- 底部按钮 ----
        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(14, 16))
        ctk.CTkButton(btns, text="🗑  清空槽位", width=120, height=38,
                      corner_radius=9, fg_color=C["red"],
                      hover_color=C["red_hover"], font=f["body"],
                      command=self._clear).pack(side="left")
        ctk.CTkButton(btns, text="保存", width=90, height=38, corner_radius=9,
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      font=f["h2"], command=self._save).pack(side="right")
        ctk.CTkButton(btns, text="取消", width=90, height=38, corner_radius=9,
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"], font=f["body"],
                      command=self.destroy).pack(side="right", padx=(0, 8))

    # ---------- 下拉交互 ----------
    def _on_key(self, event=None):
        if self._searching:
            return
        self._searching = True
        try:
            keyword = self.search_entry.get().strip().lower()

            # 空输入不弹下拉
            if not keyword:
                self._close_dropdown()
                return

            limit = 60
            prefix_hits = []
            contains_hits = []

            for cn_lower, id_lower, display in self._search_index:
                if cn_lower.startswith(keyword) or id_lower.startswith(keyword):
                    prefix_hits.append(display)
                    if len(prefix_hits) >= limit:
                        break
                elif keyword in cn_lower or keyword in id_lower:
                    if len(contains_hits) < limit:
                        contains_hits.append(display)

            filtered = (prefix_hits + contains_hits)[:limit]

            if not filtered:
                self._close_dropdown()
                return

            self._dropdown.show(filtered)
        finally:
            self._searching = False

    def _close_dropdown(self):
        if self._dropdown:
            self._dropdown.hide()

    def _on_click_outside(self, event):
        if not self._dropdown or not self._dropdown.is_visible():
            return
        widget = event.widget
        if self._is_descendant(widget, self._dropdown):
            return
        if widget is self.search_entry:
            return
        self._dropdown.hide()

    @staticmethod
    def _is_descendant(widget, ancestor):
        w = widget
        while w is not None:
            if w is ancestor:
                return True
            w = getattr(w, "master", None)
        return False

    def _on_pick(self, choice):
        try:
            if "(" in choice and choice.endswith(")"):
                iid = choice.rsplit("(", 1)[-1].rstrip(")")
            else:
                iid = choice
            cn = get_item_name(iid)

            self._selected_item_id = iid
            self._searching = True
            try:
                self.search_entry.delete(0, "end")
                self.search_entry.insert(0, cn)
            finally:
                self._searching = False

            self.selected_label.configure(text=f"已选：{cn}  ({iid})")
        except Exception:
            pass

    def _quick_pick(self, item_id):
        cn = get_item_name(item_id)
        self._selected_item_id = item_id
        self._searching = True
        try:
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, cn)
        finally:
            self._searching = False
        self.selected_label.configure(text=f"已选：{cn}  ({item_id})")

    # ---------- 保存 / 清空 ----------
    def _resolve_item_id(self):
        text = self.search_entry.get().strip()
        if not text:
            return self._selected_item_id or ""

        if self._selected_item_id:
            if text == get_item_name(self._selected_item_id):
                return self._selected_item_id

        if "(" in text and text.endswith(")"):
            return text.rsplit("(", 1)[-1].rstrip(")")

        if ":" in text:
            return text if text.startswith("minecraft:") else f"minecraft:{text}"

        iid = get_item_id(text)
        if iid:
            return iid

        return f"minecraft:{text}"

    def _save(self):
        self._close_dropdown()
        item_id = self._resolve_item_id()
        if not item_id or item_id == "minecraft:":
            messagebox.showwarning("提示", "请选择或输入物品", parent=self)
            return

        try:
            count = int(self.count_entry.get().strip())
            if not (1 <= count <= 6400):
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "数量必须为 1-6400 的整数", parent=self)
            return

        self.on_save(item_id, count)
        self.destroy()

    def _clear(self):
        self._close_dropdown()
        self.on_clear()
        self.destroy()

    def destroy(self):
        self._close_dropdown()
        super().destroy()


# ============================================================
#  玩家详情主窗口
# ============================================================
class PlayerDetailWindow(ctk.CTkToplevel):
    def __init__(self, app, player_name):
        super().__init__()
        self.app = app
        self.player = player_name
        self.f = app.fonts
        self._slot_items = {}
        self._slot_rows = {}
        self._inv_merged = {}
        self._inv_pending = 0

        self.title(f"玩家详情 · {player_name}")
        self.geometry("920x720")
        self.minsize(820, 620)
        self.configure(fg_color=C["bg"])
        self.transient()
        self.after(50, self.lift)

        try:
            self._build()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            print("=" * 60)
            print("PlayerDetailWindow._build 出错：")
            print(tb)
            print("=" * 60)

            box = ctk.CTkTextbox(self, fg_color=C["console_bg"],
                                 text_color="#f87171", font=("Consolas", 11))
            box.pack(fill="both", expand=True, padx=20, pady=20)
            box.insert("1.0", tb)
            return

        self.after(150, self.reload_inventory)
        self.after(200, self._load_online_players)

    # ========================================================
    #  骨架
    # ========================================================
    def _build(self):
        f = self.f

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(header, text=f"🎮   {self.player}", font=f["title"],
                     text_color=C["text"]).pack(side="left")
        ctk.CTkButton(header, text="✕", width=36, height=36, corner_radius=9,
                      fg_color="transparent", hover_color=C["card_hover"],
                      text_color=C["text_dim"], font=f["h2"],
                      command=self.destroy).pack(side="right")

        tabs = ctk.CTkTabview(
            self, fg_color=C["card"], segmented_button_fg_color=C["sidebar"],
            segmented_button_selected_color=C["accent"],
            segmented_button_selected_hover_color=C["accent_hover"],
            segmented_button_unselected_color=C["sidebar"],
            text_color=C["text"], corner_radius=14,
            border_width=1, border_color=C["border"],
        )
        tabs.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self._build_inventory(tabs.add("🎒  背包"))
        self._build_teleport(tabs.add("🧭  传送"))
        self._build_buff(tabs.add("✨  Buff"))
        self._build_actions(tabs.add("⚡  操作"))

    # ========================================================
    #  ① 背包
    # ========================================================
    def _build_inventory(self, parent):
        f = self.f
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 10))
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bar, text="玩家背包", font=f["h1"],
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(bar, text="🔄  刷新", width=100, height=38, corner_radius=10,
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"], text_color=C["text_dim"],
                      font=f["body"], command=self.reload_inventory
                      ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(bar, text="🧹  清空背包", width=120, height=38, corner_radius=10,
                      fg_color=C["red"], hover_color=C["red_hover"], font=f["h2"],
                      command=self._clear_whole_inventory
                      ).grid(row=0, column=2)

        self.inv_status = ctk.CTkLabel(bar, text="", font=f["small"],
                                       text_color=C["text_dim"])
        self.inv_status.grid(row=0, column=3, padx=(12, 0))

        scroll = ctk.CTkScrollableFrame(
            parent, fg_color=C["console_bg"], corner_radius=12,
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        scroll.grid_columnconfigure(1, weight=1)

        for i, (slot_name, label) in enumerate(zip(SLOT_NAMES, SLOT_LABELS)):
            self._make_slot_row(scroll, i, slot_name, label)

    def _make_slot_row(self, parent, idx, slot_name, label):
        f = self.f
        if idx in (0, 9, 36, 40):
            titles = {0: "快捷栏", 9: "背包", 36: "装备", 40: "副手"}
            ctk.CTkLabel(parent, text=titles[idx], font=f["h2"],
                         text_color=C["accent"], anchor="w").grid(
                row=idx * 2, column=0, columnspan=4, sticky="w",
                padx=14, pady=(12 if idx else 6, 4))

        row = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=8)
        row.grid(row=idx * 2 + 1, column=0, columnspan=4, sticky="ew",
                 padx=8, pady=2)
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=label, font=f["body"], text_color=C["text_dim"],
                     width=90, anchor="w").grid(row=0, column=0, padx=(14, 8), pady=8)

        value = ctk.CTkLabel(row, text="— 空 —", font=f["body"],
                             text_color=C["text_faint"], anchor="w")
        value.grid(row=0, column=1, sticky="w")
        self._slot_rows[slot_name] = value

        def edit(s=slot_name, lbl=label):
            cur = self._slot_items.get(s, ("", 1))
            ItemEditDialog(self, lbl,
                           cur[0] if cur[0] else "",
                           cur[1] if cur[0] else 1,
                           on_save=lambda i, c: self._write_slot(s, lbl, i, c),
                           on_clear=lambda: self._write_slot(s, lbl, None, 0))

        ctk.CTkButton(row, text="编辑", width=64, height=30, corner_radius=7,
                      font=f["small"], fg_color=C["accent"],
                      hover_color=C["accent_hover"], command=edit
                      ).grid(row=0, column=2, padx=4)

        def clear(s=slot_name, lbl=label):
            self._write_slot(s, lbl, None, 0)

        ctk.CTkButton(row, text="清空", width=64, height=30, corner_radius=7,
                      font=f["small"], fg_color="transparent",
                      hover_color="#3b1f24", border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=clear).grid(row=0, column=3, padx=(0, 12))

    # ---------- 背包读写 ----------
    def reload_inventory(self):
        self.inv_status.configure(text="读取中…", text_color=C["text_dim"])
        self._inv_merged = {}
        info = self.app.server_info

        def finish():
            self._slot_items = self._inv_merged
            self._apply_inventory_ui()
            self.inv_status.configure(
                text=f"✔ 已读取 {len(self._slot_items)} 个物品",
                text_color=C["green"],
            )

        def cb_inv(resp):
            self._inv_merged.update(parse_inventory(resp))
            if not info.has("equipment_field"):
                finish()
            else:
                self.app.rcon_call(
                    f"data get entity {self.player} equipment",
                    cb_equip)

        def cb_equip(resp):
            self._inv_merged.update(parse_equipment(resp))
            finish()

        self.app.rcon_call(
            f"data get entity {self.player} Inventory", cb_inv)

    def _apply_inventory_ui(self):
        for slot_name, label in self._slot_rows.items():
            entry = self._slot_items.get(slot_name)
            if entry:
                item_id, count = entry
                cn_name = get_item_name(item_id)
                label.configure(text=f"{cn_name}   ×{count}",
                                text_color=C["text"])
            else:
                label.configure(text="— 空 —", text_color=C["text_faint"])

    def _write_slot(self, slot_name, slot_label, item_id, count):
        info = self.app.server_info
        if item_id:
            cmd = info.cmd_set_item(self.player, slot_name, item_id, count)
            self.app.log_to_console(
                f"> 设置 {self.player} 的 {slot_label} = {item_id} ×{count}", "cmd")
        else:
            cmd = info.cmd_clear_slot(self.player, slot_name)
            self.app.log_to_console(
                f"> 清空 {self.player} 的 {slot_label}", "cmd")

        self.app.rcon_call(cmd, lambda _r: self.app.after(400, self.reload_inventory))

    def _clear_whole_inventory(self):
        if not messagebox.askyesno("清空背包",
                                    f"确定要清空 {self.player} 的全部物品吗？"):
            return
        self.app.log_to_console(f"> 清空 {self.player} 背包", "cmd")
        self.app.rcon_call(f"clear {self.player}",
                           lambda _r: self.app.after(400, self.reload_inventory))

    # ========================================================
    #  ② 传送
    # ========================================================
    def _build_teleport(self, parent):
        f = self.f
        parent.grid_columnconfigure(0, weight=1)

        # ---- 随机安全传送 ----
        c1 = self._tcard(parent, "🎲  随机安全传送", 0)
        ctk.CTkLabel(c1, text="在指定范围内寻找安全落点（spreadplayers）",
                     font=f["small"], text_color=C["text_faint"]
                     ).pack(anchor="w", padx=18, pady=(0, 10))

        row = ctk.CTkFrame(c1, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(row, text="最小半径", font=f["body"], text_color=C["text"],
                     width=90, anchor="w").pack(side="left")
        self.tp_min = ctk.CTkEntry(row, height=36, width=80, corner_radius=9,
                                   font=f["body"], fg_color=C["console_bg"],
                                   border_color=C["border"], border_width=1)
        self.tp_min.pack(side="left")
        self.tp_min.insert(0, "100")

        ctk.CTkLabel(row, text="最大半径", font=f["body"], text_color=C["text"],
                     width=90, anchor="w").pack(side="left", padx=(20, 0))
        self.tp_max = ctk.CTkEntry(row, height=36, width=80, corner_radius=9,
                                   font=f["body"], fg_color=C["console_bg"],
                                   border_color=C["border"], border_width=1)
        self.tp_max.pack(side="left")
        self.tp_max.insert(0, "2000")

        ctk.CTkButton(c1, text="传送到随机安全点", height=40, corner_radius=10,
                      font=f["h2"], fg_color=C["accent"],
                      hover_color=C["accent_hover"],
                      command=self._tp_random).pack(fill="x", padx=18, pady=(8, 16))

        # ---- 玩家互传 ----
        c2 = self._tcard(parent, "👥  传送到其他玩家", 1)

        row2 = ctk.CTkFrame(c2, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(row2, text="目标玩家", font=f["body"], text_color=C["text"],
                     width=90, anchor="w").pack(side="left")

        self.tp_target = ctk.CTkOptionMenu(
            row2, values=["加载中…"], width=240,
            fg_color=C["console_bg"], button_color=C["accent"],
            button_hover_color=C["accent_hover"])
        self.tp_target.pack(side="left", padx=(10, 0))
        ctk.CTkButton(row2, text="🔄", width=42, height=36, corner_radius=9,
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"], font=f["body"],
                      command=self._load_online_players).pack(side="left", padx=6)

        ctk.CTkButton(c2, text=f"把 {self.player} 传送到目标玩家", height=40,
                      corner_radius=10, font=f["h2"], fg_color=C["accent"],
                      hover_color=C["accent_hover"], command=self._tp_to_player
                      ).pack(fill="x", padx=18, pady=(8, 16))

        # ---- 定点传送 ----
        c3 = self._tcard(parent, "📍  多维度定点传送", 2)

        row3 = ctk.CTkFrame(c3, fg_color="transparent")
        row3.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(row3, text="维度", font=f["body"], text_color=C["text"],
                     width=60, anchor="w").pack(side="left")

        self.tp_dim = ctk.CTkOptionMenu(
            row3, values=DIMENSION_OPTIONS, width=240,
            fg_color=C["console_bg"], button_color=C["accent"],
            button_hover_color=C["accent_hover"])
        self.tp_dim.pack(side="left", padx=(10, 0))

        row4 = ctk.CTkFrame(c3, fg_color="transparent")
        row4.pack(fill="x", padx=18, pady=(0, 8))
        for label, attr, default in (("X", "tp_x", "0"),
                                     ("Y", "tp_y", "64"),
                                     ("Z", "tp_z", "0")):
            ctk.CTkLabel(row4, text=label, font=f["body"], text_color=C["text"],
                         width=20, anchor="w").pack(side="left", padx=(0, 2))
            entry = ctk.CTkEntry(row4, height=36, width=90, corner_radius=9,
                                 font=f["body"], fg_color=C["console_bg"],
                                 border_color=C["border"], border_width=1)
            entry.pack(side="left", padx=(0, 14))
            entry.insert(0, default)
            setattr(self, attr, entry)

        ctk.CTkButton(c3, text="传送到指定坐标", height=40, corner_radius=10,
                      font=f["h2"], fg_color=C["accent"],
                      hover_color=C["accent_hover"], command=self._tp_coords
                      ).pack(fill="x", padx=18, pady=(8, 16))

    def _tcard(self, parent, title, row):
        f = self.f
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=14,
                            border_width=1, border_color=C["border"])
        card.grid(row=row, column=0, sticky="ew", padx=10, pady=(8, 6))
        ctk.CTkLabel(card, text=title, font=f["h1"], text_color=C["text"]
                     ).pack(anchor="w", padx=18, pady=(14, 6))
        return card

    def _load_online_players(self):
        def cb(resp):
            names = []
            if ":" in resp:
                tail = resp.split(":", 1)[1].strip()
                if tail:
                    names = [n.strip() for n in tail.split(",") if n.strip()]
            names = [n for n in names if n != self.player]
            if not names:
                names = ["（无其他在线玩家）"]
            try:
                self.tp_target.configure(values=names)
                self.tp_target.set(names[0])
            except Exception:
                pass
        self.app.rcon_call("list", cb)

    def _tp_random(self):
        try:
            rmin = int(self.tp_min.get().strip())
            rmax = int(self.tp_max.get().strip())
            if rmin < 0 or rmax <= rmin:
                raise ValueError
        except ValueError:
            messagebox.showwarning("参数错误", "半径必须为整数，且最大值 > 最小值",
                                   parent=self)
            return
        cmd = (f"spreadplayers ~ ~ {rmin} {rmax} under 320 false {self.player}")
        self.app.log_to_console(f"> 随机传送：{cmd}", "cmd")
        self.app.rcon_call(cmd, lambda _r: self.app.log_to_console(
            f"{self.player} 已随机传送", "ok"))

    def _tp_to_player(self):
        target = self.tp_target.get()
        if not target or target.startswith("（"):
            messagebox.showwarning("提示", "没有可用的目标玩家", parent=self)
            return
        cmd = f"tp {self.player} {target}"
        self.app.log_to_console(f"> {cmd}", "cmd")
        self.app.rcon_call(cmd, lambda _r: self.app.log_to_console(
            f"{self.player} 已传送到 {target}", "ok"))

    def _tp_coords(self):
        dim_label = self.tp_dim.get()
        m = re.search(r"\(([^)]+)\)", dim_label)
        dim = m.group(1) if m else "minecraft:overworld"

        try:
            x = self.tp_x.get().strip() or "0"
            y = self.tp_y.get().strip() or "64"
            z = self.tp_z.get().strip() or "0"
            float(x); float(y); float(z)
        except ValueError:
            messagebox.showwarning("参数错误", "坐标必须是数字", parent=self)
            return

        cmd = f"execute in {dim} run tp {self.player} {x} {y} {z}"
        self.app.log_to_console(f"> {cmd}", "cmd")
        self.app.rcon_call(cmd, lambda _r: self.app.log_to_console(
            f"{self.player} 已传送到 {dim} ({x}, {y}, {z})", "ok"))

    # ========================================================
    #  ③ Buff
    # ========================================================
    def _build_buff(self, parent):
        f = self.f
        parent.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=14,
                            border_width=1, border_color=C["border"])
        card.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 6))

        ctk.CTkLabel(card, text="✨  给予效果", font=f["h1"], text_color=C["text"]
                     ).pack(anchor="w", padx=18, pady=(14, 8))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(row1, text="效果", font=f["body"], text_color=C["text"],
                     width=80, anchor="w").pack(side="left")
        self.eff_var = ctk.CTkOptionMenu(
            row1, values=EFFECT_OPTIONS, width=320,
            fg_color=C["console_bg"], button_color=C["accent"],
            button_hover_color=C["accent_hover"])
        self.eff_var.pack(side="left", padx=(10, 0), fill="x", expand=True)

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(row2, text="时长（秒）", font=f["body"], text_color=C["text"],
                     width=80, anchor="w").pack(side="left")
        self.eff_dur = ctk.CTkEntry(row2, height=36, width=100, corner_radius=9,
                                    font=f["body"], fg_color=C["console_bg"],
                                    border_color=C["border"], border_width=1)
        self.eff_dur.pack(side="left", padx=(10, 0))
        self.eff_dur.insert(0, "30")

        ctk.CTkLabel(row2, text="倍率", font=f["body"], text_color=C["text"],
                     width=60, anchor="w").pack(side="left", padx=(30, 0))
        self.eff_amp = ctk.CTkEntry(row2, height=36, width=80, corner_radius=9,
                                    font=f["body"], fg_color=C["console_bg"],
                                    border_color=C["border"], border_width=1)
        self.eff_amp.pack(side="left", padx=(10, 0))
        self.eff_amp.insert(0, "0")

        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.pack(fill="x", padx=18, pady=(6, 8))
        ctk.CTkLabel(row3, text="隐藏粒子", font=f["body"], text_color=C["text"],
                     width=80, anchor="w").pack(side="left")
        self.eff_hide = ctk.StringVar(value="false")
        ctk.CTkSwitch(row3, text="", variable=self.eff_hide,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="left", padx=(10, 0))

        # 预设
        presets = ctk.CTkFrame(card, fg_color="transparent")
        presets.pack(fill="x", padx=18, pady=(4, 6))

        ctk.CTkLabel(presets, text="预设", font=f["small"],
                     text_color=C["text_dim"], width=40, anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        preset_row = ctk.CTkFrame(presets, fg_color="transparent")
        preset_row.grid(row=0, column=1, sticky="ew")
        presets.grid_columnconfigure(1, weight=1)

        preset_data = [
            ("夜视 10min",   "night_vision", 600, 0),
            ("力量 II",      "strength",     300, 1),
            ("抗性 III",     "resistance",   300, 2),
            ("速度 II",      "speed",        300, 1),
            ("回血 30s",     "regeneration", 30,  4),
        ]
        for i, (label, eff, dur, amp) in enumerate(preset_data):
            preset_row.grid_columnconfigure(i, weight=1, uniform="pr")
            ctk.CTkButton(preset_row, text=label, height=28, corner_radius=7,
                          font=f["small"], fg_color="transparent",
                          hover_color=C["card_hover"], border_width=1,
                          border_color=C["border"], text_color=C["text_dim"],
                          command=lambda e=eff, d=dur, a=amp:
                          self._apply_preset(e, d, a)
                          ).grid(row=0, column=i, sticky="ew", padx=2)

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(8, 16))
        ctk.CTkButton(btns, text="✨  施加效果", height=42, corner_radius=10,
                      font=f["h2"], fg_color=C["green"],
                      hover_color=C["green_hover"], command=self._apply_effect
                      ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(btns, text="🚫  清除全部效果", height=42, corner_radius=10,
                      font=f["h2"], fg_color=C["red"],
                      hover_color=C["red_hover"], command=self._clear_effects
                      ).pack(side="left", fill="x", expand=True, padx=(10, 0))

    def _apply_preset(self, effect, dur, amp):
        for opt in EFFECT_OPTIONS:
            if f"({effect})" in opt:
                self.eff_var.set(opt)
                break
        self.eff_dur.delete(0, "end")
        self.eff_dur.insert(0, str(dur))
        self.eff_amp.delete(0, "end")
        self.eff_amp.insert(0, str(amp))

    def _apply_effect(self):
        m = re.search(r"\(([^)]+)\)", self.eff_var.get())
        if not m:
            messagebox.showwarning("提示", "请选择效果", parent=self)
            return
        effect = m.group(1)
        try:
            dur = int(self.eff_dur.get().strip())
            amp = int(self.eff_amp.get().strip())
            if dur < 1 or not (0 <= amp <= 255):
                raise ValueError
        except ValueError:
            messagebox.showwarning("参数错误",
                                   "时长必须 ≥1，倍率必须为 0-255 的整数",
                                   parent=self)
            return

        cmd = f"effect give {self.player} {effect} {dur} {amp}"
        if self.eff_hide.get() == "true":
            cmd += " true"
        self.app.log_to_console(f"> {cmd}", "cmd")
        self.app.rcon_call(cmd, lambda _r: self.app.log_to_console(
            f"已给 {self.player} 施加 {effect}", "ok"))

    def _clear_effects(self):
        cmd = f"effect clear {self.player}"
        self.app.log_to_console(f"> {cmd}", "cmd")
        self.app.rcon_call(cmd, lambda _r: self.app.log_to_console(
            f"已清除 {self.player} 的所有效果", "ok"))

    # ========================================================
    #  ④ 操作
    # ========================================================
    def _build_actions(self, parent):
        f = self.f
        parent.grid_columnconfigure(0, weight=1)

        # ---- 私信 ----
        c1 = self._tcard(parent, "💬  服务器私信", 0)
        row = ctk.CTkFrame(c1, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 16))
        self.msg_entry = ctk.CTkEntry(row, height=40, corner_radius=10,
                                      font=f["body"], fg_color=C["console_bg"],
                                      border_color=C["border"], border_width=1,
                                      placeholder_text="输入要发送给该玩家的消息…")
        self.msg_entry.pack(side="left", fill="x", expand=True)
        self.msg_entry.bind("<Return>", lambda e: self._send_msg())
        ctk.CTkButton(row, text="发送", width=90, height=40, corner_radius=10,
                      font=f["h2"], fg_color=C["accent"],
                      hover_color=C["accent_hover"], command=self._send_msg
                      ).pack(side="left", padx=(10, 0))

        # ---- 游戏模式 ----
        c2 = self._tcard(parent, "🎮  游戏模式", 1)
        gm_row = ctk.CTkFrame(c2, fg_color="transparent")
        gm_row.pack(fill="x", padx=14, pady=(0, 16))
        for i, gm in enumerate(GAMEMODES):
            gm_row.grid_columnconfigure(i, weight=1, uniform="gm")
            ctk.CTkButton(gm_row, text=GAMEMODE_CN[gm], height=40, corner_radius=10,
                          font=f["body"], fg_color="transparent",
                          hover_color=C["card_hover"], border_width=1,
                          border_color=C["border"], text_color=C["text"],
                          command=lambda g=gm: self._set_gm(g)
                          ).grid(row=0, column=i, sticky="ew", padx=3)

        # ---- 管理操作 ----
        c3 = self._tcard(parent, "⚡  管理操作", 2)
        row3 = ctk.CTkFrame(c3, fg_color="transparent")
        row3.pack(fill="x", padx=14, pady=(0, 16))

        actions = [
            ("🎁  OP",    C["green"],  C["green_hover"],  self._give_op),
            ("⛔ 取消OP", C["orange"], C["orange_hover"], self._revoke_op),
            ("👢 踢出",   C["orange"], C["orange_hover"], self._kick),
            ("☠ 击杀",    C["red"],    C["red_hover"],    self._kill),
            ("🚫 封禁",   "#b91c1c",  "#7f1d1d",          self._ban),
            ("🏠 出生点", C["accent"], C["accent_hover"], self._tp_spawn),
        ]
        for i, (label, color, hover, cmd) in enumerate(actions):
            row3.grid_columnconfigure(i, weight=1, uniform="act")
            ctk.CTkButton(row3, text=label, height=42, corner_radius=10,
                          font=f["h2"], fg_color=color, hover_color=hover,
                          command=cmd
                          ).grid(row=0, column=i, sticky="ew", padx=3)

    def _send_msg(self):
        msg = self.msg_entry.get().strip()
        if not msg:
            return
        self.msg_entry.delete(0, "end")
        safe = msg.replace('"', '\\"')
        cmd = f'tell {self.player} {safe}'
        self.app.log_to_console(f"> 私信 {self.player}：{msg}", "cmd")
        self.app.rcon_call(cmd, lambda _r: None)

    def _set_gm(self, gm):
        cmd = f"gamemode {gm} {self.player}"
        self.app.log_to_console(f"> {cmd}", "cmd")
        self.app.rcon_call(cmd, lambda _r: self.app.log_to_console(
            f"{self.player} → {GAMEMODE_CN[gm]}", "ok"))

    def _give_op(self):
        self.app.rcon_call(f"op {self.player}",
                           lambda _r: self.app.log_to_console(
                               f"{self.player} 获得 OP", "ok"))

    def _revoke_op(self):
        self.app.rcon_call(f"deop {self.player}",
                           lambda _r: self.app.log_to_console(
                               f"{self.player} 取消 OP", "ok"))

    def _kick(self):
        if not messagebox.askyesno("踢出确认", f"确定踢出 {self.player}？",
                                    parent=self):
            return
        self.app.rcon_call(f"kick {self.player}",
                           lambda _r: self.app.log_to_console(
                               f"{self.player} 已踢出", "ok"))

    def _kill(self):
        if not messagebox.askyesno("击杀确认",
                                    f"确定击杀 {self.player}？\n物品会掉落。",
                                    parent=self):
            return
        self.app.rcon_call(f"kill {self.player}",
                           lambda _r: self.app.log_to_console(
                               f"{self.player} 已被击杀", "ok"))

    def _ban(self):
        if not messagebox.askyesno("封禁确认",
                                    f"确定封禁 {self.player}？", parent=self):
            return
        self.app.rcon_call(f"ban {self.player}",
                           lambda _r: self.app.log_to_console(
                               f"{self.player} 已封禁", "ok"))

    def _tp_spawn(self):
        cmd = f"execute in minecraft:overworld run tp {self.player} 0 100 0"
        self.app.log_to_console(f"> {cmd}", "cmd")
        self.app.rcon_call(cmd, lambda _r: self.app.log_to_console(
            f"{self.player} 传送到出生点附近", "ok"))