"""区域管理页：保护区 + 清理区。"""
import re
import time
from tkinter import messagebox

import customtkinter as ctk

from core.theme import C
from core.zones import (
    load_zones, save_zones, normalize_zone,
    build_visualize_command,
    DIMENSION_CN, DIMENSION_KEYS, DIMENSION_OPTIONS,
)
from core.clean_zones import (
    normalize_clean_zone, build_clean_zone_command,
)
from core.clean_zones import DIMENSION_CN as CZ_DIM_CN


# ============================================================
#  保护区编辑对话框
# ============================================================
class ZoneEditDialog(ctk.CTkToplevel):
    def __init__(self, parent, app, zone=None):
        super().__init__(parent)
        self.app = app
        self.f = app.fonts
        self._zone = dict(zone) if zone else {}
        self._is_new = zone is None

        self.title("编辑保护区" if not self._is_new else "新建保护区")
        self.geometry("560x600")
        self.minsize(520, 480)
        self.resizable(True, True)
        self.configure(fg_color=C["bg"])
        self.transient(parent)
        self.after(60, self.focus_force)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        f = self.f
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        scroll.grid(row=0, column=0, sticky="nsew",
                    padx=(16, 8), pady=(16, 0))
        scroll.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(scroll, fg_color=C["card"], corner_radius=16,
                            border_width=1, border_color=C["border"])
        card.pack(fill="both", expand=True)

        row0 = ctk.CTkFrame(card, fg_color="transparent")
        row0.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(row0, text="名称", font=f["body"], text_color=C["text"],
                     width=70, anchor="w").pack(side="left")
        self.name_entry = ctk.CTkEntry(row0, height=38, corner_radius=9,
                                       font=f["body"], fg_color=C["console_bg"],
                                       border_color=C["border"], border_width=1)
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.name_entry.insert(0, self._zone.get("name", "新保护区"))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(row1, text="维度", font=f["body"], text_color=C["text"],
                     width=70, anchor="w").pack(side="left")
        self.dim_var = ctk.StringVar(
            value=DIMENSION_CN.get(self._zone.get("dimension", ""), "主世界"))
        ctk.CTkOptionMenu(
            row1, values=DIMENSION_OPTIONS,
            variable=self.dim_var, width=180,
            fg_color=C["console_bg"], button_color=C["accent"],
            button_hover_color=C["accent_hover"],
        ).pack(side="left", padx=(10, 0))

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(row2, text="启用", font=f["body"], text_color=C["text"],
                     width=70, anchor="w").pack(side="left")
        self.enabled_var = ctk.StringVar(
            value="true" if self._zone.get("enabled", True) else "false")
        ctk.CTkSwitch(row2, text="", variable=self.enabled_var,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(card, text="角 1（包含）", font=f["h2"],
                     text_color=C["accent"]).pack(anchor="w", padx=18,
                                                   pady=(14, 4))

        self.entries = {}
        for key_label, key_name, default in (
            ("X", "x1", self._zone.get("x1", 0)),
            ("Y", "y1", self._zone.get("y1", 0)),
            ("Z", "z1", self._zone.get("z1", 0)),
        ):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(r, text=key_label, font=f["body"],
                         text_color=C["text"], width=30,
                         anchor="w").pack(side="left")
            e = ctk.CTkEntry(r, height=34, width=120, corner_radius=8,
                             font=f["body"], fg_color=C["console_bg"],
                             border_color=C["border"], border_width=1)
            e.pack(side="left", padx=(10, 12))
            e.insert(0, str(default))
            self.entries[key_name] = e

        ctk.CTkLabel(card, text="角 2（包含）", font=f["h2"],
                     text_color=C["accent"]).pack(anchor="w", padx=18,
                                                   pady=(14, 4))

        for key_label, key_name, default in (
            ("X", "x2", self._zone.get("x2", 0)),
            ("Y", "y2", self._zone.get("y2", 0)),
            ("Z", "z2", self._zone.get("z2", 0)),
        ):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(r, text=key_label, font=f["body"],
                         text_color=C["text"], width=30,
                         anchor="w").pack(side="left")
            e = ctk.CTkEntry(r, height=34, width=120, corner_radius=8,
                             font=f["body"], fg_color=C["console_bg"],
                             border_color=C["border"], border_width=1)
            e.pack(side="left", padx=(10, 12))
            e.insert(0, str(default))
            self.entries[key_name] = e

        grab = ctk.CTkFrame(card, fg_color="transparent")
        grab.pack(fill="x", padx=18, pady=(14, 16))
        ctk.CTkLabel(grab, text="从在线玩家抓取：", font=f["small"],
                     text_color=C["text_dim"]).pack(anchor="w", pady=(0, 6))

        grab2 = ctk.CTkFrame(grab, fg_color="transparent")
        grab2.pack(fill="x")

        self.player_var = ctk.StringVar(value="加载中…")
        self.player_menu = ctk.CTkOptionMenu(
            grab2, values=["加载中…"], variable=self.player_var,
            width=140, fg_color=C["console_bg"],
            button_color=C["accent"],
            button_hover_color=C["accent_hover"])
        self.player_menu.pack(side="left", padx=(0, 6))

        ctk.CTkButton(grab2, text="抓取为角1", width=90, height=30,
                      corner_radius=8, font=f["small"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=lambda: self._grab("1")).pack(side="left", padx=2)
        ctk.CTkButton(grab2, text="抓取为角2", width=90, height=30,
                      corner_radius=8, font=f["small"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=lambda: self._grab("2")).pack(side="left", padx=2)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="ew", padx=16, pady=12)

        ctk.CTkButton(btns, text="✕ 取消", width=100, height=42,
                      corner_radius=10, font=f["body"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=self.destroy).pack(side="left")

        ctk.CTkButton(btns, text="✓ 保存", width=140, height=42,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["green"], hover_color=C["green_hover"],
                      command=self._save).pack(side="right")

        self.after(100, self._load_players)

    def _load_players(self):
        def cb(resp):
            names = []
            if ":" in resp:
                tail = resp.split(":", 1)[1].strip()
                if tail:
                    names = [n.strip() for n in tail.split(",") if n.strip()]
            if not names:
                names = ["（无玩家在线）"]
            try:
                self.player_menu.configure(values=names)
                self.player_var.set(names[0])
            except Exception:
                pass
        self.app.rcon_call("list", cb)

    def _grab(self, which):
        name = self.player_var.get()
        if not name or name.startswith("（"):
            messagebox.showwarning("提示", "没有可用的玩家", parent=self)
            return

        def cb(resp):
            m = re.search(
                r"\[([-\d.]+)d?,\s*([-\d.]+)d?,\s*([-\d.]+)d?\]", resp)
            if not m:
                messagebox.showwarning(
                    "抓取失败", f"无法解析坐标：\n{resp[:200]}", parent=self)
                return
            x, y, z = m.group(1), m.group(2), m.group(3)
            suffix = "1" if which == "1" else "2"
            for key, val in (("x" + suffix, x), ("y" + suffix, y),
                             ("z" + suffix, z)):
                self.entries[key].delete(0, "end")
                self.entries[key].insert(0, val)
            self.app.log_to_console(
                f"已抓取 {name} 的坐标 → 角{which} ({x}, {y}, {z})", "info")

        self.app.rcon_call(f"data get entity {name} Pos", cb)

    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("提示", "请填写保护区名称", parent=self)
            return

        dim_cn = self.dim_var.get()
        dim_key = next((k for k, v in DIMENSION_CN.items() if v == dim_cn),
                       "minecraft:overworld")

        try:
            coords = {k: float(e.get().strip())
                      for k, e in self.entries.items()}
        except ValueError:
            messagebox.showwarning("提示", "坐标必须是数字", parent=self)
            return

        zone = {
            "name": name,
            "dimension": dim_key,
            "enabled": self.enabled_var.get() == "true",
            **coords,
        }

        x1, y1, z1, x2, y2, z2 = normalize_zone(zone)
        zone.update({"x1": x1, "y1": y1, "z1": z1,
                     "x2": x2, "y2": y2, "z2": z2})

        self.app.add_or_update_zone(zone, is_new=self._is_new,
                                    old_name=self._zone.get("name"))
        self.destroy()


# ============================================================
#  清理区编辑对话框
# ============================================================
class CleanZoneEditDialog(ctk.CTkToplevel):
    def __init__(self, parent, app, zone=None):
        super().__init__(parent)
        self.app = app
        self.f = app.fonts
        self._zone = dict(zone) if zone else {}
        self._is_new = zone is None

        self.title("编辑清理区" if not self._is_new else "新建清理区")
        self.geometry("560x640")
        self.minsize(520, 520)
        self.resizable(True, True)
        self.configure(fg_color=C["bg"])
        self.transient(parent)
        self.after(60, self.focus_force)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        f = self.f
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        scroll.grid(row=0, column=0, sticky="nsew",
                    padx=(16, 8), pady=(16, 0))
        scroll.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(scroll, fg_color=C["card"], corner_radius=16,
                            border_width=1, border_color=C["border"])
        card.pack(fill="both", expand=True)

        # 名称
        row0 = ctk.CTkFrame(card, fg_color="transparent")
        row0.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(row0, text="名称", font=f["body"], text_color=C["text"],
                     width=70, anchor="w").pack(side="left")
        self.name_entry = ctk.CTkEntry(row0, height=38, corner_radius=9,
                                       font=f["body"], fg_color=C["console_bg"],
                                       border_color=C["border"], border_width=1)
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.name_entry.insert(0, self._zone.get("name", "新清理区"))

        # 维度
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(row1, text="维度", font=f["body"], text_color=C["text"],
                     width=70, anchor="w").pack(side="left")
        self.dim_var = ctk.StringVar(
            value=CZ_DIM_CN.get(self._zone.get("dimension", ""), "主世界"))
        ctk.CTkOptionMenu(
            row1, values=list(CZ_DIM_CN.values()),
            variable=self.dim_var, width=180,
            fg_color=C["console_bg"], button_color=C["accent"],
            button_hover_color=C["accent_hover"],
        ).pack(side="left", padx=(10, 0))

        # 启用
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(row2, text="启用", font=f["body"], text_color=C["text"],
                     width=70, anchor="w").pack(side="left")
        self.enabled_var = ctk.StringVar(
            value="true" if self._zone.get("enabled", True) else "false")
        ctk.CTkSwitch(row2, text="", variable=self.enabled_var,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="left", padx=(10, 0))

        # 清理间隔
        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(row3, text="间隔(分钟)", font=f["body"], text_color=C["text"],
                     width=80, anchor="w").pack(side="left")
        self.interval_entry = ctk.CTkEntry(row3, height=38, width=100,
                                           corner_radius=9, font=f["body"],
                                           fg_color=C["console_bg"],
                                           border_color=C["border"], border_width=1)
        self.interval_entry.pack(side="left", padx=(10, 0))
        self.interval_entry.insert(
            0, str(self._zone.get("interval_min", 15)))
        ctk.CTkLabel(row3, text="分钟（全局清理关闭时生效）",
                     font=f["small"], text_color=C["text_faint"]
                     ).pack(side="left", padx=(10, 0))

        # 角1
        ctk.CTkLabel(card, text="角 1（包含）", font=f["h2"],
                     text_color=C["accent"]).pack(anchor="w", padx=18,
                                                   pady=(14, 4))

        self.entries = {}
        for key_label, key_name, default in (
            ("X", "x1", self._zone.get("x1", 0)),
            ("Y", "y1", self._zone.get("y1", 0)),
            ("Z", "z1", self._zone.get("z1", 0)),
        ):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(r, text=key_label, font=f["body"],
                         text_color=C["text"], width=30,
                         anchor="w").pack(side="left")
            e = ctk.CTkEntry(r, height=34, width=120, corner_radius=8,
                             font=f["body"], fg_color=C["console_bg"],
                             border_color=C["border"], border_width=1)
            e.pack(side="left", padx=(10, 12))
            e.insert(0, str(default))
            self.entries[key_name] = e

        # 角2
        ctk.CTkLabel(card, text="角 2（包含）", font=f["h2"],
                     text_color=C["accent"]).pack(anchor="w", padx=18,
                                                   pady=(14, 4))

        for key_label, key_name, default in (
            ("X", "x2", self._zone.get("x2", 0)),
            ("Y", "y2", self._zone.get("y2", 0)),
            ("Z", "z2", self._zone.get("z2", 0)),
        ):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(r, text=key_label, font=f["body"],
                         text_color=C["text"], width=30,
                         anchor="w").pack(side="left")
            e = ctk.CTkEntry(r, height=34, width=120, corner_radius=8,
                             font=f["body"], fg_color=C["console_bg"],
                             border_color=C["border"], border_width=1)
            e.pack(side="left", padx=(10, 12))
            e.insert(0, str(default))
            self.entries[key_name] = e

        # 抓取
        grab = ctk.CTkFrame(card, fg_color="transparent")
        grab.pack(fill="x", padx=18, pady=(14, 16))
        ctk.CTkLabel(grab, text="从在线玩家抓取：", font=f["small"],
                     text_color=C["text_dim"]).pack(anchor="w", pady=(0, 6))

        grab2 = ctk.CTkFrame(grab, fg_color="transparent")
        grab2.pack(fill="x")

        self.player_var = ctk.StringVar(value="加载中…")
        self.player_menu = ctk.CTkOptionMenu(
            grab2, values=["加载中…"], variable=self.player_var,
            width=140, fg_color=C["console_bg"],
            button_color=C["accent"],
            button_hover_color=C["accent_hover"])
        self.player_menu.pack(side="left", padx=(0, 6))

        ctk.CTkButton(grab2, text="抓取为角1", width=90, height=30,
                      corner_radius=8, font=f["small"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=lambda: self._grab("1")).pack(side="left", padx=2)
        ctk.CTkButton(grab2, text="抓取为角2", width=90, height=30,
                      corner_radius=8, font=f["small"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=lambda: self._grab("2")).pack(side="left", padx=2)

        # 底部按钮
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="ew", padx=16, pady=12)

        ctk.CTkButton(btns, text="✕ 取消", width=100, height=42,
                      corner_radius=10, font=f["body"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=self.destroy).pack(side="left")

        ctk.CTkButton(btns, text="✓ 保存", width=140, height=42,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["green"], hover_color=C["green_hover"],
                      command=self._save).pack(side="right")

        self.after(100, self._load_players)

    def _load_players(self):
        def cb(resp):
            names = []
            if ":" in resp:
                tail = resp.split(":", 1)[1].strip()
                if tail:
                    names = [n.strip() for n in tail.split(",") if n.strip()]
            if not names:
                names = ["（无玩家在线）"]
            try:
                self.player_menu.configure(values=names)
                self.player_var.set(names[0])
            except Exception:
                pass
        self.app.rcon_call("list", cb)

    def _grab(self, which):
        name = self.player_var.get()
        if not name or name.startswith("（"):
            messagebox.showwarning("提示", "没有可用的玩家", parent=self)
            return

        def cb(resp):
            m = re.search(
                r"\[([-\d.]+)d?,\s*([-\d.]+)d?,\s*([-\d.]+)d?\]", resp)
            if not m:
                messagebox.showwarning(
                    "抓取失败", f"无法解析坐标：\n{resp[:200]}", parent=self)
                return
            x, y, z = m.group(1), m.group(2), m.group(3)
            suffix = "1" if which == "1" else "2"
            for key, val in (("x" + suffix, x), ("y" + suffix, y),
                             ("z" + suffix, z)):
                self.entries[key].delete(0, "end")
                self.entries[key].insert(0, val)
            self.app.log_to_console(
                f"已抓取 {name} 的坐标 → 角{which} ({x}, {y}, {z})", "info")

        self.app.rcon_call(f"data get entity {name} Pos", cb)

    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("提示", "请填写清理区名称", parent=self)
            return

        dim_cn = self.dim_var.get()
        dim_key = next((k for k, v in CZ_DIM_CN.items() if v == dim_cn),
                       "minecraft:overworld")

        try:
            coords = {k: float(e.get().strip())
                      for k, e in self.entries.items()}
        except ValueError:
            messagebox.showwarning("提示", "坐标必须是数字", parent=self)
            return

        try:
            interval = int(self.interval_entry.get().strip())
            if interval < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "间隔必须是 ≥1 的整数", parent=self)
            return

        zone = {
            "name": name,
            "dimension": dim_key,
            "enabled": self.enabled_var.get() == "true",
            "interval_min": interval,
            "last_clean": self._zone.get("last_clean", time.time()),
            **coords,
        }

        x1, y1, z1, x2, y2, z2 = normalize_clean_zone(zone)
        zone.update({"x1": x1, "y1": y1, "z1": z1,
                     "x2": x2, "y2": y2, "z2": z2})

        self.app.add_or_update_clean_zone(zone, is_new=self._is_new,
                                          old_name=self._zone.get("name"))
        self.destroy()


# ============================================================
#  区域管理页（保护区 + 清理区）
# ============================================================
class ZonesPage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)

        tabs = ctk.CTkTabview(
            self.frame,
            fg_color=C["card"],
            segmented_button_fg_color=C["sidebar"],
            segmented_button_selected_color=C["accent"],
            segmented_button_selected_hover_color=C["accent_hover"],
            segmented_button_unselected_color=C["sidebar"],
            text_color=C["text"], corner_radius=14,
            border_width=1, border_color=C["border"],
        )
        tabs.grid(row=0, column=0, sticky="nsew")

        self.prot_tab = tabs.add("🛡 保护区")
        self.clean_tab = tabs.add("🧹 清理区")

        self._build_protected_view(self.prot_tab)
        self._build_clean_view(self.clean_tab)

    # ========================================================
    #  保护区视图
    # ========================================================
    def _build_protected_view(self, parent):
        f = self.f
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bar, text="🛡   保护区", font=f["h1"],
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(bar, text="➕ 新建保护区", width=140, height=38,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self._add_zone).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(bar, text="🔄  刷新", width=100, height=38,
                      corner_radius=10, font=f["body"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=self.refresh).grid(row=0, column=2)

        hint = ctk.CTkFrame(parent, fg_color=C["console_bg"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        hint.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(
            hint,
            text=("💡 保护区内掉落物不会被清理。全局清理或保护区外的清理会跳过这些区域。"),
            font=f["small"], text_color=C["text_dim"], justify="left",
            wraplength=800,
        ).pack(anchor="w", padx=16, pady=12)

        self.prot_list = ctk.CTkScrollableFrame(
            parent, fg_color=C["console_bg"], corner_radius=14,
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self.prot_list.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.prot_list.grid_columnconfigure(0, weight=1)

    # ========================================================
    #  清理区视图
    # ========================================================
    def _build_clean_view(self, parent):
        f = self.f
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bar, text="🧹   清理区", font=f["h1"],
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(bar, text="➕ 新建清理区", width=140, height=38,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self._add_clean_zone).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(bar, text="🔄  刷新", width=100, height=38,
                      corner_radius=10, font=f["body"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=self.refresh).grid(row=0, column=2)

        hint = ctk.CTkFrame(parent, fg_color=C["console_bg"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        hint.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        # 全局开关状态提示
        self.clean_hint = ctk.CTkLabel(
            hint,
            text="", font=f["small"], text_color=C["text_dim"],
            justify="left", wraplength=800,
        )
        self.clean_hint.pack(anchor="w", padx=16, pady=12)

        self.clean_list = ctk.CTkScrollableFrame(
            parent, fg_color=C["console_bg"], corner_radius=14,
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self.clean_list.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.clean_list.grid_columnconfigure(0, weight=1)

    # ========================================================
    #  生命周期
    # ========================================================
    def on_show(self):
        self.refresh()

    def refresh(self):
        self._refresh_protected()
        self._refresh_clean()
        self._refresh_clean_hint()

    def _refresh_clean_hint(self):
        enabled = self.app.config_data.get("global_clean_enabled", False)
        interval = self.app.config_data.get(
            "auto_drop_clean_interval_min", 30)
        if enabled:
            text = (f"⚠ 全局清理已启用（每 {interval} 分钟全图清理一次）。\n"
                    f"   清理区自动清理在此模式下暂停。\n"
                    f"   要使用清理区独立清理，请到「设置」关闭全局清理。")
            color = C["orange"]
        else:
            text = ("✅ 全局清理已关闭，清理区将按各自间隔独立清理。\n"
                    "   每个清理区只清理其区域内的掉落物，不影响其他位置。")
            color = C["green"]
        try:
            self.clean_hint.configure(text=text, text_color=color)
        except Exception:
            pass

    # ---------- 保护区 ----------
    def _refresh_protected(self):
        for w in self.prot_list.winfo_children():
            w.destroy()

        zones = self.app.zones_data.get("zones", [])
        if not zones:
            ctk.CTkLabel(self.prot_list,
                         text="还没有任何保护区",
                         font=self.f["body"], justify="center",
                         text_color=C["text_faint"]).pack(pady=40)
            return

        for zone in zones:
            self._render_protected_row(zone)

    def _render_protected_row(self, zone):
        f = self.f
        row = ctk.CTkFrame(self.prot_list, fg_color=C["card"],
                            corner_radius=10)
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(1, weight=1)

        enabled = zone.get("enabled", True)
        ctk.CTkLabel(row, text="●", font=ctk.CTkFont(size=14),
                     text_color=C["green"] if enabled else C["text_faint"]
                     ).grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=10)

        ctk.CTkLabel(row, text=zone.get("name", "未命名"),
                     font=f["h2"], text_color=C["text"], anchor="w"
                     ).grid(row=0, column=1, sticky="w", pady=(8, 0))

        dim_cn = DIMENSION_CN.get(zone.get("dimension", ""), "?")
        try:
            x1, y1, z1, x2, y2, z2 = normalize_zone(zone)
            w = x2 - x1
            h = y2 - y1
            d = z2 - z1
            info = (f"{dim_cn}   "
                    f"({x1:g}, {y1:g}, {z1:g}) → ({x2:g}, {y2:g}, {z2:g})   "
                    f"[{w:g}×{h:g}×{d:g}]")
        except Exception:
            info = f"{dim_cn}   坐标无效"

        ctk.CTkLabel(row, text=info, font=f["small"],
                     text_color=C["text_dim"], anchor="w"
                     ).grid(row=1, column=1, sticky="w", pady=(0, 8))

        var = ctk.StringVar(value="true" if enabled else "false")

        def toggle():
            zone["enabled"] = var.get() == "true"
            self.app.save_zones_data()
            self._refresh_protected()

        ctk.CTkSwitch(row, text="", variable=var,
                      onvalue="true", offvalue="false", width=44,
                      progress_color=C["accent"],
                      command=toggle
                      ).grid(row=0, column=2, rowspan=2, padx=4)

        ctk.CTkButton(row, text="👁", width=38, height=30, corner_radius=8,
                      font=f["body"], fg_color="transparent",
                      hover_color=C["card_hover"], border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=lambda z=zone: self._visualize_prot(z)
                      ).grid(row=0, column=3, rowspan=2, padx=2)

        ctk.CTkButton(row, text="✏", width=38, height=30, corner_radius=8,
                      font=f["body"], fg_color="transparent",
                      hover_color=C["card_hover"], border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=lambda z=zone: self._edit_zone(z)
                      ).grid(row=0, column=4, rowspan=2, padx=2)

        ctk.CTkButton(row, text="🗑", width=38, height=30, corner_radius=8,
                      font=f["body"], fg_color="transparent",
                      hover_color="#3b1f24", border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=lambda z=zone: self._delete_zone(z)
                      ).grid(row=0, column=5, rowspan=2, padx=(2, 12))

    # ---------- 清理区 ----------
    def _refresh_clean(self):
        for w in self.clean_list.winfo_children():
            w.destroy()

        zones = self.app.clean_zones_data.get("zones", [])
        if not zones:
            ctk.CTkLabel(self.clean_list,
                         text="还没有任何清理区",
                         font=self.f["body"], justify="center",
                         text_color=C["text_faint"]).pack(pady=40)
            return

        for zone in zones:
            self._render_clean_row(zone)

    def _render_clean_row(self, zone):
        f = self.f
        row = ctk.CTkFrame(self.clean_list, fg_color=C["card"],
                            corner_radius=10)
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(1, weight=1)

        enabled = zone.get("enabled", True)
        ctk.CTkLabel(row, text="●", font=ctk.CTkFont(size=14),
                     text_color=C["orange"] if enabled else C["text_faint"]
                     ).grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=10)

        ctk.CTkLabel(row, text=zone.get("name", "未命名"),
                     font=f["h2"], text_color=C["text"], anchor="w"
                     ).grid(row=0, column=1, sticky="w", pady=(8, 0))

        dim_cn = CZ_DIM_CN.get(zone.get("dimension", ""), "?")
        interval = zone.get("interval_min", 15)
        try:
            x1, y1, z1, x2, y2, z2 = normalize_clean_zone(zone)
            w = x2 - x1
            h = y2 - y1
            d = z2 - z1
            info = (f"{dim_cn}   "
                    f"({x1:g}, {y1:g}, {z1:g}) → ({x2:g}, {y2:g}, {z2:g})   "
                    f"[{w:g}×{h:g}×{d:g}]   ·   每 {interval} 分钟")
        except Exception:
            info = f"{dim_cn}   坐标无效   ·   每 {interval} 分钟"

        ctk.CTkLabel(row, text=info, font=f["small"],
                     text_color=C["text_dim"], anchor="w"
                     ).grid(row=1, column=1, sticky="w", pady=(0, 8))

        var = ctk.StringVar(value="true" if enabled else "false")

        def toggle():
            zone["enabled"] = var.get() == "true"
            self.app.save_clean_zones_data()
            self._refresh_clean()

        ctk.CTkSwitch(row, text="", variable=var,
                      onvalue="true", offvalue="false", width=44,
                      progress_color=C["accent"],
                      command=toggle
                      ).grid(row=0, column=2, rowspan=2, padx=4)

        # 立即清理
        ctk.CTkButton(row, text="🧹", width=38, height=30, corner_radius=8,
                      font=f["body"], fg_color="transparent",
                      hover_color=C["card_hover"], border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=lambda z=zone: self._clean_now(z)
                      ).grid(row=0, column=3, rowspan=2, padx=2)

        ctk.CTkButton(row, text="✏", width=38, height=30, corner_radius=8,
                      font=f["body"], fg_color="transparent",
                      hover_color=C["card_hover"], border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=lambda z=zone: self._edit_clean_zone(z)
                      ).grid(row=0, column=4, rowspan=2, padx=2)

        ctk.CTkButton(row, text="🗑", width=38, height=30, corner_radius=8,
                      font=f["body"], fg_color="transparent",
                      hover_color="#3b1f24", border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=lambda z=zone: self._delete_clean_zone(z)
                      ).grid(row=0, column=5, rowspan=2, padx=(2, 12))

    # ---------- 操作 ----------
    def _add_zone(self):
        ZoneEditDialog(self.frame, self.app, zone=None)

    def _edit_zone(self, zone):
        ZoneEditDialog(self.frame, self.app, zone=zone)

    def _delete_zone(self, zone):
        if not messagebox.askyesno("删除保护区",
                                    f"确定要删除「{zone.get('name')}」吗？"):
            return
        self.app.remove_zone(zone.get("name"))

    def _visualize_prot(self, zone):
        cmd = build_visualize_command(zone)
        if not cmd:
            return
        for line in cmd.splitlines():
            if line.strip():
                self.app.quick_rcon(line)
        self.app.log_to_console(
            f"已发送粒子可视化（{zone.get('name')}）", "ok")

    def _add_clean_zone(self):
        CleanZoneEditDialog(self.frame, self.app, zone=None)

    def _edit_clean_zone(self, zone):
        CleanZoneEditDialog(self.frame, self.app, zone=zone)

    def _delete_clean_zone(self, zone):
        if not messagebox.askyesno("删除清理区",
                                    f"确定要删除「{zone.get('name')}」吗？"):
            return
        self.app.remove_clean_zone(zone.get("name"))

    def _clean_now(self, zone):
        cmd = build_clean_zone_command(zone)
        if not cmd:
            messagebox.showwarning("提示", "清理区坐标无效")
            return
        self.app.quick_rcon(cmd)
        zone["last_clean"] = time.time()
        self.app.save_clean_zones_data()
        self.app.log_to_console(
            f"🧹 已手动清理「{zone.get('name')}」", "ok")