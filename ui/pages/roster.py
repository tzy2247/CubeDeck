import json
from tkinter import messagebox
import customtkinter as ctk
from core.theme import C


class RosterPage:
    """白名单 / 封禁玩家 / 封禁 IP。"""

    CONFIGS = [
        ("whitelist",  "whitelist.json",      "whitelist add",  "whitelist remove"),
        ("ban",        "banned-players.json", "ban",            "pardon"),
        ("banip",      "banned-ips.json",     "ban-ip",         "pardon-ip"),
    ]

    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self._frames = {}
        self._remove_cmds = {}
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    def _build(self):
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)

        tabs = ctk.CTkTabview(
            self.frame,
            fg_color=C["card"], segmented_button_fg_color=C["sidebar"],
            segmented_button_selected_color=C["accent"],
            segmented_button_selected_hover_color=C["accent_hover"],
            segmented_button_unselected_color=C["sidebar"],
            text_color=C["text"], corner_radius=14,
            border_width=1, border_color=C["border"],
        )
        tabs.grid(row=0, column=0, sticky="nsew")

        tab = tabs.add("白名单")
        self._fill(tab, *self.CONFIGS[0])
        tab = tabs.add("封禁玩家")
        self._fill(tab, *self.CONFIGS[1])
        tab = tabs.add("封禁 IP")
        self._fill(tab, *self.CONFIGS[2])

    def _fill(self, parent, key, json_file, add_cmd, remove_cmd):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(8, 10))
        bar.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(bar, placeholder_text="输入玩家名或 IP…",
                             height=40, corner_radius=10, font=self.f["body"],
                             fg_color=C["console_bg"],
                             border_color=C["border"], border_width=1)
        entry.grid(row=0, column=0, sticky="ew")

        def add():
            name = entry.get().strip()
            if not name:
                return
            entry.delete(0, "end")
            self.app.quick_rcon(f"{add_cmd} {name}",
                                on_done=lambda: self.app.after(800, self.refresh))
        entry.bind("<Return>", lambda e: add())

        ctk.CTkButton(bar, text="➕ 添加", width=100, height=40, corner_radius=10,
                      font=self.f["h2"], fg_color=C["accent"],
                      hover_color=C["accent_hover"], command=add
                      ).grid(row=0, column=1, padx=(10, 0))
        ctk.CTkButton(bar, text="🔄", width=44, height=40, corner_radius=10,
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"], text_color=C["text_dim"],
                      command=self.refresh).grid(row=0, column=2, padx=(8, 0))

        frame = ctk.CTkScrollableFrame(
            parent, fg_color=C["console_bg"], corner_radius=12,
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        frame.grid(row=1, column=0, sticky="nsew")

        self._frames[key] = (frame, json_file)
        self._remove_cmds[key] = remove_cmd

    # ---------- 钩子 ----------
    def on_show(self):
        self.refresh()

    def refresh(self):
        for key, (frame, json_file) in self._frames.items():
            self._load(frame, json_file, self._remove_cmds[key])

    def _load(self, frame, json_file, remove_cmd):
        for w in frame.winfo_children():
            w.destroy()

        path = self.app.server_path / json_file
        if not path.exists():
            ctk.CTkLabel(frame, text=f"未找到 {json_file}",
                         font=self.f["body"],
                         text_color=C["text_faint"]).pack(pady=30)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            ctk.CTkLabel(frame, text=f"读取失败：{e}",
                         font=self.f["body"],
                         text_color=C["red"]).pack(pady=30)
            return

        if not data:
            ctk.CTkLabel(frame, text="列表为空", font=self.f["body"],
                         text_color=C["text_faint"]).pack(pady=30)
            return

        for entry in data:
            name = entry.get("name") or entry.get("ip") or "?"
            reason = entry.get("reason", "")
            self._row(frame, name, reason, remove_cmd)

    def _row(self, parent, name, reason, remove_cmd):
        row = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=10)
        row.pack(fill="x", padx=6, pady=4)
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text="👤", font=ctk.CTkFont(size=16),
                     text_color=C["accent"]).grid(row=0, column=0, padx=(14, 10), pady=10)
        ctk.CTkLabel(row, text=name, font=self.f["h2"], text_color=C["text"],
                     anchor="w").grid(row=0, column=1, sticky="w")
        if reason:
            ctk.CTkLabel(row, text=reason, font=self.f["small"],
                         text_color=C["text_dim"], anchor="e").grid(
                row=0, column=2, sticky="e", padx=(0, 12))

        def remove():
            if messagebox.askyesno("移除确认", f"确定要移除 {name} 吗？"):
                self.app.quick_rcon(f"{remove_cmd} {name}",
                                    on_done=lambda: self.app.after(800, self.refresh))

        ctk.CTkButton(row, text="🗑", width=40, height=32, corner_radius=8,
                      font=ctk.CTkFont(size=14), fg_color="transparent",
                      hover_color="#3b1f24", text_color=C["text_dim"],
                      command=remove).grid(row=0, column=3, padx=(0, 12))